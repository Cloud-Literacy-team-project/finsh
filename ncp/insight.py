"""Read NCP Cloud Insight CPU metrics and report measurement coverage."""

import logging
import math
import time

from ncp.api import INSIGHT, call


_CW_KEY = None
INTERVAL_MS = {"Min1": 60_000, "Min5": 300_000, "Min30": 1_800_000}
_SCHEMA_PATH = "/cw_fea/real/cw/api/schema/system/list"
_DATA_PATH = "/cw_fea/real/cw/api/data/query"


def server_cw_key():
    """Find and cache the schema key for VPC servers."""
    global _CW_KEY
    if _CW_KEY is None:
        products = call(_SCHEMA_PATH, base=INSIGHT)
        for product in products:
            if product.get("prodName") == "Server(VPC)":
                _CW_KEY = product["cw_key"]
                break
        else:
            raise RuntimeError("Cloud Insight Server(VPC) 상품 키를 찾지 못했습니다")
    return _CW_KEY


def pick_interval(days):
    """Use one minute for demos, five for a day, or thirty for longer spans."""
    if isinstance(days, bool) or not isinstance(days, (int, float)) or not math.isfinite(days) or days <= 0:
        raise ValueError("조회 기간은 0보다 큰 일 수여야 합니다")
    if days <= 1 / 24:
        return "Min1"
    if days <= 1:
        return "Min5"
    return "Min30"


def stats_from_points(points, start_ms, end_ms, interval_ms):
    """Summarize [timestamp_ms, cpu_percent] points on the expected time grid.

    Buckets are strictly after ``start_ms`` and at or before ``end_ms``.
    Missing or invalid values never count as zero-percent CPU usage.
    """
    if interval_ms <= 0 or end_ms <= start_ms:
        raise ValueError("올바른 조회 구간과 측정 간격이 필요합니다")

    first = (start_ms // interval_ms + 1) * interval_ms
    last = (end_ms // interval_ms) * interval_ms
    expected = max((last - first) // interval_ms + 1, 0)
    by_bucket = {}
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        stamp, raw_value = point
        try:
            stamp = int(stamp)
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError, OverflowError):
            continue
        if value is None or not math.isfinite(value):
            continue
        if first <= stamp <= last and stamp % interval_ms == 0:
            by_bucket[stamp] = value

    if not expected:
        return {"cpu_avg": None, "cpu_coverage": 0.0, "cpu_max_missing": 0}

    seen = sorted((stamp - first) // interval_ms for stamp in by_bucket)
    previous = -1
    max_missing = 0
    for index in seen + [expected]:
        max_missing = max(max_missing, index - previous - 1)
        previous = index

    avg = round(sum(by_bucket.values()) / len(by_bucket), 2) if by_bucket else None
    return {
        "cpu_avg": avg,
        "cpu_coverage": round(len(by_bucket) / expected, 4),
        "cpu_max_missing": max_missing,
    }


def cpu_stats(server_no, days=7):
    """Read one server's CPU measurements for the past ``days`` days."""
    interval = pick_interval(days)
    if server_no is None or not str(server_no).strip():
        raise ValueError("서버 번호가 필요합니다")

    end = int(time.time() * 1000)
    start = end - int(days * 86_400_000)
    body = {
        "timeStart": start,
        "timeEnd": end,
        "cw_key": server_cw_key(),
        "productName": "System/Server(VPC)",
        "metric": "avg_cpu_used_rto",
        "interval": interval,
        "aggregation": "AVG",
        "dimensions": {"instanceNo": str(server_no).strip()},
    }
    points = call(_DATA_PATH, method="POST", base=INSIGHT, body=body)
    if not isinstance(points, list):
        raise RuntimeError("Cloud Insight CPU 응답 형식이 올바르지 않습니다")
    return stats_from_points(points, start, end, INTERVAL_MS[interval])


def cpu_avg(server_no, days=7):
    """Convenience wrapper for consumers that need only the average."""
    return cpu_stats(server_no, days)["cpu_avg"]


def cpu_stats_many(server_nos, days=7):
    """Return successful server stats; omitted servers must be UNKNOWN."""
    result = {}
    for server_no in server_nos:
        try:
            result[str(server_no)] = cpu_stats(server_no, days)
        except Exception as exc:
            # The exception message may contain an API response; log its type only.
            logging.warning("Cloud Insight CPU 조회 실패 (%s): %s", server_no, type(exc).__name__)
    return result
