import cmd
import shlex
from datetime import datetime, timedelta

from rich.console import Console
from shell import data, screen

console = Console()
WEEKDAY = "월화수목금토일"

def _kill_plan(r):
    """kill 안전 검사 및 예상 비용 계산"""
    if r.get("terraform"):
        return None, "Terraform으로 만든 자원입니다. terraform destroy로 지우세요"
    if r.get("protected"):
        memo = r.get("protected_memo", "보호 설정됨")
        return None, f"chattr +i 보호 자원입니다 (사유: {memo})"
    if r.get("grade") not in ("ORPHAN", "ZOMBIE", "IDLE"):
        return None, f"정리 후보(ORPHAN·ZOMBIE·IDLE)가 아닙니다 (현재 상태: {r.get('grade')})"

    start = datetime.now()
    try:
        from engine.bizday import due_at
        due = due_at(start, {"unit": "bizdays", "value": 3})
    except ImportError:
        due = start + timedelta(days=3)
    hours = (due - start).total_seconds() / 3600
    return {
        "due_at": f"{due:%m/%d}({WEEKDAY[due.weekday()]}) {due:%H:%M}",
        "extra_cost": round((r.get("cost_hourly") or 0) * hours, 1),
    }, None

class FinshShell(cmd.Cmd):
    def __init__(self, user):
        super().__init__()
        self.identchars += '-'  # 하이픈(-)을 명령어 이름 문자로 허용
        self.user = user
        self.prompt = f"{user}@finsh:~$ "
        self.trash = []
        self.logs = []
        self._add_log("LOGIN", "세션 시작")

    def onecmd(self, line):
        """하이픈(-) 명령어를 언더바(_) 함수 매핑으로 자동 변환 (trash-list -> do_trash_list)"""
        cmd_name, arg, line_str = self.parseline(line)
        if not line_str:
            return self.emptyline()
        if cmd_name is None:
            return self.default(line_str)
        self.lastcmd = line_str
        
        func_name = 'do_' + cmd_name.replace('-', '_')
        try:
            func = getattr(self, func_name)
        except AttributeError:
            return self.default(line_str)
        return func(arg)

    def _add_log(self, action, target):
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append({"time": time_str, "user": self.user, "action": action, "target": target})

    def do_top(self, arg):
        """쓸모없는 자원 목록 및 요약 보기: top"""
        leaks = sorted(data.get_leaks(), key=lambda r: r.get("cost_total") or 0, reverse=True)
        screen.print_top(leaks)

    def do_stat(self, arg):
        """자원 상세 보기: stat <ID>"""
        args = shlex.split(arg)
        if not args:
            print("사용법: stat <ID>")
            return
        r = data.get_resource(args[0])
        if r is None:
            print(f"stat: {args[0]}: 그런 ID가 없습니다")
            return
        screen.print_stat(r)

    def do_kill(self, arg):
        """자원을 휴지통으로 이동: kill <ID>"""
        args = shlex.split(arg)
        if not args:
            print("사용법: kill <ID>")
            return
        r = data.get_resource(args[0])
        if r is None:
            print(f"kill: {args[0]}: 그런 ID가 없습니다")
            return

        plan, reason = _kill_plan(r)
        if plan is None:
            screen.print_refused("kill", r["id"], reason)
            return

        screen.print_kill_confirm(r, plan)
        answer = input("휴지통에 넣을까요? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("취소했습니다.")
            return

        r["deleted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.trash.append(r)
        self._add_log("KILL", r["id"])
        print(f"(연습) {r['id']}을(를) 휴지통에 넣었습니다. 삭제 예정 {plan['due_at']}")

    def do_chattr(self, arg):
        """자원 보호 속성 설정/해제: chattr [+i|-i] <ID> [-m "사유"]"""
        args = shlex.split(arg)
        if len(args) < 2:
            print("사용법: chattr [+i|-i] <ID> [-m \"사유\"]")
            return
        opt, rid = args[0], args[1]
        memo = "보호 설정됨"
        if "-m" in args:
            try:
                memo = args[args.index("-m") + 1]
            except IndexError:
                pass

        r = data.get_resource(rid)
        if not r:
            print(f"chattr: {rid}: 그런 ID가 없습니다")
            return

        if opt == "+i":
            r["protected"] = True
            r["protected_memo"] = memo
            self._add_log("CHATTR_+I", rid)
            print(f"설정 완료: '{rid}' 자원에 보호 설정(+i)이 적용되었습니다.")
        elif opt == "-i":
            r["protected"] = False
            r["protected_memo"] = ""
            self._add_log("CHATTR_-I", rid)
            print(f"해제 완료: '{rid}' 자원의 보호 설정(-i)이 해제되었습니다.")

    def do_lsattr(self, arg):
        """보호 설정된 자원 목록 조회: lsattr"""
        protected_list = [r for r in data.get_leaks() if r.get("protected")]
        if not protected_list:
            print("보호 설정된 자원이 없습니다.")
            return
        print("[보호 설정(+i) 자원 목록]")
        for r in protected_list:
            print(f"- {r['id']} ({r.get('name')}) | 사유: {r.get('protected_memo', 'N/A')}")

    def do_trash_list(self, arg):
        """휴지통 목록 조회: trash-list"""
        if not self.trash:
            print("휴지통이 비어 있습니다.")
            return
        print("[휴지통 목록]")
        for r in self.trash:
            print(f"- {r['id']} ({r.get('name')}) | 삭제 시각: {r.get('deleted_at')}")

    def do_trash_restore(self, arg):
        """휴지통 자원 복원: trash-restore <ID>"""
        args = shlex.split(arg)
        if not args:
            print("사용법: trash-restore <ID>")
            return
        rid = args[0]
        res = next((r for r in self.trash if r["id"] == rid), None)
        if not res:
            print(f"trash-restore: {rid}: 휴지통에 그런 ID가 없습니다")
            return
        self.trash.remove(res)
        self._add_log("RESTORE", rid)
        print(f"복원 완료: '{rid}' 자원이 원래대로 복원되었습니다.")

    def do_last(self, arg):
        """작업 이력 출력: last"""
        print("[작업 이력]")
        for log in self.logs:
            print(f"{log['time']} | 사용자: {log['user']} | 작업: {log['action']} | 대상: {log['target']}")

    def do_exit(self, arg):
        """finsh 종료"""
        print("finsh를 종료합니다.")
        return True

    do_EOF = do_exit

    def default(self, line):
        print(f"finsh: command not found: {line.split()[0]}")

    def emptyline(self):
        pass