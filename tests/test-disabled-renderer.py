#!/usr/bin/env python3
"""A persisted renderer backend must not execute under the image defaults."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix="disabled-renderer-fixture-") as directory:
        plugin = Path(directory) / "grafana-image-renderer"
        plugin.mkdir(mode=0o755)
        (plugin / "plugin.json").write_text(json.dumps({
            "id": "grafana-image-renderer", "type": "renderer", "name": "Renderer test fixture",
            "backend": True, "executable": "plugin_start",
            "info": {"author": {"name": "Test"}, "description": "Benign backend-start fixture",
                     "version": "1.0.0", "updated": "2026-10-07", "logos": {"small": "", "large": ""}},
            "dependencies": {"grafanaVersion": "*", "plugins": []},
        }))
        binary = plugin / "plugin_start_linux_amd64"
        binary.write_text("#!/bin/sh\ntouch /tmp/renderer-fixture-executed\nexit 1\n")
        binary.chmod(0o755)
        for enabled in (False, True):
            args = ["docker", "run", "-d", "--network", "none",
                    "-e", "GF_SECURITY_DISABLE_INITIAL_ADMIN_CREATION=true",
                    "-e", "GF_PLUGINS_PREINSTALL_DISABLED=true",
                    "-e", "GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=grafana-image-renderer",
                    "-e", "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
                    "-e", "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false",
                    "--volume", f"{plugin}:/var/lib/grafana/plugins/grafana-image-renderer:ro"]
            if enabled:
                # Positive control: prove the same harmless backend can execute.
                args += ["-e", "GF_PLUGINS_DISABLE_PLUGINS=", "-e", "GF_RENDERING_SERVER_URL="]
            command = args + [sys.argv[1]]
            if enabled:
                # Empty environment values are ignored by Grafana's config loader.
                command += ["cfg:default.rendering.server_url="]
            container = subprocess.check_output(command, text=True).strip()
            try:
                called = False
                healthy = False
                marker = Path(directory) / f"marker-{enabled}"
                for attempt in range(60):
                    time.sleep(1)
                    # The control backend exits immediately; inspect stopped containers too.
                    called = subprocess.run(["docker", "cp", f"{container}:/tmp/renderer-fixture-executed",
                                             str(marker)], capture_output=True).returncode == 0
                    if enabled and called:
                        break
                    if not enabled:
                        health = subprocess.run(["docker", "exec", container, "curl", "-fsS",
                                                 "--max-time", "2", "http://127.0.0.1:3000/api/health"],
                                                capture_output=True)
                        healthy = health.returncode == 0
                        if healthy:
                            break
                if called != enabled or (not enabled and not healthy):
                    result = subprocess.run(["docker", "logs", container], capture_output=True, text=True)
                    for line in (result.stdout + result.stderr).splitlines():
                        if "grafana-image-renderer" in line or "RenderingService" in line:
                            print(line, file=sys.stderr)
                    raise AssertionError(f"Persisted renderer control failed: enabled={enabled}, invoked={called}, healthy={healthy}")
                print(f"Persisted renderer: enabled={enabled}, backend invoked={called}")
            finally:
                subprocess.run(["docker", "rm", "-fv", container], stdout=subprocess.DEVNULL, check=True)


if __name__ == "__main__":
    main()
