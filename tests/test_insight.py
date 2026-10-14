import unittest
import json
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ncp import insight


MIN = 60_000


class InsightStatsTests(unittest.TestCase):
    def test_full_data(self):
        points = [[i * MIN, 0.5] for i in range(1, 11)]
        stats = insight.stats_from_points(points, 0, 10 * MIN, MIN)
        self.assertEqual((stats["cpu_avg"], stats["cpu_coverage"], stats["cpu_max_missing"]),
                         (0.5, 1.0, 0))
        self.assertEqual((stats["cpu_sample_count"], stats["cpu_expected_count"]), (10, 10))
        self.assertEqual(stats["cpu_interval_minutes"], 1)
        self.assertEqual(stats["cpu_last_at"], stats["cpu_window_end"])

    def test_three_missing_measurements(self):
        points = [[i * MIN, 1.0] for i in (1, 2, 6, 7, 8, 9, 10)]
        stats = insight.stats_from_points(points, 0, 10 * MIN, MIN)
        self.assertEqual((stats["cpu_coverage"], stats["cpu_max_missing"]), (0.7, 3))

    def test_no_data_does_not_mean_zero_cpu(self):
        stats = insight.stats_from_points([], 0, 10 * MIN, MIN)
        self.assertEqual((stats["cpu_avg"], stats["cpu_coverage"], stats["cpu_max_missing"]),
                         (None, 0.0, 10))
        self.assertEqual((stats["cpu_sample_count"], stats["cpu_expected_count"], stats["cpu_last_at"]),
                         (0, 10, None))

    def test_duplicates_and_out_of_range_points_do_not_increase_coverage(self):
        points = [[-MIN, 9], [0, 9], [MIN, 2], [MIN, 2], [2 * MIN, None], [11 * MIN, 9]]
        stats = insight.stats_from_points(points, 0, 10 * MIN, MIN)
        self.assertEqual((stats["cpu_avg"], stats["cpu_coverage"], stats["cpu_max_missing"]),
                         (2.0, 0.1, 9))
        self.assertEqual(stats["cpu_sample_count"], 1)

    def test_interval_by_period(self):
        self.assertEqual([insight.pick_interval(d) for d in (0.007, 0.5, 7)], ["Min1", "Min5", "Min30"])

    def test_cpu_query_uses_vpc_schema_and_post_body(self):
        insight._CW_KEY = None
        with patch.object(insight, "call", side_effect=[[{"prodName": "Server(VPC)", "cw_key": "test-key"}], [[120_000, 2.5]]]) as api:
            with patch.object(insight.time, "time", return_value=120):
                result = insight.cpu_stats("123", days=MIN / 86_400_000)
        self.assertEqual(result["cpu_avg"], 2.5)
        self.assertEqual(api.call_count, 2)
        query = api.call_args_list[1]
        self.assertEqual(query.kwargs["method"], "POST")
        self.assertEqual(query.kwargs["body"]["dimensions"], {"instanceNo": "123"})
        self.assertEqual(query.kwargs["body"]["metric"], "avg_cpu_used_rto")
        insight._CW_KEY = None

    def test_cpu_query_uses_scan_time_and_serializable_evidence(self):
        end_at = datetime(2026, 10, 13, 12, 0)
        end_ms = int(end_at.replace(tzinfo=ZoneInfo("Asia/Seoul")).timestamp() * 1000)
        insight._CW_KEY = "test-key"
        with patch.object(insight, "call", return_value=[[end_ms, 2.5]]) as api:
            stats = insight.cpu_stats("123", days=MIN / 86_400_000, end_at=end_at)
        self.assertEqual(api.call_args.kwargs["body"]["timeEnd"], end_ms)
        self.assertEqual(stats["cpu_sample_count"], 1)
        self.assertEqual(stats["cpu_last_at"], stats["cpu_window_end"])
        json.dumps(stats)
        insight._CW_KEY = None

    def test_many_omits_failed_server(self):
        with patch.object(insight, "cpu_stats", side_effect=[{"cpu_avg": 1.0}, RuntimeError("failed")]):
            with self.assertLogs(level="WARNING"):
                result = insight.cpu_stats_many(["good", "bad"])
        self.assertEqual(result, {"good": {"cpu_avg": 1.0}})

    def test_cpu_avg_many_keeps_missing_data_unknown(self):
        stats = {
            "running": {"cpu_avg": 0.5},
            "no_data": {"cpu_avg": None},
        }
        with patch.object(insight, "cpu_stats_many", return_value=stats) as query:
            result = insight.cpu_avg_many(["running", "no_data", "failed"], days=1)
        self.assertEqual(result, {"running": 0.5, "no_data": None})
        query.assert_called_once_with(["running", "no_data", "failed"], 1)


if __name__ == "__main__":
    unittest.main()
