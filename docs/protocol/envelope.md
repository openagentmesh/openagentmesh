# Message Envelope

All messages use headers for metadata and a JSON body for payload.

## Request Headers

| Header | Description |
|--------|-------------|
| `X-Mesh-Request-Id` | Unique request identifier (UUID) |
| `X-Mesh-Source` | Name of the calling agent or client |
| `X-Mesh-Reply-To` | Reply subject for async callback pattern |

## Response Headers

| Header | Description |
|--------|-------------|
| `X-Mesh-Request-Id` | Echoed from request |
| `X-Mesh-Source` | Name of the responding agent |
| `X-Mesh-Status` | `ok` or `error` |
| `X-Mesh-Usage` | Optional JSON with token usage data (see [Usage Attribution](../concepts/usage.md)) |

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

| Code | Meaning |
|------|---------|
| `validation_error` | Input failed Pydantic validation |
| `handler_error` | Unhandled exception in the handler |
| `timeout` | Agent did not respond within the deadline |
| `not_found` | No agent registered with that name |
| `rate_limited` | Agent is rate-limiting requests |
