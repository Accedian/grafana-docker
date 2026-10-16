import json
import subprocess
import tempfile
from pathlib import Path


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main():
    output = Path(tempfile.mkdtemp(prefix="pca-grafana-ui-"))
    results = []
    for uid, panel, name, filters in (("pca-service-health", 39, "service-replicas", ""),
                                     ("pca-resource-health", 3, "node-cpu", ""),
                                     ("pca-resource-health", 40, "swarm-task-cpu", ""),
                                     ("pca-resource-health", 40, "unavailable", "&var-swarm_service=missing-test-service")):
        screenshot = output / (name + ".png")
        url = f"http://127.0.0.1:13000/d/{uid}/test?orgId=1&viewPanel={panel}{filters}"
        result = subprocess.run([
            CHROME, "--headless=new", "--disable-gpu", "--disable-background-networking",
            "--no-first-run", "--no-default-browser-check", "--window-size=1600,1000",
            "--user-data-dir=" + str(output / ("profile-" + name)),
            "--screenshot=" + str(screenshot), "--virtual-time-budget=20000", "--timeout=45000",
            "--dump-dom", url,
        ], capture_output=True, text=True, timeout=90)
        if result.returncode != 0 or not screenshot.exists():
            raise RuntimeError(result.stderr)
        (output / (name + ".html")).write_text(result.stdout)
        results.append({"dashboard": uid, "panel": panel, "screenshot": str(screenshot),
                        "grafana_loaded": "grafana" in result.stdout.lower()})
    print(json.dumps({"artifacts": str(output), "screenshots": results}, indent=2))


if __name__ == "__main__":
    main()
