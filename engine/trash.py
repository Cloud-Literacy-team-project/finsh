"""Conditional, auditable trash state transitions."""

import json
from contextlib import contextmanager

from db import database
from engine.config import now


ACTIVE = ("WAITING", "HELD")
TERMINAL = ("RESTORED", "PURGED", "FAILED", "GONE")


def _row(row):
    if row and isinstance(row.get("snapshot"), str):
        row["snapshot"] = json.loads(row["snapshot"])
    return row


def active(ncp_no):
    with database.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM trash WHERE ncp_no=%s AND status IN ('WAITING','HELD') ORDER BY no DESC LIMIT 1", (str(ncp_no),))
        return _row(cur.fetchone())


def list_all():
    with database.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM trash ORDER BY no DESC")
        return [_row(row) for row in cur.fetchall()]


def waiting():
    with database.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM trash WHERE status='WAITING' ORDER BY due_at, no")
        return [_row(row) for row in cur.fetchall()]


def get(no):
    with database.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM trash WHERE no=%s", (no,))
        return _row(cur.fetchone())


def put(resource, due, at=None):
    """Serialize creation on the parent resource row to prevent duplicate active trash."""
    at = at or now()
    snapshot = {key: resource.get(key) for key in ("ncp_no", "id", "type", "name", "state", "grade")}
    snapshot["detail"] = {key: (resource.get("detail") or {}).get(key)
                          for key in ("ip", "attached_server", "storage_type", "public_ip")}
    with database.connect() as conn:
        conn.begin()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT ncp_no FROM resources WHERE ncp_no=%s AND gone=0 FOR UPDATE", (str(resource["ncp_no"]),))
                if not cur.fetchone():
                    raise ValueError("현재 DB에서 자원을 찾을 수 없습니다")
                cur.execute("SELECT no FROM trash WHERE ncp_no=%s AND status IN ('WAITING','HELD') LIMIT 1 FOR UPDATE", (str(resource["ncp_no"]),))
                if cur.fetchone():
                    raise ValueError("이미 휴지통에 있습니다")
                cur.execute("INSERT INTO trash (ncp_no,id,name,type,put_at,due_at,status,snapshot) "
                            "VALUES (%s,%s,%s,%s,%s,%s,'WAITING',%s)",
                            (str(resource["ncp_no"]), resource["id"], resource.get("name") or "",
                             resource["type"], at, due, json.dumps(snapshot, ensure_ascii=False, default=str)))
                no = cur.lastrowid
                cur.execute("INSERT INTO events (at,action,ncp_no,id,name,result,message) "
                            "VALUES (%s,'kill',%s,%s,%s,'OK',%s)",
                            (now(), str(resource["ncp_no"]), resource["id"], resource.get("name") or "",
                             f"휴지통 번호 {no}; 삭제 예정 {due}"))
            conn.commit()
            return no
        except Exception:
            conn.rollback()
            raise


def _change(no, from_status, to_status, reason=None):
    with database.connect() as conn:
        conn.begin()
        try:
            with conn.cursor() as cur:
                marks = ",".join(["%s"] * len(from_status))
                cur.execute(f"UPDATE trash SET status=%s, hold_reason=%s WHERE no=%s AND status IN ({marks})",
                            (to_status, reason, no, *from_status))
                changed = cur.rowcount == 1
                if changed:
                    cur.execute("SELECT ncp_no,id,name FROM trash WHERE no=%s", (no,))
                    row = cur.fetchone()
                    action = {"RESTORED": "restore", "HELD": "hold", "PURGED": "purge",
                              "FAILED": "purge", "GONE": "watch"}[to_status]
                    cur.execute("INSERT INTO events (at,action,ncp_no,id,name,result,message) "
                                "VALUES (%s,%s,%s,%s,%s,'OK',%s)",
                                (now(), action, row["ncp_no"], row["id"], row["name"], reason or to_status))
            conn.commit()
            return changed
        except Exception:
            conn.rollback()
            raise


def restore(identifier):
    """Restore a unique active row by trash number or short resource ID prefix."""
    with database.connect() as conn, conn.cursor() as cur:
        if isinstance(identifier, int) or str(identifier).isdigit():
            cur.execute("SELECT no FROM trash WHERE no=%s AND status IN ('WAITING','HELD')", (int(identifier),))
        else:
            cur.execute("SELECT no FROM trash WHERE id LIKE %s AND status IN ('WAITING','HELD')", (str(identifier) + "%",))
        rows = cur.fetchall()
    if len(rows) != 1:
        raise ValueError("복원할 항목이 없거나 ID가 여러 항목과 일치합니다")
    no = rows[0]["no"]
    with purge_lock(no) as acquired:
        changed = _change(no, ACTIVE, "RESTORED") if acquired else False
    return changed


def hold(no, reason, *, locked=False):
    if locked:
        return _change(no, ("WAITING",), "HELD", reason[:255])
    with purge_lock(no) as acquired:
        return _change(no, ("WAITING",), "HELD", reason[:255]) if acquired else False


def set_status(no, status, reason=None):
    if status == "HELD":
        return hold(no, reason or "안전 확인 필요")
    if status not in TERMINAL:
        raise ValueError("허용되지 않은 휴지통 상태")
    if status == "PURGED":
        raise ValueError("PURGED는 삭제 확인 후 close()로만 기록합니다")
    source = ACTIVE if status == "RESTORED" else ("WAITING",)
    with purge_lock(no) as acquired:
        return _change(no, source, status, reason) if acquired else False


def close(no, status, *, locked=False):
    if status not in {"PURGED", "GONE"}:
        raise ValueError("삭제 완료 또는 외부 소멸만 닫을 수 있습니다")
    if status == "PURGED":
        from engine.safety import is_dry_run
        if is_dry_run():
            raise RuntimeError("연습 모드에서 PURGED를 기록할 수 없습니다")
    if locked:
        return _change(no, ("WAITING",), status)
    with purge_lock(no) as acquired:
        return _change(no, ("WAITING",), status) if acquired else False


def mark_notified(no):
    with database.connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE trash SET notified=1 WHERE no=%s AND status='WAITING' AND notified=0", (no,))
        return cur.rowcount == 1


def add_try(no, max_tries=3):
    with database.connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE trash SET tries=tries+1, status=IF(tries+1 >= %s,'FAILED','WAITING') "
                    "WHERE no=%s AND status='WAITING'", (max_tries, no))
        return cur.rowcount == 1


@contextmanager
def purge_lock(no):
    """Cross-process MySQL advisory lock; held during the final check/API call."""
    conn = database.connect()
    name = f"finsh:purge:{no}"
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT GET_LOCK(%s, 0) AS acquired", (name,))
            acquired = cur.fetchone()["acquired"] == 1
        try:
            yield acquired
        finally:
            if acquired:
                with conn.cursor() as cur:
                    cur.execute("SELECT RELEASE_LOCK(%s)", (name,))
    finally:
        conn.close()
