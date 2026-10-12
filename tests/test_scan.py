"""DB와 외부 API를 대체해 스캔의 상태 보존과 실패 처리를 확인한다."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from engine import scan


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
