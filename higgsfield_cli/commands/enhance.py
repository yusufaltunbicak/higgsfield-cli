"""Enhancement commands: upscale, relight, outpaint.

These use specialized Higgsfield endpoints that take an existing image
as input and transform it. Exact API payloads are inferred from patterns
observed in the main generation endpoints.
"""

from __future__ import annotations

from pathlib import Path
import time

import click

from ..formatter import console, print_generation_progress
from ..serialization import to_json_envelope
from ._common import _get_client, _handle_api_error, _wants_json


def _enhance_job(
    client,
    job_id: str,
    endpoint: str,
    job_set_type: str,
    extra_params: dict | None = None,
    yes: bool = False,
    download: bool = False,
    output: str = ".",
    json_output: bool = False,
    label: str = "Enhance",
):
    """Shared logic for upscale/relight/outpaint."""
    source = client.get_job(job_id)

    if not source.is_completed or not source.download_url:
        console.print("  [red]Source job not completed or no image available[/red]")
        return

    if not yes:
        console.print(f"\n  [bold]{label}[/bold]")
        console.print(f"  Source: #{job_id} ({source.prompt[:40]})")
        console.print(f"  Image:  {source.download_url[:60]}...")
        console.print()
        if not click.confirm("  Proceed?", default=True):
            return

    # Build payload - uses source image as input
    params = {
        "prompt": source.prompt,
        "input_images": [{
            "data": {
                "id": source.id,
                "url": source.download_url,
                "type": "media_input",
            },
            "role": "image",
        }],
        "width": source.width,
        "height": source.height,
        "aspect_ratio": source.aspect_ratio or "1:1",
        "batch_size": 1,
    }
    if extra_params:
        params.update(extra_params)

    body = {
        "params": params,
        "use_unlim": False,
    }

    resp = client._post(endpoint, json=body)

    # Parse response like generate
    from ..models import GenerateResponse
    gen_resp = GenerateResponse.from_api(resp)
    job_ids = gen_resp.all_job_ids

    ctx = click.get_current_context()

    console.print(f"  [green]Created {len(job_ids)} job(s)[/green]")

    if _wants_json(ctx):
        click.echo(to_json_envelope(gen_resp))
        return

    # Wait
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


@click.command()
@click.argument("job_id")
@click.option("-y", "--yes", is_flag=True)
@click.option("-d", "--download", is_flag=True)
@click.option("-o", "--output", type=click.Path(), default=".")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def upscale(job_id: str, yes: bool, download: bool, output: str, json_output: bool):
    """Upscale a completed image to higher resolution.

    Examples:

        higgsfield upscale 1

        higgsfield upscale 1 --download -o ~/Pictures
    """
    client = _get_client()
    _enhance_job(
        client, job_id,
        endpoint="/jobs/v2/nano_banana_2_upscale",
        job_set_type="nano_banana_2_upscale",
        extra_params={"resolution": "4k"},
        yes=yes, download=download, output=output,
        json_output=json_output, label="Upscale",
    )


@click.command()
@click.argument("job_id")
@click.option("-y", "--yes", is_flag=True)
@click.option("-d", "--download", is_flag=True)
@click.option("-o", "--output", type=click.Path(), default=".")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def relight(job_id: str, yes: bool, download: bool, output: str, json_output: bool):
    """Relight a completed image with AI-adjusted lighting.

    Examples:

        higgsfield relight 1

        higgsfield relight 1 --download
    """
    client = _get_client()
    _enhance_job(
        client, job_id,
        endpoint="/jobs/v2/nano_banana_2_relight",
        job_set_type="nano_banana_2_relight",
        yes=yes, download=download, output=output,
        json_output=json_output, label="Relight",
    )


@click.command()
@click.argument("job_id")
@click.option("--direction", type=click.Choice(["left", "right", "up", "down", "all"]), default="all", help="Outpaint direction")
@click.option("-y", "--yes", is_flag=True)
@click.option("-d", "--download", is_flag=True)
@click.option("-o", "--output", type=click.Path(), default=".")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def outpaint(job_id: str, direction: str, yes: bool, download: bool, output: str, json_output: bool):
    """Extend an image by outpainting beyond its borders.

    Examples:

        higgsfield outpaint 1

        higgsfield outpaint 1 --direction right --download
    """
    client = _get_client()
    _enhance_job(
        client, job_id,
        endpoint="/jobs/v2/outpaint",
        job_set_type="outpaint",
        extra_params={"direction": direction},
        yes=yes, download=download, output=output,
        json_output=json_output, label="Outpaint",
    )
