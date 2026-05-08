# Python Packaging Research

**Project:** AgentMesh SDK
**Researched:** 2026-04-04
**Scope:** PyPI packaging conventions, binary embedding, CLI tooling

---

## 1. Python SDK Packaging Conventions (2025/2026)

### 1.1 pyproject.toml vs setup.py

**Recommendation: pyproject.toml only. No setup.py.**

`setup.py` is legacy. The Python Packaging Authority now declares `pyproject.toml` the standard for all new projects. `setup.py` is only needed when building C extensions that require programmatic configuration at build time. AgentMesh has no C extensions.

Confidence: HIGH — PyPA official documentation

### 1.2 Build Backend: Hatchling

**Recommendation: Hatchling.**

| Backend | When to Use | Notes |
|---------|-------------|-------|
| `hatchling` | Open-source SDKs needing build hooks, VCS versioning, or file control | Best balance of capability and config; PyPA-recommended as the modern default |
| `uv_build` | Internal/simple pure-Python projects | Zero-config, fastest; but tighter coupling to the `uv` tool chain |
| `flit-core` | Tiny pure-Python libraries with no custom build steps | Minimalistic, no hooks, not suitable for binary embedding |
| `poetry-core` | Projects already using Poetry for dependency management | Use only if team is already Poetry-native |

AgentMesh needs build hooks to handle the `py.typed` marker and potential binary download script. **Hatchling** is the correct choice.

`uv_build` would be ideal for a simple library, but the binary embedding adds enough complexity that hatchling's build hooks and granular package-data control are worth it. The two can be swapped later with no application code changes since the interface is PEP 517 standard.

Confidence: HIGH — multiple authoritative sources agree; uv docs, PyPA guide, Medium build backend comparison article

### 1.3 Project Layout: src layout

**Recommendation: `src/agentmesh/` layout.**

```
agentmesh/                     # repo root
├── src/
│   └── agentmesh/
│       ├── __init__.py
│       ├── py.typed           # PEP 561 marker (empty file)
│       ├── mesh.py            # AgentMesh class
│       ├── agent.py           # @mesh.agent decorator
│       ├── contract.py        # AgentContract model
│       ├── discovery.py       # catalog/discover
│       ├── local.py           # AgentMesh.local() — embedded NATS
│       ├── _binary.py         # binary download/management
│       └── cli/
│           ├── __init__.py
│           └── main.py        # agentmesh CLI entry point
├── tests/
├── examples/
├── pyproject.toml
├── LICENSE
└── README.md
```

**Why src layout matters:** Without it, `import agentmesh` during development resolves to the local directory instead of the installed package. Tests then run against un-installed code, masking packaging bugs. The src layout forces install before import, which catches issues early.

Confidence: HIGH — PyPA guide, uv/hatch documentation, Scientific Python development guide all recommend src layout.

### 1.4 Minimum Viable pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agentmesh"
version = "0.1.0"
description = "NATS-based protocol and Python SDK for agent-to-agent communication"
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.10"
keywords = ["nats", "agents", "messaging", "ai", "sdk"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Typing :: Typed",
]
dependencies = [
    "nats-py>=2.7.0",
    "pydantic>=2.0",
    "typer>=0.12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "mypy>=1.8",
    "ruff>=0.3",
]

[project.scripts]
agentmesh = "agentmesh.cli.main:app"

[project.urls]
Homepage = "https://github.com/your-org/agentmesh"
Repository = "https://github.com/your-org/agentmesh"
Issues = "https://github.com/your-org/agentmesh/issues"

[tool.hatch.build.targets.wheel]
packages = ["src/agentmesh"]

[tool.hatch.build.targets.wheel.shared-data]
# no shared data needed unless bundling binaries into the wheel

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.10"
strict = true
packages = ["agentmesh"]
```

### 1.5 Entry Points for CLI Commands

The `[project.scripts]` table creates shell executables at install time. Each entry maps a command name to a Python callable:

```toml
[project.scripts]
agentmesh = "agentmesh.cli.main:app"
```

This installs the `agentmesh` binary (e.g. at `~/.local/bin/agentmesh` or `.venv/bin/agentmesh`) which calls `agentmesh.cli.main.app()` — the Typer app object.

Sub-commands (`up`, `status`, `init`) are registered on the same Typer app object, not as separate entry points:

```python
# src/agentmesh/cli/main.py
import typer
app = typer.Typer(name="agentmesh", help="AgentMesh CLI")

