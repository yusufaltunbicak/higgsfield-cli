"""Extra commands: open, again, watch, use, delete, favorite, batch, free-gens."""

from __future__ import annotations

import platform
import subprocess
import sys
import time
from pathlib import Path

import click

from ..constants import MODELS
from ..formatter import console
from ..serialization import to_json_envelope
from ._common import _get_client, _handle_api_error, _wants_json


# ------------------------------------------------------------------
# open - open image in browser
# ------------------------------------------------------------------

@click.command(name="open")
@click.argument("job_id")
@_handle_api_error
def open_cmd(job_id: str):
    """Open a completed image in the browser.

    Examples:

        higgsfield open 1

        higgsfield open abc123-uuid
    """
    client = _get_client()
    job = client.get_job(job_id)

    if not job.is_completed:
        console.print(f"  [yellow]Job not completed yet ({job.status})[/yellow]")
        return

    url = job.download_url
    if not url:
        console.print("  [red]No image URL available[/red]")
        return

    console.print(f"  Opening {url[:80]}...")
    if platform.system() == "Darwin":
        subprocess.run(["open", url], check=False)
    elif platform.system() == "Linux":
        subprocess.run(["xdg-open", url], check=False)
    else:
        click.launch(url)


# ------------------------------------------------------------------
# again - re-run with same settings
# ------------------------------------------------------------------

@click.command()
@click.argument("job_id")
@click.option("--seed", type=int, default=None, help="Override seed")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@click.option("-d", "--download", is_flag=True, help="Auto-download")
@click.option("-o", "--output", type=click.Path(), default=".", help="Output dir")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def again(job_id: str, seed: int | None, yes: bool, download: bool, output: str, json_output: bool):
    """Re-run a previous generation with the same settings.

    Uses the same prompt, model, resolution, aspect ratio, and batch size.
    Generates with a new random seed unless --seed is specified.

    Examples:

        higgsfield again 1

        higgsfield again 1 --seed 42 --download
    """
    import random

    client = _get_client()
    job = client.get_job(job_id)

    # Resolve model name from job_set_type
    model_name = None
    for name, (_, jst, _) in MODELS.items():
        if jst == job.job_set_type:
            model_name = name
            break

    if not model_name:
        console.print(f"  [red]Unknown model type: {job.job_set_type}[/red]")
        return

    if not yes:
        console.print(f"\n  [bold]Re-generate[/bold]")
        console.print(f"  Model:  {model_name}")
        console.print(f"  Prompt: {job.prompt[:60]}")
        console.print(f"  Res:    {job.resolution or job.quality}")
        console.print(f"  Aspect: {job.aspect_ratio}")
        console.print(f"  Batch:  {job.batch_size}")
        console.print()
        if not click.confirm("  Proceed?", default=True):
            return

    resp = client.generate(
        prompt=job.prompt,
        model=model_name,
        resolution=job.resolution or "4k",
        quality=job.quality or "high",
        aspect_ratio=job.aspect_ratio or "16:9",
        batch_size=job.batch_size,
        seed=seed or random.randint(100000, 999999),
    )

    job_ids = resp.all_job_ids
    console.print(f"  [green]Created {len(job_ids)} job(s)[/green]")

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(resp))
        return

    # Wait + optional download
    from ..formatter import print_generation_progress
    shown: dict[str, str] = {}

    def on_status(jid: str, status: str):
        if shown.get(jid) != status:
            shown[jid] = status
            print_generation_progress(jid, status)

    console.print("  Waiting...")
    jobs = client.wait_for_jobs(job_ids, on_status=on_status)

    completed = [j for j in jobs if j.is_completed]
    for j in completed:
        if j.download_url:
            console.print(f"  #{j.display_num} {j.download_url}")

    if download and completed:
        from .generate import _download_image
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        for j in completed:
            if j.download_url:
                _download_image(j, out_dir)


# ------------------------------------------------------------------
# watch - live status tracking with progress
# ------------------------------------------------------------------

