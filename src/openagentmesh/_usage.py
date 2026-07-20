"""Usage attribution primitives (ADR-0023).

Handlers opt in by calling :func:`report_usage` while a request is being
handled. The host collects the reports per request, stamps the merged result
on the ``X-Mesh-Usage`` reply header (stream-end frame for streamers), and
publishes a ``usage_reported`` observe event. The mesh propagates usage data;
it never generates or validates it.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

from pydantic import BaseModel

X_MESH_USAGE = "X-Mesh-Usage"


class Usage(BaseModel):
    """Self-reported LLM usage for one handler invocation. All fields optional."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    model: str | None = None
    estimated_cost_usd: float | None = None


# Per-request report slot. The host sets a fresh list before invoking the
# handler; any task the handler spawns copies the context and shares the
# same (mutable) list, so usage reported from spawned work is captured too.
_usage_reports: ContextVar[list[Usage] | None] = ContextVar(
    "_usage_reports", default=None
)


def report_usage(usage: Usage) -> None:
    """Report LLM usage from inside a handler (ADR-0023).

    May be called multiple times per request; token and cost fields
    accumulate, ``model`` keeps the last reported value. Valid only while a
    call/stream request is being handled.
    """
    reports = _usage_reports.get()
    if reports is None:
        raise RuntimeError(
            "report_usage() called outside a mesh request context. It is only "
            "valid inside a handler while a call/stream request is in flight."
        )
    reports.append(usage)


def begin_usage_capture() -> Token[list[Usage] | None]:
    """Open a fresh capture slot for one request. Host-side only."""
    return _usage_reports.set([])


def end_usage_capture(token: Token[list[Usage] | None]) -> Usage | None:
    """Close the capture slot and return the merged usage, if any reported."""
    reports = _usage_reports.get()
    _usage_reports.reset(token)
    if not reports:
        return None
    merged = Usage()
    for report in reports:
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(report, field)
            if value is not None:
                setattr(merged, field, (getattr(merged, field) or 0) + value)
        if report.estimated_cost_usd is not None:
            merged.estimated_cost_usd = (
                merged.estimated_cost_usd or 0.0
            ) + report.estimated_cost_usd
        if report.model is not None:
            merged.model = report.model
    return merged
