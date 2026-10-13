"""finsh DB 함수 모음. 다른 파일은 SQL을 직접 쓰지 말고 이 함수만 부른다."""
import json
import os
from datetime import datetime
from decimal import Decimal

import pymysql
from dotenv import load_dotenv

from engine.config import now

load_dotenv()

COLUMNS = ["ncp_no", "id", "type", "name", "state", "grade", "reason", "idle_days", "cost_hourly",
           "cost_total", "cost_yesterday", "creator", "created_at", "vpc", "console_path",
           "terraform", "detail", "state_since"]


def connect():
    return pymysql.connect(
        host=os.environ["FINSH_DB_HOST"],
        port=int(os.environ.get("FINSH_DB_PORT", "3306")),
        user=os.environ.get("FINSH_DB_USER", "finsh"),
        password=os.environ["FINSH_DB_PASSWORD"],
        database=os.environ.get("FINSH_DB_NAME", "finsh"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _to_dt(value):
    """'2026-10-09T18:44:45+0900' 같은 문자열도 DATETIME으로."""
    if value is None or isinstance(value, datetime):
        return value
    text = str(value)[:19].replace("T", " ")
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S") if len(text) == 19 else \
        datetime.strptime(text, "%Y-%m-%d %H:%M")


def _to_dict(row):
    """DB 한 줄 → 약속(conventions.md) 모양의 딕셔너리."""
    if row is None:
        return None
    r = {}
    for key in COLUMNS:
        value = row.get(key)
        if isinstance(value, Decimal):
            value = float(value)
        elif isinstance(value, datetime):
            value = value.strftime("%Y-%m-%d %H:%M")
        r[key] = value
    r["detail"] = json.loads(row["detail"]) if row.get("detail") else {}
    r["terraform"] = bool(row.get("terraform"))
    r.pop("state_since", None)
    return r


# ---------- B: run_scan()이 부름 ----------
def get_known():
    """{ncp_no: {"state", "state_since", "last_seen", "type"}} — 지금 상태가 언제부터였는지 이어받기 위해."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT ncp_no, type, state, state_since, last_seen FROM resources")
        return {row["ncp_no"]: row for row in cur.fetchall()}


def save_resources(resources, failed_types=()):
    """스캔 결과 저장. 이번에 안 보인 자원은 gone=1.
    failed_types: 목록 조회가 실패한 종류 → 그 종류는 지우지 않고 UNKNOWN으로 표시 (규약 5번)."""
    t = now()
    with connect() as conn, conn.cursor() as cur:
        for r in resources:
            values = [r.get(k) for k in COLUMNS]
            values[COLUMNS.index("created_at")] = _to_dt(r.get("created_at"))
            values[COLUMNS.index("state_since")] = _to_dt(r.get("state_since"))
            values[COLUMNS.index("terraform")] = int(bool(r.get("terraform")))
            values[COLUMNS.index("detail")] = json.dumps(r.get("detail") or {}, ensure_ascii=False)
            cols = ", ".join(COLUMNS + ["first_seen", "last_seen", "gone"])
            marks = ", ".join(["%s"] * (len(COLUMNS) + 3))
            update = ", ".join(f"{k}=VALUES({k})" for k in COLUMNS if k != "ncp_no")
            cur.execute(
                f"INSERT INTO resources ({cols}) VALUES ({marks}) "
                f"ON DUPLICATE KEY UPDATE {update}, last_seen=VALUES(last_seen), gone=0",
                values + [t, t, 0],
            )
        for kind in failed_types:
            cur.execute("UPDATE resources SET grade='UNKNOWN', reason='목록 조회 실패' WHERE type=%s AND gone=0",
                        (kind,))
        seen = [r["ncp_no"] for r in resources]
        keep_types = list(failed_types) or ["-"]
        type_marks = ", ".join(["%s"] * len(keep_types))
        if seen:
            marks = ", ".join(["%s"] * len(seen))
            cur.execute(f"UPDATE resources SET gone=1 WHERE ncp_no NOT IN ({marks}) AND type NOT IN ({type_marks})",
                        seen + keep_types)
        else:
            cur.execute(f"UPDATE resources SET gone=1 WHERE type NOT IN ({type_marks})", keep_types)


# ---------- A: 셸이 부름 ----------
LEAK_SQL = """
SELECT r.* FROM resources r
WHERE r.gone = 0 AND r.grade IN ('ORPHAN', 'ZOMBIE', 'IDLE')
  AND r.terraform = 0
  AND r.ncp_no NOT IN (SELECT ncp_no FROM protections WHERE until IS NULL OR until > %s)
  AND r.ncp_no NOT IN (
      SELECT ncp_no FROM trash
      WHERE status IN ('WAITING', 'HELD', 'DELETE_REQUESTED')
         OR (status = 'FAILED' AND delete_requested_at IS NOT NULL)
  )
ORDER BY r.cost_total DESC
"""


def get_leaks():
    """top에 보일 목록: 정리 후보(ORPHAN·ZOMBIE·IDLE) + 보호 안 됨 + 휴지통에 없음."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(LEAK_SQL, (now(),))
        return [_to_dict(row) for row in cur.fetchall()]


def get_resource(rid):
    """짧은 ID 앞부분으로 자원 하나 찾기 (보호·휴지통 자원도 찾음). 0개나 2개 이상이면 None."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM resources WHERE gone = 0 AND id LIKE %s", (rid + "%",))
        rows = cur.fetchall()
        if len(rows) != 1:
            return None
        resource = _to_dict(rows[0])
        cur.execute("SELECT reason FROM protections WHERE ncp_no=%s AND (until IS NULL OR until > %s)",
                    (resource["ncp_no"], now()))
        protection = cur.fetchone()
        resource["protected"] = protection is not None
        resource["protected_memo"] = protection["reason"] if protection else None
        return resource


def get_summary():
    """top 아래 요약: 관찰 중(WAITING), 판정 불가(UNKNOWN)와 이유, 마지막 검사 시각."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT grade, reason, COUNT(*) AS n FROM resources WHERE gone = 0 "
                    "AND grade IN ('WAITING', 'UNKNOWN') GROUP BY grade, reason")
        rows = cur.fetchall()
        cur.execute("SELECT MAX(at) AS at FROM events WHERE action = 'scan'")
        last = cur.fetchone()["at"]
    waiting = sum(r["n"] for r in rows if r["grade"] == "WAITING")
    unknown = [(r["reason"], r["n"]) for r in rows if r["grade"] == "UNKNOWN"]
    return {"waiting": waiting, "unknown": unknown, "last_scan": last}


# ---------- 모두: 기록과 알림 ----------
def log(action, resource=None, result="OK", message=None):
    r = resource or {}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO events (at, action, ncp_no, id, name, result, message) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (now(), action, r.get("ncp_no"), r.get("id"), r.get("name"), result, message),
        )


def get_events(limit=20):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM events ORDER BY no DESC LIMIT %s", (limit,))
        return cur.fetchall()


def add_alert(message, level="INFO"):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO alerts (at, level, message) VALUES (%s,%s,%s)", (now(), level, message))


def pop_alerts():
    """안 읽은 알림을 돌려주고 읽음 처리."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM alerts WHERE seen = 0 ORDER BY no")
        rows = cur.fetchall()
        if rows:
            cur.execute("UPDATE alerts SET seen = 1 WHERE no <= %s", (rows[-1]["no"],))
        return rows
