"""공식 단가표를 이용한 예상 요금. 실제 청구액은 Cost Explorer가 담당한다."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


PRICE_FILE = Path(__file__).resolve().parents[1] / "config" / "prices.yaml"
KST = ZoneInfo("Asia/Seoul")


def _prices():
    return yaml.safe_load(PRICE_FILE.read_text(encoding="utf-8")) or {}


def _time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value


def _rounded(amount):
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def hourly(resource):
    """시간당 예상 원화 요금. 단가가 확인되지 않았으면 None."""
    prices = _prices()
    kind = resource["type"]
    if kind == "publicip":
        rate = prices.get("publicip_hourly")
    elif kind == "blockstorage":
        detail = resource.get("detail") or {}
        disk_type = detail.get("disk_type")
        size_gb = detail.get("size_gb")
        unit_rate = prices.get("blockstorage_hourly_per_10gb", {}).get(disk_type)
        if unit_rate is None or size_gb is None:
            return None
        rate = Decimal(str(unit_rate)) * Decimal(str(size_gb)) / Decimal("10")
    elif kind == "server":
        state = resource.get("state")
        spec = (resource.get("detail") or {}).get("spec")
        rate = prices.get("server_hourly", {}).get(state, {}).get(spec)
    else:
        return None
    return float(Decimal(str(rate))) if rate is not None else None


def total(resource, idle_since=None, as_of=None):
    """방치 시작 시각부터 쌓인 예상 요금. 시작 시각은 판정 함수가 제공한다."""
    rate = hourly(resource)
    idle_since = idle_since or resource.get("idle_since")
    if rate is None or idle_since is None:
        return None
    start = _time(idle_since)
    end = _time(as_of or datetime.now(timezone.utc))
    hours = max(Decimal("0"), Decimal(str((end - start).total_seconds())) / Decimal("3600"))
    return _rounded(Decimal(str(rate)) * hours)


def trash_cost(resource, delete_at, now=None):
    """휴지통에 머무는 동안의 예상 요금. delete_at은 C의 영업일 계산 결과다."""
    rate = hourly(resource)
    if rate is None:
        return None
    start = _time(now or datetime.now(timezone.utc))
    end = _time(delete_at)
    hours = max(Decimal("0"), Decimal(str((end - start).total_seconds())) / Decimal("3600"))
    return _rounded(Decimal(str(rate)) * hours)
