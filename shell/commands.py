import cmd
import shlex
from shell import data

TYPE_NAME = {"server": "서버", "publicip": "공인IP", "blockstorage": "스토리지"}

class FinshShell(cmd.Cmd):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.prompt = f"{user}@finsh:~$ "

    def do_top(self, arg):
        """쓸모없는 자원 목록"""
        leaks = sorted(data.get_leaks(), key=lambda r: r["cost_total"], reverse=True)
        print(f"  {'ID':<10}{'종류':<8}{'판정':<8}{'방치':<6}{'시간당':<8}쌓인 요금")
        for r in leaks:
            print(f"  {r['id']:<10}{TYPE_NAME[r['type']]:<8}{r['grade']:<8}"
                  f"{str(r['idle_days'])+'일':<6}{str(r['cost_hourly'])+'원':<8}{r['cost_total']:,}원")
        hourly = sum(r["cost_hourly"] for r in leaks)
        print(f"  합계 {len(leaks)}개 · 시간당 {hourly:.1f}원")

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
        for key, value in r.items():
            print(f"  {key}: {value}")

    def do_exit(self, arg):
        """finsh 끝내기"""
        return True

    def default(self, line):
        print(f"finsh: command not found: {line.split()[0]}")

    def emptyline(self):
        pass