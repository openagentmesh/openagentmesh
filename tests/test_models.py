"""Unit tests for AgentContract and CatalogEntry models."""

import pytest
from pydantic import BaseModel

from agentmesh.models import AgentContract, CatalogEntry


def _make_contract(**kwargs) -> AgentContract:
    defaults = dict(name="test-agent", description="A test agent")
    return AgentContract(**(defaults | kwargs))


# --- AgentContract.subject ---


def test_subject_without_channel():
    contract = _make_contract(name="summarizer", channel="")
    assert contract.subject == "mesh.agent.summarizer"


def test_subject_with_channel():
    contract = _make_contract(name="summarizer", channel="nlp")
    assert contract.subject == "mesh.agent.nlp.summarizer"


def test_subject_nested_channel():
    contract = _make_contract(name="risk-scorer", channel="finance.risk")
    assert contract.subject == "mesh.agent.finance.risk.risk-scorer"


# --- AgentContract.to_catalog_entry ---


def test_to_catalog_entry_maps_fields():
    contract = AgentContract(
        name="greeter",
        description="Says hello.",
        channel="demo",
        version="2.0.0",
        tags=["greeting", "nlp"],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    entry = contract.to_catalog_entry()
    assert entry.name == "greeter"
    assert entry.channel == "demo"
    assert entry.description == "Says hello."
    assert entry.version == "2.0.0"
    assert entry.tags == ["greeting", "nlp"]


def test_to_catalog_entry_excludes_schemas():
    contract = _make_contract(input_schema={"type": "object"}, output_schema={"type": "object"})
    entry = contract.to_catalog_entry()
    assert not hasattr(entry, "input_schema")
    assert not hasattr(entry, "output_schema")


def test_to_catalog_entry_returns_catalog_entry():
    contract = _make_contract()
    entry = contract.to_catalog_entry()
    assert isinstance(entry, CatalogEntry)


# --- CatalogEntry defaults ---


def test_catalog_entry_defaults():
    entry = CatalogEntry(name="agent-x")
    assert entry.channel == ""
    assert entry.description == ""
    assert entry.version == "1.0.0"
    assert entry.tags == []


# --- AgentContract defaults ---


def test_agent_contract_defaults():
    contract = AgentContract(name="x")
    assert contract.description == ""
    assert contract.version == "1.0.0"
    assert contract.channel == ""
    assert contract.tags == []
    assert contract.input_schema == {}
    assert contract.output_schema == {}
