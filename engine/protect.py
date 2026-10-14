"""User protection expires; Terraform protection is permanent and cannot be removed by chattr."""
import math
from datetime import timedelta

from db.database import connect
from engine.config import now, settings


def _number(resource):
    value = resource.get("ncp_no")
    if value is None or not str(value):
        raise ValueError("자원 번호가 없습니다")
    return str(value)


def get(ncp_no):
    """Return the stored row, including an expired user protection."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM protections WHERE ncp_no=%s", (str(ncp_no),))
        return cur.fetchone()


def is_protected(ncp_no):
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM protections WHERE ncp_no=%s AND (until IS NULL OR until > %s)",
                    (str(ncp_no), now()))
        return cur.fetchone() is not None


def add(resource, reason, days=None):
    if resource.get("terraform"):
        return False, "이미 Terraform으로 영구 보호 중입니다"
    try:
        number = _number(resource)
        duration = float(settings["protect_days"] if days is None else days)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError
        t = now()
        until = t + timedelta(days=duration)
    except (ValueError, TypeError, OverflowError):
        return False, "자원 번호 또는 보호 기간이 올바르지 않습니다"
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 255:
        return False, "보호 이유는 1~255자로 입력하세요"
    with connect() as conn, conn.cursor() as cur:
        conn.begin()
        try:
            # The conditional upsert also handles a simultaneous Terraform sync.
            cur.execute(
                "INSERT INTO protections (ncp_no,reason,source,until,created_at) "
                "VALUES (%s,%s,'user',%s,%s) ON DUPLICATE KEY UPDATE "
                "reason=IF(source='terraform',reason,VALUES(reason)), "
                "until=IF(source='terraform',until,VALUES(until)), "
                "created_at=IF(source='terraform',created_at,VALUES(created_at))",
                (number, reason.strip(), until, t),
            )
            cur.execute("SELECT source FROM protections WHERE ncp_no=%s", (number,))
            row = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    if row["source"] == "terraform":
        return False, "이미 Terraform으로 영구 보호 중입니다"
    return True, f"{until:%m/%d %H:%M}까지 보호합니다"


def remove(resource):
    number = _number(resource)
    if resource.get("terraform"):
        return False, "Terraform으로 만든 자원은 보호를 풀 수 없습니다"
    with connect() as conn, conn.cursor() as cur:
        # Never delete a Terraform row, even if a scan changed it concurrently.
        cur.execute("DELETE FROM protections WHERE ncp_no=%s AND source='user'", (number,))
        if cur.rowcount:
            return True, "보호를 풀었습니다"
        cur.execute("SELECT source FROM protections WHERE ncp_no=%s", (number,))
        row = cur.fetchone()
    if row and row["source"] == "terraform":
        return False, "Terraform으로 만든 자원은 보호를 풀 수 없습니다"
    return False, "보호된 자원이 아닙니다"


def list_all():
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT p.*,r.id,r.name,r.type FROM protections p "
            "LEFT JOIN resources r ON r.ncp_no=p.ncp_no "
            "WHERE p.until IS NULL OR p.until>%s ORDER BY p.source,p.created_at", (now(),))
        return cur.fetchall()


def sync_terraform(nos):
    """Use a successfully read full inventory; None must never mean an empty state."""
    if nos is None or isinstance(nos, (str, bytes)):
        raise ValueError("확인된 Terraform 번호 집합이 필요합니다")
    numbers = sorted({str(number) for number in nos})
    if any(not number.isascii() or not number.isdigit() for number in numbers):
        raise ValueError("Terraform 자원 번호 형식이 올바르지 않습니다")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK('finsh:terraform-protection',10) AS acquired")
        if cur.fetchone()["acquired"] != 1:
            raise RuntimeError("Terraform 보호 동기화가 이미 실행 중입니다")
        try:
            conn.begin()
            t = now()
            for number in numbers:
                cur.execute(
                    "INSERT INTO protections (ncp_no,reason,source,until,created_at) "
                    "VALUES (%s,'Terraform 관리 자원','terraform',NULL,%s) "
                    "ON DUPLICATE KEY UPDATE source='terraform',until=NULL,reason='Terraform 관리 자원'",
                    (number, t),
                )
            if numbers:
                marks = ','.join(['%s'] * len(numbers))
                cur.execute(f"DELETE FROM protections WHERE source='terraform' AND ncp_no NOT IN ({marks})",
                            numbers)
            else:
                cur.execute("DELETE FROM protections WHERE source='terraform'")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.execute("SELECT RELEASE_LOCK('finsh:terraform-protection')")
