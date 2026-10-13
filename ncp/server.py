from ncp.api import call
from ncp.paging import ensure_complete, page_total, response_items

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
        items = response_items(response, "serverInstanceList", "서버")
        expected_total = page_total(response, items, expected_total, len(result), "서버")
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
        if not items or len(result) >= expected_total:
            break
        page_no += 1
    ensure_complete(result, expected_total, "서버")
    return result
