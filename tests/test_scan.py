"""DB와 외부 API를 대체해 스캔의 상태 보존과 실패 처리를 확인한다."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from engine import scan
from jobs import run_scan as scan_job
from ncp.insight import stats_from_points


START = datetime(2026, 10, 12, 12, 0)


class MemoryDB:
    def __init__(self):
        self.known = {}
        self.rows = []
        self.failed = []
        self.logs = []

    def get_known(self):
        return self.known

    def save_resources(self, rows, failed):
        self.rows = rows
        self.failed = failed
        self.known = {r["ncp_no"]: {"state": r["state"], "state_since": r["state_since"],
                                     "last_seen": r["last_seen"]} for r in rows}

    def log(self, action, **fields):
        self.logs.append((action, fields))


def server(state="STOPPED"):
    return {"ncp_no": "101", "type": "server", "name": "finsh-test-b-srv1", "state": state,
            "detail": {"spec": "s2-g3a"}}


def publicip():
    return {"ncp_no": "201", "type": "publicip", "name": "finsh-test-b-ip1", "state": "DETACHED",
            "detail": {"attached_server": None}}


def basic_disk():
    return {"ncp_no": "301", "type": "blockstorage", "name": "finsh-test-b-srv1", "state": "ATTACHED",
            "detail": {"attached_server": "finsh-test-b-srv1", "storage_type": "BASIC",
                       "disk_type": "CB1", "size_gb": 10}}


class ScanTests(unittest.TestCase):
    def setUp(self):
        sync = patch("engine.protect.sync_terraform")
        self.sync = sync.start()
        self.addCleanup(sync.stop)

    def test_confirmed_empty_terraform_inventory_is_synced(self):
        db = MemoryDB()
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(scan.LISTERS, {"server": lambda: [], "publicip": lambda: [publicip()],
                                       "blockstorage": lambda: []}):
            scan.run_scan(db=db, terraform_reader=lambda: set(),
                          output_path=Path(folder) / "leak.json", at=START)
        self.sync.assert_called_once_with(set())
        self.assertEqual(db.rows[0]["grade"], "ORPHAN")

    def test_protection_sync_failure_blocks_candidates(self):
        self.sync.side_effect = RuntimeError("DB failure")
        db = MemoryDB()
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(scan.LISTERS, {"server": lambda: [], "publicip": lambda: [publicip()],
                                       "blockstorage": lambda: []}):
            scan.run_scan(db=db, terraform_reader=lambda: {"999"},
                          output_path=Path(folder) / "leak.json", at=START)
        self.assertEqual(db.rows[0]["grade"], "UNKNOWN")
        self.assertIn("동기화 실패", db.rows[0]["reason"])
        self.assertEqual(db.logs[-1][1]["result"], "FAIL")

    def test_cpu_query_uses_the_same_time_as_judgement(self):
        with patch("ncp.insight.cpu_stats_many", return_value={}) as query:
            self.assertEqual(scan._cpu(["101"], at=START), {})
        query.assert_called_once_with(["101"], days=7, end_at=START)

    def test_job_reports_detected_and_visible_counts_separately(self):
        with patch.object(scan_job, "run_scan", return_value=(5, 2)), \
             patch.object(scan_job.database, "get_leaks", return_value=[{"id": "ip-201"}]), \
             patch("builtins.print") as output:
            scan_job.main()
        self.assertIn("탐지 후보 2개, top 표시 1개", output.call_args_list[-1].args[0])

    def test_insight_evidence_reaches_idle_judgement(self):
        db = MemoryDB()
        observed_at = START + timedelta(days=8)
        db.known["101"] = {"state": "RUNNING", "state_since": START,
                           "last_seen": observed_at - timedelta(minutes=30)}
        end_ms = int(observed_at.replace(tzinfo=ZoneInfo("Asia/Seoul")).timestamp() * 1000)
        interval_ms = 30 * 60_000
        start_ms = end_ms - 7 * 86_400_000
        points = [[stamp, 2.0] for stamp in range(start_ms + interval_ms, end_ms + 1, interval_ms)]
        stats = stats_from_points(points, start_ms, end_ms, interval_ms)

        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(scan.LISTERS, {"server": lambda: [server("RUNNING")],
                                          "publicip": lambda: [], "blockstorage": lambda: []}):
                scan.run_scan(db=db, cpu_reader=lambda numbers, days: {"101": stats},
                              terraform_reader=lambda: set(),
                              output_path=Path(folder) / "leak.json", at=observed_at)
                self.assertEqual(db.rows[0]["grade"], "IDLE")
                self.assertEqual(db.rows[0]["detail"]["cpu_avg"], 2.0)

                insufficient = stats_from_points([], start_ms, end_ms, interval_ms)
                scan.run_scan(db=db, cpu_reader=lambda numbers, days: {"101": insufficient},
                              terraform_reader=lambda: set(),
                              output_path=Path(folder) / "leak.json", at=observed_at)
                self.assertEqual(db.rows[0]["grade"], "UNKNOWN")

    def test_scope_allows_named_resources_and_listed_public_ips_only(self):
        cfg = {"scan_name_prefix": "finsh-", "allowed_ncp_no": ["201"]}
        self.assertTrue(scan.in_scope(server(), cfg))
        self.assertTrue(scan.in_scope({"type": "publicip", "name": "other", "ncp_no": "201"}, cfg))
        self.assertFalse(scan.in_scope({"type": "server", "name": "other", "ncp_no": "201"}, cfg))

    def test_reconnected_ip_disappears_from_candidate_file(self):
        db = MemoryDB()
        attached = False

        def ips():
            row = publicip()
            if attached:
                row["state"] = "ATTACHED"
                row["detail"]["attached_server"] = "finsh-test-b-srv1"
            return [row]

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "leak.json"
            with patch.dict(scan.LISTERS, {"server": lambda: [], "publicip": ips,
                                          "blockstorage": lambda: []}):
                self.assertEqual(scan.run_scan(db=db, terraform_reader=lambda: set(),
                                               output_path=output, at=START), (1, 1))
                attached = True
                self.assertEqual(scan.run_scan(db=db, terraform_reader=lambda: set(),
                                               output_path=output, at=START + timedelta(minutes=30)), (1, 0))
                self.assertEqual(db.rows[0]["grade"], "OK")
                self.assertEqual(json.loads(output.read_text(encoding="utf-8")), [])

    def test_first_and_second_scan_keep_observation_and_only_export_candidates(self):
        db = MemoryDB()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "leak.json"
            with patch.dict(scan.LISTERS, {"server": lambda: [server()], "publicip": lambda: [publicip()],
                                          "blockstorage": lambda: [basic_disk()]}):
                first = scan.run_scan(db=db, terraform_reader=lambda: set(), output_path=output, at=START)
                self.assertEqual(first, (3, 1))
                grades = {r["type"]: r["grade"] for r in db.rows}
                self.assertEqual(grades, {"server": "WAITING", "publicip": "ORPHAN", "blockstorage": "OK"})
                self.assertEqual(next(r for r in db.rows if r["type"] == "server")["cost_hourly"], 1.6)
                exported = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual([r["grade"] for r in exported], ["ORPHAN"])
                self.assertNotIn("state_since", exported[0])

                scan.run_scan(db=db, terraform_reader=lambda: set(), output_path=output,
                              at=START + timedelta(minutes=10))
                stopped = next(r for r in db.rows if r["type"] == "server")
                self.assertEqual(stopped["state_since"], START)
                self.assertEqual(stopped["grade"], "WAITING")
                self.assertGreater(next(r for r in db.rows if r["type"] == "publicip")["cost_total"], 0)

    def test_failed_kind_is_reported_to_database_without_dropping_other_results(self):
        db = MemoryDB()
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(scan.LISTERS, {"server": lambda: [server()],
                                          "publicip": lambda: (_ for _ in ()).throw(RuntimeError("API 실패")),
                                          "blockstorage": lambda: []}):
                scan.run_scan(db=db, terraform_reader=lambda: set(),
                              output_path=Path(folder) / "leak.json", at=START)
        self.assertEqual(db.failed, ["publicip"])
        self.assertEqual(db.logs[0][1]["result"], "FAIL")
        self.assertEqual(db.rows[0]["grade"], "WAITING")

    def test_running_server_queries_cpu_only_after_required_observation(self):
        db = MemoryDB()
        called = []

        def cpu_reader(numbers, days):
            called.append((numbers, days))
            return {}

        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(scan.LISTERS, {"server": lambda: [server("RUNNING")],
                                          "publicip": lambda: [], "blockstorage": lambda: []}):
                scan.run_scan(db=db, cpu_reader=cpu_reader, terraform_reader=lambda: set(),
                              output_path=Path(folder) / "leak.json", at=START)
                self.assertEqual(called, [])
                db.known["101"]["state_since"] = START - timedelta(days=8)
                scan.run_scan(db=db, cpu_reader=cpu_reader, terraform_reader=lambda: set(),
                              output_path=Path(folder) / "leak.json", at=START + timedelta(minutes=30))
        self.assertEqual(called, [(["101"], 7)])
        self.assertEqual(db.rows[0]["grade"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