@app.command()
def up(...): ...

@app.command()
def status(...): ...

@app.command()
def init(...): ...
```

This means `agentmesh up`, `agentmesh status`, `agentmesh init` all work automatically.

### 1.6 Type Stubs and py.typed

**Recommendation: inline types + empty `py.typed` marker file.**

PEP 561 defines three distribution methods:
1. **Inline types** — type annotations in `.py` files, `py.typed` marker present. Simplest; best for a new SDK.
2. **In-package stubs** — `.pyi` stub files alongside `.py` files. Use only if the implementation is too complex to annotate directly.
3. **Stub-only package** — separate `agentmesh-stubs` package. Use only for third-party libraries you don't control.

For AgentMesh, inline types (option 1) is correct. The only required step is placing an **empty file** named `py.typed` inside `src/agentmesh/`:

```bash
touch src/agentmesh/py.typed
```

Hatchling automatically includes all files in the package directory, including `py.typed`, when the wheel is built. No additional configuration needed.

This makes `mypy --strict` and pyright work out of the box for downstream users.

Confidence: HIGH — PEP 561 spec, Hatchling documentation

### 1.7 Publishing Workflow

**Recommendation: uv for all build/publish operations.**

```bash
# Build
uv build              # produces dist/agentmesh-0.1.0.tar.gz and dist/agentmesh-0.1.0-py3-none-any.whl

# Test publish (always first)
uv publish --index testpypi

# Production publish
UV_PUBLISH_TOKEN=pypi-... uv publish
```

Using `uv publish` with OIDC tokens in CI (GitHub Actions) eliminates the need to store long-lived PyPI tokens as secrets.

---

## 2. Embedding a Binary in a Python Package

### 2.1 Download-at-First-Use Pattern (Recommended)

**Do not bundle the NATS server binary in the wheel.** Bundle size, platform-specific wheel complexity, license complications, and the need to update the binary independently of the SDK all argue against bundling.

The correct pattern — used by Playwright, Terraform wrappers, and hashicorp tooling — is **download at first use**:

1. On first call to `AgentMesh.local()`, check for the binary at `~/.agentmesh/bin/nats-server` (or `nats-server.exe` on Windows).
2. If not present, download from GitHub releases, verify the checksum, extract, and `chmod +x`.
3. On subsequent calls, re-use the cached binary.

This keeps the wheel tiny (`py3-none-any` instead of platform-specific), avoids PyPI wheel per-platform complexity, and allows users to pin or override the NATS version independently.

### 2.2 NATS Server Download URLs

Current latest release: **v2.12.6** (March 2026, as of research date).

URL pattern (confirmed from GitHub API):
```
https://github.com/nats-io/nats-server/releases/download/{version}/nats-server-{version}-{os}-{arch}.tar.gz
```

| Platform | `sys.platform` | `platform.machine()` | Archive filename |
|----------|----------------|---------------------|------------------|
| macOS x86_64 | `darwin` | `x86_64` | `nats-server-{ver}-darwin-amd64.tar.gz` |
| macOS arm64 | `darwin` | `arm64` | `nats-server-{ver}-darwin-arm64.tar.gz` |
| Linux x86_64 | `linux` | `x86_64` | `nats-server-{ver}-linux-amd64.tar.gz` |
| Linux arm64 | `linux` | `aarch64` | `nats-server-{ver}-linux-arm64.tar.gz` |
| Windows x86_64 | `win32` | `AMD64` | `nats-server-{ver}-windows-amd64.zip` |
| Windows arm64 | `win32` | `ARM64` | `nats-server-{ver}-windows-arm64.zip` |

Note: Windows archives are `.zip`; macOS and Linux are `.tar.gz`. The binary inside the archive is named `nats-server` (POSIX) or `nats-server.exe` (Windows).

### 2.3 Implementation Pattern

```python
# src/agentmesh/_binary.py

import os
import sys
import stat
import tarfile
import zipfile
import platform
import tempfile
import hashlib
import urllib.request
from pathlib import Path

NATS_VERSION = "v2.12.6"
BIN_DIR = Path.home() / ".agentmesh" / "bin"


