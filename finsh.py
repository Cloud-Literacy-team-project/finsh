import getpass
from shell.commands import FinshShell

if __name__ == "__main__":
    user = getpass.getuser()
    print("finsh에 오신 것을 환영합니다. 도움말: help")
    FinshShell(user).cmdloop()