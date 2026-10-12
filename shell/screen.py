"""finsh 화면 출력 (rich). 규약(docs/conventions.md)에 따른 요약 및 표 정렬 지원."""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

TYPE_NAME = {"server": "서버", "publicip": "공인IP", "blockstorage": "스토리지"}
GRADE_COLOR = {
    "ORPHAN": "red",
    "ZOMBIE": "magenta",
    "IDLE": "yellow",
    "WAITING": "cyan",
    "UNKNOWN": "white",
    "OK": "green"
}

def _v(value, unit=""):
    """None이나 빈 값은 '-'로, 금액 및 일수 포맷팅"""
    if value is None or value == "":
        return "-"
    if unit == "원" and isinstance(value, (int, float)):
        return f"{value:,.0f}원" if value >= 100 else f"{value:g}원"
    if unit == "일" and isinstance(value, (int, float)):
        return f"{value:.1f}일"
    return f"{value}{unit}"

def _grade(grade):
    color = GRADE_COLOR.get(grade, "white")
    return f"[bold {color}]{grade}[/bold {color}]"

def print_top(leaks, summary=None):
    """top: 정리 후보(ORPHAN, ZOMBIE, IDLE) 표 출력 및 상단/하단 요약 패널"""
    # 1. 정리 후보 필터링
    candidates = [r for r in leaks if r.get("grade") in ("ORPHAN", "ZOMBIE", "IDLE")]
    
    # 2. 메인 표 생성
    table = Table(title="[bold yellow]finsh - 방치 자원 및 요금 현황[/bold yellow]",
                  show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=10)
    table.add_column("이름", width=22)
    table.add_column("종류", width=8)
    table.add_column("판정", width=8)
    table.add_column("방치", justify="right", width=8)
    table.add_column("시간당", justify="right", width=8)
    table.add_column("쌓인 요금", justify="right", width=12)
    table.add_column("보호/IaC", justify="center", width=8)

    for r in candidates:
        flags = []
        if r.get("protected"):
            flags.append("[bold red]+i[/bold red]")
        if r.get("terraform"):
            flags.append("[bold blue]tf[/bold blue]")
        flag_str = " ".join(flags) if flags else "-"

        table.add_row(
            r["id"],
            _v(r.get("name")),
            TYPE_NAME.get(r.get("type"), r.get("type")),
            _grade(r.get("grade")),
            _v(r.get("idle_days"), "일"),
            _v(r.get("cost_hourly"), "원"),
            _v(r.get("cost_total"), "원"),
            flag_str
        )

    console.print(table)

    # 3. 요약 정보 계산 및 출력
    count = {g: sum(r.get("grade") == g for r in candidates) for g in ("ORPHAN", "ZOMBIE", "IDLE")}
    hourly = sum(r.get("cost_hourly") or 0 for r in candidates)
    waiting_cnt = sum(1 for r in leaks if r.get("grade") == "WAITING")
    unknown_cnt = sum(1 for r in leaks if r.get("grade") == "UNKNOWN")

    console.print("  정리 후보: " + " · ".join(f"{g} {n}" for g, n in count.items()))
    console.print(f"  후보 예상 비용: 시간당 [bold red]{hourly:,.1f}원[/bold red]")
    console.print(f"  관찰 중: WAITING {waiting_cnt}개 | 판정 불가: UNKNOWN {unknown_cnt}개")
    if summary and summary.get("last_scan"):
        console.print(f"  마지막 검사: {summary['last_scan']:%m/%d %H:%M}")
    console.print()

def print_stat(r):
    """stat <ID>: 상세 정보 출력"""
    rows = [
        ("ID", _v(r.get("id"))),
        ("이름", _v(r.get("name"))),
        ("종류", TYPE_NAME.get(r.get("type"), r.get("type"))),
        ("판정", _grade(r.get("grade"))),
        ("판정 이유", _v(r.get("reason"))),
        ("방치 기간", _v(r.get("idle_days"), "일")),
        ("시간당 요금", _v(r.get("cost_hourly"), "원")),
        ("쌓인 요금", _v(r.get("cost_total"), "원")),
        ("chattr +i 보호", f"예 (사유: {r.get('protected_memo', '보호 설정됨')})" if r.get("protected") else "아니오"),
        ("Terraform 관리", "예 (IaC 보호됨)" if r.get("terraform") else "아니오"),
    ]

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column()
    for k, v in rows:
        grid.add_row(k, v)

    console.print(Panel(grid, title=f"[bold green]stat {r['id']}[/bold green]", expand=False))

def print_kill_confirm(r, plan):
    """kill 승인 안내 패널"""
    content = (
        f"[bold]{r['id']}[/bold]  {r.get('name')}  ({TYPE_NAME.get(r.get('type'), r.get('type'))}, {r.get('grade')})\n\n"
        f"이 자원을 [bold yellow]휴지통[/bold yellow]에 넣습니다.\n"
        f"  • 영구 삭제 예정: [bold]{plan['due_at']}[/bold]\n"
        f"  • 그때까지 더 나가는 요금: [bold red]약 {_v(plan['extra_cost'], '원')}[/bold red]\n"
        f"  • 삭제 보류 안내: 유예 기간 중 재가동 시 삭제 자동 보류\n"
        f"  • 복원 명령어: trash-restore {r['id']}\n\n"
        f"[dim]기다리지 않고 바로 지우려면: sudo kill -9 {r['id']}[/dim]"
    )
    console.print(Panel(content, title="[bold red]kill 확인[/bold red]", expand=False))

def print_refused(command, rid, reason):
    """삭제 거부 메시지"""
    console.print(f"[bold red]{command}: {rid}: 거부됨[/bold red] — {reason}")