def _platform_key() -> tuple[str, str]:
    """Returns (os_name, arch) tuple matching NATS release naming."""
    machine = platform.machine().lower()
    arch_map = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    arch = arch_map.get(machine)
    if arch is None:
        raise RuntimeError(f"Unsupported architecture: {machine!r}")

    if sys.platform == "darwin":
        return "darwin", arch
    elif sys.platform.startswith("linux"):
        return "linux", arch
    elif sys.platform == "win32":
        # Windows uses uppercase in platform.machine()
        win_arch = "amd64" if machine in ("amd64", "x86_64") else "arm64"
        return "windows", win_arch
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform!r}")


def _binary_path() -> Path:
    os_name, _ = _platform_key()
    name = "nats-server.exe" if os_name == "windows" else "nats-server"
    return BIN_DIR / name


def _archive_name(version: str) -> str:
    os_name, arch = _platform_key()
    ext = "zip" if os_name == "windows" else "tar.gz"
    return f"nats-server-{version}-{os_name}-{arch}.{ext}"


def _download_url(version: str) -> str:
    archive = _archive_name(version)
    return (
        f"https://github.com/nats-io/nats-server/releases/download/"
        f"{version}/{archive}"
    )


def _extract(archive_path: Path, dest_dir: Path) -> None:
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                if member.endswith("nats-server.exe"):
                    zf.extract(member, dest_dir)
                    # Move to flat dest_dir
                    extracted = dest_dir / member
                    extracted.rename(dest_dir / "nats-server.exe")
                    break
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("nats-server"):
                    member.name = "nats-server"  # strip directory prefix
                    tf.extract(member, dest_dir)
                    break


def ensure_nats_binary(version: str = NATS_VERSION) -> Path:
    """Return path to nats-server binary, downloading if necessary."""
    binary = _binary_path()
    if binary.exists():
        return binary

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    url = _download_url(version)

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        print(f"Downloading NATS server {version}...")
        urllib.request.urlretrieve(url, tmp_path)  # noqa: S310
        _extract(tmp_path, BIN_DIR)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Set executable bit on POSIX
    if sys.platform != "win32":
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return binary
```

Key decisions in this implementation:
- **`urllib.request` only** — no dependency on `requests` or `httpx`; these are not guaranteed to be installed and adding them as a dependency for a download-once operation is wasteful.
- **`stat.S_IEXEC` etc.** — explicit bitmask is clearer than `0o755`; it only adds execute bits without wiping existing permissions.
- **Flat extraction** — strip the directory prefix inside the archive so the binary lands at `~/.agentmesh/bin/nats-server` directly.
- **`tempfile.NamedTemporaryFile`** — the download goes to a temp file, not directly to the destination. This prevents a corrupt partial download from being cached.

### 2.4 Running NATS Server as a Subprocess (Async)

For `AgentMesh.local()`, the NATS server runs as a managed subprocess inside the same Python process. The correct pattern uses `asyncio.create_subprocess_exec` so it does not block the event loop.

```python
# src/agentmesh/local.py

import asyncio
import sys
import tempfile
from pathlib import Path
from agentmesh._binary import ensure_nats_binary


class EmbeddedNATSServer:
    """Manages a local nats-server subprocess for development."""

    def __init__(self, port: int = 4222, store_dir: Path | None = None) -> None:
        self._port = port
        self._store_dir = store_dir or Path(tempfile.mkdtemp(prefix="agentmesh-js-"))
        self._process: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        binary = ensure_nats_binary()
        cmd = [
            str(binary),
            "--port", str(self._port),
            "--jetstream",
            "--store_dir", str(self._store_dir),
        ]
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Give NATS a moment to start and listen
        await asyncio.sleep(0.2)
        if self._process.returncode is not None:
            stderr = await self._process.stderr.read()
            raise RuntimeError(
                f"NATS server failed to start: {stderr.decode()}"
            )

    async def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()
        self._process = None

    @property
    def url(self) -> str:
        return f"nats://localhost:{self._port}"
