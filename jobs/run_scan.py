"""cron 실행 진입점: cd /opt/finsh && .venv/bin/python -m jobs.run_scan"""

from engine.config import now
from engine.scan import run_scan


def main():
    print(f"[{now()}] scan 시작", flush=True)
    total, leaks = run_scan()
    print(f"[{now()}] scan 끝: {total}개, 정리 후보 {leaks}개", flush=True)


if __name__ == "__main__":
    main()
