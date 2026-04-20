"""Tests for AgentContract tool conversion methods (ADR-0039)."""

import pytest

from openagentmesh import AgentContract


def _contract(
    name: str = "summarizer",
    description: str = "Summarizes text",
    **kwargs,
) -> AgentContract:
    defaults = dict(
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "max_length": {"type": "integer", "default": 100},
            },
            "required": ["text"],
        },
    )
    defaults.update(kwargs)
    return AgentContract(name=name, description=description, **defaults)


class TestToToolSchema:
    def test_returns_canonical_triple(self):
        c = _contract()
        result = c.to_tool_schema()
        assert set(result.keys()) == {"name", "description", "input_schema"}
        assert result["name"] == "summarizer"
        assert result["description"] == "Summarizes text"
        assert result["input_schema"]["type"] == "object"

    def test_dots_replaced_with_underscores(self):
        c = _contract(name="billing.invoice.create")
        result = c.to_tool_schema()
        assert result["name"] == "billing_invoice_create"

    def test_hyphens_preserved(self):
        c = _contract(name="my-agent")
        result = c.to_tool_schema()
        assert result["name"] == "my-agent"

    def test_invalid_name_raises(self):
        c = _contract(name="bad name!")
        with pytest.raises(ValueError, match="does not match"):
            c.to_tool_schema()

    def test_name_too_long_raises(self):
        c = _contract(name="a" * 65)
        with pytest.raises(ValueError, match="does not match"):
            c.to_tool_schema()

    def test_output_schema_appends_returns_line(self):
        c = _contract(
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        )
        result = c.to_tool_schema()
        assert result["description"].startswith("Summarizes text")
        assert "Returns:" in result["description"]
        assert "summary" in result["description"]
        assert "confidence" in result["description"]

    def test_no_output_schema_no_returns_line(self):
        c = _contract(output_schema=None)
        result = c.to_tool_schema()
        assert "Returns:" not in result["description"]

    def test_no_input_schema_returns_empty_object(self):
        c = _contract(input_schema=None)
        result = c.to_tool_schema()
        assert result["input_schema"] == {"type": "object", "properties": {}}

    def test_publisher_raises(self):
        c = _contract(invocable=False)
        with pytest.raises(ValueError, match="not invocable"):
            c.to_tool_schema()

    def test_input_schema_not_mutated(self):
        original_schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        }
        c = _contract(input_schema=original_schema)
        c.to_tool_schema()
        assert "title" not in original_schema


class TestToOpenaiTool:
    def test_chat_completions_envelope(self):
        c = _contract()
        result = c.to_openai_tool()
        assert result["type"] == "function"
        assert "function" in result
        fn = result["function"]
        assert fn["name"] == "summarizer"
        assert fn["description"] == "Summarizes text"
        assert fn["parameters"]["type"] == "object"

    def test_responses_api_flat(self):
        c = _contract()
        result = c.to_openai_tool(api="responses")
        assert result["type"] == "function"
        assert "function" not in result
        assert result["name"] == "summarizer"
        assert result["parameters"]["type"] == "object"

    def test_strict_mode_sets_flag(self):
        c = _contract()
        result = c.to_openai_tool(strict=True)
        fn = result["function"]
        assert fn["strict"] is True

    def test_strict_adds_additional_properties_false(self):
        c = _contract()
        result = c.to_openai_tool(strict=True)
        schema = result["function"]["parameters"]
        assert schema["additionalProperties"] is False

    def test_strict_all_properties_required(self):
        c = _contract()
        result = c.to_openai_tool(strict=True)
        schema = result["function"]["parameters"]
        assert "text" in schema["required"]
        assert "max_length" in schema["required"]

    def test_strict_optional_becomes_nullable(self):
        c = _contract(
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "lang": {"type": "string"},
                },
                "required": ["text"],
            },
        )
        result = c.to_openai_tool(strict=True)
        schema = result["function"]["parameters"]
        lang_type = schema["properties"]["lang"]["type"]
        assert lang_type == ["string", "null"]

    def test_strict_strips_unsupported_keywords(self):
        c = _contract(
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "title": "Text",
                        "format": "uri",
                        "pattern": "^https://",
                        "minLength": 1,
                        "maxLength": 1000,
                        "default": "hello",
                    },
                    "count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                    },
                },
                "required": ["text", "count"],
            },
        )
        result = c.to_openai_tool(strict=True)
        props = result["function"]["parameters"]["properties"]
        for kw in ("title", "format", "pattern", "minLength", "maxLength", "default"):
            assert kw not in props["text"]
        for kw in ("minimum", "maximum"):
            assert kw not in props["count"]

    def test_strict_nested_objects(self):
        c = _contract(
            input_schema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "properties": {
                            "verbose": {"type": "boolean"},
                        },
                    },
                },
                "required": ["config"],
            },
        )
        result = c.to_openai_tool(strict=True)
        nested = result["function"]["parameters"]["properties"]["config"]
        assert nested["additionalProperties"] is False

    def test_strict_responses_api(self):
        c = _contract()
        result = c.to_openai_tool(api="responses", strict=True)
        assert result["strict"] is True
        assert result["parameters"]["additionalProperties"] is False

    def test_publisher_raises(self):
        c = _contract(invocable=False)
        with pytest.raises(ValueError, match="not invocable"):
            c.to_openai_tool()

    def test_dots_in_name(self):
        c = _contract(name="finance.scorer")
        result = c.to_openai_tool()
        assert result["function"]["name"] == "finance_scorer"


class TestToAnthropicTool:
    def test_flat_format(self):
        c = _contract()
        result = c.to_anthropic_tool()
        assert result["name"] == "summarizer"
        assert result["description"] == "Summarizes text"
        assert "input_schema" in result
        assert "function" not in result
        assert "type" not in result

    def test_schema_passed_through(self):
        c = _contract()
        result = c.to_anthropic_tool()
        assert result["input_schema"]["properties"]["text"]["type"] == "string"

    def test_no_strict_parameter(self):
        """to_anthropic_tool has no strict parameter."""
        c = _contract()
        with pytest.raises(TypeError):
            c.to_anthropic_tool(strict=True)

    def test_publisher_raises(self):
        c = _contract(invocable=False)
        with pytest.raises(ValueError, match="not invocable"):
            c.to_anthropic_tool()

    def test_dots_in_name(self):
        c = _contract(name="billing.invoice")
        result = c.to_anthropic_tool()
        assert result["name"] == "billing_invoice"

    def test_output_schema_in_description(self):
        c = _contract(
            output_schema={
                "type": "object",
                "properties": {"result": {"type": "string"}},
            },
        )
        result = c.to_anthropic_tool()
        assert "Returns:" in result["description"]
        assert "result" in result["description"]


class TestNameCollision:
    def test_dot_and_underscore_produce_same_name(self):
        """Document the known lossy collision (risk in ADR-0039)."""
        c1 = _contract(name="finance.scorer")
        c2 = _contract(name="finance_scorer")
        assert c1.to_tool_schema()["name"] == c2.to_tool_schema()["name"]