```

Key decisions:
- **`create_subprocess_exec`** (not `create_subprocess_shell`) — prevents shell injection if any argument ever comes from user input.
- **`terminate()` then `kill()` fallback** — NATS handles SIGTERM gracefully for clean shutdown; `kill()` is the last resort after a 5-second timeout.
- **`asyncio.sleep(0.2)`** — a short yield lets the NATS server bind its port before the caller attempts a NATS client connection. A more robust approach is to poll the connection (retry `nats.connect()` up to N times), but 200ms is sufficient for the dev-only embedded case.
- **Dedicated temp dir for JetStream store** — JetStream requires a store dir; using a temp dir means state is not persisted across restarts, which is correct behavior for a dev-only server.

### 2.5 Logging Subprocess Output

For debugging, optionally drain stdout/stderr into Python logging without blocking:

```python
async def _drain_logs(stream: asyncio.StreamReader, prefix: str) -> None:
    import logging
    logger = logging.getLogger("agentmesh.nats-server")
    async for line in stream:
        logger.debug("%s %s", prefix, line.decode().rstrip())

# In start():
asyncio.create_task(_drain_logs(self._process.stdout, "[nats-out]"))
asyncio.create_task(_drain_logs(self._process.stderr, "[nats-err]"))
```

---

## 3. CLI Tooling

### 3.1 Library Choice: Typer

**Recommendation: Typer with `asyncio.run()` wrapper pattern.**

| Library | Pros | Cons | Verdict |
|---------|------|------|---------|
| **Typer** | Type-hint driven, minimal boilerplate, automatic `--help`, pairs naturally with Pydantic-centric code | No native async support; workaround required | **Use this** |
| **Click** | Most widely used (38.7% of CLI projects), excellent documentation, mature plugin ecosystem | More boilerplate than Typer; no native async | Viable but more verbose |
| **argparse** | Zero dependencies, stdlib | No decorator API; much more boilerplate for subcommands | Avoid for user-facing SDK CLI |

Typer's type-hint–driven API matches AgentMesh's Pydantic-centric codebase well. The async workaround is a one-time 4-line pattern per command, not a recurring cost.

Confidence: MEDIUM — WebSearch, multiple comparison articles from 2025. The recommendation that Typer "handles async automatically" in some sources appears to be from informal summaries rather than official docs. The official async status is: **not natively supported**; the `asyncio.run()` wrapper is the documented workaround.

### 3.2 Async Support Pattern

Typer does not natively support `async def` command functions. The canonical workaround, confirmed via the official Typer GitHub discussions:

```python
# src/agentmesh/cli/main.py

import asyncio
import typer
from typing import Optional

app = typer.Typer(name="agentmesh", help="AgentMesh local development tools")


@app.command()
def up(
    port: int = typer.Option(4222, "--port", "-p", help="NATS port"),
) -> None:
    """Start a local NATS server with JetStream enabled."""
    asyncio.run(_up(port))


async def _up(port: int) -> None:
    from agentmesh.local import EmbeddedNATSServer
    server = EmbeddedNATSServer(port=port)
    await server.start()
    typer.echo(f"NATS server running on nats://localhost:{port}")
    typer.echo("Press Ctrl+C to stop.")
    try:
        await asyncio.sleep(float("inf"))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await server.stop()


@app.command()
def status() -> None:
    """Show registered agents and health status."""
    asyncio.run(_status())


async def _status() -> None:
    import nats
    try:
        nc = await nats.connect("nats://localhost:4222", connect_timeout=2)
    except Exception:
        typer.echo("No NATS server reachable at nats://localhost:4222", err=True)
        raise typer.Exit(1)
    # ... display status
    await nc.close()
```

The pattern is:
- Sync `@app.command()` function with `asyncio.run(_impl(...))` as the body
- Private `async def _impl(...)` function that does the actual work
- This is not an extra file; both live in the same module

**Why not `async-typer`?** It's a third-party package (latest 0.1.10, August 2025), adds a dependency, and the pattern above is 4 lines of overhead. For a project that controls its own CLI, the inline `asyncio.run()` approach is simpler and dependency-free.

### 3.3 Typer App Structure for Multiple Subcommands

```python
# src/agentmesh/cli/main.py

app = typer.Typer(
    name="agentmesh",
    help="AgentMesh local development tools",
    no_args_is_help=True,          # print help when called with no args
    rich_markup_mode="rich",       # enable Rich formatting in help text (if rich installed)
)

# Register commands
@app.command()
def up(...): ...

@app.command()
def status(...): ...

@app.command()
def init(...): ...

# The entry point
def main() -> None:
    app()
