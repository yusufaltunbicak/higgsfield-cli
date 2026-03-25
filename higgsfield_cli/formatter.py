"""Rich table output for Higgsfield CLI."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from .models import Job, UserInfo, Wallet

# stderr for tables so JSON piping stays clean on stdout
console = Console(stderr=True)


def print_jobs(jobs: list[Job], title: str = "History") -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Model", style="cyan", width=18)
    table.add_column("Prompt", width=35)
    table.add_column("Status", width=12)
    table.add_column("Res", width=5)
    table.add_column("Ratio", width=6)
    table.add_column("Created", width=18)

    for job in jobs:
        status_style = {
            "completed": "green",
            "in_progress": "yellow",
            "waiting": "dim",
            "queued": "dim",
            "failed": "red",
        }.get(job.status, "white")

        created = ""
        if job.created_at:
            dt = datetime.fromtimestamp(job.created_at, tz=timezone.utc)
            created = dt.strftime("%Y-%m-%d %H:%M")

        table.add_row(
            f"#{job.display_num}" if job.display_num else "",
            job.job_set_type.replace("_", " "),
            job.prompt[:35] if job.prompt else "",
            f"[{status_style}]{job.status}[/{status_style}]",
            job.resolution or job.quality or "",
            job.aspect_ratio or "",
            created,
        )

    console.print(table)


def print_job_detail(job: Job) -> None:
    console.print(f"\n  [bold cyan]Job #{job.display_num}[/bold cyan]" if job.display_num else "")
    console.print(f"  ID:     {job.id}")
    console.print(f"  Model:  {job.job_set_type}")
    console.print(f"  Status: {job.status}")
    console.print(f"  Prompt: {job.prompt}")

    if job.resolution:
        console.print(f"  Resolution: {job.resolution}")
    if job.quality:
        console.print(f"  Quality: {job.quality}")
    console.print(f"  Aspect: {job.aspect_ratio}")
    console.print(f"  Size:   {job.width}x{job.height}")
    if job.seed is not None:
        console.print(f"  Seed:   {job.seed}")
    console.print(f"  Batch:  {job.batch_size}")

    if job.results and job.results.raw_url:
        console.print(f"  Image:  [link={job.results.raw_url}]{job.results.raw_url}[/link]")

    if job.created_at:
        dt = datetime.fromtimestamp(job.created_at, tz=timezone.utc)
        console.print(f"  Created: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")


def print_generation_progress(job_id: str, status: str) -> None:
    icon = {
        "waiting": "[dim]...[/dim]",
        "queued": "[dim]queued[/dim]",
        "in_progress": "[yellow]generating[/yellow]",
        "completed": "[green]done[/green]",
        "failed": "[red]failed[/red]",
    }.get(status, status)
    console.print(f"  {job_id[:8]}... {icon}", highlight=False)


def print_user_info(user: UserInfo, wallet: Wallet) -> None:
    console.print(f"\n  [bold cyan]Account[/bold cyan]")
    console.print(f"  Plan:    {user.plan_type}")
    console.print(f"  Credits: {user.total_credits:.1f} / {user.total_plan_credits}")
    console.print(f"  Wallet:  {wallet.credits_display:.1f}")
    console.print(f"  Period:  {user.billing_period}")
    if user.plan_ends_at:
        console.print(f"  Expires: {user.plan_ends_at[:10]}")


def print_credits(wallet: Wallet) -> None:
    console.print(f"  Credits: [bold green]{wallet.credits_display:.1f}[/bold green] / {wallet.total_credits / 100:.0f}")


def print_models(models: dict) -> None:
    table = Table(title="Available Models")
    table.add_column("Name", style="cyan")
    table.add_column("Slug")
    table.add_column("Type")
    table.add_column("Version")

    for name, (slug, jst, ver) in models.items():
        table.add_row(name, slug, jst, ver)

    console.print(table)
