"""Deletion planning and final live safety checks.

The live path handles one detached IP, detached extra disk, or stopped server.
It never detaches or cascades into a second resource.
"""

import os
import time
from datetime import timedelta

from db import database
from engine import bizday, price, safety, trash
from engine.config import now, settings
from ncp import blockstorage, publicip, server
from ncp.api import call


LISTERS = {"server": server.list_all, "publicip": publicip.list_all,
           "blockstorage": blockstorage.list_all}
DELETE = {
    "server": ("/vserver/v2/terminateServerInstances", "serverInstanceNoList.1", "terminateServerInstancesResponse"),
    "publicip": ("/vserver/v2/deletePublicIpInstance", "publicIpInstanceNo", "deletePublicIpInstanceResponse"),
    "blockstorage": ("/vserver/v2/deleteBlockStorageInstances", "blockStorageInstanceNoList.1", "deleteBlockStorageInstancesResponse"),
}


class UnsafeDeletion(Exception):
    """A guard failed. Retrying the API is inappropriate."""


def _stored(ncp_no):
    with database.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM resources WHERE ncp_no=%s AND gone=0", (str(ncp_no),))
        return cur.fetchone()


def _protected(ncp_no):
    with database.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 AS protected FROM protections WHERE ncp_no=%s AND (until IS NULL OR until>%s)",
                    (str(ncp_no), now()))
        return bool(cur.fetchone())


def _terraform_nos():
    # A missing or broken D adapter is an unknown safety state, not an empty set.
    from engine import iac
    fn = getattr(iac, "terraform_nos", None)
    if not callable(fn):
        raise UnsafeDeletion("Terraform 보호 목록을 확인할 수 없습니다")
    try:
        nos = fn()
    except Exception as exc:
        raise UnsafeDeletion("Terraform 보호 목록 조회 실패") from exc
    if nos is None:
        raise UnsafeDeletion("Terraform 보호 목록이 없습니다")
    return {str(value) for value in nos}


def _guard(resource, stored, terraform_nos):
    if not stored:
        raise UnsafeDeletion("DB에서 현재 자원을 확인할 수 없습니다")
    if str(resource.get("ncp_no")) != str(stored["ncp_no"]) or resource.get("type") != stored["type"]:
        raise UnsafeDeletion("자원 번호 또는 종류가 변경되었습니다")
    if str(resource["ncp_no"]) in terraform_nos or stored.get("terraform"):
        raise UnsafeDeletion("Terraform 관리 자원입니다")
    resource["terraform"] = False
    allowed, reason = safety.check(resource)
    if not allowed:
        raise UnsafeDeletion(reason)
    if _protected(resource["ncp_no"]):
        raise UnsafeDeletion("chattr 보호 중입니다")
    if stored.get("grade") not in {"ORPHAN", "ZOMBIE", "IDLE"}:
        raise UnsafeDeletion("현재 DB 판정이 정리 후보가 아닙니다")
    if stored.get("state") != resource.get("state"):
        raise UnsafeDeletion("DB 이후 자원 상태가 바뀌었습니다")
    last_seen = stored.get("last_seen")
    max_gap = timedelta(minutes=float(settings.get("observe_max_gap_minutes", 90)))
    if last_seen is None or now() - last_seen > max_gap or last_seen > now():
        raise UnsafeDeletion("스캔 결과가 오래되었거나 시각이 잘못되었습니다")
    kind, state = resource["type"], resource["state"]
    detail = resource.get("detail") or {}
    if kind == "publicip":
        if state != "DETACHED" or detail.get("attached_server") or stored["grade"] != "ORPHAN":
            raise UnsafeDeletion("공인 IP가 미할당 상태가 아닙니다")
    elif kind == "blockstorage":
        if (state != "DETACHED" or detail.get("attached_server") or
                detail.get("storage_type") != "SVRBS" or stored["grade"] != "ORPHAN"):
            raise UnsafeDeletion("분리된 추가 스토리지가 아닙니다")
    elif kind == "server":
        if state != "STOPPED" or stored["grade"] != "ZOMBIE":
            raise UnsafeDeletion("정지된 ZOMBIE 서버만 자동 반납할 수 있습니다")
        if detail.get("public_ip"):
            raise UnsafeDeletion("서버에 공인 IP가 연결돼 있어 별도 확인이 필요합니다")
        if detail.get("termination_protected") is not False:
            raise UnsafeDeletion("서버 반납 보호 여부를 확인할 수 없거나 보호 중입니다")
        if any(str((ip.get("detail") or {}).get("attached_server")) in
               {str(resource["ncp_no"]), resource.get("name")}
               for ip in publicip.list_all()):
            raise UnsafeDeletion("서버에 공인 IP가 연결돼 있습니다")
        if any((disk.get("detail") or {}).get("storage_type") != "BASIC" and
               str((disk.get("detail") or {}).get("attached_server")) in
               {str(resource["ncp_no"]), resource.get("name")}
               for disk in blockstorage.list_all()):
            raise UnsafeDeletion("서버에 추가 스토리지가 연결돼 있습니다")
        since = stored.get("state_since")
        if since is None or now() - since < timedelta(days=float(settings["zombie_days"])):
            raise UnsafeDeletion("연속 정지 관측 기간이 부족합니다")
    else:
        raise UnsafeDeletion("지원하지 않는 자원 종류입니다")


