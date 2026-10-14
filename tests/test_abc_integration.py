"""Exercise the A/B/C contracts without a database or cloud deletion."""

import io
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from rich.console import Console
except ModuleNotFoundError:
    # Exercise command contracts on a development machine without Rich. The
    # deployed CLI still uses the real dependency from requirements.txt.
    class Console:
        def __init__(self, file=None, **_):
            self.file = file or sys.stdout

        def print(self, value=""):
            self.file.write(f"{value}\n")

    class Table:
        def __init__(self, *_, **__):
            self.rows = []

        @classmethod
        def grid(cls, **_):
            return cls()

        def add_column(self, *_, **__):
            pass

        def add_row(self, *values):
            self.rows.append(values)

        def __str__(self):
            return "\n".join(" ".join(str(value) for value in row) for row in self.rows)

    class Panel:
        def __init__(self, value, **_):
            self.value = value

        def __str__(self):
            return str(self.value)

    rich = types.ModuleType("rich")
    rich.console = types.ModuleType("rich.console")
    rich.panel = types.ModuleType("rich.panel")
    rich.table = types.ModuleType("rich.table")
    rich.console.Console = Console
    rich.panel.Panel = Panel
    rich.table.Table = Table
    sys.modules.update({"rich": rich, "rich.console": rich.console,
                        "rich.panel": rich.panel, "rich.table": rich.table})

from engine import killer, scan, trash
from engine.config import now
from shell import data, screen
from shell.commands import FinshShell


def detached_ip():
    return {"ncp_no": "201", "type": "publicip", "name": "finsh-test-abc-ip",
            "state": "DETACHED", "detail": {"ip": "192.0.2.40", "attached_server": None}}


