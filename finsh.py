import sys
from shell import login
from shell.commands import FinshShell

if __name__ == "__main__":
    user = login.authenticate()
    if not user:
        sys.exit(1)
        
    print("finsh에 오신 것을 환영합니다. 도움말: help")
    FinshShell(user).cmdloop()