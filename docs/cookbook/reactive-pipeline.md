# Reactive Pipeline

A three-stage pipeline where each stage watches for its input to appear, does its work, and writes the result for the next stage. No orchestrator dispatches work. No agent calls another agent. Coordination happens through the data.

This recipe demonstrates `mesh.kv.watch()` as a coordination primitive: agents react to state changes instead of being told what to do.

## The Pipeline

```
[ingest] --writes--> KV:"pipeline.{id}.raw"
                         |
                [extract] watches, writes --> KV:"pipeline.{id}.extracted"
                                                   |
                                            [summarize] watches, writes --> KV:"pipeline.{id}.summary"
```

Each stage is an independent process. Start them in any order. Drop one and the pipeline pauses at that stage. Add it back and it picks up where it left off.

!!! tip "Dot-separated keys for wildcard watching"
    KV keys use `.` as the hierarchy separator (not `/`) because NATS subject matching treats `.` as a token delimiter. This enables `watch("pipeline.*.raw")` to match any document ID in the middle. Keys with `/` work fine for `put`/`get`/`delete` but won't match wildcard patterns in `watch()`.

## Models

```python
import json
from pydantic import BaseModel

class Document(BaseModel):
    id: str
    title: str
    body: str

class Extracted(BaseModel):
    id: str
    entities: list[str]
    word_count: int

class Summary(BaseModel):
    id: str
    title: str
    one_liner: str
    entity_count: int
```

## Stage 1: Ingest

Receives a document via `mesh.call()` and writes the raw content to KV. This is the only stage that is invocable; the rest are purely reactive.

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

spec = AgentSpec(
    name="ingest",
    channel="pipeline",
    description="Accepts a document and writes it to the pipeline KV for downstream processing.",
)

@mesh.agent(spec)
async def ingest(req: Document) -> Document:
    await mesh.kv.put(f"pipeline.{req.id}.raw", req.model_dump_json())
    return req

mesh.run()
```

## Stage 2: Extract

Watches for new raw documents. When one appears, extracts entities and writes the result for the next stage. Registered as a [watcher agent](../concepts/agents.md#watcher): visible in the catalog and tracked for liveness, but not invocable.

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

spec = AgentSpec(
    name="extract",
    channel="pipeline",
    description="Watches for raw documents and extracts entities.",
)

@mesh.agent(spec)
async def extract():
    print("extract: watching for raw documents...")
    async for value in mesh.kv.watch("pipeline.*.raw"):
        doc = Document.model_validate_json(value)
        print(f"extract: processing {doc.id}")

        # Simulate entity extraction
        words = doc.body.split()
        entities = [w for w in words if w[0].isupper()] if words else []

        extracted = Extracted(
            id=doc.id,
            entities=entities,
            word_count=len(words),
        )
        await mesh.kv.put(
            f"pipeline.{doc.id}.extracted",
            extracted.model_dump_json(),
        )
        print(f"extract: wrote pipeline.{doc.id}.extracted")

mesh.run()
```

## Stage 3: Summarize

Watches for extracted results and produces a final summary.

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

spec = AgentSpec(
    name="summarize",
    channel="pipeline",
    description="Watches for extracted documents and produces a summary.",
)

@mesh.agent(spec)
async def summarize():
    print("summarize: watching for extracted documents...")
    async for value in mesh.kv.watch("pipeline.*.extracted"):
        extracted = Extracted.model_validate_json(value)
        print(f"summarize: processing {extracted.id}")

        # Look up the original document for the title
        raw = await mesh.kv.get(f"pipeline.{extracted.id}.raw")
        doc = Document.model_validate_json(raw)

        summary = Summary(
            id=extracted.id,
            title=doc.title,
            one_liner=doc.body[:80] + "..." if len(doc.body) > 80 else doc.body,
            entity_count=len(extracted.entities),
        )
        await mesh.kv.put(
            f"pipeline.{extracted.id}.summary",
            summary.model_dump_json(),
        )
        print(f"summarize: wrote pipeline.{extracted.id}.summary")

