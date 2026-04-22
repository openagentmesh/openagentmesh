"""NATS subject and KV key computation (ADR-0049).

An agent's name is a dotted identifier that maps directly to the NATS
subject tail after ``mesh.agent.``. These helpers encode that mapping.
"""

from __future__ import annotations


def compute_subject(name: str) -> str:
    return f"mesh.agent.{name}"


def compute_error_subject(name: str) -> str:
    return f"mesh.errors.{name}"


def compute_event_subject(name: str) -> str:
    return f"mesh.agent.{name}.events"
