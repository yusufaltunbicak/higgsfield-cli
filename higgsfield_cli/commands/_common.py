"""Shared helpers for CLI commands."""

from __future__ import annotations

import sys

import click

from ..auth import get_token
from ..client import HiggsClient
from ..exceptions import HiggsError, error_code_for_exception
from ..serialization import error_json, is_piped, to_json_envelope


def _get_client() -> HiggsClient:
    token = get_token()
    return HiggsClient(token)


def _wants_json(ctx: click.Context) -> bool:
    return ctx.params.get("json_output", False) or is_piped()


def _handle_api_error(func):
    """Decorator to catch API errors and show structured output."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HiggsError as exc:
            code = error_code_for_exception(exc)
            ctx = click.get_current_context(silent=True)
            if ctx and _wants_json(ctx):
                click.echo(error_json(code, str(exc)))
            else:
                from ..formatter import console
                console.print(f"  [red]Error:[/red] {exc}")
            sys.exit(1)
        except KeyboardInterrupt:
            sys.exit(130)

    return wrapper
