#!/usr/bin/env python3
"""Verify browser URLs, loopback callbacks and rollouts for PCA access modes."""
import json
from pathlib import Path
import re
import subprocess

CHART = Path(__file__).resolve().parent.parent / "helm"


def render(*flags, success=True):
    result = subprocess.run(["helm", "template", "chart-check", str(CHART),
                             "--show-only", "templates/configmap.yaml",
                             "--show-only", "templates/statefulset.yaml", *flags],
                            capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stderr
    return result.stdout if success else result.stderr


def verify(output, host, subpath=True):
    env = {name: json.loads(value) for name, value in
           re.findall(r'^\s+(GF_[A-Z_]+): (".*")$', output, re.M)}
    assert env["GF_SERVER_ROOT_URL"] == "https://" + host + "/grafana/"
    assert env["GF_SERVER_DOMAIN"] == host
    assert env["GF_SERVER_SERVE_FROM_SUB_PATH"] == str(subpath).lower()
    assert env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    callback = "http://127.0.0.1:3000/" + ("grafana/" if subpath else "")
    assert 'value: "' + callback + '"' in output
    return re.search(r'checksum/config: ([a-f0-9]{64})', output)[1]


default = render()
default_checksum = verify(default, "deployment.accedian.local")
dns = render("--set", "global.analytics.deployment.name=performance",
             "--set", "global.analytics.deployment.domain=onprem.cisco.internal")
dns_checksum = verify(dns, "performance.onprem.cisco.internal")
ip = render("--set", "global.dns.support=false", "--set-string", "global.external_ip=172.25.77.12")
ip_checksum = verify(ip, "172.25.77.12")
assert len({default_checksum, dns_checksum, ip_checksum}) == 3
verify(render("--set", "grafana.server.serveFromSubPath=false"), "deployment.accedian.local", False)
disabled = render("--set", "grafana.renderer.enabled=false")
assert 'checksum/config: ' in disabled and 'name: renderer' not in disabled
assert 'global.external_ip is required' in render("--set", "global.dns.support=false", success=False)
assert 'global.dns.support must be a boolean' in render("--set-string", "global.dns.support=false", success=False)
for renderer in ("true", "false"):
    assert 'grafana.server.serveFromSubPath must be a boolean' in render(
        "--set-string", "grafana.server.serveFromSubPath=false",
        "--set", "grafana.renderer.enabled=" + renderer, success=False)
print("PASS: DNS/IP URLs, loopback subpath callbacks, configuration rollouts, authenticated defaults and invalid settings.")
