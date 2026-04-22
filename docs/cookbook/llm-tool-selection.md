# LLM-Driven Tool Selection

An orchestrator agent receives a task in natural language, browses the mesh catalog, selects which agents fit, fetches their full contracts, and calls them as tools. No hardcoded tool list. New agents on the mesh become callable the moment they register.

This is the **enterprise tool search** pattern: instead of pre-wiring every tool a model can call, the orchestrator discovers them at runtime. The two-tier catalog keeps token cost flat even with hundreds of agents on the mesh.

## The Code

```python
import asyncio
import json

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class SummarizeInput(BaseModel):
    text: str


class SummarizeOutput(BaseModel):
    summary: str


class TranslateInput(BaseModel):
    text: str
    target_language: str = "es"


class TranslateOutput(BaseModel):
    translated: str


class TaskRequest(BaseModel):
    task: str


class TaskResponse(BaseModel):
    answer: str


async def main(mesh: AgentMesh) -> None:
    # Register some tool agents
    @mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes text."))
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        return SummarizeOutput(summary=req.text[:80] + "...")

    @mesh.agent(AgentSpec(name="nlp.translator", description="Translates text to a target language."))
    async def translate(req: TranslateInput) -> TranslateOutput:
        return TranslateOutput(translated=f"[{req.target_language}] {req.text}")

    # Orchestrator discovers and selects agents from the catalog
    @mesh.agent(AgentSpec(name="orchestrator", description="Selects and calls agents based on task description."))
    async def orchestrator(req: TaskRequest) -> TaskResponse:
        # Tier 1: browse catalog (cheap, ~25 tokens per agent)
        catalog = await mesh.catalog()
        invocable = [e for e in catalog if e.invocable and e.name != "orchestrator"]

        # Tier 2: select relevant agents (simulated LLM selection)
        selected = [e.name for e in invocable if "summar" in req.task.lower() and "summar" in e.name]
        if not selected:
            selected = [invocable[0].name] if invocable else []

        # Fetch full contracts for selected agents
        for name in selected:
            contract = await mesh.contract(name)
            print(f"  Contract for {name}: input_schema={json.dumps(contract.input_schema)[:60]}...")

        # Execute (simulated LLM tool call)
        if selected:
            result = await mesh.call(selected[0], {"text": "The quarterly report shows 15% growth."})
            return TaskResponse(answer=json.dumps(result))
        return TaskResponse(answer="No suitable agent found.")

    # Run the orchestrator
    result = await mesh.call("orchestrator", TaskRequest(task="Summarize the quarterly report"))
    print(f"Result: {result['answer']}")
```

!!! note
    The recipe simulates LLM selection with keyword matching. In production, replace the selection logic with an actual LLM call (see the full pattern below).

## Run It

```python
import asyncio
from openagentmesh import AgentMesh

async def run():
    async with AgentMesh.local() as mesh:
        await main(mesh)

asyncio.run(run())
```

## Pattern

```mermaid
sequenceDiagram
    participant User
    participant Orchestrator
    participant LLM
    participant Mesh

    User->>Orchestrator: "Summarize the Q3 report"
    Orchestrator->>Mesh: catalog()
    Mesh-->>Orchestrator: [name, description] x N
    Orchestrator->>LLM: task + catalog (cheap context)
    LLM-->>Orchestrator: ["summarizer", "report-fetcher"]
    Orchestrator->>Mesh: contract("summarizer"), contract("report-fetcher")
    Mesh-->>Orchestrator: full schemas
    Orchestrator->>LLM: task + tools(schemas)
    LLM-->>Orchestrator: tool_use(report-fetcher, ...)
    Orchestrator->>Mesh: call("report-fetcher", ...)
    Mesh-->>Orchestrator: result
    Orchestrator->>LLM: tool_result
    LLM-->>Orchestrator: tool_use(summarizer, ...)
    Orchestrator->>Mesh: call("summarizer", ...)
    Mesh-->>Orchestrator: result
    LLM-->>User: final answer
```

## Why Two Tiers

A single-tier approach (load every contract into the LLM context) breaks down past a few dozen agents:

| Approach | Tokens for selection | Tokens for execution |
|----------|---------------------|---------------------|
| All contracts upfront | ~500 per agent x N | ~500 per agent x N |
| Catalog then contract | ~25 per agent x N | ~500 per **selected** agent |

For a mesh with 200 agents and 3 selected per task, the two-tier approach cuts selection cost roughly **20x** and keeps execution context small enough for the model to focus.

## Production Orchestrator

Replace the simulated selection with a real LLM call:

```python
from anthropic import AsyncAnthropic

client = AsyncAnthropic()

# Tier 1: ask the LLM which agents to use
catalog = await mesh.catalog()
catalog_text = "\n".join(f"- {e.name}: {e.description}" for e in catalog if e.invocable)

selection = await client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=512,
    messages=[{
        "role": "user",
        "content": (
            f"Available agents:\n{catalog_text}\n\n"
            f"Task: {req.task}\n\n"
            "Reply with a JSON array of agent names useful for this task."
        ),
    }],
)
names = json.loads(selection.content[0].text)

# Tier 2: fetch full contracts and expose as tools
tools = []
for name in names:
    contract = await mesh.contract(name)
    tools.append(contract.to_anthropic_tool())
```

## Variants

- **RAG over the catalog.** Replace the LLM selection turn with embedding-based retrieval over `name + description + tags`.
- **Channel pre-filter.** Narrow with `mesh.catalog(channel="finance")` before LLM selection when the task domain is known.
- **Streaming tools.** Swap `mesh.call()` for `mesh.stream()` when a selected agent is streaming-capable.
