# Message Envelope

All messages use headers for metadata and a JSON body for payload.

## Request Headers

| Header | Description |
|--------|-------------|
| `X-Mesh-Request-Id` | Unique request identifier (UUID) |
| `X-Mesh-Stream` | Set to `true` when the caller expects a streaming response |
| `X-Mesh-Reply-To` | Reply subject for async callback pattern |

## Response Headers

| Header | Description |
|--------|-------------|
| `X-Mesh-Request-Id` | Echoed from request |
| `X-Mesh-Source` | Name of the responding agent |
| `X-Mesh-Status` | `ok` or `error` |

## Streaming Headers

Used on `mesh.stream.{request_id}` subjects for streaming responses, and on `mesh.agent.{name}.events` subjects for publisher emissions.

| Header | Description |
|--------|-------------|
| `X-Mesh-Stream-Seq` | Sequence number of the chunk (starts at 0) |
| `X-Mesh-Stream-End` | `true` on the terminal message, `false` on data chunks |
| `X-Mesh-Request-Id` | Echoed from request (streaming responses only) |
| `X-Mesh-Status` | Set to `error` when the stream terminates due to an error |

## Success Response

`X-Mesh-Status: ok`: body contains the agent's output as JSON.

## Error Response

`X-Mesh-Status: error`: body contains a structured error:

```json
{
  "code": "validation_error",
  "message": "Field 'text' is required",
  "agent": "summarizer",
  "request_id": "abc-123",
  "details": {}
}
```

### Error Codes

| Code | Meaning | Origin |
|------|---------|--------|
| `handler_error` | Unhandled exception in the handler (including validation failures) | Agent-side |
| `invocation_mismatch` | Caller used the wrong verb for the agent's capabilities | Agent-side or client pre-flight |
| `chunk_sequence_error` | Stream chunks arrived out of order | Client-side |
| `timeout` | No response within the deadline | Client-side |
| `not_found` | No agent registered with that name | Client-side |
| `connection_failed` | Could not connect to the mesh | Client-side |
