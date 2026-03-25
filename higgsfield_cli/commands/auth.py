"""Auth commands: login, whoami."""

from __future__ import annotations

import click

from .. import auth as auth_service
from ..formatter import console, print_user_info
from ._common import _get_client, _handle_api_error, _wants_json

from ..serialization import to_json_envelope


@click.command()
@click.option("--with-token", "token", default=None, help="JWT token (short-lived, for testing)")
@click.option("--json", "json_output", is_flag=True, hidden=True)
@_handle_api_error
def login(token: str | None, json_output: bool):
    """Authenticate with Higgsfield.

    Paste your browser cookies for persistent auth (recommended):

    \b
    1. Open higgsfield.ai in Chrome
    2. Press Cmd+Option+J (Console)
    3. Type: document.cookie
    4. Copy the output and paste here

    This is a one-time setup. The CLI will auto-refresh tokens.
    """
    if token is not None:
        # Direct JWT token (expires in 60s, not recommended)
        saved = auth_service.login_with_token(token)
        payload = auth_service.decode_jwt_payload(saved)
        console.print(f"  [green]Logged in as {payload.get('email', 'unknown')}[/green]")
        console.print(f"  [yellow]Warning: This token expires in ~60s.[/yellow]")
        console.print(f"  [yellow]Run 'higgsfield login' (without --with-token) for persistent auth.[/yellow]")
        return

    # Cookie-based login (recommended)
    console.print("  [bold]Higgsfield Login[/bold]\n")
    console.print("  1. Open [cyan]higgsfield.ai[/cyan] in Chrome")
    console.print("  2. Open Console ([dim]Cmd+Option+J[/dim])")
    console.print("  3. Type: [cyan]document.cookie[/cyan]")
    console.print("  4. Copy the output and paste below\n")

    cookie_string = click.prompt("  Cookies", hide_input=False)

    saved = auth_service.login_with_cookies(cookie_string)
    payload = auth_service.decode_jwt_payload(saved)

    console.print(f"\n  [green]Logged in as {payload.get('email', 'unknown')}[/green]")
    console.print(f"  Session saved. Tokens will auto-refresh.")
    console.print(f"  You won't need to do this again until the session expires.")


@click.command()
@click.option("--json", "json_output", is_flag=True, help="JSON output")
@_handle_api_error
def whoami(json_output: bool):
    """Show current user info and credits."""
    client = _get_client()
    user = client.get_user()
    wallet = client.get_wallet()

    ctx = click.get_current_context()
    if _wants_json(ctx):
        click.echo(to_json_envelope({"user": user, "wallet": wallet}))
    else:
        print_user_info(user, wallet)
