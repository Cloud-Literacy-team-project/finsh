"""Development allowlist for actions that can stop or remove NCP resources.

Call ``check`` immediately before an action, then separately enforce the
resource's protection, state, user permission, confirmation and dry-run rules.
"""

import os

from engine.config import settings


def is_dry_run():
    """Only the exact value ``0`` opts into real actions."""
    return os.environ.get("FINSH_DRY_RUN") != "0"


def check(resource, cfg=None):
    """Return ``(allowed, reason)`` for the development resource allowlist."""
    if cfg is None:
        cfg = settings

    if not isinstance(resource, dict) or not isinstance(cfg, dict):
        return False, "자원 또는 안전 설정을 확인할 수 없습니다"

    name = resource.get("name")
    name = name if isinstance(name, str) else ""
    raw_no = resource.get("ncp_no")
    ncp_no = str(raw_no).strip() if raw_no is not None else ""

    never_touch = cfg.get("never_touch")
    if not isinstance(never_touch, (list, tuple, set)):
        never_touch = ()
    if name and name in never_touch:
        return False, f"{name}은(는) 보호 대상이라 건드릴 수 없습니다"
    if resource.get("terraform"):
        return False, "Terraform으로 만든 자원입니다. Terraform 코드에서 변경하세요"
    if not ncp_no:
        return False, "자원 번호가 없어 실행 대상을 확인할 수 없습니다"

    prefix = cfg.get("allowed_name_prefix")
    if isinstance(prefix, str) and prefix and name.startswith(prefix):
        return True, "이름 허용"

    allowed_nos = cfg.get("allowed_ncp_no")
    if not isinstance(allowed_nos, (list, tuple, set)):
        allowed_nos = ()
    if ncp_no and ncp_no in {str(no).strip() for no in allowed_nos if no is not None}:
        return True, "번호 허용"

    return False, "개발 중 허용된 테스트 이름 또는 자원 번호가 아닙니다"
