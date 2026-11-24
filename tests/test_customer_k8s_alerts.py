import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALERTS = ROOT / "provisioning/alerting/customer-k8s-alerts.yaml"
ALERTING_DIR = ROOT / "provisioning/alerting"
CUSTOMER_K8S = ROOT / "dashboards/Customer (k8s)"
EXPECTED_UIDS = [
    "pca-cust-pods-stuck-waiting",
    "pca-cust-workloads-degraded",
    "pca-cust-pods-pending",
    "pca-cust-node-cpu-high",
    "pca-cust-node-memory-high",
    "pca-cust-node-filesystem-high",
    "pca-cust-pod-oomkilled",
    "pca-cust-kafka-consumer-lag",
    "pca-cust-ignite-ingestion-lag",
    "pca-cust-druid-slots-exhausted",
    "pca-cust-client-cert-expiring",
    "pca-cust-tenant-ca-cert-expiring",
    "pca-cust-api-5xx-rate-high",
    "pca-cust-sla-reports-api-down",
    "pca-cust-sla-trigger-api-down",
    "pca-cust-sla-consolidation-failing",
]
PANEL_BY_UID = {
    "pca-cust-pods-stuck-waiting": ("pca-service-health", "32"),
    "pca-cust-workloads-degraded": ("pca-service-health", "4"),
    "pca-cust-pods-pending": ("pca-service-health", "5"),
    "pca-cust-node-cpu-high": ("pca-resource-health", "25"),
    "pca-cust-node-memory-high": ("pca-resource-health", "26"),
    "pca-cust-node-filesystem-high": ("pca-resource-health", "5"),
    "pca-cust-pod-oomkilled": ("pca-resource-health", "19"),
    "pca-cust-kafka-consumer-lag": ("pca-ingestion-v2", "31"),
    "pca-cust-ignite-ingestion-lag": ("pca-ingestion-v2", "25"),
    "pca-cust-druid-slots-exhausted": ("pca-ingestion-v2", "45"),
    "pca-cust-client-cert-expiring": ("pca-sensor-connectivity", "31"),
    "pca-cust-tenant-ca-cert-expiring": ("pca-sensor-connectivity", "32"),
    "pca-cust-api-5xx-rate-high": ("pca-application-speed", "8"),
    "pca-cust-sla-reports-api-down": ("pca-sla-reports", "5"),
    "pca-cust-sla-trigger-api-down": ("pca-sla-reports", "3"),
    "pca-cust-sla-consolidation-failing": ("pca-sla-reports", "8"),
}
FORBIDDEN_VARS = ("$namespace", "$tenant", "$__rate_interval")
SECRET_MARKERS = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
    "SUPER_SECRET_VALUE",
    "hunter2-token",
)
def walk_panels(panels):
    for panel in panels:
        yield panel
        yield from walk_panels(panel.get("panels", []))


def dashboard_panels_by_uid():
    found = {}
    for path in CUSTOMER_K8S.glob("*.json"):
        dashboard = json.loads(path.read_text())
        ids = {str(panel["id"]) for panel in walk_panels(dashboard["panels"])}
        found[dashboard["uid"]] = ids
    return found


def parse_alert_rules(text):
    rules = []
    blocks = re.split(r"\n(?=      - uid: )", text)
    for block in blocks:
        match = re.search(r"^- uid: (\S+)", block.strip(), re.MULTILINE)
        if not match:
            match = re.search(r"^      - uid: (\S+)", block, re.MULTILINE)
        if not match:
            continue
        uid = match.group(1)
        if uid in {"prometheus"}:
            continue
        expr_match = re.search(
            r"expr: \|-?\n((?:                .*\n)*)",
            block,
        )
        expr = ""
        if expr_match:
            expr = "\n".join(
                line[16:] if line.startswith("                ") else line
                for line in expr_match.group(1).splitlines()
            )
        evaluator = re.search(
            r"evaluator: \{ params: \[([^\]]*)\], type: (\w+) \}",
            block,
        )
        rules.append({
            "uid": uid,
            "block": block,
            "folder": re.search(r"folder: (.+)$", text[: text.find(block) + 1], re.MULTILINE),
            "expr": expr,
            "eval_params": evaluator.group(1) if evaluator else "",
            "eval_type": evaluator.group(2) if evaluator else "",
            "audience": re.search(r"audience: (\S+)", block),
            "managed": re.search(r"managed-by: (\S+)", block),
            "dashboard": re.search(r"__dashboardUid__: (\S+)", block),
            "panel": re.search(r'__panelId__: "(\d+)"', block),
            "no_data": re.search(r"noDataState: (\S+)", block),
            "exec_err": re.search(r"execErrState: (\S+)", block),
        })
    return rules


