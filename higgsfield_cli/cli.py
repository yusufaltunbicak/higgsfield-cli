"""Higgsfield CLI entry point - command registration only."""

from __future__ import annotations

import click

from .commands import (
    account as account_mod,
    auth as auth_mod,
    enhance as enhance_mod,
    extras as extras_mod,
    generate as generate_mod,
    history as history_mod,
)
from .formatter import console

BANNER = r"""
 ╦ ╦┬┌─┐┌─┐┌─┐┌─┐┬┌─┐┬  ┌┬┐
 ╠═╣││ ┬│ ┬└─┐├┤ │├┤ │   ││
 ╩ ╩┴└─┘└─┘└─┘└  ┴└─┘┴─┘─┴┘
"""


class HiggsGroup(click.Group):
    def format_help(self, ctx, formatter):
        console.print(f"[bold magenta]{BANNER}[/bold magenta]", highlight=False)
        console.print("  [dim]AI image generation from your terminal[/dim]")
        console.print()
        super().format_help(ctx, formatter)


@click.group(cls=HiggsGroup, invoke_without_command=True)
@click.version_option(package_name="higgsfield-cli")
@click.pass_context
def cli(ctx: click.Context):
    """Higgsfield CLI - generate AI images from the terminal."""
    if ctx.invoked_subcommand is None and not ctx.resilient_parsing:
        click.echo(ctx.get_help())


# Auth
cli.add_command(auth_mod.login)
cli.add_command(auth_mod.whoami)

# Generation
cli.add_command(generate_mod.generate)
cli.add_command(extras_mod.again)
cli.add_command(extras_mod.batch)
cli.add_command(extras_mod.use)

# Enhancement
cli.add_command(enhance_mod.upscale)
cli.add_command(enhance_mod.relight)
cli.add_command(enhance_mod.outpaint)

# History & download
cli.add_command(history_mod.history)
cli.add_command(history_mod.status)
cli.add_command(history_mod.download)
cli.add_command(extras_mod.watch)
cli.add_command(extras_mod.open_cmd)

# Management
cli.add_command(extras_mod.delete)
cli.add_command(extras_mod.favorite)

# Account
cli.add_command(account_mod.credits)
cli.add_command(account_mod.models)
cli.add_command(extras_mod.free_gens)
