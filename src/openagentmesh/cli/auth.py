"""`oam auth` commands: credential identity and management (ADR-0038)."""

from __future__ import annotations

from pathlib import Path

import typer

from .._auth import read_user_jwt_claims, resolve_creds

auth_app = typer.Typer(
    name="auth",
    help="Manage and inspect mesh credentials.",
    no_args_is_help=True,
)


@auth_app.command("whoami")
def whoami(
    creds_flag: str | None = typer.Option(
        None, "--creds", help="Credentials file to inspect (overrides OAM_CREDS/.oam-url)."
    ),
) -> None:
    """Report the identity the CLI would connect with."""
    creds = resolve_creds(creds_flag)
    if creds is None:
        typer.echo("No credentials configured; connecting open (anonymous).")
        typer.echo("Set creds via `oam mesh connect <url> --creds <file>` or OAM_CREDS.")
        return

    creds_path = Path(creds)
    if not creds_path.is_file():
        typer.echo(f"Credentials file not found: {creds}", err=True)
        raise typer.Exit(1)

    try:
        claims = read_user_jwt_claims(creds_path)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"user:    {claims.get('name', '?')}")
    typer.echo(f"nkey:    {claims.get('sub', '?')}")
    typer.echo(f"account: {claims.get('iss', '?')}")
    typer.echo(f"creds:   {creds}")


__all__ = ["auth_app"]
