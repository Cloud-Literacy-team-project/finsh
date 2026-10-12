import getpass
import os

from shell import data, screen
from shell.commands import FinshShell

if __name__ == "__main__":
    user = getpass.getuser()
    print("finsh에 오신 것을 환영합니다. 도움말: help")
    if data._fake():
        print("(가짜 모드: samples/fake_leaks.json)")
    else:
        if os.environ.get("FINSH_DRY_RUN", "1").strip() != "0":
            print("(연습 모드: 실제로는 지우지 않습니다)")
        try:
            from db import database
            screen.print_alerts(database.pop_alerts())
        except Exception as e:
            print(f"알림을 불러오지 못했습니다: {e}")
    FinshShell(user).cmdloop()