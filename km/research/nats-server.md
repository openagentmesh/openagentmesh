# NATS Server Research: Embedded Mode, JetStream, and KV

**Project:** AgentMesh Python SDK
**Researched:** 2026-04-04
**Overall confidence:** HIGH (official docs + Go source validation)

---

## 1. Binary Download

### Current Version

Latest stable: **v2.12.6** (released 2026-03-24). The server is still on the 2.x line — there is no NATS Server 3.x. (Version 3.x seen in the ecosystem refers to client libraries, not the server.)

### GitHub Releases URL Pattern

```
https://github.com/nats-io/nats-server/releases/download/{version}/nats-server-{version}-{os}-{arch}.{ext}
```

| Platform | OS Token | Arch Token | Extension |
|----------|----------|------------|-----------|
| macOS Intel | `darwin` | `amd64` | `.zip` |
| macOS Apple Silicon | `darwin` | `arm64` | `.zip` |
| Linux x86-64 | `linux` | `amd64` | `.tar.gz` |
| Linux ARM64 | `linux` | `arm64` | `.tar.gz` |
| Windows x86-64 | `windows` | `amd64` | `.zip` |
| Windows ARM64 | `windows` | `arm64` | `.zip` |

**macOS uses `.zip`, Linux uses `.tar.gz`, Windows uses `.zip`.**

Example for v2.12.6, Linux amd64:
```
https://github.com/nats-io/nats-server/releases/download/v2.12.6/nats-server-v2.12.6-linux-amd64.tar.gz
```

### Programmatic Latest Version Discovery

```python
import urllib.request, json

url = "https://api.github.com/repos/nats-io/nats-server/releases/latest"
with urllib.request.urlopen(url) as r:
    data = json.loads(r.read())
version = data["tag_name"]  # e.g. "v2.12.6"
```

### Platform Detection (Python)

```python
import platform, sys

def _platform_key() -> tuple[str, str]:
    system = sys.platform          # "darwin", "linux", "win32"
    machine = platform.machine()   # "x86_64", "arm64", "aarch64", "AMD64"

    os_token = {
        "darwin": "darwin",
        "linux": "linux",
        "win32": "windows",
    }.get(system)
    if os_token is None:
        raise RuntimeError(f"Unsupported platform: {system}")

    arch_token = {
        "x86_64": "amd64",
        "AMD64": "amd64",   # Windows reports this
        "arm64": "arm64",
        "aarch64": "arm64", # Linux ARM
    }.get(machine)
    if arch_token is None:
        raise RuntimeError(f"Unsupported arch: {machine}")

    ext = "zip" if os_token in ("darwin", "windows") else "tar.gz"
    return os_token, arch_token, ext
```

### Recommended Install Path

```
~/.agentmesh/bin/nats-server          # on macOS / Linux
~/.agentmesh/bin/nats-server.exe      # on Windows
```

Mirror the pattern used by tools like Pulumi, Dagger, and other SDK-managed binaries that download Go server binaries on first use.

### Alternative: Script-Based Install

NATS also offers a script installer that handles platform detection:

```bash
curl -fsSL https://binaries.nats.dev/nats-io/nats-server/v2@v2.12.6 | sh
```

This is useful for CI/CD but not for programmatic use in the SDK — use the direct GitHub download for `AgentMesh.local()`.

---

## 2. Server Startup: Minimum Flags for Embedded Dev Mode

### Quickest: All Flags, No Config File

```bash
nats-server \
  -js \                     # enable JetStream
  -p 4222 \                 # client port (default, can omit)
  -m 8222 \                 # HTTP monitoring port (needed for /healthz)
  -sd /tmp/agentmesh-js \   # JetStream store dir (temp is fine for dev)
  -D                        # debug output (omit for quiet)
```

To suppress all output in dev mode, redirect stdout/stderr rather than use a quiet flag — the NATS server docs do not document a `-q` flag in current versions. Use `stdout=subprocess.DEVNULL` in Python subprocess calls when you want silence.

### Config File Approach (Preferred for Embedded)

Minimum `nats-server.conf` for embedded dev:

```
port: 4222
http_port: 8222

jetstream {
  store_dir: "/tmp/agentmesh/jetstream"
  max_mem: 256M
  max_file: 1G
}
```

Start with:
```bash
nats-server --config /path/to/nats-server.conf
```

**Why prefer a config file:** The SDK can write the config to a temp file, giving it full control over store_dir scoped to the process (e.g., under `~/.agentmesh/run/{pid}/`). This avoids conflicts between concurrent `AgentMesh.local()` instances.

