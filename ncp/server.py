from ncp.api import call

STATUS = {
    "RUN": "RUNNING",
    "NSTOP": "STOPPED",
}
PAGE_SIZE = 1000


def list_all():
    result = []
    page_no = 1
    expected_total = None
    while True:
        data = call("/vserver/v2/getServerInstanceList",
                    {"regionCode": "KR", "pageNo": page_no, "pageSize": PAGE_SIZE})
        response = data["getServerInstanceListResponse"]
        if str(response.get("returnCode")) != "0":
            raise RuntimeError(response.get("returnMessage", "서버 목록 조회 실패"))
        items = response.get("serverInstanceList") or []
        if response.get("totalRows") is None:
            raise RuntimeError("서버 목록 총건수를 확인할 수 없습니다")
        total = int(response["totalRows"])
        if expected_total is None:
            expected_total = total
        if total != expected_total or (total == 0 and items):
            raise RuntimeError("서버 목록이 조회 중 변경되었습니다")
        if not items and total > len(result):
            raise RuntimeError("서버 목록이 일부만 조회되었습니다")
        for server in items:
            code = (server.get("serverInstanceStatus") or {}).get("code")

            result.append({
                "ncp_no": str(server["serverInstanceNo"]),
                "type": "server",
                "name": server["serverName"],
                "state": STATUS.get(code, code or "UNKNOWN"),
                "created_at": server.get("createDate"),
                "console_path": "Server > Server",
                "detail": {
                    "spec": server.get("serverSpecCode") or server.get("serverProductCode"),
                    "cpu_avg": None,
                    "public_ip": server.get("publicIp") or None,
                    "termination_protected": server.get("isProtectServerTermination"),
                },
            })
        if not items or len(result) >= total:
            break
        page_no += 1
    if len(result) != expected_total or len({item["ncp_no"] for item in result}) != len(result):
        raise RuntimeError("서버 전체 목록을 완전하게 확인하지 못했습니다")
    return result
