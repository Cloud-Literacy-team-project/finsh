"""NCP VPC 블록 스토리지 목록을 finsh 자원 형식으로 변환한다."""

from ncp.api import call


PAGE_SIZE = 1000
BYTES_PER_GIB = 1024 ** 3


def list_all():
    """기본 디스크를 포함한 블록 스토리지 전체를 반환한다."""
    result = []
    page_no = 1

    while True:
        data = call(
            "/vserver/v2/getBlockStorageInstanceList",
            {"regionCode": "KR", "pageNo": page_no, "pageSize": PAGE_SIZE},
        )
        response = data["getBlockStorageInstanceListResponse"]
        if str(response.get("returnCode")) != "0":
            raise RuntimeError(response.get("returnMessage", "블록 스토리지 목록 조회 실패"))

        items = response.get("blockStorageInstanceList") or []
        for item in items:
            code = (item.get("blockStorageInstanceStatus") or {}).get("code")
            operation = (item.get("blockStorageInstanceOperation") or {}).get("code")
            attached_server = item.get("serverName") or item.get("serverInstanceNo") or None
            storage_type = (item.get("blockStorageType") or {}).get("code")
            size_bytes = item.get("blockStorageSize")

            if code == "CREAT" and not attached_server and operation in (None, "NULL"):
                state = "DETACHED"
            elif code == "ATTAC":
                state = "ATTACHED"
            else:
                state = operation if operation not in (None, "NULL") else code or "UNKNOWN"

            result.append({
                "ncp_no": str(item["blockStorageInstanceNo"]),
                "type": "blockstorage",
                "name": item["blockStorageName"],
                "state": state,
                "created_at": item.get("createDate"),
                "console_path": "Server > Storage",
                "detail": {
                    "size_gb": size_bytes / BYTES_PER_GIB if size_bytes is not None else None,
                    "attached_server": attached_server,
                    "storage_type": storage_type,
                },
            })

        total_rows = int(response.get("totalRows") or 0)
        if not items or len(items) < PAGE_SIZE or (total_rows and len(result) >= total_rows):
            break
        page_no += 1

    return result