### Subprocess Pattern in Python

```python
import asyncio, subprocess, tempfile, os, pathlib, time, urllib.request

async def _start_embedded_nats(port: int = 4222, store_dir: str | None = None) -> subprocess.Popen:
    if store_dir is None:
        store_dir = str(pathlib.Path.home() / ".agentmesh" / "jetstream")
    os.makedirs(store_dir, exist_ok=True)

    config = f"""
port: {port}
http_port: {port + 1000}  # monitoring on port+1000

jetstream {{
  store_dir: "{store_dir}"
  max_mem: 256M
  max_file: 1G
}}
"""
    # Write config to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".conf", prefix="agentmesh-", delete=False
    ) as f:
        f.write(config)
        config_path = f.name

    binary = str(pathlib.Path.home() / ".agentmesh" / "bin" / "nats-server")
    proc = subprocess.Popen(
        [binary, "--config", config_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready via /healthz
    mon_port = port + 1000
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{mon_port}/healthz?js-enabled-only=true",
                timeout=0.5,
            ) as r:
                if r.status == 200:
                    return proc
        except Exception:
            pass
        await asyncio.sleep(0.1)

    proc.kill()
    raise RuntimeError("nats-server failed to start within 10s")
```

### Key Flags Summary

| Flag | Long form | Purpose | Notes |
|------|-----------|---------|-------|
| `-js` | `--jetstream` | Enable JetStream | Required |
| `-p` | `--port` | Client port | Default 4222 |
| `-m` | `--http_port` | Monitoring port | Required for `/healthz` |
| `-sd` | `--store_dir` | JetStream storage path | Set to avoid `/tmp` collision |
| `-c` | `--config` | Path to config file | Preferred for embedded |
| `-l` | `--log` | Log file path | Redirect output in dev |
| `-D` | `--debug` | Debug logging | Verbose, dev only |
| `-V` | `--trace` | Protocol trace | Very verbose |

---

## 3. JetStream KV Bucket Creation via nats-py

### Package

```bash
pip install nats-py>=2.14.0
```

Latest release: **v2.14.0** (2026-02-23). Requires Python 3.8+.

### Creating a KV Bucket

```python
import nats
from nats.js.api import KeyValueConfig, StorageType
from datetime import timedelta

nc = await nats.connect("nats://localhost:4222")
js = nc.jetstream()

# Minimal — for development
kv = await js.create_key_value(
    config=KeyValueConfig(bucket="mesh-catalog")
)

# With options — for production-oriented setup
kv = await js.create_key_value(
    config=KeyValueConfig(
        bucket="mesh-registry",
        description="Per-agent full contract storage",
        history=5,                    # keep last N versions (default: 1)
        ttl=timedelta(hours=24),      # bucket-level default TTL
        max_value_size=1024 * 256,    # 256 KB per value
        max_bytes=1024 * 1024 * 100,  # 100 MB total
        replicas=1,                   # 1 for dev, 3 for production cluster
    )
)
```

### Binding to an Existing Bucket

```python
# Will fail if bucket does not exist
kv = await js.key_value("mesh-catalog")
```

### Core KV Operations

```python
# Write
revision = await kv.put("some-key", b"value bytes")

# Create (fails if key already exists)
revision = await kv.create("some-key", b"initial")

# Compare-And-Swap — update only if revision matches
# This is the CAS primitive for safe catalog updates
revision = await kv.update("some-key", b"new value", last=revision)

# Read
entry = await kv.get("some-key")
entry.value    # bytes
entry.revision # int — use as `last` in CAS update

# Soft delete (keeps revision history)
await kv.delete("some-key")

# Purge (removes all revisions for a key)
await kv.purge("some-key")

# Delete entire bucket
await js.delete_key_value("mesh-catalog")
```

### KeyValueConfig Fields Reference

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `bucket` | `str` | required | Name: `[a-zA-Z0-9_-]+` only |
| `description` | `str` | `""` | Human-readable |
| `max_value_size` | `int` | `-1` (unlimited) | Bytes per value |
| `history` | `int` | `1` | Number of revisions kept |
| `ttl` | `timedelta` | `None` | Bucket-level TTL for all keys |
| `max_bytes` | `int` | `-1` (unlimited) | Total bucket size |
| `replicas` | `int` | `1` | Set to 3 for HA production |
| `storage` | `StorageType` | `FILE` | `FILE` or `MEMORY` |

### Per-Message TTL (nats-server 2.11+)

