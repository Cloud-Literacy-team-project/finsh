"""config/settings.yaml 을 한 번만 읽어서 돌려준다.  사용: from engine.config import settings"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name="settings.yaml"):
    with open(ROOT / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


settings = load()


def now():
    """한국 시간 (Bastion 서버 시계가 UTC여도 항상 KST). DB에는 이 값만 넣는다."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None, microsecond=0)