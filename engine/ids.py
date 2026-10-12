"""NCP 자원 번호에서 스캔 사이에 변하지 않는 짧은 ID를 만든다."""

import hashlib


PREFIX = {"server": "srv", "publicip": "ip", "blockstorage": "blk"}


def make_id(resource):
    kind = resource["type"]
    raw_number = resource.get("ncp_no")
    number = str(raw_number).strip() if raw_number is not None else ""
    if kind not in PREFIX or not number:
        raise ValueError(f"알 수 없는 자원 종류 또는 번호: {kind!r}, {number!r}")
    digest = hashlib.sha256(f"{kind}:{number}".encode("utf-8")).hexdigest()[:4]
    return f"{PREFIX[kind]}-{digest}"


def assign_ids(resources):
    """ID 충돌이 나면 잘못된 자원을 선택하지 않도록 스캔을 중단한다."""
    seen = {}
    for resource in resources:
        rid = make_id(resource)
        identity = (resource["type"], str(resource["ncp_no"]))
        if rid in seen and seen[rid] != identity:
            raise ValueError(f"짧은 ID 충돌: {rid}. ID 길이를 늘려야 합니다")
        seen[rid] = identity
        resource["id"] = rid
    return resources


def add_ids(resources):
    """팀 공통 이름. 기존 assign_ids 호출과 같은 안전한 ID 생성기를 사용한다."""
    return assign_ids(resources)