Since NATS server 2.11, individual KV entries can have their own TTL independent of the bucket TTL. In nats-py, the `put()`, `create()`, and `update()` methods accept a `msg_ttl` parameter:

```python
# This key expires in 60 seconds regardless of bucket TTL
await kv.put("ephemeral-key", b"value", msg_ttl=timedelta(seconds=60))
```

This is useful for heartbeat-style TTL on agent registrations without needing a separate cleanup process.

---

## 4. CRITICAL: KV Bucket Name Constraint

**Dots (`.`) are NOT allowed in KV bucket names.**

The validation regex, sourced directly from the nats.go client source (`kv.go`), is:

```
^[a-zA-Z0-9_-]+$
```

This means `mesh.catalog` and `mesh.registry` — as named in the current AgentMesh spec — are **invalid bucket names**. The server will reject them.

### Impact on AgentMesh Design

The spec references:
- `mesh.catalog` — KV bucket for the lightweight catalog index
- `mesh.registry.{channel}.{name}` — per-agent full contract storage

These must be renamed. Recommended replacements:

| Spec Name | Valid Bucket Name |
|-----------|-------------------|
| `mesh.catalog` | `mesh-catalog` |
| `mesh.registry` | `mesh-registry` |

**Note on `mesh.registry.{channel}.{name}`:** This was likely intended as a KV key path (not a bucket name), since KV keys can contain dots. The catalog is one bucket, the registry is a second bucket, and the per-agent entries are keys within the registry bucket. Using `{channel}.{name}` as the KV key is valid — dots are allowed in keys.

Correct interpretation:
- Bucket: `mesh-registry` (one bucket for all agents)
- Keys inside: `{channel}.{name}` (dots allowed in keys)
  - e.g., `nlp.summarizer`, `finance.risk.scorer`, `root.classifier`

### Distinct Constraint: JetStream Stream/Consumer Names

JetStream stream and consumer names (which underpin KV buckets) have additional constraints:
- Forbidden: spaces, tabs, `.`, `>`, `*`, `/`, `\`
- Recommended: alphanumeric only
- Length: keep under 32 characters (the storage directory path combines account + stream + consumer names)

KV bucket names map to internal stream names with a `KV_` prefix, so `mesh-catalog` → `KV_mesh-catalog`.

---

## 5. Subject Naming Rules and Gotchas

### Valid Subject Characters

- Any Unicode character except: `null`, space, `.`, `*`, `>`
- Recommended: `a-z`, `A-Z`, `0-9`, `-`, `_`
- Subjects are case-sensitive

### Special Meaning

| Character | Role |
|-----------|------|
| `.` | Token separator — this is how hierarchy works |
| `*` | Single-token wildcard (subscriber only) |
| `>` | Multi-token wildcard (subscriber only) |
| `$` | Prefix reserved for system subjects |

### Limits

- No hard character limit, but best practice: under 256 characters, maximum 16 tokens
- Subjects cannot start or end with `.`

### AgentMesh Subject Patterns — All Valid

The proposed subjects use `.` as hierarchy separators and tokens of alphanumeric/hyphen characters:

```
mesh.agent.nlp.summarizer          ✓  (4 tokens)
mesh.agent.finance.risk.scorer     ✓  (5 tokens)
mesh.registry.nlp.summarizer       ✓  (4 tokens)
mesh.health.nlp.summarizer         ✓  (4 tokens)
mesh.agent.nlp.summarizer.events   ✓  (5 tokens)
mesh.errors.nlp.summarizer         ✓  (4 tokens)
mesh.results.abc123                ✓  (3 tokens)
```

### Channel Name Gotchas

Channel names like `finance.risk` are valid as subject tokens when used as part of a subject (`mesh.agent.finance.risk.scorer`). However, be careful in the code that constructs subjects from channel+name: if channel itself contains a dot (hierarchical channel), the subject token count grows accordingly.

Avoid channels using `*` or `>` — they will corrupt the subject namespace and match as wildcards. Validate channel names on input.

Recommended validation for channel and agent names:

```python
import re

VALID_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
VALID_CHANNEL_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$')  # dots allowed in channels

def validate_name(name: str) -> None:
    if not VALID_NAME_RE.match(name):
        raise ValueError(f"Invalid agent name '{name}': use alphanumeric, dash, underscore")

def validate_channel(channel: str) -> None:
    if not VALID_CHANNEL_RE.match(channel):
        raise ValueError(f"Invalid channel '{channel}': dots allowed as separator")
    if '..' in channel:
        raise ValueError(f"Invalid channel '{channel}': consecutive dots not allowed")
