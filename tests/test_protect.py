import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from engine import protect

T = datetime(2026, 10, 13, 12, 0)
RESOURCE = {"ncp_no": "103", "id": "srv-103", "terraform": False}


class ProtectTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.cur = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.conn.cursor.return_value.__enter__.return_value = self.cur
        self.connection = patch.object(protect, "connect", return_value=self.conn)
        self.clock = patch.object(protect, "now", return_value=T)
        self.connection.start()
        self.clock.start()
        self.addCleanup(self.connection.stop)
        self.addCleanup(self.clock.stop)

    def test_user_default_thirty_days_and_update_preserves_terraform(self):
        self.cur.fetchone.return_value = {"source": "user"}
        with patch.dict(protect.settings, {"protect_days": 30}):
            ok, message = protect.add(RESOURCE, "시연")
        self.assertTrue(ok)
        sql, args = self.cur.execute.call_args_list[0].args
        self.assertEqual(args, ("103", "시연", T + timedelta(days=30), T))
        self.assertIn("IF(source='terraform'", sql)
        self.conn.commit.assert_called_once()

    def test_terraform_existing_row_cannot_be_overridden(self):
        self.cur.fetchone.return_value = {"source": "terraform"}
        self.assertFalse(protect.add(RESOURCE, "시연")[0])

    def test_terraform_resource_cannot_add_or_remove_even_without_row(self):
        r = {**RESOURCE, "terraform": True}
        self.assertFalse(protect.add(r, "시연")[0])
        self.assertFalse(protect.remove(r)[0])
        self.cur.execute.assert_not_called()

    def test_invalid_duration_or_reason_does_not_write(self):
        for days in (0, -1, float("inf"), "bad"):
            self.assertFalse(protect.add(RESOURCE, "시연", days)[0])
        self.assertFalse(protect.add(RESOURCE, "")[0])
        self.cur.execute.assert_not_called()

    def test_remove_is_conditioned_on_user_source(self):
        self.cur.rowcount = 1
        self.assertTrue(protect.remove(RESOURCE)[0])
        self.assertIn("source='user'", self.cur.execute.call_args.args[0])

    def test_remove_terraform_refused_after_concurrent_sync(self):
        self.cur.rowcount = 0
        self.cur.fetchone.return_value = {"source": "terraform"}
        self.assertFalse(protect.remove(RESOURCE)[0])

    def test_expired_user_protection_is_excluded_from_queries(self):
        self.cur.fetchone.return_value = None
        self.assertFalse(protect.is_protected("103"))
        self.assertIn("until > %s", self.cur.execute.call_args.args[0])
        self.assertEqual(self.cur.execute.call_args.args[1], ("103", T))
        protect.list_all()
        self.assertIn("until>%s", self.cur.execute.call_args.args[0])

    def test_sync_is_atomic_and_deduplicates_numbers(self):
        self.cur.fetchone.return_value = {"acquired": 1}
        protect.sync_terraform([103, "103", "104"])
        calls = self.cur.execute.call_args_list
        inserts = [c for c in calls if c.args[0].startswith("INSERT")]
        self.assertEqual(len(inserts), 2)
        self.assertIn("source='terraform',until=NULL", inserts[0].args[0])
        self.conn.commit.assert_called_once()
        self.assertIn("RELEASE_LOCK", calls[-1].args[0])

    def test_confirmed_empty_inventory_clears_only_terraform_rows(self):
        self.cur.fetchone.return_value = {"acquired": 1}
        protect.sync_terraform(set())
        self.assertIn(unittest.mock.call("DELETE FROM protections WHERE source='terraform'"),
                      self.cur.execute.call_args_list)

    def test_unknown_inventory_does_not_touch_db(self):
        with self.assertRaises(ValueError):
            protect.sync_terraform(None)
        self.cur.execute.assert_not_called()

    def test_sync_failure_rolls_back_and_releases_lock(self):
        self.cur.fetchone.return_value = {"acquired": 1}
        self.cur.execute.side_effect = [None, RuntimeError("write failed"), None]
        with self.assertRaises(RuntimeError):
            protect.sync_terraform({"103"})
        self.conn.rollback.assert_called_once()
        self.assertIn("RELEASE_LOCK", self.cur.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
