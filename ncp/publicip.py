"""NCP VPC 공인 IP 목록을 finsh 자원 형식으로 변환한다."""

from ncp.api import call


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
        if str(response.get("returnCode")) != "0":
            raise RuntimeError(response.get("returnMessage", "공인 IP 목록 조회 실패"))

        items = response.get("publicIpInstanceList") or []
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

        if response.get("totalRows") is None:
            raise RuntimeError("공인 IP 목록 총건수를 확인할 수 없습니다")
        total_rows = int(response["totalRows"])
        if expected_total is None:
            expected_total = total_rows
        if total_rows != expected_total or (total_rows == 0 and items):
            raise RuntimeError("공인 IP 목록이 조회 중 변경되었습니다")
        if not items and total_rows > len(result):
            raise RuntimeError("공인 IP 목록이 일부만 조회되었습니다")
        if not items or (total_rows and len(result) >= total_rows):
            break
        page_no += 1

    if len(result) != expected_total or len({item["ncp_no"] for item in result}) != len(result):
        raise RuntimeError("공인 IP 전체 목록을 완전하게 확인하지 못했습니다")
    return result