```

---

## 6. `agentmesh up` CLI — Recommended Behavior

### Purpose

Start a local NATS server with JetStream and pre-create the two KV buckets required by the AgentMesh protocol. This is the "zero-config dev setup" command.

### Sequence

1. **Check for existing NATS** — attempt connection to `nats://127.0.0.1:4222`. If it succeeds, skip server start (user has their own NATS running).
2. **Ensure binary** — check `~/.agentmesh/bin/nats-server`. If missing, download the correct platform binary from GitHub releases.
3. **Write temp config** — write a config file to `~/.agentmesh/run/nats-server.conf` with JetStream enabled and store_dir at `~/.agentmesh/jetstream/`.
4. **Start subprocess** — launch `nats-server --config ~/.agentmesh/run/nats-server.conf`.
5. **Wait for ready** — poll `http://127.0.0.1:8222/healthz?js-enabled-only=true` until 200 OK or 10s timeout.
6. **Create KV buckets** — connect with nats-py, create `mesh-catalog` and `mesh-registry` if they don't exist (`key_value()` will raise `BucketNotFoundError`, catch it and call `create_key_value()`).
7. **Print status** — show server version, address, JetStream state, bucket names.
8. **Block** — keep the process running (Ctrl-C for graceful shutdown, which kills the subprocess and optionally cleans up JetStream store).

### Output Format

```
AgentMesh local NATS server
  Address:    nats://127.0.0.1:4222
  Monitoring: http://127.0.0.1:8222
  JetStream:  enabled
  Buckets:    mesh-catalog  mesh-registry
  Store:      ~/.agentmesh/jetstream

Press Ctrl-C to stop.
```

### Implementation Notes

