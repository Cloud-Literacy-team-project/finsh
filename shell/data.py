import json
import os

def get_leaks():
    """쓸모없는 자원 목록"""
    if os.environ.get("FINSH_SOURCE", "fake") == "fake":
        with open("samples/fake_leaks.json", encoding="utf-8") as f:
            return json.load(f)
    from db import database
    return database.get_leaks()

def get_resource(rid):
    """자원 하나 (ID 앞부분만 입력해도 하나로 특정되면 찾아줌)"""
    found = [r for r in get_leaks() if r["id"].startswith(rid)]
    return found[0] if len(found) == 1 else None