@click.command()
@click.argument("job_ids", nargs=-1, required=False)
@click.option("--all", "watch_all", is_flag=True, help="Watch all recent pending jobs")
@click.option("--interval", type=float, default=2.0, help="Poll interval in seconds")
@click.option("-d", "--download", is_flag=True, help="Auto-download on completion")
@click.option("-o", "--output", type=click.Path(), default=".", help="Output dir")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def watch(job_ids: tuple[str, ...], watch_all: bool, interval: float, download: bool, output: str, json_output: bool):
    """Watch job(s) with live status updates.

    Shows a live-updating display of job progress.

    Examples:

        higgsfield watch 1 2 3

        higgsfield watch --all

        higgsfield watch 1 --download
    """
    from rich.live import Live
    from rich.table import Table

    client = _get_client()

    # Resolve job IDs
    ids_to_watch = list(job_ids)
    if watch_all or not ids_to_watch:
        # Get recent jobs and find pending ones
        history = client.get_history(size=20)
        for j in history:
            if j.status in ("waiting", "queued", "in_progress"):
                ids_to_watch.append(j.id)
        if not ids_to_watch:
            console.print("  No pending jobs found.")
            return

    console.print(f"  Watching {len(ids_to_watch)} job(s)... (Ctrl+C to stop)\n")

    states: dict[str, dict] = {}
    for jid in ids_to_watch:
        states[jid] = {"status": "...", "model": "", "prompt": ""}

    def build_table() -> Table:
        table = Table(show_header=True, show_lines=False, expand=False)
        table.add_column("Job", width=10)
        table.add_column("Model", width=18)
        table.add_column("Prompt", width=30)
        table.add_column("Status", width=14)

        for jid, info in states.items():
            status = info["status"]
            style = {
                "completed": "[green]completed[/green]",
                "in_progress": "[yellow]generating...[/yellow]",
                "queued": "[dim]queued[/dim]",
                "waiting": "[dim]waiting[/dim]",
                "failed": "[red]failed[/red]",
            }.get(status, status)

            short_id = jid[:8] if len(jid) > 8 else jid
            table.add_row(
                short_id,
                info.get("model", ""),
                info.get("prompt", "")[:30],
                style,
            )
        return table

    completed_jobs = []

    try:
        with Live(build_table(), console=console, refresh_per_second=1) as live:
            all_done = False
            while not all_done:
                all_done = True
                for jid in ids_to_watch:
                    current = states[jid]["status"]
                    if current in ("completed", "failed", "error", "cancelled"):
                        continue
                    all_done = False

                    try:
                        status_resp = client.get_job_status(jid)
                        new_status = status_resp.get("status", "unknown")
                        states[jid]["status"] = new_status
                        states[jid]["model"] = status_resp.get("job_set_type", states[jid].get("model", ""))

                        if new_status == "completed":
                            job = client.get_job(jid)
                            states[jid]["prompt"] = job.prompt[:30]
                            states[jid]["model"] = job.job_set_type.replace("_", " ")
                            completed_jobs.append(job)
                        elif not states[jid].get("prompt"):
                            try:
                                job = client.get_job(jid)
                                states[jid]["prompt"] = job.prompt[:30]
                                states[jid]["model"] = job.job_set_type.replace("_", " ")
                            except Exception:
                                pass
                    except Exception:
                        pass

                live.update(build_table())
                if not all_done:
                    time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n  Stopped.")

    # Summary
    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(completed_jobs))
        return

    if completed_jobs:
        console.print(f"\n  [green]{len(completed_jobs)} completed[/green]")
        for j in completed_jobs:
            if j.download_url:
                console.print(f"  {j.download_url}")

        if download:
            from .generate import _download_image
            out_dir = Path(output)
            out_dir.mkdir(parents=True, exist_ok=True)
            for j in completed_jobs:
                if j.download_url:
                    _download_image(j, out_dir)


# ------------------------------------------------------------------
# use - set reference image from a previous job
# ------------------------------------------------------------------

