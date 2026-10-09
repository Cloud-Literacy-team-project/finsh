from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

TYPE_NAME = {"server": "서버", "publicip": "공인IP", "blockstorage": "스토리지"}

def print_top(leaks):
    """top 명령어: 터미널 표 시각화"""
    table = Table(title="[bold yellow]finsh - 방치 자원 및 요금 현황[/bold yellow]", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=10)
    table.add_column("종류", width=10)
    table.add_column("판정", style="bold red", width=10)
    table.add_column("방치", justify="right", width=8)
    table.add_column("시간당", justify="right", width=10)
    table.add_column("쌓인 요금", justify="right", width=12)

    for r in leaks:
        table.add_row(
            r["id"],
            TYPE_NAME.get(r["type"], r["type"]),
            r["grade"],
            f"{r['idle_days']}일",
            f"{r['cost_hourly']}원",
            f"{r['cost_total']:,}원"
        )

    console.print(table)
    hourly = sum(r["cost_hourly"] for r in leaks)
    console.print(f"  [bold yellow]합계 {len(leaks)}개 · 시간당 [bold red]{hourly:.1f}원[/bold red][/bold yellow]\n")

def print_stat(r):
    """stat <ID> 명령어: 상세 정보 패널 출력"""
    if not r:
        return

    content = (
        f"[bold cyan]ID:[/bold cyan] {r['id']}\n"
        f"[bold cyan]이름:[/bold cyan] {r['name']}\n"
        f"[bold cyan]NCP 자원번호:[/bold cyan] {r['ncp_no']}\n"
        f"[bold cyan]유형:[/bold cyan] {TYPE_NAME.get(r['type'], r['type'])}\n"
        f"[bold cyan]상태:[/bold cyan] {r['state']}\n"
        f"[bold cyan]판정:[/bold cyan] [bold red]{r['grade']}[/bold red]\n"
        f"[bold cyan]방치 기간:[/bold cyan] {r['idle_days']}일\n"
        f"[bold cyan]시간당 요금:[/bold cyan] {r['cost_hourly']}원\n"
        f"[bold cyan]누적 요금:[/bold cyan] {r['cost_total']:,}원\n"
        f"[bold cyan]생성자:[/bold cyan] {r['creator']}\n"
        f"[bold cyan]생성일시:[/bold cyan] {r['created_at']}\n"
        f"[bold cyan]VPC:[/bold cyan] {r['vpc']}\n"
        f"[bold cyan]콘솔 경로:[/bold cyan] {r['console_path']}\n"
        f"[bold cyan]Terraform 여부:[/bold cyan] {r['terraform']}\n"
    )

    detail = r.get("detail", {})
    content += "\n[bold yellow]< 종류별 상세 정보 >[/bold yellow]\n"
    if r['type'] == 'server':
        content += f"  • 스펙: {detail.get('spec')}\n"
        content += f"  • CPU 평균: {detail.get('cpu_avg')}\n"
        content += f"  • 공인 IP: {detail.get('public_ip')}\n"
    elif r['type'] == 'publicip':
        content += f"  • IP 주소: {detail.get('ip')}\n"
        content += f"  • 연결된 서버: {detail.get('attached_server')}\n"
    elif r['type'] == 'blockstorage':
        content += f"  • 용량(GB): {detail.get('size_gb')}\n"
        content += f"  • 연결된 서버: {detail.get('attached_server')}\n"

    panel = Panel(content, title=f"[bold green]자원 상세 정보 - {r['id']}[/bold green]", expand=False)
    console.print(panel)