class ABCIntegrationTests(unittest.TestCase):
    def setUp(self):
        sync = patch("engine.protect.sync_terraform")
        sync.start()
        self.addCleanup(sync.stop)

    def test_stat_shows_cpu_evidence_and_protection(self):
        output = io.StringIO()
        resource = {"id": "srv-101", "type": "server", "name": "finsh-test-server",
                    "grade": "IDLE", "protected": True, "protected_memo": "시연 중",
                    "detail": {"cpu_avg": 2.0, "cpu_sample_count": 8,
                               "cpu_expected_count": 10, "cpu_coverage": 0.8,
                               "cpu_last_at": "2026-10-13T12:00:00+09:00"}}
        with patch.object(screen, "console", Console(file=output)):
            screen.print_stat(resource)
        rendered = output.getvalue()
        self.assertIn("CPU 평균", rendered)
        self.assertIn("2.0%", rendered)
        self.assertIn("8/10 (80%)", rendered)
        self.assertIn("시연 중", rendered)

    def test_top_identifies_unknown_cost(self):
        output = io.StringIO()
        candidate = {"id": "ip-201", "name": "finsh-test-ip", "type": "publicip",
                     "grade": "ORPHAN", "cost_hourly": None, "cost_total": None}
        with patch.object(screen, "console", Console(file=output)):
            screen.print_top([candidate])
        self.assertIn("확인된 금액 시간당", output.getvalue())
        self.assertIn("요금 미확인 1개", output.getvalue())

    def test_scan_top_kill_trash_and_restore(self):
        state = {"rows": [], "trashed": False, "due": None}
        db = Mock()
        db.get_known.return_value = {}
        db.save_resources.side_effect = lambda rows, failed: state.update(rows=rows)

        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(scan.LISTERS, {"server": lambda: [], "publicip": lambda: [detached_ip()],
                                       "blockstorage": lambda: []}):
            self.assertEqual(scan.run_scan(db=db, terraform_reader=lambda: set(),
                                           output_path=Path(folder) / "leak.json", at=now()), (1, 1))
        resource = state["rows"][0]
        self.assertEqual(resource["grade"], "ORPHAN")

        def put(item, due):
            self.assertEqual(item["ncp_no"], resource["ncp_no"])
            self.assertIsInstance(due, datetime)
            state.update(trashed=True, due=due)
            return 1

        def restore(identifier):
            self.assertEqual(identifier, resource["id"])
            state["trashed"] = False
            return True

        def trash_rows():
            if not state["trashed"]:
                return []
            return [{"no": 1, "id": resource["id"], "name": resource["name"],
                     "type": "publicip", "status": "WAITING", "put_at": now(),
                     "due_at": state["due"], "hold_reason": None}]

        output = io.StringIO()
        shell = FinshShell("tester")
        stored = {**resource, "last_seen": now(), "terraform": 0}
        with patch.object(screen, "console", Console(file=output, width=110)), \
             patch.object(data, "_fake", return_value=False), \
             patch.object(data, "get_leaks", side_effect=lambda: [] if state["trashed"] else [resource]), \
             patch.object(data, "get_resource", return_value=resource), \
             patch.object(data, "get_summary", return_value={"waiting": 0, "unknown": [], "last_scan": now()}), \
             patch.object(killer, "_live", return_value=resource), \
             patch.object(killer, "_stored", return_value=stored), \
             patch.object(killer, "_terraform_nos", return_value=set()), \
             patch.object(killer, "_protected", return_value=False), \
             patch.object(trash, "active", side_effect=lambda _: trash_rows()[0] if state["trashed"] else None), \
             patch.object(trash, "put", side_effect=put) as put_call, \
             patch.object(trash, "list_all", side_effect=trash_rows), \
             patch.object(trash, "restore", side_effect=restore), \
             patch("builtins.input", return_value="y"):
            shell.do_top("")
            shell.do_kill(resource["id"])
            self.assertTrue(state["trashed"])
            put_call.assert_called_once()
            shell.do_top("")
            shell.do_trash_list("")
            shell.do_trash_restore(resource["id"])
            shell.do_top("")

        rendered = output.getvalue()
        self.assertIn("정리 후보: ORPHAN 1", rendered)
        self.assertIn("정리 후보: ORPHAN 0", rendered)
        self.assertIn("휴지통", rendered)

    def test_kill9_requires_matching_id_and_dry_run_never_calls_cloud(self):
        resource = {**detached_ip(), "id": "ip-201", "grade": "ORPHAN"}
        stored = {**resource, "last_seen": now(), "terraform": 0}
        output = io.StringIO()
        shell = FinshShell("tester")
        with patch.object(screen, "console", Console(file=output)), \
             patch.object(data, "_fake", return_value=False), \
             patch.object(data, "get_resource", return_value=resource), \
             patch.object(killer, "_live", return_value=resource), \
             patch.object(killer, "_stored", return_value=stored), \
             patch.object(killer, "_terraform_nos", return_value=set()), \
             patch.object(killer, "_protected", return_value=False), \
             patch.object(trash, "active", return_value=None), \
             patch.object(killer.safety, "is_dry_run", return_value=True), \
             patch.object(killer.database, "log") as logged, \
             patch.object(killer, "call") as cloud_call, \
             patch("builtins.input", side_effect=["wrong-id", resource["id"]]):
            shell.do_sudo(f"kill -9 {resource['id']}")
            cloud_call.assert_not_called()
            shell.do_sudo(f"kill -9 {resource['id']}")
            cloud_call.assert_not_called()
        logged.assert_called_once()
        self.assertEqual(logged.call_args.args[0], "kill-9")
        self.assertEqual(logged.call_args.args[2], "DRYRUN")

    def test_missing_iac_inventory_hides_unverified_candidates(self):
        db = Mock()
        db.get_known.return_value = {}
        saved = []
        db.save_resources.side_effect = lambda rows, failed: saved.extend(rows)
        output = None
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(scan.LISTERS, {"server": lambda: [], "publicip": lambda: [detached_ip()],
                                       "blockstorage": lambda: []}):
            output = Path(folder) / "leak.json"
            self.assertEqual(scan.run_scan(db=db, terraform_reader=lambda: None,
                                           output_path=output, at=now()), (1, 0))
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), [])
        self.assertEqual(saved[0]["grade"], "UNKNOWN")
        self.assertEqual(db.log.call_args.kwargs["result"], "FAIL")

    def test_top_summary_uses_database_counts(self):
        output = io.StringIO()
        with patch.object(screen, "console", Console(file=output)):
            screen.print_top([], {"waiting": 3, "unknown": [("CPU 없음", 2)], "last_scan": now()})
        self.assertIn("WAITING 3개", output.getvalue())
        self.assertIn("UNKNOWN 2개", output.getvalue())


if __name__ == "__main__":
    unittest.main()
