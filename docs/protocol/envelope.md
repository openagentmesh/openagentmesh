# Message Envelope

All messages use headers for metadata and a JSON body for payload.

## Request Headers

| Header | Description |
|--------|-------------|
| `X-Mesh-Request-Id` | Unique request identifier (UUID) |
| `X-Mesh-Stream` | Set to `true` when the caller expects a streaming response |
| `X-Mesh-Reply-To` | Reply subject for async callback pattern |
| `X-Mesh-Instance-Id` | Id of the mesh instance that sent the message (stamped on every outbound message) |

## Response Headers

| Header | Description |
|--------|-------------|
| `X-Mesh-Request-Id` | Echoed from request |
| `X-Mesh-Source` | Name of the responding agent |
| `X-Mesh-Status` | `ok` or `error` |
| `X-Mesh-Instance-Id` | Id of the mesh instance that sent the message (stamped on every outbound message) |
| `X-Mesh-Usage` | Optional self-reported LLM usage as JSON ([usage attribution](../concepts/usage.md)) |

## Publish Headers

`mesh.publish()` (raw publishing to arbitrary subjects, ADR-0058) auto-stamps:

| Header | Description |
|--------|-------------|
| `X-Mesh-Request-Id` | Unique message identifier (UUID) |
| `X-Mesh-Instance-Id` | Id of the publishing mesh instance |
| `X-Mesh-Content-Type` | `application/json` (BaseModel), `application/octet-stream` (bytes), or `text/plain` (str) |

User-supplied headers take priority over the auto-stamped values.

## Streaming Headers

Used on `mesh.stream.{request_id}` subjects for streaming responses, and on `mesh.agent.{name}.events` subjects for publisher emissions.

| Header | Description |
|--------|-------------|
| `X-Mesh-Stream-Seq` | Sequence number of the chunk (starts at 0) |
| `X-Mesh-Stream-End` | `true` on the terminal message, `false` on data chunks |
| `X-Mesh-Request-Id` | Echoed from request (streaming responses only) |
| `X-Mesh-Status` | Set to `error` when the stream terminates due to an error |
| `X-Mesh-Usage` | Optional self-reported LLM usage as JSON, on the stream-end frame only ([usage attribution](../concepts/usage.md)) |

## Success Response

`X-Mesh-Status: ok`: body contains the agent's output as JSON.

## Error Response

`X-Mesh-Status: error`: body contains a structured error:

```json
{
  "code": "invalid_input",
  "message": "Field 'text' is required",
  "agent": "summarizer",
  "request_id": "abc-123",
  "details": {}
}
```

### Error Codes

| Code | Meaning | Origin |
|------|---------|--------|
| `invalid_input` | Caller's payload failed schema validation | Agent-side (no handler call) |
| `handler_error` | Unhandled exception in the handler | Agent-side |
| `invocation_mismatch` | Caller used the wrong verb for the agent's capabilities | Agent-side or client pre-flight |
| `chunk_sequence_error` | Stream chunks arrived out of order | Client-side |
| `timeout` | No response within the deadline | Client-side |
| `not_found` | No agent registered with that name | Client-side |
| `not_available` | Agent in the catalog but currently offline (lifecycle gate closed or draining) | Client-side |
| `agent_died` | Agent left the mesh during an in-flight request | Client-side |
| `connection_failed` | Could not connect to the mesh | Client-side |
| `connection_denied` | Connection or operation rejected by mesh permissions | Client-side |
| `kv_key_exists` | `mesh.kv.create()` on a key that already exists | Client-side |

The full taxonomy, with the Python exception class for each code and retry
guidance, is in [Errors](../concepts/errors.md).
