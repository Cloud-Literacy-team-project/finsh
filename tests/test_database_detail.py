"""상세 조회가 실제 보호 상태를 화면 데이터에 포함하는지 확인한다."""

import unittest
from unittest.mock import MagicMock, patch

from db import database


class ResourceDetailTests(unittest.TestCase):
    def test_active_protection_is_included_in_resource_detail(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [{"ncp_no": "201", "id": "ip-201",
                                          "type": "publicip", "name": "finsh-test-ip",
                                          "detail": "{}", "terraform": 0}]
        cursor.fetchone.return_value = {"reason": "시연 중"}

        with patch.object(database, "connect", return_value=connection):
            resource = database.get_resource("ip-201")

        self.assertTrue(resource["protected"])
        self.assertEqual(resource["protected_memo"], "시연 중")
        self.assertIn("until IS NULL OR until >", cursor.execute.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