@click.command()
@click.argument("job_id")
@click.argument("prompt")
@click.option("-m", "--model", default=None, help="Model (defaults to same as source)")
@click.option("-r", "--resolution", default="4k")
@click.option("-a", "--aspect", default=None, help="Aspect ratio (defaults to same)")
@click.option("-b", "--batch", type=int, default=4)
@click.option("-y", "--yes", is_flag=True)
@click.option("-d", "--download", is_flag=True)
@click.option("-o", "--output", type=click.Path(), default=".")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def use(job_id: str, prompt: str, model: str | None, resolution: str, aspect: str | None, batch: int, yes: bool, download: bool, output: str, json_output: bool):
    """Generate using a previous image as reference.

    Takes a completed job's output image and uses it as input for a new generation.

    Examples:

        higgsfield use 1 "make it more colorful"

        higgsfield use 1 "anime style version" -m nano-banana-pro
    """
    client = _get_client()
    source = client.get_job(job_id)

    if not source.is_completed or not source.download_url:
        console.print("  [red]Source job not completed or no image available[/red]")
        return

    # Resolve model
    if model is None:
        for name, (_, jst, _) in MODELS.items():
            if jst == source.job_set_type:
                model = name
                break
        if model is None:
            model = "nano-banana-pro"

    aspect = aspect or source.aspect_ratio or "16:9"

    # Build reference from the completed image
    input_images = [{
        "data": {
            "id": source.id,
            "url": source.download_url,
            "type": "media_input",
        },
        "role": "image",
    }]

    if not yes:
        console.print(f"\n  [bold]Generate with reference[/bold]")
        console.print(f"  Source:  #{job_id} ({source.prompt[:40]})")
        console.print(f"  Prompt:  {prompt[:60]}")
        console.print(f"  Model:   {model}")
        console.print()
        if not click.confirm("  Proceed?", default=True):
            return

    resp = client.generate(
        prompt=prompt,
        model=model,
        resolution=resolution,
        aspect_ratio=aspect,
        batch_size=batch,
        input_images=input_images,
    )

    job_ids = resp.all_job_ids
    console.print(f"  [green]Created {len(job_ids)} job(s)[/green]")

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(resp))
        return

    from ..formatter import print_generation_progress
    shown: dict[str, str] = {}

    def on_status(jid: str, status: str):
        if shown.get(jid) != status:
            shown[jid] = status
            print_generation_progress(jid, status)

    console.print("  Waiting...")
    jobs = client.wait_for_jobs(job_ids, on_status=on_status)

    for j in jobs:
        if j.is_completed and j.download_url:
            console.print(f"  #{j.display_num} {j.download_url}")

    if download:
        from .generate import _download_image
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        for j in jobs:
            if j.is_completed and j.download_url:
                _download_image(j, out_dir)


# ------------------------------------------------------------------
# delete - delete jobs
# ------------------------------------------------------------------

@click.command()
@click.argument("job_ids", nargs=-1, required=True)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def delete(job_ids: tuple[str, ...], yes: bool, json_output: bool):
    """Delete jobs from history.

    Examples:

        higgsfield delete 1 2 3

        higgsfield delete 1 -y
    """
    client = _get_client()

    if not yes:
        console.print(f"  Delete {len(job_ids)} job(s)?")
        if not click.confirm("  Proceed?", default=False):
            return

    results = []
    for jid in job_ids:
        try:
            real_id = client._resolve_id(jid)
            resp = client._client.delete(
                f"/jobs/{real_id}",
                headers={"Authorization": f"Bearer {client._token}"},
            )
            if resp.status_code in (200, 204):
                console.print(f"  [green]Deleted #{jid}[/green]")
                results.append({"id": real_id, "deleted": True})
            else:
                console.print(f"  [yellow]#{jid}: HTTP {resp.status_code}[/yellow]")
                results.append({"id": real_id, "deleted": False, "status": resp.status_code})
        except Exception as exc:
            console.print(f"  [red]#{jid}: {exc}[/red]")
            results.append({"id": jid, "deleted": False, "error": str(exc)})

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(results))


# ------------------------------------------------------------------
# favorite - toggle favorite
# ------------------------------------------------------------------

@click.command()
@click.argument("job_ids", nargs=-1, required=True)
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def favorite(job_ids: tuple[str, ...], json_output: bool):
    """Toggle favorite on job(s).

    Examples:

        higgsfield favorite 1

        higgsfield favorite 1 2 3
    """
    client = _get_client()
    results = []

    for jid in job_ids:
        try:
            job = client.get_job(jid)
            new_state = not job.is_favourite
            real_id = client._resolve_id(jid)
            resp = client._client.patch(
                f"/jobs/{real_id}",
                json={"is_favourite": new_state},
            )
            if resp.status_code == 200:
                icon = "starred" if new_state else "unstarred"
                console.print(f"  [green]#{jid} {icon}[/green]")
                results.append({"id": real_id, "is_favourite": new_state})
            else:
                console.print(f"  [yellow]#{jid}: HTTP {resp.status_code}[/yellow]")
        except Exception as exc:
            console.print(f"  [red]#{jid}: {exc}[/red]")

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(results))


