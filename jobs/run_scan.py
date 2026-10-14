"""cron 실행 진입점: cd /opt/finsh && .venv/bin/python -m jobs.run_scan"""

from engine.config import now
from engine.scan import run_scan
from db import database


def main():
    print(f"[{now()}] scan 시작", flush=True)
    total, detected = run_scan()
    visible = len(database.get_leaks())
    print(f"[{now()}] scan 끝: {total}개, 탐지 후보 {detected}개, top 표시 {visible}개", flush=True)


if __name__ == "__main__":
    main()
