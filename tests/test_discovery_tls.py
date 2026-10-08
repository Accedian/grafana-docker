"""Real curl discovery preserves TLS identity when public routing is unavailable."""
import http.server
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import unittest


class InternalDiscoveryTLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        for args in (
            ["req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
             "-nodes", "-sha256", "-days", "1", "-subj", "/CN=Test CA",
             "-keyout", "ca.key", "-out", "ca.crt",
             "-addext", "basicConstraints=critical,CA:TRUE"],
            ["req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
             "-nodes", "-sha256", "-subj", "/CN=localhost", "-keyout", "server.key",
             "-out", "server.csr", "-addext", "subjectAltName=DNS:localhost"],
            ["x509", "-req", "-in", "server.csr", "-CA", "ca.crt", "-CAkey", "ca.key",
             "-CAcreateserial", "-out", "server.crt", "-days", "1", "-sha256",
             "-copy_extensions", "copy"],
        ):
            subprocess.run(["openssl", *args], cwd=cls.directory, check=True,
                           capture_output=True, timeout=20)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                cls.hosts.append(self.headers.get("Host"))
                cls.tenant_headers.append(self.headers.get("X-Forwarded-Server"))
                body = json.dumps({"data": {"type": "tenant-info", "attributes": {
                    "tenantId": "AAA_ROOT", "zitadelAuth": True,
                    "zitadelConfig": {"clients": [{"name": "pca-grafana-pkce",
                        "appId": "app-id", "clientId": "public-client-id"}]}}}}).encode()
                self.send_response(302 if cls.redirect else 200)
                self.send_header("Location", "https://unreachable.invalid/tenant-info")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cls.directory / "server.crt", cls.directory / "server.key")
        context.set_servername_callback(lambda sock, name, ctx: cls.sni.append(name))
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def setUp(self):
        type(self).hosts, type(self).tenant_headers, type(self).sni = [], [], []
        type(self).redirect = False

    def discover(self, hostname="localhost", trust=True, ca_file=None, system_trust=False):
        env = dict(os.environ,
            GF_AUTH_GENERIC_OAUTH_ENABLED="true", GF_AUTH_GENERIC_OAUTH_CLIENT_ID="",
            GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL=f"https://{hostname}:9443/tenant-info",
            GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_HOST="Root-Tenant.example.test",
            GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_APPLICATION="pca-grafana-pkce",
            GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS="1",
            GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT=str(self.server.server_port),
            GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE=str(self.directory / "ca.crt") if trust else "",
            HTTPS_PROXY="http://unreachable.invalid:1")
        if ca_file is not None:
            env["GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE"] = str(ca_file)
        if system_trust:
            # Curl's default CA source models an issuer installed by the image.
            env["CURL_CA_BUNDLE"] = str(self.directory / "ca.crt")
        else:
            for key in ("CURL_CA_BUNDLE", "SSL_CERT_FILE", "SSL_CERT_DIR"):
                env.pop(key, None)
        # Substitute only Kubernetes Service DNS in this standalone fixture.
        script = '''
        source "$1"
        curl() {
            local -a args=("$@")
            local i
            for i in "${!args[@]}"; do
                args[$i]="${args[$i]/:nginx-service:/:127.0.0.1:}"
            done
            command curl "${args[@]}"
        }
        resolve_generic_oauth_client_id || exit 1
        test "$GF_AUTH_GENERIC_OAUTH_CLIENT_ID" = public-client-id
        '''
        return subprocess.run(["bash", "-c", script, "discovery-test",
            str(Path(__file__).parents[1] / "oauth-client-discovery.sh")],
            env=env, capture_output=True, text=True, timeout=10)

    def test_internal_route_preserves_sni_and_root_identity(self):
        result = self.discover()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sni, ["localhost"])
        self.assertEqual(self.hosts, ["Root-Tenant.example.test"])
        self.assertEqual(self.tenant_headers, ["Root-Tenant.example.test"])

    def test_wrong_certificate_hostname_is_rejected(self):
        self.assertNotEqual(self.discover("wrong.invalid").returncode, 0)
        self.assertEqual(self.hosts, [])

    def test_untrusted_ca_is_rejected(self):
        self.assertNotEqual(self.discover(trust=False).returncode, 0)
        self.assertEqual(self.hosts, [])

    def test_empty_optional_ca_uses_default_trust(self):
        empty = self.directory / "empty.crt"
        empty.write_bytes(b"")
        result = self.discover(ca_file=empty, system_trust=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.sni, ["localhost"])

    def test_empty_optional_ca_does_not_disable_verification(self):
        empty = self.directory / "empty.crt"
        empty.write_bytes(b"")
        for hostname, system_trust in (("localhost", False), ("wrong.invalid", True)):
            with self.subTest(hostname=hostname):
                result = self.discover(hostname, ca_file=empty, system_trust=system_trust)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.hosts, [])

    def test_missing_and_malformed_optional_ca_fail_closed(self):
        invalid = self.directory / "invalid.crt"
        invalid.write_text("not a CA certificate")
        for path in (self.directory / "missing.crt", invalid):
            with self.subTest(path=path.name):
                result = self.discover(ca_file=path, system_trust=True)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.hosts, [])

    def test_redirect_is_not_adopted_or_followed(self):
        type(self).redirect = True
        self.assertNotEqual(self.discover().returncode, 0)
        self.assertEqual(self.hosts, ["Root-Tenant.example.test"])
