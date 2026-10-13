"""Run with: python -m jobs.run_watch"""

from db import database
from engine.watcher import run_watch


def main():
    database.log("watch", message="휴지통 감시 시작")
    try:
        result = run_watch()
    except Exception:
        database.log("watch", result="FAIL", message="휴지통 감시 오류")
        raise
    database.log("watch", message=f"휴지통 감시 완료: {result}")


if __name__ == "__main__":
    main()
