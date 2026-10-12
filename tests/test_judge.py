"""정리 후보를 잘못 표시하지 않는지 확인한다."""

import unittest
from datetime import datetime, timedelta

from engine.ids import add_ids, make_id
from engine.judge import judge, next_state_since


NOW = datetime(2026, 10, 12, 12, 0)
CFG = {
    "zombie_days": 7,
    "idle_days": 7,
    "idle_cpu_percent": 5,
    "cpu_min_coverage": 0.8,
    "cpu_max_missing": 2,
    "observe_max_gap_minutes": 90,
}


def resource(kind, state, **detail):
    return {"ncp_no": "1001", "type": kind, "state": state, "detail": detail}


def cpu_data(avg=0.4, count=320, expected=336, missing=1):
    return {
        "cpu_avg": avg,
        "cpu_sample_count": count,
        "cpu_expected_count": expected,
        "cpu_max_missing": missing,
        "cpu_window_start": NOW - timedelta(days=7),
        "cpu_window_end": NOW,
        "cpu_last_at": NOW - timedelta(minutes=10),
        "cpu_interval_minutes": 30,
        "cpu_error": False,
    }


class JudgeTests(unittest.TestCase):
    def grade(self, row, days=0):
        return judge(row, NOW - timedelta(days=days), NOW, CFG)["grade"]

    def test_orphan_requires_detached_and_extra_resource(self):
        self.assertEqual(self.grade(resource("publicip", "DETACHED")), "ORPHAN")
        self.assertEqual(self.grade(resource("publicip", "ATTACHED")), "OK")
        self.assertEqual(self.grade(resource("blockstorage", "DETACHED", storage_type="SVRBS")), "ORPHAN")
        self.assertEqual(self.grade(resource("blockstorage", "DETACHED", storage_type="BASIC")), "OK")
        self.assertEqual(self.grade(resource("blockstorage", "DETACHED")), "UNKNOWN")

    def test_stopped_time_uses_observation_not_creation_date(self):
        row = resource("server", "STOPPED")
        row["created_at"] = "2020-01-01"
        self.assertEqual(self.grade(row, days=0), "WAITING")
        self.assertEqual(self.grade(resource("server", "STOPPED"), days=8), "ZOMBIE")
        self.assertEqual(judge(resource("server", "STOPPED"), None, NOW, CFG)["grade"], "UNKNOWN")

    def test_running_requires_full_cpu_evidence(self):
        self.assertEqual(self.grade(resource("server", "RUNNING"), days=1), "OK")
        self.assertEqual(self.grade(resource("server", "RUNNING"), days=8), "UNKNOWN")
        self.assertEqual(self.grade(resource("server", "RUNNING", **cpu_data()), days=8), "IDLE")
        self.assertEqual(self.grade(resource("server", "RUNNING", **cpu_data(avg=6.0)), days=8), "OK")

    def test_missing_or_stale_cpu_cannot_be_idle(self):
        self.assertEqual(self.grade(resource("server", "RUNNING", **cpu_data(count=100)), days=8), "UNKNOWN")
        self.assertEqual(self.grade(resource("server", "RUNNING", **cpu_data(missing=3)), days=8), "UNKNOWN")
        stale = cpu_data()
        stale["cpu_last_at"] = NOW - timedelta(hours=2)
        self.assertEqual(self.grade(resource("server", "RUNNING", **stale), days=8), "UNKNOWN")
        short = cpu_data()
        short["cpu_window_start"] = NOW - timedelta(days=1)
        self.assertEqual(self.grade(resource("server", "RUNNING", **short), days=8), "UNKNOWN")

    def test_transition_and_conflicting_attachment_are_unknown(self):
        self.assertEqual(self.grade(resource("server", "INIT")), "UNKNOWN")
        self.assertEqual(self.grade(resource("publicip", "ASSOC")), "UNKNOWN")
        self.assertEqual(self.grade(resource("publicip", "DETACHED", attached_server="srv")), "UNKNOWN")

    def test_state_change_and_gap_reset_observation(self):
        since = NOW - timedelta(days=8)
        old = {"state": "STOPPED", "state_since": since, "last_seen": NOW - timedelta(minutes=30)}
        self.assertEqual(next_state_since(resource("server", "STOPPED"), old, NOW, CFG), since)
        self.assertEqual(next_state_since(resource("server", "RUNNING"), old, NOW, CFG), NOW)
        old["last_seen"] = NOW - timedelta(minutes=91)
        self.assertEqual(next_state_since(resource("server", "STOPPED"), old, NOW, CFG), NOW)

    def test_id_is_stable_and_invalid_number_is_rejected(self):
        row = resource("server", "STOPPED")
        self.assertEqual(add_ids([row])[0]["id"], make_id(row))
        self.assertEqual(make_id(row), make_id(dict(row)))
        with self.assertRaises(ValueError):
            make_id({"type": "server", "ncp_no": None})


if __name__ == "__main__":
    unittest.main()