- PID file at `~/.agentmesh/run/nats-server.pid` — allows other processes to check if embedded NATS is running.
- On SIGINT/SIGTERM, send SIGTERM to subprocess, wait up to 5s, then SIGKILL.
- The `agentmesh up` command is for development only. For production, users run their own NATS server.
- Creating KV buckets is idempotent: check first with `js.key_value(name)`, create only if it raises (nats-py raises `nats.js.errors.NotFoundError` or similar if bucket doesn't exist).

---

## 7. JetStream Configuration Reference

### Minimum Dev Config

```
jetstream {
  store_dir: "/tmp/agentmesh/jetstream"
}
```

### Full Dev Config with Resource Caps

```
port: 4222
http_port: 8222

jetstream {
  store_dir: "/Users/yourname/.agentmesh/jetstream"
  max_mem: 256M
  max_file: 2G
}
```

### Key JetStream Config Fields

| Field | Purpose | Dev Value | Notes |
|-------|---------|-----------|-------|
| `store_dir` | Where JetStream persists data | `~/.agentmesh/jetstream` | Required |
| `max_mem` | Memory storage limit | `256M` | Default is 75% of RAM |
| `max_file` | File storage limit | `2G` | Default is 1TB |
| `domain` | JetStream domain name | omit | For multi-cluster federation only |

---

## 8. Health Check Pattern

The `/healthz` endpoint is the authoritative readiness check:

```
GET http://127.0.0.1:8222/healthz
```

Returns `{"status": "ok"}` when server accepts connections.

For JetStream readiness specifically:

```
GET http://127.0.0.1:8222/healthz?js-enabled-only=true
```

Returns 200 only when JetStream is initialized. Use this as the wait condition in `AgentMesh.local()` and `agentmesh up`.

Additional useful monitoring endpoints:
- `http://127.0.0.1:8222/varz` — server version, uptime, config
- `http://127.0.0.1:8222/jsz` — JetStream stats: streams, consumers, memory, storage

---

## 9. NATS 2.11 vs 2.12 Feature Delta

### 2.11 — Required Minimum

- **Per-message TTL** (`Nats-TTL` header): individual KV entries can expire independently of bucket TTL. Critical for heartbeat-based agent health without a cleanup cron.
- Exposed in nats-py via `msg_ttl` parameter on KV operations.
- **Recommendation: require nats-server >= 2.11** in AgentMesh to unlock per-message TTL for heartbeats.

### 2.12 — Not Required, But Available

- Atomic batch publishing (`AllowAtomicPublish`)
- Distributed counter CRDT (`AllowMsgCounter`)
- Delayed message scheduling
- **Breaking change: strict JetStream API validation** — invalid requests that previously logged warnings now return errors. This is actually good for AgentMesh since it will surface bugs faster.
- Async stream flushing for better write performance

### Recommendation

Target **nats-server >= 2.11** as the minimum. The per-message TTL feature is essential for the heartbeat pattern and avoids needing external cleanup. nats-py 2.14.0 (current) supports both 2.11 and 2.12.

---

## 10. Pitfalls and Gotchas

### Pitfall 1: Dot in KV Bucket Names

**What goes wrong:** The spec names `mesh.catalog` and `mesh.registry` will fail with a server error — dots are not valid in bucket names. The Go regex is `^[a-zA-Z0-9_-]+$`.

**Prevention:** Use `mesh-catalog` and `mesh-registry`. Dots in KV _keys_ are fine.

**Confidence:** HIGH — validated against nats.go source (`kv.go:validBucketRe`).

### Pitfall 2: JetStream Store Dir Conflicts

**What goes wrong:** Two `AgentMesh.local()` instances using the same store_dir will conflict — the second server will either fail to start or corrupt data.

**Prevention:** Use a unique store_dir per process, e.g., `~/.agentmesh/jetstream/{port}/` or `~/.agentmesh/jetstream/dev/` with a PID lock file.

### Pitfall 3: `js.key_value()` vs `js.create_key_value()`

**What goes wrong:** `js.key_value("name")` binds to an existing bucket and raises if it doesn't exist. `js.create_key_value(config)` creates it. Calling `create_key_value` on an already-existing bucket with the same config is safe in nats-py (it behaves as "get or create" for identical configs). Calling it with different config raises an error.

**Prevention:** Use `create_key_value` on startup with idempotent config. Don't call `key_value()` as the first access path in `agentmesh up` initialization.

### Pitfall 4: No `-q` Quiet Flag

**What goes wrong:** Attempting `nats-server -q` will fail — no quiet flag exists in current versions.

**Prevention:** Redirect subprocess stdout/stderr via `subprocess.PIPE` or `subprocess.DEVNULL`.

### Pitfall 5: Monitoring Port Required for Health Checks

**What goes wrong:** Without `-m 8222` (or `http_port: 8222` in config), the `/healthz` endpoint is not available. The subprocess start will hang on health check.

**Prevention:** Always include the monitoring port in the embedded NATS config.

### Pitfall 6: 2.12 Strict JetStream API Validation

**What goes wrong:** NATS 2.12 introduced strict validation — requests that were silently ignored before now return errors. Operations that worked against 2.10/2.11 may fail against 2.12.

**Prevention:** Test against nats-server 2.12.x specifically in CI. Handle `APIError` responses defensively in the SDK.

### Pitfall 7: Windows Binary Extension and Path

**What goes wrong:** The Windows binary is `nats-server.exe`, not `nats-server`. Code that constructs the binary path without checking the platform will fail on Windows.

**Prevention:** Check `sys.platform == "win32"` and append `.exe` to the binary path on Windows.

---

## Sources

- [NATS Server Releases — GitHub](https://github.com/nats-io/nats-server/releases) (MEDIUM — release page assets failed to render; URL pattern confirmed from install docs)
- [Installing a NATS Server — NATS Docs](https://docs.nats.io/running-a-nats-service/introduction/installation) (HIGH)
- [NATS Server Flags — NATS Docs](https://docs.nats.io/running-a-nats-service/introduction/flags) (HIGH)
- [JetStream Configuration — NATS Docs](https://docs.nats.io/running-a-nats-service/configuration/resource_management) (HIGH)
- [Subject-Based Messaging — NATS Docs](https://docs.nats.io/nats-concepts/subjects) (HIGH)
- [JetStream Naming — NATS Docs](https://docs.nats.io/running-a-nats-service/nats_admin/jetstream_admin/naming) (HIGH)
- [KV Store Developer Docs — NATS Docs](https://docs.nats.io/using-nats/developer/develop_jetstream/kv) (HIGH)
- [nats.go kv.go source — validBucketRe](https://github.com/nats-io/nats.go/blob/main/kv.go) (HIGH — source of truth for bucket name validation)
- [nats.py on GitHub](https://github.com/nats-io/nats.py) (HIGH)
- [NATS Server Monitoring — NATS Docs](https://docs.nats.io/running-a-nats-service/nats_admin/monitoring) (HIGH)
- [What's New in NATS 2.11 — Synadia](https://www.synadia.com/blog/per-message-ttl-nats-2-11) (MEDIUM)
- [What's New in NATS 2.12 — NATS Docs](https://docs.nats.io/release-notes/whats_new/whats_new_212) (HIGH)
- [NATS ADR-8 KV Architecture](https://github.com/nats-io/nats-architecture-and-design/blob/main/adr/ADR-8.md) (HIGH)
