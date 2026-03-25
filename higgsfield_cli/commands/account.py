"""Account commands: credits, models."""

from __future__ import annotations

import click

from ..constants import MODELS
from ..formatter import console, print_credits, print_models
from ..serialization import to_json_envelope
from ._common import _get_client, _handle_api_error, _wants_json


@click.command()
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def credits(json_output: bool):
    """Show current credit balance."""
    client = _get_client()
    wallet = client.get_wallet()

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(wallet))
    else:
        print_credits(wallet)


@click.command()
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def models(json_output: bool):
    """List available image generation models."""
    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope(MODELS))
    else:
        print_models(MODELS)