def collect_rule_uids():
    uids = []
    for path in sorted(ALERTING_DIR.glob("*.yaml")):
        if path.name.endswith("-delete.yaml"):
            continue
        for match in re.finditer(r"^\s+- uid: (\S+)", path.read_text(), re.MULTILINE):
            uids.append((match.group(1), path.name))
    return uids


def helm_template(*args, expect_fail=False):
    command = ["helm", "template", "grafana", str(ROOT / "helm"), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if expect_fail:
        if result.returncode == 0:
            raise AssertionError(f"helm template succeeded unexpectedly:\n{output}")
        return output
    if result.returncode != 0:
        raise AssertionError(f"helm template failed:\n{output}")
    return result.stdout


def configmap_docs(rendered):
    docs = []
    current = []
    kind = None
    for line in rendered.splitlines(True):
        if line.startswith("---"):
            if kind == "ConfigMap" and current:
                docs.append("".join(current))
            current = [line]
            kind = None
            continue
        current.append(line)
        if line.startswith("kind: "):
            kind = line.split(":", 1)[1].strip()
    if kind == "ConfigMap" and current:
        docs.append("".join(current))
    return docs


class CustomerK8sAlertRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = ALERTS.read_text()
        cls.rules = parse_alert_rules(cls.text)
        cls.by_uid = {rule["uid"]: rule for rule in cls.rules}
        cls.dashboards = dashboard_panels_by_uid()

    def test_expected_rule_count_and_uids(self):
        self.assertEqual([rule["uid"] for rule in self.rules], EXPECTED_UIDS)

    def test_uids_are_unique_across_all_alerting_files(self):
        seen = {}
        for uid, filename in collect_rule_uids():
            self.assertNotIn(uid, seen, f"duplicate uid {uid} in {filename} and {seen.get(uid)}")
            seen[uid] = filename
        for uid in EXPECTED_UIDS:
            self.assertEqual(seen[uid], "customer-k8s-alerts.yaml")

    def test_folder_is_customer_alerts_k8s(self):
        self.assertIn("folder: Customer Alerts (k8s)", self.text)
        self.assertNotIn("folder: Customer (k8s)", self.text)
        self.assertEqual(self.text.count("folder: Customer Alerts (k8s)"), 6)

    def test_common_labels_and_states(self):
        for rule in self.rules:
            with self.subTest(uid=rule["uid"]):
                self.assertEqual(rule["audience"].group(1), "customer")
                self.assertEqual(rule["managed"].group(1), "grafana-docker")
                self.assertEqual(rule["no_data"].group(1), "OK")
                self.assertEqual(rule["exec_err"].group(1), "Error")
                self.assertIn("datasourceUid: prometheus", rule["block"])
                self.assertIn("uid: prometheus", rule["block"])
                self.assertIn('type: __expression__', rule["block"])
                self.assertIn('uid: "-100"', rule["block"])
                self.assertIn("instant: true", rule["block"])

    def test_dashboard_and_panel_links_exist(self):
        for uid, (dashboard, panel) in PANEL_BY_UID.items():
            rule = self.by_uid[uid]
            self.assertEqual(rule["dashboard"].group(1), dashboard)
            self.assertEqual(rule["panel"].group(1), panel)
            self.assertIn(dashboard, self.dashboards)
            self.assertIn(panel, self.dashboards[dashboard])

    def test_expressions_avoid_dashboard_variables(self):
        for rule in self.rules:
            expr = rule["expr"]
            with self.subTest(uid=rule["uid"]):
                self.assertTrue(expr.strip())
                for var in FORBIDDEN_VARS:
                    self.assertNotIn(var, expr)
                self.assertIsNone(re.search(r"\bcluster\s*=", expr))

    def test_zero_equality_not_paired_with_gt_zero(self):
        for rule in self.rules:
            expr = rule["expr"]
            with self.subTest(uid=rule["uid"]):
                if re.search(r"==\s*0|<=\s*0", expr):
                    self.assertNotEqual(
                        (rule["eval_type"], rule["eval_params"]),
                        ("gt", "0"),
                    )

    def test_workloads_cover_deployments_statefulsets_daemonsets(self):
        expr = self.by_uid["pca-cust-workloads-degraded"]["expr"]
        self.assertIn("kube_deployment_spec_replicas", expr)
        self.assertIn("kube_statefulset_replicas", expr)
        self.assertIn("kube_daemonset_status_desired_number_scheduled", expr)
        self.assertIn("workload_kind", expr)
        self.assertIn("Deployment", expr)
        self.assertIn("StatefulSet", expr)
        self.assertIn("DaemonSet", expr)

    def test_api_5xx_covers_six_services_without_clamp_min(self):
        expr = self.by_uid["pca-cust-api-5xx-rate-high"]["expr"]
        for metric in (
            "gather_api_call_duration_count",
            "skylight_aaa_api_call_duration_count",
            "stitchit_api_call_duration_count",
            "alert_service_api_call_duration_count",
            "weld_watcher_http_status",
            "foxtrot_ws_server_handle_duration_count",
        ):
            self.assertIn(metric, expr)
        self.assertIn("> 0.1", expr)
        self.assertNotIn("clamp_min", expr)

    def test_disable_tombstone_covers_every_starter_uid(self):
        text = (ALERTING_DIR / "customer-k8s-alerts-delete.yaml").read_text()
        self.assertIn("deleteRules:", text)
        self.assertNotIn("folder: Customer (k8s)", text)
        found = re.findall(r"^    uid: (\S+)", text, re.MULTILINE)
        self.assertEqual(found, EXPECTED_UIDS)

    def test_dockerfile_keeps_k8s_alerts_out_of_default_provisioning(self):
        docker = (ROOT / "Dockerfile").read_text()
        self.assertIn("/tmp/k8s-alerting/customer-k8s-alerts.yaml", docker)
        self.assertIn("mv /tmp/provisioning/alerting/customer-k8s-alerts.yaml", docker)
        self.assertIn("mv /tmp/provisioning/alerting/customer-k8s-alerts-delete.yaml", docker)
        gid_at = docker.find("addgroup --system --gid 472 grafana")
        uid_at = docker.find("--uid 472")
        dpkg_at = docker.find("dpkg --install")
        self.assertNotEqual(gid_at, -1)
        self.assertNotEqual(uid_at, -1)
        self.assertLess(gid_at, dpkg_at)
        self.assertLess(uid_at, dpkg_at)

    def test_run_sh_copies_k8s_alerts_only_when_enabled(self):
        run = (ROOT / "run.sh").read_text()
        self.assertIn('case "${PCA_ENABLE_K8S_CUSTOMER_ALERTS:-}" in', run)
        self.assertIn("/tmp/k8s-alerting/customer-k8s-alerts.yaml", run)
        self.assertIn("/tmp/k8s-alerting/customer-k8s-alerts-delete.yaml", run)
        self.assertIn("stage_grafana_file_secret", run)
        self.assertIn("/tmp/grafana-file-secrets", run)
        self.assertIn("install_grafana_ca_bundle", run)
        self.assertNotIn("cat \"$ca_file\" >&", run)
        self.assertIn("PRIVATE KEY", run)
        true_at = run.find("\n  true)\n")
        false_at = run.find("\n  false)\n")
        copy_alerts = run.find('cp "$k8s_alerts_src" "$k8s_alerts_dest"')
        copy_delete = run.find('cp "$k8s_alerts_delete_src" "$k8s_alerts_delete_dest"')
        self.assertNotEqual(true_at, -1)
        self.assertLess(true_at, copy_alerts)
        self.assertLess(copy_alerts, false_at)
        self.assertLess(false_at, copy_delete)


@unittest.skipUnless(shutil.which("helm"), "helm is required to render the chart")
class GrafanaAlertingHelmTest(unittest.TestCase):
    def test_defaults_enable_k8s_alerts_without_smtp_or_webhook(self):
        rendered = helm_template()
        self.assertIn('PCA_ENABLE_K8S_CUSTOMER_ALERTS: "true"', rendered)
        self.assertIn("fsGroup: 472", rendered)
        self.assertNotIn("GF_SMTP_ENABLED", rendered)
        self.assertNotIn("HTTP_PROXY:", rendered)
        self.assertNotIn("uid: pca-customer-email", rendered)
        self.assertNotIn("deleteContactPoints:", rendered)
        self.assertNotIn("resetPolicies:", rendered)
        self.assertNotIn("type: email", rendered)
        self.assertNotIn("GF_SMTP_PASSWORD:", rendered)
        self.assertNotIn("GF_SECURITY_SECRET_KEY:", rendered)
        self.assertNotIn("PCA_GRAFANA_WEBHOOK_AUTH_SECRET", rendered)
        self.assertNotIn("kind: NetworkPolicy", rendered)
        for marker in SECRET_MARKERS:
            self.assertNotIn(marker, rendered)

    def test_swarm_style_disables_k8s_customer_alerts(self):
        rendered = helm_template("--set", "grafana.customerK8sAlerts.enabled=false")
        self.assertIn('PCA_ENABLE_K8S_CUSTOMER_ALERTS: "false"', rendered)

    def test_smtp_and_email_contact_point(self):
        rendered = helm_template(
            "--set", "grafana.smtp.enabled=true",
            "--set-string", "grafana.smtp.host=smtp.example.com:587",
            "--set-string", "grafana.smtp.fromAddress=alerts@example.com",
            "--set-string", "grafana.smtp.existingSecret=grafana-smtp",
            "--set", "grafana.alerting.contactPoints.email.enabled=true",
            "--set-json", 'grafana.alerting.contactPoints.email.addresses="ops$alerts@example.com,other@example.com"',
            "--set", "grafana.security.secretKeyExistingSecret=grafana-security-secret-key",
        )
        self.assertIn('GF_SMTP_ENABLED: "true"', rendered)
        self.assertIn('GF_SMTP_SKIP_VERIFY: "false"', rendered)
        self.assertIn('GF_SMTP_PASSWORD: "$__file{/var/run/secrets/grafana-smtp/password}"', rendered)
        self.assertIn(
            'GF_SECURITY_SECRET_KEY: "$__file{/var/run/secrets/grafana-security/secret-key}"',
            rendered,
        )
        self.assertIn('addresses: "ops$$alerts@example.com;other@example.com"', rendered)
        self.assertIn("name: pca-customer-email", rendered)
        self.assertIn("defaultMode: 0440", rendered)
        self.assertIn("/var/run/secrets/grafana-smtp", rendered)
        self.assertIn("/var/run/secrets/grafana-security", rendered)
        self.assertNotIn("subPath: ca.crt", rendered)
        for doc in configmap_docs(rendered):
            self.assertNotIn("ops$alerts@example.com", doc.replace("ops$$alerts@example.com", ""))
            self.assertNotIn("BEGIN PRIVATE KEY", doc)

    def test_webhook_bearer_basic_and_ca(self):
        pem = "-----BEGIN CERTIFICATE----- MIIB -----END CERTIFICATE-----"
        rendered = helm_template(
            "--set", "grafana.alerting.contactPoints.webhook.enabled=true",
            "--set-string", "grafana.alerting.contactPoints.webhook.url=https://hooks.example.com/alert",
            "--set-string", "grafana.alerting.contactPoints.webhook.authType=bearer",
            "--set-string", "grafana.alerting.contactPoints.webhook.existingSecret=grafana-alerting-webhook",
            "--set-string", f"grafana.alerting.contactPoints.webhook.caCertPem={pem}",
            "--set", "grafana.alerting.notificationPolicy.managed=true",
        )
        self.assertIn("name: pca-customer-webhook", rendered)
        self.assertIn('authorization_credentials: "$PCA_GRAFANA_WEBHOOK_AUTH_SECRET"', rendered)
        self.assertNotIn("$__file{", rendered.split("pca-customer-webhook")[1].split("kind:")[0])
        self.assertIn("caCertificate: |-", rendered)
        self.assertIn("BEGIN CERTIFICATE", rendered)
        self.assertIn("name: PCA_GRAFANA_WEBHOOK_AUTH_SECRET", rendered)
        self.assertIn("secretKeyRef:", rendered)
        self.assertIn("pca-unrouted-default", rendered)
        self.assertIn("- ['audience', '=', 'customer']", rendered)

        basic = helm_template(
            "--set", "grafana.alerting.contactPoints.webhook.enabled=true",
            "--set-string", "grafana.alerting.contactPoints.webhook.url=https://hooks.example.com/alert",
            "--set-string", "grafana.alerting.contactPoints.webhook.authType=basic",
            "--set-string", "grafana.alerting.contactPoints.webhook.basicAuthUser=hookuser",
            "--set-string", "grafana.alerting.contactPoints.webhook.existingSecret=grafana-alerting-webhook",
        )
        self.assertIn("username:", basic)
        self.assertIn('password: "$PCA_GRAFANA_WEBHOOK_AUTH_SECRET"', basic)

    def test_email_and_webhook_managed_policy_versus_reset(self):
        managed = helm_template(
            "--set", "grafana.smtp.enabled=true",
            "--set-string", "grafana.smtp.host=smtp.example.com:587",
            "--set-string", "grafana.smtp.fromAddress=alerts@example.com",
            "--set", "grafana.alerting.contactPoints.email.enabled=true",
            "--set-string", "grafana.alerting.contactPoints.email.addresses=ops@example.com",
            "--set", "grafana.alerting.contactPoints.webhook.enabled=true",
            "--set-string", "grafana.alerting.contactPoints.webhook.url=https://hooks.example.com/alert",
            "--set", "grafana.alerting.notificationPolicy.managed=true",
        )
        self.assertIn("continue: true", managed)
        self.assertIn("receiver: pca-customer-email", managed)
        self.assertIn("receiver: pca-customer-webhook", managed)
        self.assertNotIn("resetPolicies:", managed)
        self.assertNotIn("deleteContactPoints:", managed)

        reset = helm_template(
            "--set", "grafana.alerting.notificationPolicy.resetPoliciesOnDisable=true",
        )
        self.assertIn("resetPolicies:", reset)
        self.assertIn("- 1", reset)
        self.assertIn("uid: pca-customer-email", reset)
        self.assertIn("uid: pca-customer-webhook", reset)

        unlocked = helm_template(
            "--set", "grafana.alerting.notificationPolicy.managed=false",
        )
        self.assertNotIn("resetPolicies:", unlocked)
        self.assertNotIn("customer-notification-policies.yaml", unlocked)
        self.assertNotIn("deleteContactPoints:", unlocked)

    def test_disable_one_contact_point_rewrites_managed_policy_then_deletes(self):
        rendered = helm_template(
            "--set", "grafana.smtp.enabled=true",
            "--set-string", "grafana.smtp.host=smtp.example.com:587",
            "--set-string", "grafana.smtp.fromAddress=alerts@example.com",
            "--set", "grafana.alerting.contactPoints.email.enabled=true",
            "--set-string", "grafana.alerting.contactPoints.email.addresses=ops@example.com",
            "--set", "grafana.alerting.contactPoints.webhook.enabled=false",
            "--set", "grafana.alerting.notificationPolicy.managed=true",
        )
        self.assertIn("receiver: pca-customer-email", rendered)
        self.assertNotIn("receiver: pca-customer-webhook", rendered)
        self.assertIn("deleteContactPoints:", rendered)
        self.assertIn("uid: pca-customer-webhook", rendered)
        self.assertNotIn("uid: pca-customer-email", rendered.split("deleteContactPoints:", 1)[1])
        self.assertNotIn("resetPolicies:", rendered)

    def test_disable_last_contact_point_keeps_receiver_until_reset(self):
        last_off = helm_template(
            "--set", "grafana.smtp.enabled=true",
            "--set-string", "grafana.smtp.host=smtp.example.com:587",
            "--set-string", "grafana.smtp.fromAddress=alerts@example.com",
            "--set", "grafana.alerting.contactPoints.email.enabled=false",
            "--set", "grafana.alerting.notificationPolicy.managed=true",
        )
        self.assertNotIn("deleteContactPoints:", last_off)
        self.assertNotIn("resetPolicies:", last_off)
        self.assertNotIn("customer-notification-policies.yaml", last_off)

        last_off_with_reset = helm_template(
            "--set", "grafana.smtp.enabled=true",
            "--set-string", "grafana.smtp.host=smtp.example.com:587",
            "--set-string", "grafana.smtp.fromAddress=alerts@example.com",
            "--set", "grafana.alerting.contactPoints.email.enabled=false",
            "--set", "grafana.alerting.notificationPolicy.managed=true",
            "--set", "grafana.alerting.notificationPolicy.resetPoliciesOnDisable=true",
        )
        self.assertIn("resetPolicies:", last_off_with_reset)
        self.assertIn("deleteContactPoints:", last_off_with_reset)
        self.assertIn("uid: pca-customer-email", last_off_with_reset)
        self.assertIn("uid: pca-customer-webhook", last_off_with_reset)
        self.assertIn("uid: pca-unrouted-default", last_off_with_reset)

    def test_proxy_propagation(self):
        rendered = helm_template(
            "--set", "grafana.proxy.enabled=true",
            "--set-string", "grafana.proxy.httpProxy=http://proxy.example.com:3128",
            "--set-string", "grafana.proxy.httpsProxy=http://proxy.example.com:3128",
        )
        self.assertIn('HTTP_PROXY: "http://proxy.example.com:3128"', rendered)
        self.assertIn('HTTPS_PROXY: "http://proxy.example.com:3128"', rendered)
        self.assertIn("NO_PROXY:", rendered)
        self.assertIn(".svc.cluster.local", rendered)

    def test_ssrf_and_validation_rejections(self):
        cases = [
            (["--set", "grafana.alerting.contactPoints.webhook.enabled=true",
              "--set-string", "grafana.alerting.contactPoints.webhook.url=http://evil.example.com"],
             "https://"),
            (["--set", "grafana.alerting.contactPoints.webhook.enabled=true",
              "--set-string", "grafana.alerting.contactPoints.webhook.url=https://127.0.0.1"],
             "loopback"),
            (["--set", "grafana.alerting.contactPoints.webhook.enabled=true",
              "--set-string", "grafana.alerting.contactPoints.webhook.url=https://[::1]"],
             "loopback"),
            (["--set", "grafana.alerting.contactPoints.webhook.enabled=true",
              "--set-string", "grafana.alerting.contactPoints.webhook.url=https://[::ffff:169.254.169.254]"],
             "metadata"),
            (["--set", "grafana.alerting.contactPoints.webhook.enabled=true",
              "--set-string", "grafana.alerting.contactPoints.webhook.url=https://zitadel/"],
             "single-label"),
            (["--set", "grafana.alerting.contactPoints.webhook.enabled=true",
              "--set-string", "grafana.alerting.contactPoints.webhook.url=https://grafana.default.svc.cluster.local"],
             "cluster service"),
            (["--set", "grafana.alerting.contactPoints.webhook.enabled=true",
              "--set-string", "grafana.alerting.contactPoints.webhook.url=https://hooks.example.com/a",
              "--set-string", "grafana.alerting.contactPoints.webhook.caCertPem=-----BEGIN PRIVATE KEY-----\nMII\n-----END PRIVATE KEY-----"],
             "PRIVATE KEY"),
            (["--set", "grafana.smtp.enabled=true",
              "--set-string", "grafana.smtp.host=smtp.example.com:587",
              "--set-string", "grafana.smtp.fromAddress=a@b.com",
              "--set", "grafana.alerting.contactPoints.email.enabled=true",
              "--set-json", 'grafana.alerting.contactPoints.email.addresses="'
              + ",".join(f"u{i}@example.com" for i in range(51)) + '"'],
             "50 recipients"),
        ]
        for args, needle in cases:
            with self.subTest(needle=needle):
                output = helm_template(*args, expect_fail=True)
                self.assertIn(needle, output)

    def test_dollar_escaping_and_hostile_templates(self):
        rendered = helm_template(
            "--set", "grafana.smtp.enabled=true",
            "--set-string", "grafana.smtp.host=smtp.example.com:587",
            "--set-string", "grafana.smtp.fromAddress=alerts@example.com",
            "--set", "grafana.alerting.contactPoints.email.enabled=true",
            "--set-json", 'grafana.alerting.contactPoints.email.addresses="a@b.com{{.Values.grafana}},ops$x@example.com"',
            "--set", "grafana.alerting.contactPoints.webhook.enabled=true",
            "--set-string", "grafana.alerting.contactPoints.webhook.url=https://hooks.example.com/a?token=$abc",
        )
        self.assertIn("{{.Values.grafana}}", rendered)
        self.assertIn("ops$$x@example.com", rendered)
        self.assertIn("token=$$abc", rendered)
        self.assertNotIn("token=$abc", rendered.replace("token=$$abc", ""))

    def test_configmaps_contain_no_plaintext_secrets(self):
        rendered = helm_template(
            "--set", "grafana.smtp.enabled=true",
            "--set-string", "grafana.smtp.host=smtp.example.com:587",
            "--set-string", "grafana.smtp.fromAddress=alerts@example.com",
            "--set-string", "grafana.smtp.existingSecret=grafana-smtp",
            "--set", "grafana.alerting.contactPoints.webhook.enabled=true",
            "--set-string", "grafana.alerting.contactPoints.webhook.url=https://hooks.example.com/alert",
            "--set-string", "grafana.alerting.contactPoints.webhook.authType=bearer",
            "--set-string", "grafana.alerting.contactPoints.webhook.existingSecret=grafana-alerting-webhook",
            "--set", "grafana.security.secretKeyExistingSecret=grafana-security-secret-key",
        )
        for doc in configmap_docs(rendered):
            for marker in SECRET_MARKERS:
                self.assertNotIn(marker, doc)
            if "GF_SMTP_PASSWORD:" in doc:
                self.assertIn('$__file{/var/run/secrets/grafana-smtp/password}', doc)
            if "GF_SECURITY_SECRET_KEY:" in doc:
                self.assertIn('$__file{/var/run/secrets/grafana-security/secret-key}', doc)
            if "authorization_credentials:" in doc:
                self.assertIn('"$PCA_GRAFANA_WEBHOOK_AUTH_SECRET"', doc)
                self.assertNotIn("$__file{", doc.split("authorization_credentials:")[1][:200])

    def test_checksums_and_ca_directory_mount(self):
        rendered = helm_template(
            "--set", "grafana.smtp.enabled=true",
            "--set-string", "grafana.smtp.host=smtp.example.com:587",
            "--set-string", "grafana.smtp.fromAddress=alerts@example.com",
            "--set-string", "grafana.smtp.existingSecret=grafana-smtp",
            "--set-string", "grafana.smtp.caCertExistingSecret=grafana-alerting-ca",
            "--set-string", "grafana.smtp.secretChecksum=abc123",
            "--set-string", "grafana.smtp.caCertChecksum=def456",
            "--set-string", "grafana.alerting.webhookSecretChecksum=ghi789",
        )
        self.assertIn("checksum/alerting-provisioning:", rendered)
        self.assertIn('checksum/smtp-secret: "abc123"', rendered)
        self.assertIn('checksum/ca-cert: "def456"', rendered)
        self.assertIn('checksum/webhook-secret: "ghi789"', rendered)
        self.assertIn("mountPath: /var/run/secrets/grafana-ca", rendered)
        self.assertNotRegex(
            rendered,
            r"name: grafana-ca\n(?:.*\n){0,6}\s+subPath:",
        )

    def test_networkpolicy_egress_blocks_metadata(self):
        rendered = helm_template(
            "--set", "grafana.networkPolicy.enabled=true",
            "--set-string", "grafana.networkPolicy.trustedIngress[0].podSelector.matchLabels.app=nginx",
        )
        self.assertIn("kind: NetworkPolicy", rendered)
        self.assertIn("169.254.169.254/32", rendered)
        self.assertIn("Egress", rendered)
        self.assertIn("port: 53", rendered)
        self.assertIn("port: 9090", rendered)
        self.assertIn("port: 10000", rendered)


class CustomerAlertSmokeContractTest(unittest.TestCase):
    def test_smoke_script_exists_and_is_gated(self):
        script = ROOT / "tests/smoke-customer-k8s-alerts.sh"
        self.assertTrue(script.is_file())
        text = script.read_text()
        self.assertIn("PCA_ENABLE_K8S_CUSTOMER_ALERTS", text)
        self.assertIn("PCA_ENABLE_K8S_CUSTOMER_ALERTS=false", text)
        self.assertIn("customer-k8s-alerts-delete.yaml", text)
        self.assertIn("/api/health", text)
        self.assertIn("Customer Alerts (k8s)", text)
        self.assertIn("--user grafana", text)
        self.assertIn("/tmp/grafana-file-secrets", text)


if __name__ == "__main__":
    unittest.main()
