"""Exercise the generated JMESPath policy, not a separate role evaluator."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import jmespath

ROOT = Path(__file__).resolve().parents[1]
CLAIM = "urn:zitadel:iam:org:project:200:roles"


class DeploymentAdminRoleTests(unittest.TestCase):
    def test_full_startup_requires_discovery_even_with_a_static_client_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            document = path / "tenant.json"
            metadata = self.metadata()
            metadata["clients"] = [{"name": "pca-grafana-pkce", "appId": "app",
                                    "clientId": "client"}]
            document.write_text(json.dumps({"data": {"type": "tenant-info", "attributes": {
                "tenantId": "AAA_ROOT", "zitadelAuth": True, "zitadelConfig": metadata}}}))
            curl = path / "curl"
            curl.write_text('#!/bin/sh\ncat "$ROLE_DOCUMENT"\n')
            curl.chmod(0o700)
            startup = path / "ci-startup.sh"
            startup.write_text('export PATH=/nonexistent\nexit 97\n')
            # CI startup files must not hide the mocked curl by replacing PATH.
            with patch.dict(os.environ, {"BASH_ENV": str(startup), "ENV": str(startup)}):
                env = {k: v for k, v in os.environ.items()
                       if k not in ("BASH_ENV", "ENV")
                       and not k.startswith(("GF_", "GRAFANA_OAUTH_"))}
            self.assertNotIn("BASH_ENV", env)
            self.assertNotIn("ENV", env)
            env.update(PATH=str(path) + os.pathsep + env["PATH"], ROLE_DOCUMENT=str(document),
                GF_AUTH_GENERIC_OAUTH_ENABLED="true", GF_AUTH_GENERIC_OAUTH_CLIENT_ID="client",
                GRAFANA_OAUTH_DEPLOYMENT_ADMIN_ROLE_ENABLED="true",
                GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL="https://root.example.test/tenant-info",
                GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_HOST="root.example.test",
                GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_APPLICATION="pca-grafana-pkce",
                GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS="10",
                GRAFANA_OAUTH_END_SESSION_URL="https://auth.example.test/logout",
                GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL="https://root.example.test/grafana/")
            argv = ["bash", "-euc", '. "$1"; configure_generic_oauth; '
                    'printf "role=%s\\n" "${GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH:-}"',
                    "startup-test", str(ROOT / "oauth-client-discovery.sh")]
            # Successful discovery must tolerate scheduling delays on CI workers.
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"urn:zitadel:iam:org:project:200:roles"', result.stdout)
            missing = dict(metadata, organizationId="")
            document.write_text(json.dumps({"data": {"type": "tenant-info", "attributes": {
                "tenantId": "AAA_ROOT", "zitadelAuth": True, "zitadelConfig": missing}}}))
            env["GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS"] = "1"
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Timed out", result.stderr)
            env["GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS"] = "10"
            document.write_text(json.dumps({"data": {"type": "tenant-info", "attributes": {
                "tenantId": "AAA_ROOT", "zitadelAuth": True, "zitadelConfig": metadata}}}))
            env["GF_AUTH_GENERIC_OAUTH_CLIENT_ID"] = "wrong-client"
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            env["GF_AUTH_GENERIC_OAUTH_ENABLED"] = "false"
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "role=\n")
            env["GF_AUTH_GENERIC_OAUTH_ENABLED"] = "true"
            env["GRAFANA_OAUTH_DEPLOYMENT_ADMIN_ROLE_ENABLED"] = "invalid"
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)

    def configure(self, metadata):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "tenant.json"
            document.write_text(json.dumps({"data": {"attributes": {
                "zitadelConfig": metadata}}}))
            result = subprocess.run(
                ["bash", "-euc", '. "$1"; configure_deployment_admin_role "$2"; '
                 'env | grep -E "^GF_(AUTH_GENERIC_OAUTH|USERS)_"',
                 "role-test", str(ROOT / "oauth-client-discovery.sh"), str(document)],
                env={k: v for k, v in os.environ.items()
                     if k not in ("BASH_ENV", "ENV") and not k.startswith("GF_")},
                capture_output=True, text=True, timeout=10,
            )
            return result

    def metadata(self):
        return {"organizationId": "100", "projects": [
            {"name": "Analytics", "projectId": "200"}]}

    def test_role_configuration_ignores_inherited_shell_startup_files(self):
        with tempfile.TemporaryDirectory() as directory:
            startup = Path(directory) / "ci-startup.sh"
            startup.write_text('export PATH=/nonexistent\nexit 97\n')
            with patch.dict(os.environ, {"BASH_ENV": str(startup), "ENV": str(startup)}):
                result = self.configure(self.metadata())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"urn:zitadel:iam:org:project:200:roles"', result.stdout)

    def test_policy_only_grants_the_expected_project_and_organization(self):
        result = self.configure(self.metadata())
        self.assertEqual(result.returncode, 0, result.stderr)
        env = dict(line.split("=", 1) for line in result.stdout.splitlines())
        expression = jmespath.compile(env["GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH"])
        cases = [
            ({CLAIM: {"skylight-admin": {"100": "root.example.test"}}}, "Admin"),
            ({CLAIM: {"skylight-admin": {"999": "child.example.test"}}}, "Viewer"),
            ({CLAIM: {"tenant-admin": {"100": "root.example.test"}}}, "Viewer"),
            ({"urn:zitadel:iam:org:project:999:roles": {
                "skylight-admin": {"100": "root.example.test"}}}, "Viewer"),
            ({"urn:zitadel:iam:org:project:roles": {
                "skylight-admin": {"100": "root.example.test"}}}, "Viewer"),
            ({}, "Viewer"),
        ]
        for malformed in (None, False, True, [], {}, "", 42):
            cases.append(({CLAIM: {"skylight-admin": {"100": malformed}}}, "Viewer"))
        for claims, expected in cases:
            with self.subTest(claims=claims):
                self.assertEqual(expression.search(claims), expected)
        self.assertEqual(env["GF_AUTH_GENERIC_OAUTH_SKIP_ORG_ROLE_SYNC"], "false")
        self.assertEqual(env["GF_AUTH_GENERIC_OAUTH_ALLOW_ASSIGN_GRAFANA_ADMIN"], "false")
        self.assertEqual(env["GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_STRICT"], "true")
        self.assertEqual(env["GF_AUTH_GENERIC_OAUTH_ID_TOKEN_ATTRIBUTE_NAME"], "__disabled_id_token")
        self.assertEqual(env["GF_USERS_AUTO_ASSIGN_ORG_ROLE"], "Viewer")
        self.assertIn("urn:zitadel:iam:org:project:id:200:aud",
                      env["GF_AUTH_GENERIC_OAUTH_SCOPES"].split())
        self.assertIn("urn:zitadel:iam:org:projects:roles",
                      env["GF_AUTH_GENERIC_OAUTH_SCOPES"].split())

    def test_reject_missing_ambiguous_and_expression_injecting_identities(self):
        cases = [{}, {"organizationId": "100", "projects": []}]
        for field in ("organizationId", "projectId"):
            for bad in (None, 100, "", "100\" || 'Admin'", "1" * 65):
                metadata = copy.deepcopy(self.metadata())
                if field == "organizationId":
                    metadata[field] = bad
                else:
                    metadata["projects"][0][field] = bad
                cases.append(metadata)
        duplicate = self.metadata()
        duplicate["projects"] *= 2
        cases.append(duplicate)
        for metadata in cases:
            with self.subTest(metadata=metadata):
                self.assertNotEqual(self.configure(metadata).returncode, 0)
