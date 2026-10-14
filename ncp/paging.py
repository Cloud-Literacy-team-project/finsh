"""NCP 목록 API의 페이지 완전성 검사."""


def response_items(response, key, label):
    if str(response.get("returnCode")) != "0":
        raise RuntimeError(response.get("returnMessage", f"{label} 목록 조회 실패"))
    return response.get(key) or []


def page_total(response, items, expected_total, seen, label):
    if response.get("totalRows") is None:
        raise RuntimeError(f"{label} 목록 총건수를 확인할 수 없습니다")
    total = int(response["totalRows"])
    if expected_total is None:
        expected_total = total
    if total != expected_total or (total == 0 and items):
        raise RuntimeError(f"{label} 목록이 조회 중 변경되었습니다")
    if not items and total > seen:
        raise RuntimeError(f"{label} 목록이 일부만 조회되었습니다")
    return expected_total


def ensure_complete(result, expected_total, label):
    if len(result) != expected_total or len({item["ncp_no"] for item in result}) != len(result):
        raise RuntimeError(f"{label} 전체 목록을 완전하게 확인하지 못했습니다")
