from ncp.api import call

STATUS = {
    "RUN": "RUNNING",
    "NSTOP": "STOPPED",
}


def list_all():
    data = call("/vserver/v2/getServerInstanceList", {"regionCode": "KR"})
    response = data["getServerInstanceListResponse"]

    if str(response.get("returnCode")) != "0":
        raise RuntimeError(response.get("returnMessage", "서버 목록 조회 실패"))

    result = []
    for server in response.get("serverInstanceList") or []:
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
            },
        })

    return result