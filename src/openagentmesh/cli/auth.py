"""`oam auth` commands: credential management wrapping nsc (ADR-0038).

`oam auth init` bootstraps an isolated nsc store under `.oam/` (operator with
a system account, one application account with JetStream enabled) and emits a
ready-to-run server config with a memory resolver. `user add` mints
role-templated credentials; `user revoke` revokes a user and regenerates the
config. Everything is standard NATS material — any nsc/NATS tooling can take
over the store.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import typer

from .._auth import read_user_jwt_claims, resolve_creds
from .._local import NATS_BIN_DIR

auth_app = typer.Typer(
    name="auth",
    help="Manage and inspect mesh credentials.",
    no_args_is_help=True,
)

user_app = typer.Typer(name="user", help="Manage mesh users.", no_args_is_help=True)
auth_app.add_typer(user_app, name="user")

DEFAULT_DIR = ".oam"

# Role templates (ADR-0038 §5, subjects corrected against actual SDK wire
# usage — see the ADR's implementation notes). Buckets are named explicitly so
# a credential never grants access to KV/Object buckets OAM does not own.
_MESH_BUCKET_SUBJECTS = [
    "$KV.mesh-catalog.>",
    "$KV.mesh-registry.>",
    "$KV.mesh-context.>",
    "$O.mesh-artifacts.>",
]

ROLE_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "worker": {
        "pub": ["mesh.>", "_INBOX.>", "$JS.API.>", *_MESH_BUCKET_SUBJECTS],
        "sub": ["mesh.>", "_INBOX.>", *_MESH_BUCKET_SUBJECTS],
    },
    "invoker": {
        "pub": ["mesh.agent.>", "_INBOX.>", "$JS.API.>"],
        "sub": [
            "_INBOX.>",
            "$KV.mesh-catalog.>",
            "$KV.mesh-registry.>",
            "mesh.agent.*.*.events",
        ],
    },
    "observer": {
        "pub": ["_INBOX.>", "$JS.API.>"],
        "sub": [
            "_INBOX.>",
            "$KV.mesh-catalog.>",
            "$KV.mesh-registry.>",
            "mesh.agent.*.*.events",
            "mesh.errors.>",
            "mesh.health.>",
        ],
    },
}


def find_nsc() -> Path | None:
    """Find nsc: prefer PATH, fall back to ~/.agentmesh/bin/ (like nats-server)."""
    path_binary = shutil.which("nsc")
    if path_binary:
        return Path(path_binary)
    local_binary = NATS_BIN_DIR / "nsc"
    if local_binary.exists():
        return local_binary
    return None


def _require_nsc() -> Path:
    nsc = find_nsc()
    if nsc is None:
        typer.echo(
            "nsc (the NATS credentials CLI) is required but was not found on PATH "
            "or in ~/.agentmesh/bin/.\n"
            "Install it: https://github.com/nats-io/nsc (e.g. `brew install nsc` "
            "or `go install github.com/nats-io/nsc/v2@latest`).",
            err=True,
        )
        raise typer.Exit(1)
    return nsc


def _nsc_env(oam_dir: Path) -> dict[str, str]:
    """Environment that pins nsc to an isolated store under `oam_dir`."""
    home = oam_dir / "nsc"
    env = dict(os.environ)
    env.update(
        {
            "NSC_HOME": str(home / "home"),
            "XDG_DATA_HOME": str(home / "data"),
            "XDG_CONFIG_HOME": str(home / "config"),
            "NKEYS_PATH": str(home / "keys"),
        }
    )
    return env


def _run_nsc(oam_dir: Path, *args: str) -> str:
    nsc = _require_nsc()
    result = subprocess.run(
        [str(nsc), *args],
        env=_nsc_env(oam_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        typer.echo(f"nsc {' '.join(args)} failed:\n{result.stderr}", err=True)
        raise typer.Exit(1)
    return result.stdout


def _read_account_name(oam_dir: Path) -> str:
    import tomllib

    auth_file = oam_dir / "auth.toml"
    if not auth_file.is_file():
        typer.echo(
            f"No {auth_file} found. Run `oam auth init --dir {oam_dir}` first.",
            err=True,
        )
        raise typer.Exit(1)
    return tomllib.loads(auth_file.read_text())["name"]


def _write_server_conf(oam_dir: Path) -> Path:
    conf = _run_nsc(oam_dir, "generate", "config", "--mem-resolver", "--sys-account", "SYS")
    target = oam_dir / "server.conf"
    target.write_text(
        conf
        + f'\njetstream {{ store_dir: "{oam_dir / "jetstream"}" }}\n'
    )
    return target


@auth_app.command("init")
def init(
    name: str = typer.Option("mesh", "--name", help="Operator and account name."),
    dir_flag: str = typer.Option(DEFAULT_DIR, "--dir", help="Directory for the credential store."),
) -> None:
    """Bootstrap a credential tree: operator + system account + app account.

    Emits a ready-to-run server config (memory resolver) into DIR/server.conf.
    """
    oam_dir = Path(dir_flag)
    if (oam_dir / "auth.toml").is_file():
        typer.echo(f"{oam_dir}/auth.toml already exists; refusing to re-init.", err=True)
        raise typer.Exit(1)
    oam_dir.mkdir(parents=True, exist_ok=True)

    _run_nsc(oam_dir, "add", "operator", "--name", name, "--sys")
    _run_nsc(oam_dir, "add", "account", "--name", name)
    _run_nsc(
        oam_dir, "edit", "account", name,
        "--js-mem-storage", "-1", "--js-disk-storage", "-1",
        "--js-streams", "-1", "--js-consumer", "-1",
    )
    conf_path = _write_server_conf(oam_dir)
    (oam_dir / "auth.toml").write_text(f'name = "{name}"\n')

    typer.echo(f"Created operator '{name}' (with SYS account) and account '{name}'.")
    typer.echo(f"Server config: {conf_path}")
    typer.echo("Next steps:")
    typer.echo(f"  nats-server -c {conf_path}")
    typer.echo("  oam auth user add <name> --role worker|invoker|observer")


@user_app.command("add")
def user_add(
    username: str = typer.Argument(..., help="User name, e.g. risk-pipeline."),
    role: str = typer.Option(..., "--role", help="Role template: worker, invoker, or observer."),
    dir_flag: str = typer.Option(DEFAULT_DIR, "--dir", help="Credential store directory."),
    out: str | None = typer.Option(None, "--out", help="Where to write the .creds file (default ./<name>.creds)."),
) -> None:
    """Create a user from a role template and write its .creds file."""
    if role not in ROLE_TEMPLATES:
        typer.echo(
            f"Unknown role '{role}'. Choose from: {', '.join(ROLE_TEMPLATES)}.", err=True
        )
        raise typer.Exit(1)
    oam_dir = Path(dir_flag)
    account = _read_account_name(oam_dir)
    template = ROLE_TEMPLATES[role]

    _run_nsc(
        oam_dir, "add", "user", "--account", account, "--name", username,
        "--allow-pub", ",".join(template["pub"]),
        "--allow-sub", ",".join(template["sub"]),
    )
    creds = _run_nsc(oam_dir, "generate", "creds", "--account", account, "--name", username)
    out_path = Path(out) if out else Path(f"./{username}.creds")
    out_path.write_text(creds)
    out_path.chmod(0o600)

    typer.echo(f"Created user '{username}' with role '{role}'.")
    typer.echo(f"Credentials: {out_path}")
    typer.echo(f"Use with: AgentMesh(url=..., creds=\"{out_path}\") or OAM_CREDS.")


@user_app.command("revoke")
def user_revoke(
    username: str = typer.Argument(..., help="User to revoke."),
    dir_flag: str = typer.Option(DEFAULT_DIR, "--dir", help="Credential store directory."),
) -> None:
    """Revoke a user and regenerate the server config (reload/restart to apply)."""
    oam_dir = Path(dir_flag)
    account = _read_account_name(oam_dir)
    _run_nsc(oam_dir, "revocations", "add-user", "--account", account, "--name", username)
    conf_path = _write_server_conf(oam_dir)
    typer.echo(f"Revoked user '{username}'.")
    typer.echo(f"Regenerated {conf_path}; reload or restart the server to apply.")


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


__all__ = ["auth_app", "find_nsc", "ROLE_TEMPLATES"]
