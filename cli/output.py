from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
error_console = Console(stderr=True, style="bold red")


def print_success(message: str) -> None:
    console.print(f"[bold green]✅ {message}[/bold green]")


def print_error(message: str) -> None:
    error_console.print(f"❌ {message}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]⚠ {message}[/bold yellow]")


def print_info(message: str) -> None:
    console.print(f"[bold blue]ℹ {message}[/bold blue]")


def create_table(title: str, columns: list[str]) -> Table:
    table = Table(title=title, show_header=True, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    return table
