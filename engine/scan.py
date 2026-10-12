"""자원 수집 → 범위 제한 → ID/요금 부여 → 판정/저장."""

import json
from pathlib import Path

import yaml

from engine.ids import assign_ids
from engine.price import hourly, total
from ncp import blockstorage, publicip, server


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.yaml"
LEAK_FILE = PROJECT_ROOT / "leak.json"
LEAK_GRADES = {"ORPHAN", "ZOMBIE", "IDLE"}


def _settings():
    return yaml.safe_load(SETTINGS_FILE.read_text(encoding="utf-8")) or {}


def _in_scope(resource, settings):
    prefix = settings.get("scan_name_prefix", "finsh-")
    if not prefix or resource.get("name", "").startswith(prefix):
        return True

    # ===== [회의 1: 공인 IP 탐지 범위가 정해지면 교체 시작] =====
    # 실제 NCP 응답에서 공인 IP 설명이 비어 있어 이름 접두사만으로는 구분되지 않는다.
    # 지금은 settings.yaml에 명시한 자원 번호만 추가로 포함한다.
    if resource["type"] == "publicip":
        allowed = {str(number) for number in settings.get("scan_publicip_ncp_nos", [])}
        return str(resource["ncp_no"]) in allowed
    # ===== [회의 1: 공인 IP 탐지 범위 교체 끝] =====

    return False


def collect_resources():
    """판정 없이 현재 자원과 확인 가능한 시간당 요금을 모은다."""
    settings = _settings()
    resources = server.list_all() + publicip.list_all() + blockstorage.list_all()
    resources = [resource for resource in resources if _in_scope(resource, settings)]
    assign_ids(resources)
    for resource in resources:
        resource["cost_hourly"] = hourly(resource)
        resource["cost_total"] = None
    return resources


def run_scan(judge_fn=None, save_fn=None, output_path=LEAK_FILE):
    """판정과 DB 함수가 준비되면 전체 스캔을 실행한다.

    judge_fn(resource) -> {"grade": "ORPHAN/ ZOMBIE/ IDLE/ OK", "idle_since": "..."}
    save_fn(resources) -> None
    """
    if judge_fn is None:
        raise NotImplementedError("engine/judge.py 판정 함수가 정해지면 judge_fn을 연결하세요")

    # ===== [팀장 DB 저장 함수가 정해지면 교체 시작] =====
    # 예: from db.database import save_scan
    #     save_fn = save_fn or save_scan
    if save_fn is None:
        raise NotImplementedError("db/database.py 저장 함수가 정해지면 save_fn을 연결하세요")
    # ===== [팀장 DB 저장 함수 교체 끝] =====

    resources = collect_resources()
    for resource in resources:
        verdict = judge_fn(resource)
        if not isinstance(verdict, dict) or verdict.get("grade") not in LEAK_GRADES | {"OK"}:
            raise ValueError(f"판정 결과 형식 오류: {resource['id']}")
        resource.update(verdict)
        resource["cost_total"] = total(resource)

    leaks = [resource for resource in resources if resource["grade"] in LEAK_GRADES]
    save_fn(resources)
    Path(output_path).write_text(
        json.dumps(leaks, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return leaks

