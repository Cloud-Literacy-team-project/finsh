"""NCP VPC 공인 IP 목록을 finsh 자원 형식으로 변환한다."""

from ncp.api import call
from ncp.paging import ensure_complete, page_total, response_items


PAGE_SIZE = 1000


def list_all():
    """공인 IP 전체를 반환한다. 할당 여부는 IP 자체의 RUN 상태와 별개다."""
    result = []
    page_no = 1
    expected_total = None

    while True:
        data = call(
            "/vserver/v2/getPublicIpInstanceList",
            {"regionCode": "KR", "pageNo": page_no, "pageSize": PAGE_SIZE},
        )
        response = data["getPublicIpInstanceListResponse"]
        items = response_items(response, "publicIpInstanceList", "공인 IP")
        for item in items:
            code = (item.get("publicIpInstanceStatus") or {}).get("code")
            operation = (item.get("publicIpInstanceOperation") or {}).get("code")
            attached_server = (
                item.get("serverName") or item.get("serverInstanceNo") or item.get("privateIp") or None
            )

            # RUN은 IP 자원의 운영 상태다. 서버 연결 여부는 별도로 확인한다.
            if code == "RUN" and operation in (None, "NULL"):
                state = "ATTACHED" if attached_server else "DETACHED"
            else:
                state = operation if operation not in (None, "NULL") else code or "UNKNOWN"

            result.append({
                "ncp_no": str(item["publicIpInstanceNo"]),
                "type": "publicip",
                "name": item.get("publicIpDescription") or item.get("publicIp") or "",
                "state": state,
                "created_at": item.get("createDate"),
                "console_path": "Server > Public IP",
                "detail": {
                    "ip": item.get("publicIp"),
                    "attached_server": attached_server,
                },
            })

        expected_total = page_total(response, items, expected_total, len(result), "공인 IP")
        if not items or (expected_total and len(result) >= expected_total):
            break
        page_no += 1

    ensure_complete(result, expected_total, "공인 IP")
    return result
