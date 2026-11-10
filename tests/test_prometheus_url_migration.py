import os
import shutil
import sqlite3
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD_URL = "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"
NEW_URL = OLD_URL + "/prometheus"
SCRIPT = (ROOT / "run.sh").read_text()
MIGRATION = SCRIPT[
    SCRIPT.index("# Repair only the obsolete bundled URL;") : SCRIPT.index("\ngrafana_args=(")
]


@unittest.skipUnless(shutil.which("sqlite3"), "sqlite3 is required to run the startup migration")
class PrometheusUrlMigrationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.database = self.root / "grafana.db"
        self.provisioning = self.root / "provisioning/datasources/prometheus-datasource.yaml"
        self.provisioning.parent.mkdir(parents=True)
        self.provisioning.write_text(f'  url: "{NEW_URL}"\n  version: 1\n')
        with sqlite3.connect(self.database) as db:
            db.execute("""CREATE TABLE data_source (
                org_id INTEGER, uid TEXT, name TEXT, type TEXT, url TEXT,
                version INTEGER, json_data TEXT, secure_json_data TEXT
            )""")

    def seed(self, url=OLD_URL, version=2, org_id=1, uid="prometheus",
             name="Prometheus", kind="prometheus"):
        with sqlite3.connect(self.database) as db:
            db.execute("DELETE FROM data_source")
            db.execute("INSERT INTO data_source VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (org_id, uid, name, kind, url, version,
                        '{"timeInterval":"30s"}', "encrypted-secret"))

    def record(self):
        with sqlite3.connect(self.database) as db:
            return db.execute("SELECT * FROM data_source").fetchone()

    def migrate(self, **overrides):
        env = dict(os.environ, GF_PATHS_DATA=str(self.root),
                   GF_PATHS_PROVISIONING=str(self.root / "provisioning"),
                   DONT_COPY_STOCK_DASHBOARDS="")
        env.update(overrides)
        return subprocess.run(["bash", "-e", "-c", MIGRATION], env=env,
                              capture_output=True, text=True)

    def test_repairs_existing_versions_and_preserves_other_fields(self):
        for version in (2, 47):
            for url in (OLD_URL, OLD_URL + "/"):
                with self.subTest(version=version, url=url):
                    self.seed(url=url, version=version)
                    before = self.record()
                    result = self.migrate()
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.record(), before[:4] + (NEW_URL, version + 1) + before[6:])
                    self.assertIn("Migrated bundled Prometheus datasource URL", result.stdout)

    def test_second_start_does_not_change_the_record(self):
        self.seed()
        self.assertEqual(self.migrate().returncode, 0)
        first = self.record()
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.record(), first)
        self.assertEqual(result.stdout, "")

    @unittest.skipUnless(shutil.which("helm"), "helm is required to render the chart")
    def test_accepts_the_actual_helm_provisioning_file(self):
        rendered = subprocess.run(
            ["helm", "template", "grafana", str(ROOT / "helm"),
             "--show-only", "templates/prometheus-datasource.yaml"],
            check=True, capture_output=True, text=True,
        ).stdout
        self.provisioning.write_text(textwrap.dedent(
            rendered.split("  prometheus-datasource.yaml: |-\n", 1)[1]
        ))
        self.seed()
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.record()[4:6], (NEW_URL, 3))

    def test_leaves_unrelated_datasources_unchanged(self):
        cases = (
            {"url": NEW_URL},
            {"url": "https://external.example/prometheus"},
            {"url": "http://prometheus:9090"},
            {"org_id": 2},
            {"uid": "custom-prometheus"},
            {"name": "Custom Prometheus"},
            {"kind": "other-plugin"},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                self.seed(**fields)
                before = self.record()
                result = self.migrate()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.record(), before)

    def test_respects_external_url_in_provisioning(self):
        self.seed()
        self.provisioning.write_text('  url: "https://external.example/prometheus"\n')
        before = self.record()
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.record(), before)

    def test_respects_disabled_stock_provisioning(self):
        self.seed()
        before = self.record()
        result = self.migrate(DONT_COPY_STOCK_DASHBOARDS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.record(), before)

    def test_skips_missing_provisioning_file(self):
        self.seed()
        self.provisioning.unlink()
        before = self.record()
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.record(), before)

    def test_fresh_install_does_not_create_a_database(self):
        self.database.unlink()
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.database.exists())

    def test_database_without_datasource_table_is_left_for_grafana_to_initialize(self):
        with sqlite3.connect(self.database) as db:
            db.execute("DROP TABLE data_source")
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_database_error_stops_startup(self):
        self.database.write_bytes(b"not a SQLite database")
        result = self.migrate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a database", result.stderr)


if __name__ == "__main__":
    unittest.main()