def _live(kind, ncp_no):
    if kind not in LISTERS:
        raise UnsafeDeletion("지원하지 않는 자원 종류입니다")
    items = LISTERS[kind]()  # A successful complete list is needed to infer absence.
    matches = [item for item in items if str(item.get("ncp_no")) == str(ncp_no)]
    if len(matches) > 1:
        raise UnsafeDeletion("동일 번호의 자원이 중복 조회되었습니다")
    return matches[0] if matches else None


def _identity_matches(resource, snapshot):
    if not snapshot:
        return True
    if str(snapshot.get("ncp_no")) != str(resource.get("ncp_no")) or snapshot.get("type") != resource.get("type"):
        return False
    if snapshot.get("name") != resource.get("name"):
        return False
    if resource["type"] == "publicip":
        return (snapshot.get("detail") or {}).get("ip") == (resource.get("detail") or {}).get("ip")
    return True


def prepare(resource):
    """Return (confirmation plan, None) or (None, reason). No cloud mutation."""
    try:
        live = _live(resource.get("type"), resource.get("ncp_no"))
        if not live or not _identity_matches(live, resource):
            raise UnsafeDeletion("현재 자원 신원을 확인할 수 없습니다")
        _guard(live, _stored(live["ncp_no"]), _terraform_nos())
        if trash.active(live["ncp_no"]):
            raise UnsafeDeletion("이미 휴지통에 있습니다")
        at = now()
        due = bizday.due_at(at, settings["trash_wait"])
        return {"resource": resource, "due_at": due,
                "estimated_cost": price.trash_cost(resource, due, now=at)}, None
    except UnsafeDeletion as exc:
        return None, str(exc)
    except Exception:
        return None, "현재 자원 또는 안전 정보를 확인하지 못했습니다"


def execute_now(resource, *, expected=None, confirmed=False, absence_checks=5, poll_seconds=2,
                action="purge"):
    """Re-read, re-guard, request one deletion, then confirm disappearance.

    Returns DRYRUN or PURGED. An API acknowledgement alone is never PURGED.
    """
    if not confirmed:
        raise UnsafeDeletion("사용자 확인이 필요합니다")
    if action not in {"purge", "kill-9"}:
        raise ValueError("허용되지 않은 삭제 동작입니다")
    kind, ncp_no = resource.get("type"), resource.get("ncp_no")
    current = _live(kind, ncp_no)
    if current is None:
        raise UnsafeDeletion("대상이 이미 보이지 않습니다. 자동 삭제를 중단합니다")
    if not _identity_matches(current, expected or resource):
        raise UnsafeDeletion("휴지통에 넣은 자원과 현재 자원 신원이 다릅니다")
    _guard(current, _stored(ncp_no), _terraform_nos())
    if safety.is_dry_run():
        database.log(action, current, "DRYRUN", "삭제 조건 확인; NCP 변경 요청은 보내지 않음")
        return "DRYRUN"
    approved = {number.strip() for number in os.environ.get("FINSH_REAPER_APPROVED_NCP_NOS", "").split(",")}
    if str(ncp_no) not in approved:
        raise UnsafeDeletion("실제 삭제 대상으로 승인된 자원 번호가 아닙니다")
    path, param, key = DELETE[kind]
    result = call(path, {"regionCode": "KR", param: str(ncp_no)}, account="REAPER")
    payload = result.get(key) if isinstance(result, dict) else None
    if not isinstance(payload, dict) or str(payload.get("returnCode")) != "0":
        raise RuntimeError("NCP 삭제 요청이 실패했습니다")
    for attempt in range(absence_checks):
        if attempt:
            time.sleep(poll_seconds)
        if _live(kind, ncp_no) is None:
            database.log(action, current, "OK", "NCP 목록에서 삭제 완료 확인")
            return "PURGED"
    raise RuntimeError("삭제 요청 후 자원 소멸을 확인하지 못했습니다")


def kill_now(resource, *, confirmed=False):
    return execute_now(resource, confirmed=confirmed, action="kill-9")
