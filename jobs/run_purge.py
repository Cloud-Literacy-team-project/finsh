"""Run with: python -m jobs.run_purge"""

from db import database
from engine.purger import run_purge


def main():
    database.log("purge", message="기한 삭제 시작")
    try:
        result = run_purge()
    except Exception:
        database.log("purge", result="FAIL", message="기한 삭제 오류")
        raise
    database.log("purge", message=f"기한 삭제 완료: {result}")


if __name__ == "__main__":
    main()
