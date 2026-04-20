"""Three-stage pipeline coordinated through KV watches, no orchestrator."""

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
            print(f"  extract: processed {doc.id} ({len(entities)} entities)")
            break  # demo processes one document

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
            print(f"  summarize: produced summary for {extracted.id}")
            break  # demo processes one document

    # Start watchers
    extract_task = asyncio.create_task(extract_stage())
    summarize_task = asyncio.create_task(summarize_stage())
    await asyncio.sleep(0.1)  # let watchers attach

    # Submit a document
    print("Submitting document...")
    await mesh.call("ingest", Document(
        id="doc-001",
        title="Quarterly Report",
        body="Revenue at Acme Corp grew 15% in Q3. The Berlin office expanded headcount. Alice and Bob led the new initiative.",
    ))

    # Wait for pipeline to complete
    await asyncio.wait_for(asyncio.gather(extract_task, summarize_task), timeout=5.0)

    # Read final summary
    summary_raw = await mesh.kv.get("pipeline.doc-001.summary")
    summary = Summary.model_validate_json(summary_raw)
    print(f"\nFinal summary: {summary.title} - {summary.one_liner}")
    print(f"  Entities found: {summary.entity_count}")