mesh.run()
```

## Submitting a Document

```python
import asyncio
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh()
    async with mesh:
        result = await mesh.call("ingest", {
            "id": "doc-001",
            "title": "Quarterly Report",
            "body": "Revenue at Acme Corp grew 15% in Q3. The Berlin office expanded headcount. Alice and Bob led the new initiative.",
        })
        print(f"Submitted: {result['id']}")

        # Wait for the pipeline to complete, then read the summary
        await asyncio.sleep(1)
        summary_raw = await mesh.kv.get("pipeline.doc-001.summary")
        print(f"Summary: {summary_raw}")

asyncio.run(main())
```

## Run It

Start each stage in its own terminal, in any order:

```bash
# Terminal 1
oam mesh up

# Terminal 2
python extract.py

# Terminal 3
python summarize.py

# Terminal 4
python ingest.py

# Terminal 5
python submit.py
```

Output across terminals:

```
# extract.py
extract: watching for raw documents...
extract: processing doc-001
extract: wrote pipeline.doc-001.extracted

# summarize.py
summarize: watching for extracted documents...
summarize: processing doc-001
summarize: wrote pipeline.doc-001.summary

# submit.py
Submitted: doc-001
Summary: {"id": "doc-001", "title": "Quarterly Report", "one_liner": "Revenue at Acme Corp grew 15% in Q3. The Berlin office expanded headcount. Alice...", "entity_count": 5}
```

## How It Works

```mermaid
sequenceDiagram
    participant Client as submit.py
    participant KV as mesh-context KV
    participant Ingest as ingest.py
    participant Extract as extract.py
    participant Summarize as summarize.py

    Extract->>KV: watch("pipeline.*.raw")
    Summarize->>KV: watch("pipeline.*.extracted")

    Client->>Ingest: mesh.call("ingest", doc)
    Ingest->>KV: put("pipeline.doc-001.raw", ...)

    KV-->>Extract: notification: pipeline.doc-001.raw changed
    Extract->>KV: put("pipeline.doc-001.extracted", ...)

    KV-->>Summarize: notification: pipeline.doc-001.extracted changed
    Summarize->>KV: get("pipeline.doc-001.raw")
    KV-->>Summarize: original document
    Summarize->>KV: put("pipeline.doc-001.summary", ...)

    Client->>KV: get("pipeline.doc-001.summary")
```

Key properties:

- **No orchestrator.** No central process decides what runs when. Each stage watches for its input and reacts. The pipeline emerges from the data flow.
- **Order-independent startup.** Start the stages in any order. Watchers that start before data exists simply wait. Watchers that start after data was written receive the current value immediately.
- **Stage independence.** Kill the summarize stage midway. Ingest and extract continue producing. Restart summarize and it picks up the unprocessed extracted results.
- **Parallel pipelines.** Submit ten documents. Each flows through the pipeline independently. Stages process whichever document update arrives next.
- **Observable state.** Every intermediate result is a KV entry. Debugging is reading keys, not tracing RPC chains.
- **Visible participants.** All three stages are registered agents. They appear in `mesh.catalog()`, participate in liveness tracking, and can be filtered with `mesh.catalog(invocable=True)` when selecting tools for LLM invocation.

!!! tip "Scaling expensive processing"
    Watcher agents run as a single instance; every replica receives every KV update. If the processing step is expensive, split the watcher into a thin routing layer that calls an invocable agent via `mesh.call()`. The invocable agent scales via queue groups:

    ```python
    @mesh.agent(AgentSpec(name="extract-watcher", channel="pipeline",
        description="Routes raw documents to the extract processor."))
    async def extract_watcher():
        async for value in mesh.kv.watch("pipeline.*.raw"):
            doc = Document.model_validate_json(value)
            await mesh.call("extract-processor", {"id": doc.id, "body": doc.body})
    ```
