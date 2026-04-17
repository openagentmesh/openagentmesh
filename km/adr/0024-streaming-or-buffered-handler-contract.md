# ADR-0024: Streaming or buffered as a per-agent handler choice, both typed

- **Type:** api-design
- **Date:** 2026-04-14
- **Status:** documented
- **Source:** conversation (design discussion on streaming DX, typed chunks, and SDK enforcement)

## Context

ADR-0005 introduced the wire protocol for streaming (per-request `mesh.stream.{request_id}` subjects, `X-Mesh-Stream` headers) and established `capabilities.streaming` in the contract. What it left unresolved is the **provider-side handler API**: how does a developer write an agent that streams? And how does the SDK enforce that declared capabilities are actually implemented?

Several handler models were considered:

**Side-channel model (`MeshStream` parameter):** The handler returns a typed response AND accepts a `stream: MeshStream` parameter for emitting deltas. `stream.write(token)` is a no-op when the caller didn't request streaming; the SDK assembles the final return for `mesh.call()` consumers.

Problem: streaming becomes a side-effect of a handler whose primary output is the typed return. The stream is the main output for LLM-powered agents — making it the secondary path inverts importance. Additionally, once a consumer has received all streamed chunks, the final typed return is redundant — they already have the content.

**Separate class methods:** A class with `call()` and `stream()` methods, introspected at registration. Clean SDK enforcement, independent typing for each path. Rejected: breaks the function-first DX that is central to OAM's design philosophy (see `km/agentmesh-developer-experience.md` §1).

**Sub-decorator pattern:** Register a streaming handler first; optionally attach a `@handler.aggregate` function that assembles chunks into a typed buffered response for `mesh.call()` consumers. Correct direction (streaming is primary, buffered is derived) but introduces a new SDK concept with non-obvious behavior. Deferred to v2.

The core insight that resolves the tension: **LLM API clients are already either streaming or not.** A developer knows when they write the handler whether they're calling an LLM in streaming mode or waiting for the complete response. Forcing a single handler to do both is artificial. Letting the handler shape declare the mode is natural.

## Decision

In v1, an agent is either buffered or streaming. Not both. Both modes produce typed, validated output. The handler's return-vs-yield behavior determines the mode; the SDK enforces it at registration time.

### Buffered agents

The handler is a standard async function that returns a typed Pydantic model:

```python
@mesh.agent(name="classifier", channel="nlp", description="...")
async def classify(req: ClassifyInput) -> ClassifyOutput:
    result = await call_llm_complete(req.text)
    return ClassifyOutput(label=result.label, confidence=result.score)
```

- `capabilities.streaming: false` set in contract
- Return type annotation validated against `output_schema` at registration
- Consumer invokes with `mesh.call()`, receives typed `ClassifyOutput`
- `mesh.stream()` against this agent returns `streaming_not_supported` error

### Streaming agents

The handler is an async generator function that yields typed chunk models:

```python
class SummarizeChunk(BaseModel):
    delta: str

@mesh.agent(name="summarizer", channel="nlp", description="...")
async def summarize(req: SummarizeInput) -> SummarizeChunk:
    async for token in call_llm_stream(req.text):
        yield SummarizeChunk(delta=token)
```

- `capabilities.streaming: true` set in contract
- Yield type annotation validated against `chunk_schema` at registration
- Consumer invokes with `mesh.stream()`, receives a typed async generator of `SummarizeChunk`
- `mesh.call()` against this agent returns `streaming_not_supported` error
- Chunk schema is published in the contract under `x-agentmesh.chunk_schema`

### SDK enforcement at registration time

The SDK inspects the handler at `@mesh.agent` decoration time:

1. `inspect.isasyncgenfunction(handler)` → streaming agent
2. Not an async generator → buffered agent
3. Return annotation required in both cases. Missing annotation raises `RegistrationError`.
4. For buffered agents: return type must be a `BaseModel` subclass.
5. For streaming agents: yield type must be a `BaseModel` subclass.
6. `capabilities.streaming` in the contract is set automatically based on (1)/(2). Manual override is permitted but discouraged.

### Handler signature summary

```
Buffered agent:   async def handler(req: Input) -> Output      # return, streaming: false
Streaming agent:  async def handler(req: Input) -> Chunk       # yield, streaming: true
Publisher:        async def handler() -> Event                 # yield, no request, type="publisher"
```

