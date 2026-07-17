"""Tests for AgentContract.to_agent_card (ADR-0012 projection)."""

import json

from openagentmesh import AgentContract


def _contract(**kwargs) -> AgentContract:
    defaults: dict = dict(
        name="summarizer",
        description="Summarizes input text",
        version="1.0.0",
        subject="mesh.agent.summarizer",
        tags=["text", "summarization"],
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
    )
    defaults.update(kwargs)
    return AgentContract(**defaults)


class TestToAgentCard:
    def test_is_registry_doc_without_x_agentmesh(self):
        c = _contract()
        card = c.to_agent_card()

        registry_doc = json.loads(c.to_registry_json())
        assert "x-agentmesh" in registry_doc
        assert "x-agentmesh" not in card

        registry_doc.pop("x-agentmesh")
        assert card == registry_doc

    def test_a2a_top_level_fields(self):
        card = _contract().to_agent_card()
        assert card["name"] == "summarizer"
        assert card["description"] == "Summarizes input text"
        assert card["version"] == "1.0.0"
        assert card["capabilities"] == {"streaming": False, "invocable": True}
        skill = card["skills"][0]
        assert skill["id"] == "summarizer"
        assert skill["inputSchema"]["required"] == ["text"]
        assert skill["outputSchema"]["properties"]["summary"] == {"type": "string"}

    def test_url_injected_when_given(self):
        card = _contract().to_agent_card(url="https://agents.example.com/summarizer")
        assert card["url"] == "https://agents.example.com/summarizer"

    def test_url_omitted_by_default(self):
        card = _contract().to_agent_card()
        assert "url" not in card

    def test_publisher_contracts_project_too(self):
        # Projection is not gated on invocability: A2A cards can describe
        # streaming/publishing agents as well.
        c = _contract(invocable=False, streaming=True)
        card = c.to_agent_card()
        assert card["capabilities"] == {"streaming": True, "invocable": False}

    def test_card_is_json_serializable(self):
        card = _contract().to_agent_card(url="https://example.com/a")
        json.dumps(card)
