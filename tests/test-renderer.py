#!/usr/bin/env python3
"""Verify real PNG rendering with the same loopback boundary as the Helm sidecar."""
import base64
import json
import os
from pathlib import Path
import re
import secrets
import struct
import subprocess
import sys
import tempfile
import time


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, capture_output=True, **kwargs)


def request(container, url, header=None, payload=None, timeout=10):
    args = ["exec", "-i", container, "curl", "--silent", "--show-error",
            "--max-time", str(timeout), "--config", "-", "--write-out", "\n%{http_code}"]
    if payload is not None:
        args += ["--header", "Content-Type: application/json", "--data-binary", json.dumps(payload)]
    args += [url]
    # Credentials travel over stdin, never in argv, source, URLs or test output.
    config = "" if header is None else f'header = "{header}"\n'
    result = docker(*args, input=config.encode(), timeout=timeout + 10)
    body, status = result.stdout.rsplit(b"\n", 1)
    return int(status), body


def main():
    grafana_image, renderer_image = sys.argv[1:]
    startup = Path(__file__).resolve().parent.parent / "helm/files/run-renderer.sh"
    # These rejected values never reach exec, so the guard can run without
    # starting a renderer. In particular, a long CSV list must not pass.
    for invalid in (None, "", "-", "short", "-," + "a" * 64):
        guard_env = os.environ.copy()
        guard_env.pop("AUTH_TOKEN", None)
        if invalid is not None:
            guard_env["AUTH_TOKEN"] = invalid
        rejected = subprocess.run(["/bin/sh", str(startup)], env=guard_env, capture_output=True)
        if rejected.returncode != 1 or not rejected.stderr.startswith(b"Renderer requires"):
            raise AssertionError("Renderer startup accepted an invalid token")
    print("Renderer startup rejects missing, default, short and list-valued tokens.")
    containers = []
    with tempfile.TemporaryDirectory(prefix="grafana-renderer-test-") as directory:
        password, token = secrets.token_hex(32), secrets.token_hex(32)
        basic = base64.b64encode(f"admin:{password}".encode()).decode()
        auth = f"Authorization: Basic {basic}"
        env = Path(directory) / "grafana.env"
        env.write_text("\n".join([
            f"GF_SECURITY_ADMIN_PASSWORD={password}",
            "GF_SERVER_ROOT_URL=https://pca.example/grafana",
            "GF_PLUGINS_PREINSTALL_DISABLED=true",
            "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
            "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false",
            "GF_RENDERING_SERVER_URL=http://127.0.0.1:8081/render",
            "GF_RENDERING_CALLBACK_URL=http://127.0.0.1:3000/",
            f"GF_RENDERING_RENDERER_TOKEN={token}",
        ]) + "\n")
        os.chmod(env, 0o600)
        renderer_env = Path(directory) / "renderer.env"
        renderer_env.write_text(f"AUTH_TOKEN={token}\nSERVER_ADDR=127.0.0.1:8081\nAPI_DEFAULT_ENCODING=png\n"
                                "BROWSER_MIN_WIDTH=100\nBROWSER_MIN_HEIGHT=100\n"
                                "API_SILENCE_REQUEST_LOG_PATH=/render,/render/csv\nHOME=/tmp\nGOMEMLIMIT=1GiB\n")
        os.chmod(renderer_env, 0o600)
        try:
            grafana = docker("run", "-d", "--network", "none", "--env-file", str(env),
                             grafana_image).stdout.decode().strip()
            containers.append(grafana)
            renderer = docker("run", "-d", "--network", f"container:{grafana}",
                              "--env-file", str(renderer_env), "--cap-drop", "ALL",
                              "--security-opt", "no-new-privileges", "--read-only",
                              "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777,size=1g",
                              "--shm-size", "512m", "--memory", "16g", "--cpus", "4",
                              "--workdir", "/tmp", "--entrypoint", "/bin/sh",
                              "--volume", f"{startup}:/etc/renderer/run-renderer.sh:ro",
                              renderer_image, "/etc/renderer/run-renderer.sh").stdout.decode().strip()
            containers.append(renderer)
            for attempt in range(90):
                try:
                    status, body = request(grafana, "http://127.0.0.1:3000/api/health")
                    if status == 200 and json.loads(body)["database"] == "ok":
                        status, _ = request(grafana, "http://127.0.0.1:8081/healthz")
                        if status == 200:
                            break
                except (subprocess.SubprocessError, ValueError):
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Grafana/renderer did not become healthy")

            render_url = "http://127.0.0.1:8081/render"
            for header in [None, "X-Auth-Token: wrong-test-token"]:
                status, _ = request(grafana, render_url, header)
                if status not in (401, 403):
                    raise AssertionError(f"Unauthenticated render request returned {status}")
            print("Missing and wrong renderer tokens are denied.")

            status, _ = request(grafana, render_url + "?renderKey=redaction-test-marker",
                                f"X-Auth-Token: {token}")
            if status != 400:
                raise AssertionError(f"Authenticated invalid render request returned {status}")

            dashboard = {"dashboard": {"uid": "renderer-test", "title": "Renderer test",
                         "schemaVersion": 41, "panels": [{"id": 1, "type": "text",
                         "title": "Renderer integration", "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                         "options": {"mode": "markdown", "content": "PNG rendering works."}}]},
                         "overwrite": True}
            status, _ = request(grafana, "http://127.0.0.1:3000/api/dashboards/db", auth, dashboard)
            if status != 200:
                raise AssertionError(f"Dashboard creation returned {status}")
            url = "http://127.0.0.1:3000/render/d-solo/renderer-test/renderer-test?panelId=1&width=800&height=400&timeout=60"
            status, png = request(grafana, url, auth, timeout=90)
            if status != 200 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise AssertionError(f"PNG rendering failed: HTTP {status}, {len(png)} bytes")
            width, height = struct.unpack(">II", png[16:24])
            if (width, height) != (800, 400) or len(png) < 1000:
                raise AssertionError(f"Unexpected PNG dimensions/content: {width}x{height}, {len(png)} bytes")
            print(f"Grafana rendered a valid {width}x{height} PNG ({len(png)} bytes) using the service.")
            for container in containers:
                result = docker("logs", container)
                logs = (result.stdout + result.stderr).decode(errors="replace")
                if any(value in logs for value in (password, token, basic, "renderKey=", "redaction-test-marker")):
                    raise AssertionError("Rendering credentials/query marker appeared in container logs")
            print("Rendering credentials are absent from success and rejected-request logs.")
        except Exception:
            for container in containers:
                result = docker("logs", "--tail", "40", container)
                logs = (result.stdout + result.stderr).decode(errors="replace")
                for value in (password, token, basic):
                    logs = logs.replace(value, "[REDACTED]")
                logs = re.sub(r"(renderKey[=:])[^&\s\"']+", r"\1[REDACTED]", logs)
                print(logs, file=sys.stderr)
            raise
        finally:
            for container in reversed(containers):
                docker("rm", "-fv", container)


if __name__ == "__main__":
    main()