The return annotation in Python cannot distinguish `-> Chunk` (return) from `-> Chunk` (yield) syntactically. The SDK uses `isasyncgenfunction` to detect generators, not the annotation. The annotation is used solely for schema extraction.

### Consumer side

```python
# Buffered
result = await mesh.call("classifier", payload)
# result is ClassifyOutput, validated against output_schema

# Streaming
async for chunk in mesh.stream("summarizer", payload):
    print(chunk.delta, end="")
# chunk is SummarizeChunk, validated against chunk_schema
```

`mesh.call()` and `mesh.stream()` are not interchangeable. Calling the wrong one returns a `MeshError` with `code: "streaming_not_supported"` (ADR-0005 enforcement already covers the request-side check; this ADR adds the registration-time enforcement on the provider side).

### Contract schema additions

The contract gains a `chunk_schema` field under `x-agentmesh` for streaming agents:

```json
{
  "capabilities": { "streaming": true },
  "x-agentmesh": {
    "chunk_schema": {
      "type": "object",
      "properties": {
        "delta": { "type": "string" }
      },
      "required": ["delta"]
    }
  }
}
```

`output_schema` (in `skills[0]`) is still present but reflects the final aggregated output type if known, or is omitted for streaming-only agents that have no declared aggregate output.

## Future: dual-mode agents (v2)

A common real-world need: an LLM agent that can serve both streaming and buffered callers from the same registration. The natural extension is a sub-decorator that declares an aggregator:

```python
@mesh.agent(name="summarizer", channel="nlp", description="...")
async def summarize(req: SummarizeInput) -> SummarizeChunk:
    async for token in call_llm_stream(req.text):
        yield SummarizeChunk(delta=token)

@summarize.aggregate
def assemble(chunks: list[SummarizeChunk]) -> SummarizeOutput:
    text = "".join(c.delta for c in chunks)
    return SummarizeOutput(summary=text, token_count=len(text.split()))
```

When `@summarize.aggregate` is declared:
- `mesh.stream()` routes to the generator
- `mesh.call()` runs the generator, collects all chunks, passes them to the assembler, returns the typed `SummarizeOutput`
- Both `chunk_schema` and `output_schema` are published in the contract

This is deferred to v2. The v1 constraint (pick one mode) is intentional: it keeps the implementation surface small and forces the common case to be explicit.

## Alternatives Considered

**`mesh.call()` auto-buffers streaming agents.** The SDK could silently collect all chunks and return them assembled when `mesh.call()` is used against a streaming agent. Rejected: the assembly logic is domain-specific (text concatenation, JSON merging, last-chunk-wins) and cannot be inferred generically. Silent buffering would produce garbage for non-text chunk types.

**Untyped streaming (raw string/bytes chunks).** Chunks could be untyped strings rather than Pydantic models. Simpler for the LLM token streaming case (each chunk is just a string delta). Rejected: typed chunks enable consumer-side validation, contract introspection, and multi-field chunk models (e.g., a chunk with `delta`, `model`, `finish_reason`). The overhead of a single-field Pydantic model is negligible.

**`streaming=True` flag on the decorator.** The streaming mode could be declared explicitly via `@mesh.agent(..., streaming=True)` rather than inferred from the handler shape. Rejected: it creates a mismatch risk (flag says streaming, handler returns) that the SDK would have to detect anyway. Using the handler shape as the ground truth is more robust and eliminates the flag as a redundant surface.

## Risks and Implications

- Consumers must know whether an agent is streaming or buffered before calling it. This is visible in the contract (`capabilities.streaming`) and the catalog entry, so runtime discovery is sufficient. Documentation should emphasize checking the contract before invoking.
- The `streaming_not_supported` error from a mismatched `mesh.call()` / `mesh.stream()` invocation may be confusing if the consumer assumed the SDK would adapt. Documentation and error messages must make the strict mode/method pairing clear.
- v1's hard split means an LLM-powered agent that wants to serve both streaming and non-streaming consumers must register two separate agents (e.g., `summarizer` and `summarizer-buffered`). This is an acknowledged limitation to be resolved by the v2 aggregator pattern.
