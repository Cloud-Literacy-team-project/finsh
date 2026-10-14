"""공식 단가의 계산 단위를 확인한다."""

import unittest

from engine import price


PRICES = {
    "server_hourly": {"RUNNING": {"s2-g3a": 100}},
    "publicip_hourly": 5,
    "blockstorage_hourly_per_10gb": {"CB1": 2, "FB1": 1},
}


class PriceTests(unittest.TestCase):
    def test_running_server_rate(self):
        row = {"type": "server", "state": "RUNNING", "detail": {"spec": "s2-g3a"}}
        self.assertEqual(price.hourly(row, PRICES), 100)

    def test_stopped_server_uses_its_own_basic_disk(self):
        row = {"type": "server", "state": "STOPPED",
               "detail": {"spec": "s2-g3a", "base_disk_gb": 50, "base_disk_type": "CB1"}}
        self.assertEqual(price.hourly(row, PRICES), 10)
        self.assertIsNone(price.hourly({"type": "server", "state": "STOPPED", "detail": {}}, PRICES))

    def test_ip_and_extra_storage_total(self):
        ip = {"type": "publicip", "state": "DETACHED", "detail": {}}
        disk = {"type": "blockstorage", "state": "DETACHED",
                "detail": {"disk_type": "FB1", "size_gb": 10}}
        self.assertEqual(price.total(ip, 24, PRICES), 120)
        self.assertEqual(price.total(disk, 10, PRICES), 10)
        self.assertIsNone(price.hourly({"type": "blockstorage", "detail": {"size_gb": 10}}, PRICES))


if __name__ == "__main__":
    unittest.main()
