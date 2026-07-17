"""Tests for the parallel RAG indexing cookbook recipe (docs/cookbook/parallel-rag-indexing.md).

Exercises the recipe's mesh machinery for real: the source document lives in the
ObjectStore workspace, indexing fans out via ``mesh.call`` to a queue-grouped
``rag.indexer`` agent, and the chunk-splitting logic is copied verbatim from the
recipe. ChromaDB and sentence-transformers are heavyweight external dependencies,
so the embed-and-store step writes to an in-memory collection instead — the mesh
primitives the recipe demonstrates are unchanged.
"""

import asyncio

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec

DOC = "\n\n".join(f"Paragraph {i}: some content about topic {i}." for i in range(10))
CHUNK_COUNT = 4


class IndexRequest(BaseModel):
    workspace_key: str  # ObjectStore key for the source document
    chunk_index: int
    chunk_count: int


class IndexResult(BaseModel):
    chunk_index: int
    num_embeddings: int
    collection: str


def register_indexer(mesh: AgentMesh, collection: dict[str, str]) -> None:
    spec = AgentSpec(
        name="rag.indexer",
        description="Indexes a chunk of a document into ChromaDB. Input: ObjectStore key, chunk index, total chunks.",
    )

    @mesh.agent(spec)
    async def index_chunk(req: IndexRequest) -> IndexResult:
        # Read the full document from the mesh ObjectStore
        doc_bytes = await mesh.workspace.get(req.workspace_key)
        text = doc_bytes.decode("utf-8")

        # Split into paragraphs and select this agent's portion (verbatim from the recipe)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunk_size = max(1, len(paragraphs) // req.chunk_count)
        start = req.chunk_index * chunk_size
        end = start + chunk_size if req.chunk_index < req.chunk_count - 1 else len(paragraphs)
        my_paragraphs = paragraphs[start:end]

        if not my_paragraphs:
            return IndexResult(chunk_index=req.chunk_index, num_embeddings=0, collection=req.workspace_key)

        # Embed and store (in-memory stand-in for ChromaDB)
        for i, p in enumerate(my_paragraphs):
            collection[f"{req.workspace_key}-{req.chunk_index}-{i}"] = p

        return IndexResult(
            chunk_index=req.chunk_index,
            num_embeddings=len(my_paragraphs),
            collection="docs",
        )


class TestParallelRagIndexingRecipe:
    async def test_fan_out_indexes_every_paragraph_exactly_once(self):
        collection: dict[str, str] = {}
        async with AgentMesh.local() as mesh:
            register_indexer(mesh, collection)

            # Upload document to the mesh ObjectStore
            await mesh.workspace.put("docs/quarterly-report.txt", DOC.encode())

            # Fan out indexing across available indexer instances
            tasks = [
                mesh.call("rag.indexer", {
                    "workspace_key": "docs/quarterly-report.txt",
                    "chunk_index": i,
                    "chunk_count": CHUNK_COUNT,
                })
                for i in range(CHUNK_COUNT)
            ]
            results = await asyncio.gather(*tasks)

            total = sum(r["num_embeddings"] for r in results)
            assert total == 10  # every paragraph indexed
            assert len(collection) == 10  # exactly once, no overlap
            assert {r["chunk_index"] for r in results} == {0, 1, 2, 3}

            # Cleanup
            await mesh.workspace.delete("docs/quarterly-report.txt")
