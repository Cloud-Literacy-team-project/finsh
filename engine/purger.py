"""Send expiry notices and safely purge due trash entries."""

from datetime import timedelta

from db import database
from engine import bizday, killer, notify, safety, trash
from engine.config import now, settings


def _confirm_requested(row, counts):
    """이미 시작한 서버 삭제는 재요청하지 않고 목록에서 사라졌는지만 확인한다."""
    live = killer._live(row["type"], row["ncp_no"])
    if live is None:
        if trash.close(row["no"], "PURGED", locked=True, after_requested=True):
            counts["purged"] += 1
            notify.send(f"{row['id']} 삭제 완료")
        return

    requested_at = row.get("delete_requested_at")
    reason = None
    if not killer._identity_matches(live, row.get("snapshot") or {}):
        reason = "삭제 요청 후 자원 신원 변경; 수동 확인 필요"
    elif live["state"] == "RUNNING":
        reason = "삭제 요청 후 서버 실행 관측; 수동 확인 필요"
    elif requested_at is None or now() - requested_at >= timedelta(
            minutes=float(settings.get("delete_confirmation_minutes", 60))):
        reason = "삭제 요청 후 완료 확인 시간 초과; 수동 확인 필요"

    if reason:
        if trash.fail_delete_confirmation(row["no"], reason, locked=True):
            counts["errors"] += 1
            notify.send(f"{row['id']} {reason}", "WARN")
    else:
        counts["requested"] += 1


def run_purge():
    counts = {"checked": 0, "notified": 0, "purged": 0, "held": 0,
              "gone": 0, "dryrun": 0, "requested": 0, "errors": 0}
    for item in trash.pending_deletions():
        counts["checked"] += 1
        with trash.purge_lock(item["no"]) as acquired:
            if not acquired:
                continue
            row = trash.get(item["no"])
            if not row or row["status"] != "DELETE_REQUESTED":
                continue
            try:
                _confirm_requested(row, counts)
            except Exception:
                counts["errors"] += 1
                database.log("purge", row, "FAIL", "삭제 요청 완료 확인 실패; 삭제 API 재호출 안 함")
    for item in trash.waiting():
        counts["checked"] += 1
        with trash.purge_lock(item["no"]) as acquired:
            if not acquired:
                continue
            row = trash.get(item["no"])
            if not row or row["status"] != "WAITING":
                continue
            try:
                current_time = now()
                if not isinstance(row.get("snapshot"), dict) or not row["snapshot"].get("ncp_no"):
                    raise killer.UnsafeDeletion("휴지통 스냅샷이 없어 안전하게 삭제할 수 없습니다")
                if not row["notified"] and current_time >= bizday.notify_at(row["due_at"], settings["notify_before"]):
                    try:
                        notify.send(f"{row['id']} 삭제 예정: {row['due_at']}", "WARN")
                    except Exception:
                        counts["errors"] += 1
                        database.log("notify", row, "FAIL", "삭제 사전 알림 저장 실패")
                        continue
                    if trash.mark_notified(row["no"]):
                        counts["notified"] += 1
                if current_time < row["due_at"]:
                    continue
                live = killer._live(row["type"], row["ncp_no"])
                if live is None:
                    if trash.close(row["no"], "GONE", locked=True):
                        counts["gone"] += 1
                    continue
                if not killer._identity_matches(live, row.get("snapshot") or {}):
                    raise killer.UnsafeDeletion("휴지통 스냅샷과 현재 자원이 다릅니다")
                if safety.is_dry_run():
                    # execute_now performs all the same live checks before returning DRYRUN.
                    result = killer.execute_now(live, expected=row["snapshot"], confirmed=True)
                    if result == "DRYRUN":
                        counts["dryrun"] += 1
                    continue
                on_before_request = (lambda: trash.mark_delete_requested(row["no"])) if row["type"] == "server" else None
                result = killer.execute_now(live, expected=row["snapshot"], confirmed=True,
                                            on_before_request=on_before_request)
                if result == "PURGED" and trash.close(row["no"], "PURGED", locked=True,
                                                       after_requested=row["type"] == "server"):
                    counts["purged"] += 1
                    try:
                        notify.send(f"{row['id']} 삭제 완료")
                    except Exception:
                        database.log("notify", row, "FAIL", "삭제 완료 알림 저장 실패")
                elif result == "DELETE_REQUESTED":
                    counts["requested"] += 1
            except killer.UnsafeDeletion as exc:
                if trash.hold(row["no"], str(exc), locked=True):
                    counts["held"] += 1
                    notify.send(f"{row['id']} 삭제 보류: {exc}", "WARN")
            except Exception:
                counts["errors"] += 1
                if row["type"] == "server":
                    updated = trash.get(row["no"])
                    if updated and updated["status"] == "DELETE_REQUESTED":
                        database.log("purge", row, "FAIL", "삭제 요청 결과 불명; 완료만 재확인하고 API는 재호출하지 않음")
                        counts["requested"] += 1
                        continue
                database.log("purge", row, "FAIL", "삭제 또는 확인 실패; 재시도 예정")
                if trash.add_try(row["no"]):
                    updated = trash.get(row["no"])
                    if updated and updated["status"] == "FAILED":
                        notify.send(f"{row['id']} 삭제 3회 실패; 수동 확인 필요", "WARN")
    return counts
