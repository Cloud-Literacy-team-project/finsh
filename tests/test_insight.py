import unittest
from unittest.mock import patch

from ncp import insight


MIN = 60_000


class InsightStatsTests(unittest.TestCase):
    def test_full_data(self):
        points = [[i * MIN, 0.5] for i in range(1, 11)]
        self.assertEqual(
            insight.stats_from_points(points, 0, 10 * MIN, MIN),
            {"cpu_avg": 0.5, "cpu_coverage": 1.0, "cpu_max_missing": 0},
        )

    def test_three_missing_measurements(self):
        points = [[i * MIN, 1.0] for i in (1, 2, 6, 7, 8, 9, 10)]
        stats = insight.stats_from_points(points, 0, 10 * MIN, MIN)
        self.assertEqual((stats["cpu_coverage"], stats["cpu_max_missing"]), (0.7, 3))

    def test_no_data_does_not_mean_zero_cpu(self):
        self.assertEqual(
            insight.stats_from_points([], 0, 10 * MIN, MIN),
            {"cpu_avg": None, "cpu_coverage": 0.0, "cpu_max_missing": 10},
        )

    def test_duplicates_and_out_of_range_points_do_not_increase_coverage(self):
        points = [[-MIN, 9], [0, 9], [MIN, 2], [MIN, 2], [2 * MIN, None], [11 * MIN, 9]]
        stats = insight.stats_from_points(points, 0, 10 * MIN, MIN)
        self.assertEqual(stats, {"cpu_avg": 2.0, "cpu_coverage": 0.1, "cpu_max_missing": 9})

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

    def test_many_omits_failed_server(self):
        with patch.object(insight, "cpu_stats", side_effect=[{"cpu_avg": 1.0}, RuntimeError("failed")]):
            with self.assertLogs(level="WARNING"):
                result = insight.cpu_stats_many(["good", "bad"])
        self.assertEqual(result, {"good": {"cpu_avg": 1.0}})


if __name__ == "__main__":
    unittest.main()
