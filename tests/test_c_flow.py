"""C deletion flow: every cloud-changing path is mocked."""

import unittest
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from engine import iac, killer, notify, purger, trash, watcher
from engine.config import now
from ncp import server


IP = {"ncp_no": "1", "id": "ip-1", "type": "publicip", "name": "finsh-test-ip",
      "state": "DETACHED", "grade": "ORPHAN", "detail": {"ip": "192.0.2.1", "attached_server": None}}
SERVER = {"ncp_no": "2", "id": "srv-2", "type": "server", "name": "finsh-test-server",
          "state": "STOPPED", "grade": "ZOMBIE",
          "detail": {"public_ip": None, "termination_protected": False}}


class CFlowTests(unittest.TestCase):
    def test_server_request_is_tracked_before_api_and_not_retried_after_ack(self):
        stored = {**SERVER, "last_seen": now(), "state_since": now() - timedelta(days=8), "terraform": 0}
        order = []

        def reserve():
            order.append("reserved")
            return True

        def delete_api(*_, **__):
            order.append("api")
            return {"terminateServerInstancesResponse": {"returnCode": "0"}}

        with patch.dict("os.environ", {"FINSH_REAPER_APPROVED_NCP_NOS": "2"}), \
             patch.object(killer, "_live", return_value=SERVER), \
             patch.object(killer, "_stored", return_value=stored), \
             patch.object(killer, "_terraform_nos", return_value=set()), \
             patch.object(killer, "_protected", return_value=False), \
             patch.object(killer.publicip, "list_all", return_value=[]), \
             patch.object(killer.blockstorage, "list_all", return_value=[]), \
             patch.object(killer.safety, "is_dry_run", return_value=False), \
             patch.object(killer.database, "log"), \
             patch.object(killer.time, "sleep"), \
             patch.object(killer, "call", side_effect=delete_api) as api:
            self.assertEqual(killer.execute_now(SERVER, confirmed=True,
                                                on_before_request=reserve), "DELETE_REQUESTED")
        self.assertEqual(order, ["reserved", "api"])
        api.assert_called_once()

    def test_server_live_delete_requires_durable_request_state(self):
        stored = {**SERVER, "last_seen": now(), "state_since": now() - timedelta(days=8), "terraform": 0}
        with patch.dict("os.environ", {"FINSH_REAPER_APPROVED_NCP_NOS": "2"}), \
             patch.object(killer, "_live", return_value=SERVER), \
             patch.object(killer, "_stored", return_value=stored), \
             patch.object(killer, "_terraform_nos", return_value=set()), \
             patch.object(killer, "_protected", return_value=False), \
             patch.object(killer.publicip, "list_all", return_value=[]), \
             patch.object(killer.blockstorage, "list_all", return_value=[]), \
             patch.object(killer.safety, "is_dry_run", return_value=False), \
             patch.object(killer, "call") as api:
            with self.assertRaisesRegex(killer.UnsafeDeletion, "삭제 요청 상태"):
                killer.execute_now(SERVER, confirmed=True)
        api.assert_not_called()

    def test_immediate_server_delete_is_recorded_before_execution(self):
        order = []

        @contextmanager
        def lock(_):
            yield True

        def reserve(_):
            order.append("reserved")
            return 8

        def execute(*_, **kwargs):
            self.assertTrue(kwargs["on_before_request"]())
            order.append("executed")
            return "DELETE_REQUESTED"

        with patch.dict("os.environ", {"FINSH_REAPER_APPROVED_NCP_NOS": "2"}), \
             patch.object(killer.safety, "is_dry_run", return_value=False), \
             patch.object(killer.trash, "start_immediate", side_effect=reserve), \
             patch.object(killer.trash, "purge_lock", side_effect=lock), \
             patch.object(killer, "execute_now", side_effect=execute), \
             patch.object(killer.trash, "close") as close:
            self.assertEqual(killer.kill_now(SERVER, confirmed=True), "DELETE_REQUESTED")
        self.assertEqual(order, ["reserved", "executed"])
        close.assert_not_called()

    def test_immediate_server_preflight_failure_cancels_unsent_reservation(self):
        @contextmanager
        def lock(_):
            yield True

        with patch.dict("os.environ", {"FINSH_REAPER_APPROVED_NCP_NOS": "2"}), \
             patch.object(killer.safety, "is_dry_run", return_value=False), \
             patch.object(killer.trash, "start_immediate", return_value=8), \
             patch.object(killer.trash, "purge_lock", side_effect=lock), \
             patch.object(killer, "execute_now", side_effect=killer.UnsafeDeletion("보호됨")), \
             patch.object(killer.trash, "cancel_unsubmitted", return_value=True) as cancel:
            with self.assertRaises(killer.UnsafeDeletion):
                killer.kill_now(SERVER, confirmed=True)
        cancel.assert_called_once_with(8, "삭제 요청 전 안전 검사 실패: 보호됨", locked=True)

    def test_purger_confirms_existing_request_without_new_api_call(self):
        row = {**SERVER, "no": 8, "snapshot": SERVER, "status": "DELETE_REQUESTED",
               "delete_requested_at": now() - timedelta(minutes=5)}

        @contextmanager
        def lock(_):
            yield True

        with patch.object(purger.trash, "pending_deletions", return_value=[row]), \
             patch.object(purger.trash, "waiting", return_value=[]), \
             patch.object(purger.trash, "purge_lock", side_effect=lock), \
             patch.object(purger.trash, "get", return_value=row), \
             patch.object(purger.killer, "_live", side_effect=[SERVER, None]), \
             patch.object(purger.killer, "execute_now") as api, \
             patch.object(purger.trash, "close", return_value=True) as close, \
             patch.object(purger.notify, "send"):
            self.assertEqual(purger.run_purge()["requested"], 1)
            self.assertEqual(purger.run_purge()["purged"], 1)
        api.assert_not_called()
        close.assert_called_once_with(8, "PURGED", locked=True, after_requested=True)

    def test_purger_reserves_server_request_before_delete(self):
        row = {**SERVER, "no": 8, "snapshot": SERVER, "status": "WAITING",
               "due_at": now() - timedelta(minutes=1), "notified": 1}

        @contextmanager
        def lock(_):
            yield True

        def execute(*_, **kwargs):
            self.assertTrue(kwargs["on_before_request"]())
            return "DELETE_REQUESTED"

        with patch.object(purger.trash, "pending_deletions", return_value=[]), \
             patch.object(purger.trash, "waiting", return_value=[row]), \
             patch.object(purger.trash, "purge_lock", side_effect=lock), \
             patch.object(purger.trash, "get", return_value=row), \
             patch.object(purger.killer, "_live", return_value=SERVER), \
             patch.object(purger.safety, "is_dry_run", return_value=False), \
             patch.object(purger.trash, "mark_delete_requested", return_value=True) as reserve, \
             patch.object(purger.killer, "execute_now", side_effect=execute), \
             patch.object(purger.trash, "close") as close:
            self.assertEqual(purger.run_purge()["requested"], 1)
        reserve.assert_called_once_with(8)
        close.assert_not_called()

    def test_request_timeout_needs_manual_review_without_retry(self):
        row = {**SERVER, "no": 8, "snapshot": SERVER, "status": "DELETE_REQUESTED",
               "delete_requested_at": now() - timedelta(hours=2)}

        @contextmanager
        def lock(_):
            yield True

        with patch.object(purger.trash, "pending_deletions", return_value=[row]), \
             patch.object(purger.trash, "waiting", return_value=[]), \
             patch.object(purger.trash, "purge_lock", side_effect=lock), \
             patch.object(purger.trash, "get", return_value=row), \
             patch.object(purger.killer, "_live", return_value=SERVER), \
             patch.object(purger.killer, "execute_now") as api, \
             patch.object(purger.trash, "fail_delete_confirmation", return_value=True) as failed, \
             patch.object(purger.notify, "send"):
            self.assertEqual(purger.run_purge()["errors"], 1)
        api.assert_not_called()
        failed.assert_called_once()

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
        with patch.object(iac, "terraform_nos", None):
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

        with patch.object(purger.trash, "pending_deletions", return_value=[]), \
             patch.object(purger.trash, "waiting", return_value=[row]), \
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

        with patch.object(purger.trash, "pending_deletions", return_value=[]), \
             patch.object(purger.trash, "waiting", return_value=[row]), \
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

        with patch.object(purger.trash, "pending_deletions", return_value=[]), \
             patch.object(purger.trash, "waiting", return_value=[row]), \
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

    def test_confirmed_live_request_can_finish_after_dryrun_is_restored(self):
        with patch("engine.safety.is_dry_run", return_value=True), \
             patch.object(trash, "_change", return_value=True) as change:
            self.assertTrue(trash.close(7, "PURGED", locked=True, after_requested=True))
        change.assert_called_once_with(7, ("DELETE_REQUESTED",), "PURGED")


if __name__ == "__main__":
    unittest.main()