# ------------------------------------------------------------------
# batch - bulk generation from file
# ------------------------------------------------------------------

@click.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("-m", "--model", default=None, help="Model for all prompts")
@click.option("-r", "--resolution", default="4k")
@click.option("-q", "--quality", default="high")
@click.option("-a", "--aspect", default="16:9")
@click.option("-b", "--batch", type=int, default=4)
@click.option("-d", "--download", is_flag=True)
@click.option("-o", "--output", type=click.Path(), default=".")
@click.option("--delay", type=float, default=2.0, help="Delay between requests (seconds)")
@click.option("-y", "--yes", is_flag=True)
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def batch(file: str, model: str | None, resolution: str, quality: str, aspect: str, batch_size: int, download: bool, output: str, delay: float, yes: bool, json_output: bool):
    """Generate images from a file of prompts (one per line).

    Empty lines and lines starting with # are skipped.

    Examples:

        higgsfield batch prompts.txt --download -o ./output

        higgsfield batch ideas.txt -m seedream-v4.5 -q high
    """
    from .. import config as cfg

    prompts = []
    for line in Path(file).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            prompts.append(line)

    if not prompts:
        console.print("  [yellow]No prompts found in file[/yellow]")
        return

    if model is None:
        model = cfg.get("model", "nano-banana-pro")

    if not yes:
        console.print(f"\n  [bold]Batch Generate[/bold]")
        console.print(f"  Prompts: {len(prompts)}")
        console.print(f"  Model:   {model}")
        console.print(f"  Each:    {batch_size} images, {resolution}, {aspect}")
        console.print(f"  Total:   ~{len(prompts) * batch_size} images")
        console.print()
        if not click.confirm("  Proceed?", default=True):
            return

    client = _get_client()
    all_job_ids = []

    for i, prompt in enumerate(prompts):
        console.print(f"\n  [{i+1}/{len(prompts)}] {prompt[:50]}...")
        try:
            resp = client.generate(
                prompt=prompt,
                model=model,
                resolution=resolution,
                quality=quality,
                aspect_ratio=aspect,
                batch_size=batch_size,
            )
            ids = resp.all_job_ids
            all_job_ids.extend(ids)
            console.print(f"  [green]{len(ids)} job(s) created[/green]")
        except Exception as exc:
            console.print(f"  [red]Failed: {exc}[/red]")

        if i < len(prompts) - 1:
            time.sleep(delay)

    console.print(f"\n  [bold]Total: {len(all_job_ids)} jobs created[/bold]")

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope({"job_ids": all_job_ids, "count": len(all_job_ids)}))
        return

    if download and all_job_ids:
        console.print("  Waiting for all jobs to complete...")
        from ..formatter import print_generation_progress
        shown: dict[str, str] = {}

        def on_status(jid: str, status: str):
            if shown.get(jid) != status:
                shown[jid] = status

        jobs = client.wait_for_jobs(all_job_ids, on_status=on_status, timeout=600)
        completed = [j for j in jobs if j.is_completed]

        from .generate import _download_image
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        for j in completed:
            if j.download_url:
                _download_image(j, out_dir)

        console.print(f"\n  [green]{len(completed)} images downloaded[/green]")


# ------------------------------------------------------------------
# free-gens - show free generation counts
# ------------------------------------------------------------------

@click.command(name="free-gens")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def free_gens(json_output: bool):
    """Show remaining free generation counts per model."""
    from rich.table import Table

    client = _get_client()
    data = client.get_free_gens()

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(data))
        return

    table = Table(title="Free Generations")
    table.add_column("Model", style="cyan")
    table.add_column("Remaining", justify="right")

    # Sort: non-zero first, then by count desc
    items = sorted(data.items(), key=lambda x: (-x[1], x[0]))
    for model_type, count in items:
        if count > 0:
            table.add_row(model_type.replace("_", " "), f"[green]{count}[/green]")
        else:
            table.add_row(f"[dim]{model_type.replace('_', ' ')}[/dim]", "[dim]0[/dim]")

    console.print(table)