```

The `[project.scripts]` entry in `pyproject.toml` should point to `main()`:

```toml
[project.scripts]
agentmesh = "agentmesh.cli.main:main"
```

### 3.4 Rich Output (Optional)

Typer automatically uses [Rich](https://github.com/Textualize/rich) for colored help text and error messages if `rich` is installed. It is listed as an optional dependency of Typer itself. For AgentMesh:

```toml
[project.optional-dependencies]
cli = ["rich>=13.0"]
```

Do not make `rich` a required dependency — it adds 5MB and 70+ transitive lines for users who only use the programmatic SDK API, not the CLI.

---

## 4. Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| pyproject.toml / hatchling | HIGH | Official PyPA docs, multiple verified sources |
| src layout | HIGH | Universal recommendation across all authoritative sources |
| py.typed / PEP 561 | HIGH | Spec is clear; hatchling includes it automatically |
| NATS binary URL pattern | HIGH | Verified directly from GitHub API (live check on v2.12.6) |
| Binary download pattern | MEDIUM | Pattern is well-established (Playwright, Terraform wrappers); specific code is original |
| asyncio subprocess | HIGH | Python stdlib docs; standard patterns |
| Typer async workaround | MEDIUM | GitHub discussions confirmed the `asyncio.run()` pattern; "native async" claims in some articles appear inaccurate |
| uv publish workflow | MEDIUM | Official uv docs + community articles; not personally verified end-to-end |

---

## 5. Key Implementation Decisions for AgentMesh

### Decision 1: Wheel type

Publish as `py3-none-any` (universal pure-Python wheel). Do NOT publish platform-specific wheels. The NATS binary is downloaded lazily at runtime, not bundled. This keeps the PyPI package simple and avoids the 6-wheel publishing matrix (darwin-arm64, darwin-amd64, linux-amd64, linux-arm64, windows-amd64, windows-arm64).

### Decision 2: Binary version pinning

Pin `NATS_VERSION = "v2.12.6"` as a constant in `_binary.py`. Allow override via `AGENTMESH_NATS_VERSION` environment variable for testing against different versions:

```python
NATS_VERSION = os.environ.get("AGENTMESH_NATS_VERSION", "v2.12.6")
```

### Decision 3: Binary location

`~/.agentmesh/bin/nats-server` — follows the XDG-adjacent pattern of putting user-managed binaries under a tool-specific home directory (same as `~/.cargo/bin`, `~/.local/bin`, etc.). Not in the virtualenv, so the binary persists across `pip install --upgrade agentmesh`.

### Decision 4: No checksum verification in v0.1

Checksum verification (SHA256SUMS file is published alongside each NATS release) is a security best practice but adds complexity. Defer to a post-MVP phase. Document this as a known gap.

### Decision 5: `AgentMesh.local()` is dev-only

The embedded NATS pattern is explicitly not for production. Add a `DeprecationWarning`-style notice in the docstring. Production users should run NATS via Docker or the `agentmesh up` CLI command against a persistent server.

---

## 6. Sources

- [Writing your pyproject.toml — Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [Packaging Python Projects — Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [Python Build Backends in 2025: uv_build vs Hatchling vs poetry-core](https://medium.com/@dynamicy/python-build-backends-in-2025-what-to-use-and-why-uv-build-vs-hatchling-vs-poetry-core-94dd6b92248f)
- [Creating and packaging command-line tools](https://packaging.python.org/en/latest/guides/creating-command-line-tools/)
- [PEP 561 — Distributing and Packaging Type Information](https://peps.python.org/pep-0561/)
- [Building and publishing a package — uv docs](https://docs.astral.sh/uv/guides/package/)
- [Typer features](https://typer.tiangolo.com/features/)
- [On using Asyncio — Typer GitHub Discussion #864](https://github.com/fastapi/typer/discussions/864)
- [async-typer on PyPI](https://pypi.org/project/async-typer/)
- [Playwright Python installation and setup](https://deepwiki.com/microsoft/playwright-python/2-installation-and-setup)
- [NATS server releases — GitHub](https://github.com/nats-io/nats-server/releases)
- [asyncio subprocesses — Python docs](https://docs.python.org/3/library/asyncio-subprocess.html)
- [NATS server flags documentation](https://docs.nats.io/running-a-nats-service/introduction/flags)
