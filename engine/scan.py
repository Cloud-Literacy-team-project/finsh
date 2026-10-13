"""NCP 목록 → 범위 → ID → 관측/CPU → 판정/요금 → DB → 후보 파일."""

import json
import os
from pathlib import Path

from db import database
from engine import price
from engine.config import now, settings
from engine.ids import add_ids
from engine.judge import CANDIDATES, judge, next_state_since
from ncp import blockstorage, publicip, server


ROOT = Path(__file__).resolve().parents[1]
LISTERS = {"server": server.list_all, "publicip": publicip.list_all, "blockstorage": blockstorage.list_all}


def in_scope(resource, cfg=None):
    """이름 접두사 또는 명시적으로 허용한 공인 IP 번호만 스캔한다."""
    cfg = settings if cfg is None else cfg
    prefix = cfg.get("scan_name_prefix") or ""
    if not prefix or str(resource.get("name") or "").startswith(prefix):
        return True
    allowed = {str(number) for number in (cfg.get("allowed_ncp_no") or [])}
    return resource.get("type") == "publicip" and str(resource.get("ncp_no")) in allowed


def collect():
    """세 목록이 모두 성공해야 반환한다. 감시/삭제 전 재확인에도 사용한다."""
    rows = server.list_all() + publicip.list_all() + blockstorage.list_all()
    return add_ids([row for row in rows if in_scope(row)])


def collect_resources():
    """이전 호출부를 위한 collect 별칭."""
    return collect()


def collect_safe():
    """스캔용: 실패한 종류는 DB가 UNKNOWN으로 바꾸도록 실패 목록도 반환한다."""
    rows, failed = [], []
    for kind, list_all in LISTERS.items():
        try:
            rows.extend(list_all())
        except Exception as exc:
            print(f"[scan] {kind} 목록 조회 실패: {exc}")
            failed.append(kind)
    return add_ids([row for row in rows if in_scope(row)]), failed


def _attach_basic_disks(rows):
    """정지 서버 요금에 필요한 실제 기본 디스크 종류/용량을 연결한다."""
    servers = {}
    for row in rows:
        if row["type"] == "server":
            servers[str(row["ncp_no"])] = row
            servers[str(row["name"])] = row
    for disk in rows:
        if disk["type"] != "blockstorage":
            continue
        detail = disk.get("detail") or {}
        if detail.get("storage_type") != "BASIC":
            continue
        owner = servers.get(str(detail.get("attached_server")))
        if owner:
            owner_detail = owner.setdefault("detail", {})
            owner_detail["base_disk_gb"] = detail.get("size_gb")
            owner_detail["base_disk_type"] = detail.get("disk_type")


def _cpu(server_nos, cpu_reader=None):
    if not server_nos:
        return {}
    try:
        if cpu_reader is None:
            from ncp.insight import cpu_stats_many
            cpu_reader = cpu_stats_many
        result = cpu_reader(server_nos, days=settings["idle_days"])
        if not isinstance(result, dict):
            raise TypeError("CPU 조회 결과는 자원 번호별 dict여야 합니다")
        return {str(number): values for number, values in result.items()}
    except Exception as exc:
        print(f"[scan] CPU 조회 실패: {exc}")
        return {}


def _terraform_nos(terraform_reader=None):
    try:
        if terraform_reader is None:
            from engine.iac import terraform_nos
            terraform_reader = terraform_nos
        return {str(number) for number in terraform_reader()}
    except Exception as exc:
        print(f"[scan] Terraform 기록 읽기 실패: {exc}")
        return None  # 미확인은 비보호(False)가 아니다.


def log_dir():
    """Bastion에서는 /var/log/finsh, 로컬에서는 프로젝트 logs."""
    configured = os.environ.get("FINSH_LOG_DIR")
    bastion = Path("/var/log/finsh")
    path = Path(configured) if configured else (
        bastion if bastion.is_dir() and os.access(bastion, os.W_OK) else ROOT / "logs"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _require_database(db):
    missing = [name for name in ("get_known", "save_resources", "log")
               if not callable(getattr(db, name, None))]
    if missing:
        raise RuntimeError("DB 연결 함수가 아직 없습니다: " + ", ".join(missing))


def run_scan(db=None, cpu_reader=None, terraform_reader=None, output_path=None, at=None):
    """모든 판정을 저장하고 후보만 leak.json에 쓴다. (전체 수, 후보 수) 반환."""
    db = database if db is None else db
    _require_database(db)
    t = now() if at is None else at
    known = db.get_known() or {}
    if not isinstance(known, dict):
        raise TypeError("get_known()은 NCP 번호를 키로 하는 dict를 반환해야 합니다")
    known = {str(number): old for number, old in known.items()}

    rows, failed = collect_safe()
    _attach_basic_disks(rows)
    for row in rows:
        row["state_since"] = next_state_since(row, known.get(str(row["ncp_no"])), t)
        row["last_seen"] = t

    need_cpu = [row["ncp_no"] for row in rows if row["type"] == "server" and row["state"] == "RUNNING"
                and (t - row["state_since"]).total_seconds() >= float(settings["idle_days"]) * 86400]
    cpu = _cpu(need_cpu, cpu_reader)
    terraform_nos = _terraform_nos(terraform_reader)

    for row in rows:
        metrics = cpu.get(str(row["ncp_no"]))
        if isinstance(metrics, dict):
            row.setdefault("detail", {}).update(metrics)
        judge(row, row["state_since"], t)
        if terraform_nos is None and row["grade"] in CANDIDATES:
            # The DB schema stores terraform as a boolean. Keep an unverified
            # candidate out of top until the IaC inventory can be read.
            row["grade"] = "UNKNOWN"
            row["reason"] = "Terraform 보호 목록 확인 실패"
        row["cost_hourly"] = price.hourly(row)
        hours = max(0, (t - row["state_since"]).total_seconds() / 3600)
        row["cost_total"] = price.total(row, hours)
        row["cost_yesterday"] = None
        row["creator"] = None
        row["vpc"] = None
        row["terraform"] = None if terraform_nos is None else str(row["ncp_no"]) in terraform_nos

    # DB 계약: save_resources는 모든 rows를 갱신하고 failed 종류의 기존 자원은
    # 삭제하지 않은 채 UNKNOWN(목록 조회 실패)으로 표시해야 한다.
    db.save_resources(rows, failed)
    if terraform_nos:
        try:
            from engine.protect import sync_terraform
            sync_terraform(terraform_nos)
        except Exception as exc:
            print(f"[scan] Terraform 보호 동기화 실패: {exc}")

    leaks = [row for row in rows if row["grade"] in CANDIDATES]
    out = [{key: value for key, value in row.items() if key not in ("state_since", "last_seen")}
           for row in leaks]
    target = Path(output_path) if output_path is not None else log_dir() / "leak.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str) + "\n",
                         encoding="utf-8")
    temporary.replace(target)

    grades = ("ORPHAN", "ZOMBIE", "IDLE", "WAITING", "UNKNOWN")
    message = " · ".join(f"{grade} {sum(row['grade'] == grade for row in rows)}" for grade in grades)
    if failed:
        message += " · 조회 실패: " + ", ".join(failed)
    if terraform_nos is None:
        message += " · Terraform 보호 목록 확인 실패"
    db.log("scan", result="FAIL" if failed or terraform_nos is None else "OK", message=message)
    return len(rows), len(leaks)
