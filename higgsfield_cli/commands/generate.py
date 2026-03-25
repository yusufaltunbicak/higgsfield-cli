"""Generate command - create images."""

from __future__ import annotations

from pathlib import Path

import click
import httpx

from .. import config as cfg
from ..constants import ASPECT_RATIOS, DEFAULT_MODEL, MODELS, QUALITIES, RESOLUTIONS
from ..exceptions import HiggsError
from ..formatter import console, print_generation_progress, print_job_detail, print_jobs
from ..serialization import to_json_envelope
from ._common import _get_client, _handle_api_error, _wants_json


@click.command()
@click.argument("prompt")
@click.option(
    "-m", "--model",
    type=click.Choice(list(MODELS.keys()), case_sensitive=False),
    default=None,
    help="Model to use",
)
@click.option(
    "-r", "--resolution",
    type=click.Choice(RESOLUTIONS, case_sensitive=False),
    default=None,
    help="Image resolution (nano-banana models)",
)
@click.option(
    "-q", "--quality",
    type=click.Choice(QUALITIES, case_sensitive=False),
    default=None,
    help="Image quality (seedream models)",
)
@click.option(
    "-a", "--aspect",
    type=click.Choice(list(ASPECT_RATIOS.keys())),
    default=None,
    help="Aspect ratio",
)
@click.option(
    "-b", "--batch",
    type=click.IntRange(1, 4),
    default=None,
    help="Number of images to generate",
)
@click.option("--seed", type=int, default=None, help="Random seed (seedream models)")
@click.option("--unlim", is_flag=True, help="Use unlimited mode")
@click.option("--no-wait", is_flag=True, help="Don't wait for completion")
@click.option(
    "-d", "--download",
    is_flag=True,
    help="Auto-download completed images",
)
@click.option(
    "-o", "--output",
    type=click.Path(),
    default=".",
    help="Output directory for downloads",
)
@click.option(
    "--attach", "-A",
    type=click.Path(exists=True),
    multiple=True,
    help="Attach reference image(s)",
)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def generate(
    prompt: str,
    model: str | None,
    resolution: str | None,
    quality: str | None,
    aspect: str | None,
    batch: int | None,
    seed: int | None,
    unlim: bool,
    no_wait: bool,
    download: bool,
    output: str,
    attach: tuple[str, ...],
    yes: bool,
    json_output: bool,
):
    """Generate images from a text prompt.

    Examples:

        higgsfield generate "a red apple on a white table"

        higgsfield generate "sunset over mountains" -m seedream-v4.5 -q high

        higgsfield generate "portrait" -a 9:16 -b 2 --download
    """
    # Apply config defaults for unset options
    conf = cfg.load_config()
    model = model or conf.get("model", DEFAULT_MODEL)
    resolution = resolution or conf.get("resolution", "4k")
    quality = quality or conf.get("quality", "high")
    aspect = aspect or conf.get("aspect_ratio", "16:9")
    batch = batch if batch is not None else conf.get("batch_size", 4)
    if conf.get("auto_download") and not download:
        download = True
    output = output if output != "." else conf.get("output_dir", ".")

    ctx = click.get_current_context()
    client = _get_client()

    # Upload attached images
    input_images = []
    if attach:
        for file_path in attach:
            console.print(f"  Uploading {Path(file_path).name}...")
            media = client.upload_image(Path(file_path))
            input_images.append(media)
            console.print(f"  [green]Uploaded[/green]")

    # Confirmation
    if not yes and not _wants_json(ctx):
        console.print(f"\n  [bold]Generate Images[/bold]")
        console.print(f"  Model:      {model}")
        console.print(f"  Prompt:     {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
        if "seedream" in model:
            console.print(f"  Quality:    {quality}")
        else:
            console.print(f"  Resolution: {resolution}")
        console.print(f"  Aspect:     {aspect}")
        console.print(f"  Batch:      {batch}")
        if seed is not None:
            console.print(f"  Seed:       {seed}")
        if input_images:
            console.print(f"  Attachments: {len(input_images)} image(s)")
        console.print()

        if not click.confirm("  Proceed?", default=True):
            raise SystemExit(0)

    # Generate - try direct API first, fallback to Chrome bridge on 403
    resp = None
    job_ids = []
    try:
        resp = client.generate(
            prompt=prompt,
            model=model,
            resolution=resolution,
            quality=quality,
            aspect_ratio=aspect,
            batch_size=batch,
            seed=seed,
            use_unlim=unlim,
            input_images=input_images,
        )
        job_ids = resp.all_job_ids
    except (HiggsError, httpx.HTTPStatusError) as exc:
        is_datadome = (
            isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 403
        ) or "DataDome" in str(exc) or "Forbidden" in str(exc)

        if not is_datadome:
            raise

        # DataDome blocked - use Chrome bridge
        from ..chrome_bridge import generate_via_chrome, is_available
        if not is_available():
            raise
        console.print("  [yellow]Using Chrome bridge (DataDome bypass)...[/yellow]")
        url_slug = MODELS[model][0]
        generate_via_chrome(
            prompt=prompt,
            model_slug=url_slug,
            resolution=resolution,
            quality=quality,
            aspect_ratio=aspect,
            batch_size=batch,
            use_unlim=unlim,
        )
        # Wait for job to appear in history
        console.print("  Submitted via Chrome. Polling for new job...")
        import time
        time.sleep(5)
        history = client.get_history(size=5)
        new_jobs = [j for j in history if j.prompt and prompt[:20] in j.prompt]
        if new_jobs:
            job_ids = [j.id for j in new_jobs]
            console.print(f"  [green]Found {len(job_ids)} job(s)[/green]")
        else:
            console.print("  [yellow]Job submitted but not found in history yet. Run 'higgsfield watch --all'[/yellow]")
            return

    if _wants_json(ctx) and no_wait:
        click.echo(to_json_envelope(resp if resp is not None else {"job_ids": job_ids}))
        return

    console.print(f"  [green]Created {len(job_ids)} job(s)[/green]")
    for jid in job_ids:
        console.print(f"  {jid}")

    if no_wait:
        return

    # Wait for completion
    console.print(f"\n  Waiting for completion...")

    shown_status: dict[str, str] = {}

    def on_status(jid: str, status: str):
        prev = shown_status.get(jid)
        if prev != status:
            shown_status[jid] = status
            print_generation_progress(jid, status)

    jobs = client.wait_for_jobs(job_ids, on_status=on_status)

    if _wants_json(ctx):
        click.echo(to_json_envelope(jobs))
        return

    # Show results
    completed = [j for j in jobs if j.is_completed]
    failed = [j for j in jobs if j.status in ("failed", "error")]

    console.print(f"\n  [green]{len(completed)} completed[/green]", end="")
    if failed:
        console.print(f", [red]{len(failed)} failed[/red]")
    else:
        console.print()

    for job in completed:
        if job.results and job.results.raw_url:
            console.print(f"  #{job.display_num} [link={job.results.raw_url}]{job.results.raw_url}[/link]")

    # Download
    if download and completed:
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"\n  Downloading to {out_dir.absolute()}...")

        for job in completed:
            if not job.download_url:
                continue
            _download_image(job, out_dir)


def _download_image(job, out_dir: Path) -> None:
    url = job.download_url
    ext = ".png" if ".png" in url else ".jpeg" if ".jpeg" in url else ".webp"
    filename = f"higgsfield_{job.id[:8]}{ext}"
    filepath = out_dir / filename

    try:
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        filepath.write_bytes(resp.content)
        size_mb = len(resp.content) / (1024 * 1024)
        console.print(f"  [green]Saved[/green] {filename} ({size_mb:.1f} MB)")
    except Exception as exc:
        console.print(f"  [red]Failed[/red] {filename}: {exc}")
