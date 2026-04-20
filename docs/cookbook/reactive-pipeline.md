# Reactive Pipeline

A three-stage pipeline where each stage watches for its input to appear, does its work, and writes the result for the next stage. No orchestrator dispatches work. No agent calls another agent. Coordination happens through the data.

This recipe demonstrates `mesh.kv.watch()` as a coordination primitive: agents react to state changes instead of being told what to do.

## The Code

```python
import asyncio

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


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


async def main(mesh: AgentMesh) -> None:
    # Stage 1: Ingest agent writes raw document to KV
    @mesh.agent(AgentSpec(
        name="ingest",
        channel="pipeline",
        description="Accepts a document and writes it to pipeline KV for downstream processing.",
    ))
    async def ingest(req: Document) -> Document:
        await mesh.kv.put(f"pipeline.{req.id}.raw", req.model_dump_json())
        return req

    # Stage 2: Extract watches for raw documents
    async def extract_stage():
        async for value in mesh.kv.watch("pipeline.*.raw"):
            doc = Document.model_validate_json(value)
            words = doc.body.split()
            entities = [w for w in words if w and w[0].isupper()]
            extracted = Extracted(id=doc.id, entities=entities, word_count=len(words))
            await mesh.kv.put(f"pipeline.{doc.id}.extracted", extracted.model_dump_json())
            break  # process one document

    # Stage 3: Summarize watches for extracted results
    async def summarize_stage():
        async for value in mesh.kv.watch("pipeline.*.extracted"):
            extracted = Extracted.model_validate_json(value)
            raw = await mesh.kv.get(f"pipeline.{extracted.id}.raw")
            doc = Document.model_validate_json(raw)
            summary = Summary(
                id=extracted.id,
                title=doc.title,
                one_liner=doc.body[:80] + "..." if len(doc.body) > 80 else doc.body,
                entity_count=len(extracted.entities),
            )
            await mesh.kv.put(f"pipeline.{extracted.id}.summary", summary.model_dump_json())
            break  # process one document

    # Start watchers
    extract_task = asyncio.create_task(extract_stage())
    summarize_task = asyncio.create_task(summarize_stage())
    await asyncio.sleep(0.1)  # let watchers attach

    # Submit a document
    await mesh.call("ingest", Document(
        id="doc-001",
        title="Quarterly Report",
        body="Revenue at Acme Corp grew 15% in Q3. The Berlin office expanded headcount.",
    ))

    # Wait for pipeline to complete
    await asyncio.wait_for(asyncio.gather(extract_task, summarize_task), timeout=5.0)

    # Read final summary
    summary_raw = await mesh.kv.get("pipeline.doc-001.summary")
    summary = Summary.model_validate_json(summary_raw)
    print(f"Final summary: {summary.title} - {summary.one_liner}")
    print(f"  Entities found: {summary.entity_count}")
```

## Run It

```bash
oam demo run reactive_pipeline
```

## How It Works

```
[ingest] --writes--> KV:"pipeline.{id}.raw"
                        |
               [extract] watches, writes --> KV:"pipeline.{id}.extracted"
                                                  |
                                           [summarize] watches, writes --> KV:"pipeline.{id}.summary"
```

Each stage is independent. Start them in any order. Drop one and the pipeline pauses at that stage. Add it back and it picks up where it left off.

```mermaid
sequenceDiagram
    participant Client
    participant KV as mesh-context KV
    participant Ingest
    participant Extract
    participant Summarize

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

!!! tip "Dot-separated keys for wildcard watching"
    KV keys use `.` as the hierarchy separator (not `/`) because NATS subject matching treats `.` as a token delimiter. This enables `watch("pipeline.*.raw")` to match any document ID in the middle.

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
