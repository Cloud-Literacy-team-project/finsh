"""Watch waiting trash entries for renewed use or verified disappearance."""

from db import database
from engine import killer, notify, trash


def run_watch():
    counts = {"checked": 0, "held": 0, "gone": 0, "errors": 0}
    for row in trash.waiting():
        counts["checked"] += 1
        try:
            current = killer._live(row["type"], row["ncp_no"])
            if current is None:
                if trash.close(row["no"], "GONE"):
                    counts["gone"] += 1
                continue
            detail = current.get("detail") or {}
            reused = ((row["type"] == "server" and current["state"] == "RUNNING") or
                      (row["type"] in {"publicip", "blockstorage"} and
                       (current["state"] == "ATTACHED" or bool(detail.get("attached_server")))))
            changed = not killer._identity_matches(current, row.get("snapshot") or {})
            if reused or changed:
                reason = "자원 사용 재개" if reused else "자원 신원 변경"
                if trash.hold(row["no"], reason):
                    counts["held"] += 1
                    notify.send(f"{row['id']} 삭제 보류: {reason}", "WARN")
        except Exception:
            counts["errors"] += 1
            database.log("watch", row, "FAIL", "자원 확인 실패; 휴지통 상태 유지")
    return counts
