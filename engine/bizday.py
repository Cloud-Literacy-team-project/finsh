"""Calculate trash deadlines and notifications in Korean business days."""

from datetime import date, datetime, timedelta
from math import isfinite

import holidays


_KR_HOLIDAYS = holidays.KR()  # Lazily expands years as dates are queried.


def is_bizday(day):
    """Whether a date or datetime is a Korean business day."""
    if not isinstance(day, (date, datetime)):
        raise TypeError("날짜 또는 시각이 필요합니다")
    return day.weekday() < 5 and day not in _KR_HOLIDAYS


def _business_day_count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("영업일 수는 0 이상의 정수여야 합니다")
    return value


def add_bizdays(start, n):
    """Move forward by ``n`` business days, preserving the time of day."""
    n = _business_day_count(n)
    current = start
    while n:
        current += timedelta(days=1)
        if is_bizday(current):
            n -= 1
    return current


def _parts(period):
    if not isinstance(period, dict):
        raise ValueError("기간 설정은 unit과 value가 필요합니다")
    unit = period.get("unit")
    value = period.get("value")
    if unit == "bizdays":
        return unit, _business_day_count(value)
    if unit not in ("minutes", "hours"):
        raise ValueError(f"모르는 기간 단위: {unit}")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError("기간 값은 0 이상의 유한한 숫자여야 합니다")
    return unit, value


def due_at(start, wait):
    """Return the trash deadline for the configured wait period."""
    unit, value = _parts(wait)
    if unit == "bizdays":
        return add_bizdays(start, value)
    return start + timedelta(**{unit: value})


def notify_at(due, before):
    """Return the time to notify before the trash deadline."""
    unit, value = _parts(before)
    if unit != "bizdays":
        return due - timedelta(**{unit: value})

    current = due
    while value:
        current -= timedelta(days=1)
        if is_bizday(current):
            value -= 1
    return current
