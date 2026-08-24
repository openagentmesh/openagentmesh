"""Scenario UI dashboard backend for the wildfire demo.

The backend is a FastAPI app launched via ``python -m demos.wildfire.dashboard``
that connects to NATS as a plain ``AgentMesh`` client (not an ``@mesh.agent``
registered scenario agent), watches four namespaces, and exposes one
WebSocket endpoint that bidirectionally fans out updates and accepts click
writes.

See ``km/specs/wildfire/dashboard.md`` (post D-25 amendment) and
``.planning/phases/02-cascade-closure/02-CONTEXT.md`` decisions D-37, D-38,
D-39, D-49, D-50, D-52, D-53 for the design rationale.
"""
