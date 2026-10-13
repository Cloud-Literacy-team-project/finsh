"""C deletion flow: every cloud-changing path is mocked."""

import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from engine import killer, notify, purger, trash, watcher
from engine.config import now
from ncp import server


IP = {"ncp_no": "1", "id": "ip-1", "type": "publicip", "name": "finsh-test-ip",
      "state": "DETACHED", "grade": "ORPHAN", "detail": {"ip": "192.0.2.1", "attached_server": None}}


class CFlowTests(unittest.TestCase):
    def test_server_lister_fetches_every_page_before_absence_check(self):
        one = {"serverInstanceNo": "1", "serverName": "finsh-test-one",
               "serverInstanceStatus": {"code": "NSTOP"}, "isProtectServerTermination": False}
        two = {**one, "serverInstanceNo": "2", "serverName": "finsh-test-two"}
        responses = [{"getServerInstanceListResponse": {"returnCode": "0", "totalRows": 2,
                                                       "serverInstanceList": [item]}} for item in (one, two)]
        with patch.object(server, "call", side_effect=responses) as api:
            self.assertEqual(len(server.list_all()), 2)
            self.assertEqual(api.call_count, 2)
            self.assertEqual(api.call_args_list[0].args[1]["pageSize"], 1000)

    def test_incomplete_server_listing_is_error_not_disappearance(self):
        one = {"serverInstanceNo": "1", "serverName": "finsh-test-one"}
        responses = [{"getServerInstanceListResponse": {"returnCode": "0", "totalRows": 2,
                                                       "serverInstanceList": [one]}},
                     {"getServerInstanceListResponse": {"returnCode": "0", "totalRows": 2,
                                                       "serverInstanceList": []}}]
        with patch.object(server, "call", side_effect=responses):
            with self.assertRaises(RuntimeError):
                server.list_all()

    def test_missing_terraform_reader_fails_closed(self):
        with self.assertRaises(killer.UnsafeDeletion):
            killer._terraform_nos()

    def test_dryrun_does_not_call_delete_api(self):
        stored = {**IP, "last_seen": now(), "terraform": 0}
        with patch.object(killer, "_live", return_value=IP), \
             patch.object(killer, "_stored", return_value=stored), \
             patch.object(killer, "_terraform_nos", return_value=set()), \
             patch.object(killer, "_protected", return_value=False), \
             patch.object(killer.safety, "is_dry_run", return_value=True), \
             patch.object(killer.database, "log"), \
             patch.object(killer, "call") as api:
            self.assertEqual(killer.execute_now(IP, confirmed=True), "DRYRUN")
            api.assert_not_called()

    def test_attached_ip_is_rejected_even_if_db_says_orphan(self):
        attached = {**IP, "state": "ATTACHED", "detail": {"ip": "192.0.2.1", "attached_server": "server"}}
        stored = {**IP, "state": "ATTACHED", "last_seen": now(), "terraform": 0}
        with patch.object(killer, "_live", return_value=attached), \
             patch.object(killer, "_stored", return_value=stored), \
             patch.object(killer, "_terraform_nos", return_value=set()), \
             patch.object(killer, "_protected", return_value=False), \
             patch.object(killer, "call") as api:
            with self.assertRaises(killer.UnsafeDeletion):
                killer.execute_now(attached, confirmed=True)
            api.assert_not_called()

    def test_watcher_holds_reused_ip(self):
        row = {**IP, "no": 7, "snapshot": IP}
        current = {**IP, "state": "ATTACHED", "detail": {"attached_server": "server"}}
        with patch.object(watcher.trash, "waiting", return_value=[row]), \
             patch.object(watcher.killer, "_live", return_value=current), \
             patch.object(watcher.trash, "hold", return_value=True) as hold, \
             patch.object(watcher.trash, "close") as close, \
             patch.object(watcher.database, "log"), patch.object(watcher.notify, "send"):
            self.assertEqual(watcher.run_watch()["held"], 1)
            hold.assert_called_once()
            close.assert_not_called()

    def test_watcher_lookup_failure_never_marks_gone(self):
        row = {**IP, "no": 7}
        with patch.object(watcher.trash, "waiting", return_value=[row]), \
             patch.object(watcher.killer, "_live", side_effect=RuntimeError()), \
             patch.object(watcher.trash, "close") as close, \
             patch.object(watcher.database, "log"):
            self.assertEqual(watcher.run_watch()["errors"], 1)
            close.assert_not_called()

    def test_purger_dryrun_keeps_waiting(self):
        from datetime import timedelta
        row = {**IP, "no": 7, "snapshot": IP, "due_at": now() - timedelta(minutes=1),
               "notified": 1, "status": "WAITING"}

        @contextmanager
        def lock(_):
            yield True

        with patch.object(purger.trash, "waiting", return_value=[row]), \
             patch.object(purger.trash, "purge_lock", side_effect=lock), \
             patch.object(purger.trash, "get", return_value=row), \
             patch.object(purger.killer, "_live", return_value=IP), \
             patch.object(purger.killer, "execute_now", return_value="DRYRUN"), \
             patch.object(purger.safety, "is_dry_run", return_value=True), \
             patch.object(purger.trash, "close") as close:
            self.assertEqual(purger.run_purge()["dryrun"], 1)
            close.assert_not_called()

    def test_purger_guard_failure_holds_without_retrying_api(self):
        from datetime import timedelta
        row = {**IP, "no": 7, "snapshot": IP, "due_at": now() - timedelta(minutes=1),
               "notified": 1, "status": "WAITING"}

        @contextmanager
        def lock(_):
            yield True

        with patch.object(purger.trash, "waiting", return_value=[row]), \
             patch.object(purger.trash, "purge_lock", side_effect=lock), \
             patch.object(purger.trash, "get", return_value=row), \
             patch.object(purger.killer, "_live", return_value=IP), \
             patch.object(purger.killer, "execute_now", side_effect=killer.UnsafeDeletion("보호됨")), \
             patch.object(purger.safety, "is_dry_run", return_value=False), \
             patch.object(purger.trash, "hold", return_value=True) as hold, \
             patch.object(purger.trash, "add_try") as retry, \
             patch.object(purger.notify, "send"):
            self.assertEqual(purger.run_purge()["held"], 1)
            hold.assert_called_once()
            retry.assert_not_called()

    def test_third_api_failure_marks_failed_without_false_purge(self):
        from datetime import timedelta
        row = {**IP, "no": 7, "snapshot": IP, "due_at": now() - timedelta(minutes=1),
               "notified": 1, "status": "WAITING", "tries": 2}

        @contextmanager
        def lock(_):
            yield True

        with patch.object(purger.trash, "waiting", return_value=[row]), \
             patch.object(purger.trash, "purge_lock", side_effect=lock), \
             patch.object(purger.trash, "get", side_effect=[row, {**row, "status": "FAILED", "tries": 3}]), \
             patch.object(purger.killer, "_live", return_value=IP), \
             patch.object(purger.killer, "execute_now", side_effect=RuntimeError("API 실패")), \
             patch.object(purger.safety, "is_dry_run", return_value=False), \
             patch.object(purger.trash, "add_try", return_value=True) as retry, \
             patch.object(purger.trash, "close") as close, \
             patch.object(purger.database, "log"), \
             patch.object(purger.notify, "send") as alert:
            self.assertEqual(purger.run_purge()["errors"], 1)
            retry.assert_called_once_with(7)
            close.assert_not_called()
            alert.assert_called_once()

    def test_notify_slack_failure_preserves_db_alert(self):
        with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://example.invalid/test"}), \
             patch.object(notify.database, "add_alert") as alert, \
             patch.object(notify.database, "log"), \
             patch.object(notify.requests, "post", side_effect=notify.requests.RequestException):
            self.assertFalse(notify.send("test"))
            alert.assert_called_once_with("test", "INFO")

    def test_dryrun_cannot_close_as_purged(self):
        with patch("engine.safety.is_dry_run", return_value=True):
            with self.assertRaises(RuntimeError):
                trash.close(7, "PURGED")


if __name__ == "__main__":
    unittest.main()
