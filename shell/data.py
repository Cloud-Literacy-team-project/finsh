import json
import os
from dotenv import load_dotenv

load_dotenv()

_FAKE_CACHE = None

def _fake():
    return os.environ.get("FINSH_SOURCE", "fake") == "fake"

def get_leaks():
    """자원 목록 로드 (가짜 모드 시 메모리 캐시로 실행 중 변경 사항 유지)"""
    global _FAKE_CACHE
    if _fake():
        if _FAKE_CACHE is None:
            with open("samples/fake_leaks.json", encoding="utf-8") as f:
                _FAKE_CACHE = json.load(f)
        return _FAKE_CACHE
    from db import database
    return database.get_leaks()

def get_resource(rid):
    """자원 단건 조회 (ID Prefix 매칭)"""
    if _fake():
        found = [r for r in get_leaks() if r["id"].startswith(rid)]
        return found[0] if len(found) == 1 else None
    from db import database
    return database.get_resource(rid)

def get_summary():
    """top 아래 요약 (가짜 모드에서는 없음)"""
    if _fake():
        return None
    from db import database
    return database.get_summary()