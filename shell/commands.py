import cmd
import shlex
from datetime import datetime, timedelta

from shell import data, screen

WEEKDAY = "월화수목금토일"
DASH_COMMANDS = {"trash-list": "trash_list", "trash-restore": "trash_restore"}

def _fake_kill_plan(r):
    """가짜 모드 전용 (DB 없이 화면만 볼 때)."""
    if r.get("terraform"):
        return None, "Terraform으로 만든 자원입니다. terraform destroy로 지우세요"
    if r["grade"] not in ("ORPHAN", "ZOMBIE", "IDLE"):
        return None, f"정리 후보(ORPHAN·ZOMBIE·IDLE)가 아닙니다 (지금 판정: {r['grade']})"
    due = datetime.now() + timedelta(days=3)
    return {"due": due, "due_at": f"{due:%m/%d}({WEEKDAY[due.weekday()]}) {due:%H:%M}",
            "extra_cost": round((r["cost_hourly"] or 0) * 72, 1)}, None

def _need_db(name):
    if data._fake():
        print(f"{name}: 가짜 모드에서는 쓸 수 없습니다 (FINSH_SOURCE=db 필요)")
        return True
    return False


def _due_label(value):
    if isinstance(value, datetime):
        return f"{value:%m/%d}({WEEKDAY[value.weekday()]}) {value:%H:%M}"
    return str(value)


class FinshShell(cmd.Cmd):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.prompt = f"{user}@finsh:~$ "

    def precmd(self, line):
        """trash-list 처럼 '-'가 들어간 명령어를 trash_list 로 바꿔서 처리"""
        head, _, rest = line.strip().partition(" ")
        return f"{DASH_COMMANDS.get(head, head)} {rest}".strip()

    def _get(self, command, args, usage):
        if not args:
            print(f"사용법: {usage}")
            return None
        r = data.get_resource(args[0])
        if r is None:
            print(f"{command}: {args[0]}: 그런 ID가 없습니다")
        return r

    # ---------- 보기 ----------
    def do_top(self, arg):
        """쓸모없는 자원 목록: top"""
        leaks = sorted(data.get_leaks(), key=lambda r: r["cost_total"] or 0, reverse=True)
        screen.print_top(leaks, data.get_summary())

    def do_stat(self, arg):
        """자원 하나 자세히 보기: stat <ID>"""
        r = self._get("stat", shlex.split(arg), "stat <ID>")
        if r:
            screen.print_stat(r)

    # ---------- 지우기 ----------
    def do_kill(self, arg):
        """자원을 휴지통에 넣기: kill <ID>"""
        r = self._get("kill", shlex.split(arg), "kill <ID>")
        if r is None:
            return
        if data._fake():
            plan, reason = _fake_kill_plan(r)
        else:
            from engine import killer
            plan, reason = killer.prepare(r)
        if plan is None:
            screen.print_refused("kill", r["id"], reason)
            return

        screen.print_kill_confirm(r, plan)
        answer = input("휴지통에 넣을까요? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):            # 그냥 엔터 = 취소
            print("취소했습니다.")
            return
        if data._fake():
            print(f"(가짜 모드) {r['id']}을(를) 휴지통에 넣었습니다. 삭제 예정 {plan['due_at']}")
            return
        from engine import trash
        try:
            trash.put(r, plan["due_at"])
        except ValueError as exc:
            screen.print_refused("kill", r["id"], str(exc))
            return
        print(f"{r['id']}을(를) 휴지통에 넣었습니다. 삭제 예정 {_due_label(plan['due_at'])}")

    def do_sudo(self, arg):
        """바로 영구 삭제: sudo kill -9 <ID>"""
        args = shlex.split(arg)
        if args[:2] != ["kill", "-9"] or len(args) != 3:
            print("사용법: sudo kill -9 <ID>")
            return
        if _need_db("sudo kill -9"):
            return
        from engine import killer, safety
        r = self._get("sudo kill -9", args[2:], "sudo kill -9 <ID>")
        if r is None:
            return
        plan, reason = killer.prepare(r)
        if plan is None:
            screen.print_refused("sudo kill -9", r["id"], reason)
            return
        screen.print_kill9_warning(r, safety.is_dry_run())
        typed = input(f"정말 지우려면 ID를 다시 입력하세요 ({r['id']}): ").strip()
        if typed != r["id"]:
            print("ID가 달라서 취소했습니다.")
            return
        print("삭제 중입니다... (서버는 몇 분 걸릴 수 있어요)")
        try:
            result = killer.kill_now(r, confirmed=True)
        except killer.UnsafeDeletion as exc:
            screen.print_refused("sudo kill -9", r["id"], str(exc))
            return
        except Exception:
            print("실패: 삭제 또는 결과 확인에 실패했습니다. 자원 상태를 확인하세요.")
            return
        if result == "DRYRUN":
            print("완료: (연습 모드) 실제로는 지우지 않았습니다")
        elif result == "PURGED":
            print("완료: 자원 삭제를 확인했습니다")
        else:
            print("실패: 삭제 결과를 확인할 수 없습니다")

    # ---------- 휴지통 ----------
    def do_trash_list(self, arg):
        """휴지통 보기: trash-list"""
        if _need_db("trash-list"):
            return
        from engine import trash
        screen.print_trash(trash.list_all())

    def do_trash_restore(self, arg):
        """휴지통에서 꺼내기: trash-restore <ID>"""
        args = shlex.split(arg)
        if not args:
            print("사용법: trash-restore <ID>")
            return
        if _need_db("trash-restore"):
            return
        from engine import trash
        try:
            restored = trash.restore(args[0])
        except ValueError as exc:
            print(f"trash-restore: {args[0]}: {exc}")
            return
        if not restored:
            print(f"trash-restore: {args[0]}: 다른 작업 중이거나 이미 처리된 항목입니다")
            return
        print(f"{args[0]}을(를) 휴지통에서 꺼냈습니다. 다시 top에 보입니다.")

    # ---------- 보호 ----------
    def do_chattr(self, arg):
        """보호: chattr +i <ID> -m "이유"   /   보호 풀기: chattr -i <ID>"""
        args = shlex.split(arg)
        if len(args) < 2 or args[0] not in ("+i", "-i"):
            print('사용법: chattr +i <ID> -m "이유"  /  chattr -i <ID>')
            return
        if _need_db("chattr"):
            return
        from db import database
        from engine import protect
        r = self._get("chattr", args[1:2], "chattr +i <ID>")
        if r is None:
            return
        if args[0] == "+i":
            reason = args[args.index("-m") + 1] if "-m" in args and args.index("-m") + 1 < len(args) else "이유 없음"
            ok, message = protect.add(r, reason)
            action = "protect"
        else:
            ok, message = protect.remove(r)
            action = "unprotect"
        if ok:
            database.log(action, r, "OK", message)
            print(f"{r['id']}: {message}")
        else:
            screen.print_refused("chattr", r["id"], message)

    def do_lsattr(self, arg):
        """보호 중인 자원 보기: lsattr"""
        if _need_db("lsattr"):
            return
        from engine import protect
        screen.print_lsattr(protect.list_all())

    def do_last(self, arg):
        """최근 기록 보기: last"""
        if _need_db("last"):
            return
        from db import database
        screen.print_last(database.get_events(20))

    # ---------- 기타 ----------
    def do_exit(self, arg):
        """finsh 끝내기"""
        print("finsh를 종료합니다.")
        return True

    do_EOF = do_exit                                # Ctrl+D 로도 종료

    def default(self, line):
        print(f"finsh: command not found: {line.split()[0]}")

    def emptyline(self):
        pass
