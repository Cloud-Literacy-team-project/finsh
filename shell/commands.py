import cmd
import shlex
from shell import data, screen

class FinshShell(cmd.Cmd):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.prompt = f"{user}@finsh:~$ "

    def do_top(self, arg):
        """쓸모없는 자원 목록 출력"""
        leaks = sorted(data.get_leaks(), key=lambda r: r["cost_total"], reverse=True)
        screen.print_top(leaks)

    def do_stat(self, arg):
        """자원 하나 자세히 보기: stat <ID>"""
        args = shlex.split(arg)
        if not args:
            print("사용법: stat <ID>")
            return
        r = data.get_resource(args[0])
        if r is None:
            print(f"stat: {args[0]}: 그런 ID가 없습니다")
            return
        screen.print_stat(r)

    def do_exit(self, arg):
        """finsh 끝내기"""
        print("finsh를 종료합니다.")
        return True

    def default(self, line):
        print(f"finsh: command not found: {line.split()[0]}")

    def emptyline(self):
        pass