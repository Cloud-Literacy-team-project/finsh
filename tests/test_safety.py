import os
import unittest
from unittest.mock import patch

from engine import safety


CFG = {
    "allowed_name_prefix": "finsh-test-",
    "allowed_ncp_no": ["111"],
    "never_touch": ["finsh-db"],
}


class SafetyTests(unittest.TestCase):
    def test_test_resource_name_is_allowed(self):
        self.assertTrue(safety.check({"name": "finsh-test-c-srv1", "ncp_no": "9"}, CFG)[0])

    def test_unnamed_ip_number_is_allowed(self):
        self.assertTrue(safety.check({"name": "211.1.1.1", "ncp_no": 111}, CFG)[0])

    def test_unlisted_resource_is_blocked(self):
        self.assertFalse(safety.check({"name": "lab-web", "ncp_no": "222"}, CFG)[0])

    def test_never_touch_takes_priority_over_number(self):
        self.assertFalse(safety.check({"name": "finsh-db", "ncp_no": "111"}, CFG)[0])

    def test_terraform_takes_priority_over_test_name(self):
        self.assertFalse(safety.check({"name": "finsh-test-tf-web", "terraform": True}, CFG)[0])

    def test_missing_number_cannot_match_allowlist(self):
        cfg = {**CFG, "allowed_ncp_no": [None, "None"]}
        self.assertFalse(safety.check({"name": "211.1.1.1", "ncp_no": None}, cfg)[0])

    def test_test_name_without_number_is_still_blocked(self):
        self.assertFalse(safety.check({"name": "finsh-test-c-srv1"}, CFG)[0])

    def test_empty_configuration_fails_closed(self):
        self.assertFalse(safety.check({"name": "finsh-test-c-srv1"}, {})[0])

    def test_dry_run_is_the_default_and_only_zero_disables_it(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(safety.is_dry_run())
            os.environ["FINSH_DRY_RUN"] = "1"
            self.assertTrue(safety.is_dry_run())
            os.environ["FINSH_DRY_RUN"] = " 0 "
            self.assertTrue(safety.is_dry_run())
            os.environ["FINSH_DRY_RUN"] = "0"
            self.assertFalse(safety.is_dry_run())


if __name__ == "__main__":
    unittest.main()
