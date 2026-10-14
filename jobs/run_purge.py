"""Run with: python -m jobs.run_purge"""

from db import database
from engine.purger import run_purge
from engine.config import now


def main():
    print(f"[{now()}] purge 시작", flush=True)
    database.log("purge", message="기한 삭제 시작")
    try:
        result = run_purge()
    except Exception:
        database.log("purge", result="FAIL", message="기한 삭제 오류")
        raise
    database.log("purge", message=f"기한 삭제 완료: {result}")
    print(f"[{now()}] purge 끝: {result}", flush=True)


if __name__ == "__main__":
    main()
