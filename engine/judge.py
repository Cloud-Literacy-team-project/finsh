"""자원 판정. 서버 생성 시각은 정지/실행 관측 기간에 사용하지 않는다.

DB 연결 전에는 next_state_since(resource, old, now)의 반환값을 저장해 두고,
다음 스캔에서 old={state, state_since, last_seen}로 다시 넘긴다.
"""

from datetime import datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from engine.config import settings


CANDIDATES = frozenset({"ORPHAN", "ZOMBIE", "IDLE"})
KNOWN_STATES = {
    "server": {"RUNNING", "STOPPED"},
    "publicip": {"ATTACHED", "DETACHED"},
    "blockstorage": {"ATTACHED", "DETACHED"},
}
KST = ZoneInfo("Asia/Seoul")


def _time(value):
    """DB 문자열과 Insight의 시간대 있는 시각을 KST 시각으로 비교한다."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise TypeError("시각은 datetime 또는 ISO 문자열이어야 합니다")
    return value.astimezone(KST).replace(tzinfo=None) if value.tzinfo else value


def next_state_since(resource, old, now, cfg=None):
    """같은 상태를 연속 관측했으면 기존 시작 시각을, 아니면 이번 시각을 반환한다."""
    cfg = settings if cfg is None else cfg
    now = _time(now)
    if not old or old.get("state") != resource.get("state"):
        return now
    since, last_seen = _time(old.get("state_since")), _time(old.get("last_seen"))
    if since is None or last_seen is None:
        return now
    gap = now - last_seen
    max_gap = timedelta(minutes=float(cfg.get("observe_max_gap_minutes", 90)))
    if gap < timedelta(0) or gap > max_gap or since > last_seen:
        return now
    return since


def _cpu_reason(detail, now, cfg):
    """충분한 CPU 근거이면 (평균, None), 아니면 (None, 이유)."""
    if detail.get("cpu_error"):
        return None, "CPU 조회 실패"

    required = (
        "cpu_avg", "cpu_sample_count", "cpu_expected_count", "cpu_max_missing",
        "cpu_window_start", "cpu_window_end", "cpu_last_at",
    )
    if any(detail.get(key) is None for key in required):
        return None, "CPU 데이터 또는 측정 기간 정보 부족"

    try:
        avg = float(detail["cpu_avg"])
        count = int(detail["cpu_sample_count"])
        expected = int(detail["cpu_expected_count"])
        max_missing = int(detail["cpu_max_missing"])
        start = _time(detail["cpu_window_start"])
        end = _time(detail["cpu_window_end"])
        last = _time(detail["cpu_last_at"])
        interval_minutes = float(detail.get("cpu_interval_minutes") or
                                 (1 if float(cfg["idle_days"]) < 1 else 30))
    except (TypeError, ValueError):
        return None, "CPU 데이터 형식 오류"

    period_start = now - timedelta(days=float(cfg["idle_days"]))
    interval = timedelta(minutes=interval_minutes)
    if interval <= timedelta(0) or start > period_start or end < now - interval:
        return None, "CPU 조회 기간이 부족함"
    if last > now or last < now - interval:
        return None, "최근 CPU 측정값이 없음"
    if expected <= 0 or count < 0 or count > expected or max_missing < 0:
        return None, "CPU 측정값 개수 오류"
    coverage = count / expected
    if coverage < float(cfg.get("cpu_min_coverage", 0.8)) or max_missing > int(cfg.get("cpu_max_missing", 2)):
        return None, f"CPU 데이터 부족 (충족률 {coverage:.0%}, 연속 누락 {max_missing}구간)"
    if not isfinite(avg) or not 0 <= avg <= 100:
        return None, "CPU 평균값 오류"
    return avg, None


def judge(resource, state_since, now, cfg=None):
    """grade, reason, idle_days를 자원에 붙여 반환한다. 판정은 삭제 명령이 아니다."""
    cfg = settings if cfg is None else cfg
    now, state_since = _time(now), _time(state_since)
    kind, state = resource.get("type"), resource.get("state")
    detail = resource.get("detail") or {}
    elapsed = (now - state_since).total_seconds() / 86400 if state_since else None
    resource["idle_days"] = round(elapsed, 2) if elapsed is not None and elapsed >= 0 else None

    def result(grade, reason):
        resource["grade"], resource["reason"] = grade, reason
        return resource

    if state not in KNOWN_STATES.get(kind, set()):
        return result("UNKNOWN", f"작업 중이거나 알 수 없는 상태: {state}")

    if kind == "publicip":
        if state == "DETACHED":
            if detail.get("attached_server"):
                return result("UNKNOWN", "서버 연결 정보와 상태가 일치하지 않음")
            return result("ORPHAN", "서버에 연결되지 않음")
        return result("OK", "서버에 연결됨")

    if kind == "blockstorage":
        if detail.get("storage_type") == "BASIC":
            return result("OK", "서버 기본 디스크")
        if state == "DETACHED":
            if detail.get("attached_server"):
                return result("UNKNOWN", "서버 연결 정보와 상태가 일치하지 않음")
            if not detail.get("storage_type"):
                return result("UNKNOWN", "추가 스토리지 여부를 확인할 수 없음")
            return result("ORPHAN", "서버에서 분리됨")
        return result("OK", "서버에 연결됨")

    if elapsed is None or elapsed < 0:
        return result("UNKNOWN", "연속 상태 관측 시작 시각이 없음")
    if state == "STOPPED":
        if elapsed >= float(cfg["zombie_days"]):
            return result("ZOMBIE", f"정지 관측 {elapsed:.1f}일 (기준 {cfg['zombie_days']}일 이상)")
        return result("WAITING", f"정지 관측 {elapsed:.1f}일 (기준 {cfg['zombie_days']}일)")

    if elapsed < float(cfg["idle_days"]):
        return result("OK", f"실행 관측 {elapsed:.1f}일 (기준 {cfg['idle_days']}일 미만)")
    avg, reason = _cpu_reason(detail, now, cfg)
    if reason:
        return result("UNKNOWN", reason)
    if avg < float(cfg["idle_cpu_percent"]):
        return result("IDLE", f"CPU 평균 {avg:g}% (검토 후보)")
    return result("OK", f"CPU 평균 {avg:g}%")
