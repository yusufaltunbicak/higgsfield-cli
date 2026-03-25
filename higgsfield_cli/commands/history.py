"""History, status, and download commands."""

from __future__ import annotations

from pathlib import Path

import click
import httpx

from ..constants import MODELS
from ..formatter import console, print_job_detail, print_jobs
from ..serialization import to_json_envelope
from ._common import _get_client, _handle_api_error, _wants_json


@click.command()
@click.option("--max", "max_items", type=int, default=20, help="Max items")
@click.option("--model", type=str, default=None, help="Filter by model name")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def history(max_items: int, model: str | None, json_output: bool):
    """Show recent image generation history."""
    client = _get_client()

    model_types = None
    if model:
        match = MODELS.get(model)
        if match:
            model_types = [match[1]]
        else:
            model_types = [model]

    jobs = client.get_history(model_types=model_types, size=max_items)

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(jobs))
    else:
        print_jobs(jobs)


@click.command()
@click.argument("job_id")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def status(job_id: str, json_output: bool):
    """Check status of a generation job."""
    client = _get_client()
    job = client.get_job(job_id)

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(job))
    else:
        print_job_detail(job)


@click.command()
@click.argument("job_ids", nargs=-1, required=True)
@click.option(
    "-o", "--output",
    type=click.Path(),
    default=".",
    help="Output directory",
)
@click.option("--thumbnail", is_flag=True, help="Download thumbnail instead of full-res")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def download(job_ids: tuple[str, ...], output: str, thumbnail: bool, json_output: bool):
    """Download completed images by job ID or display number.

    Examples:

        higgsfield download 1 2 3

        higgsfield download abc123-uuid -o ./images
    """
    client = _get_client()
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for jid in job_ids:
        job = client.get_job(jid)

        if not job.is_completed:
            console.print(f"  [yellow]#{jid} not completed ({job.status})[/yellow]")
            continue

        if not job.results:
            console.print(f"  [yellow]#{jid} no results available[/yellow]")
            continue

        url = job.results.min_url if thumbnail else job.results.raw_url
        if not url:
            console.print(f"  [yellow]#{jid} no download URL[/yellow]")
            continue

        ext = ".webp" if thumbnail else (".png" if ".png" in url else ".jpeg")
        filename = f"higgsfield_{job.id[:8]}{ext}"
        filepath = out_dir / filename

        try:
            resp = httpx.get(url, timeout=120, follow_redirects=True)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            size_mb = len(resp.content) / (1024 * 1024)
            console.print(f"  [green]Saved[/green] {filename} ({size_mb:.1f} MB)")
            results.append({"job_id": job.id, "file": str(filepath), "size": len(resp.content)})
        except Exception as exc:
            console.print(f"  [red]Failed[/red] {filename}: {exc}")

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(results))
