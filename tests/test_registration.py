"""
test_registration.py — Release gate tests for MCP SDK compatibility.

These tests verify the two runtime-critical claims from the APG pattern:
1. The low-level Server API exposes tools with full inputSchema to the agent
   (Finding 1: the agent must see parameter names, types, descriptions)
2. The handler return contract (list[TextContent]) is accepted by the SDK
   (Finding 2: bare dicts vs TextContent objects)

If these tests fail after a SDK version upgrade, the server will not work
correctly at runtime. Fix before publishing.
"""
import os
import sys
import json
import asyncio
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SKILL_TOOLS_SECRET", "__mock__")


class TestToolRegistration:
    """Verify that tools registered via low-level Server API expose full schemas."""

    def test_server_starts_without_error(self):
        """The server module imports and initializes without crashing."""
        from mcp_server import server
        assert server.TOOL_LIST is not None
        assert server.TOOL_HANDLERS is not None

    def test_tool_list_contains_registered_tools(self):
        """list_tools returns Tool objects with names from skill files."""
        from mcp_server import server
        tools = asyncio.run(server.handle_list_tools())
        assert len(tools) >= 1
        names = [t.name for t in tools]
        assert "dr-healthcheck" in names

    def test_tool_has_input_schema_with_properties(self):
        """
        RELEASE GATE: The agent must see parameter names, types, and descriptions.
        If inputSchema is empty or missing properties, the agent cannot construct
        valid tool calls.
        """
        from mcp_server import server
        tools = asyncio.run(server.handle_list_tools())
        dr_tool = next(t for t in tools if t.name == "dr-healthcheck")

        schema = dr_tool.inputSchema
        assert "properties" in schema, "inputSchema must have properties"
        assert "service_name" in schema["properties"], "service_name param missing"
        assert "region" in schema["properties"], "region param missing"

        # Verify param metadata is preserved
        sn = schema["properties"]["service_name"]
        assert sn.get("type") == "string"
        assert "description" in sn

        # Verify required list
        assert "required" in schema
        assert "service_name" in schema["required"]

    def test_tool_schema_includes_defaults(self):
        """Default values declared in frontmatter are visible in inputSchema."""
        from mcp_server import server
        tools = asyncio.run(server.handle_list_tools())
        dr_tool = next(t for t in tools if t.name == "dr-healthcheck")

        region = dr_tool.inputSchema["properties"]["region"]
        assert region.get("default") == "us-west-2"

    def test_tool_schema_includes_pattern_constraints(self):
        """Pattern constraints for injection prevention are in the schema."""
        from mcp_server import server
        tools = asyncio.run(server.handle_list_tools())
        dr_tool = next(t for t in tools if t.name == "dr-healthcheck")

        sn = dr_tool.inputSchema["properties"]["service_name"]
        assert "pattern" in sn, "pattern constraint missing — injection defense relies on this"


class TestHandlerReturnContract:
    """Verify that handler returns are accepted by the MCP SDK."""

    def test_handler_returns_text_content_list(self):
        """
        RELEASE GATE: The handler must return list[TextContent].
        Some SDK versions reject bare dicts; TextContent objects are the safe contract.
        """
        from mcp.types import TextContent
        from mcp_server import server

        result = asyncio.run(
            server.handle_call_tool("dr-healthcheck", {"service_name": "test-svc"})
        )

        assert isinstance(result, list), f"Expected list, got {type(result)}"
        assert len(result) >= 1
        assert isinstance(result[0], TextContent), (
            f"Expected TextContent, got {type(result[0])}. "
            "The SDK may reject bare dicts — use TextContent(type='text', text=...)"
        )
        assert result[0].type == "text"

    def test_handler_response_is_valid_json(self):
        """The text field contains parseable JSON."""
        from mcp_server import server

        result = asyncio.run(
            server.handle_call_tool("dr-healthcheck", {"service_name": "payment-svc"})
        )
        parsed = json.loads(result[0].text)
        assert isinstance(parsed, dict)
        assert "error" not in parsed, f"Tool returned error: {parsed}"

    def test_handler_includes_provenance_metadata(self):
        """Every successful response includes _meta with source/freshness/skill_file."""
        from mcp_server import server

        result = asyncio.run(
            server.handle_call_tool("dr-healthcheck", {"service_name": "order-svc"})
        )
        parsed = json.loads(result[0].text)
        assert "_meta" in parsed
        assert "source" in parsed["_meta"]
        assert "data_freshness" in parsed["_meta"]
        assert "skill_file" in parsed["_meta"]

    def test_handler_validation_error_returns_text_content(self):
        """Even error responses use TextContent (not exceptions)."""
        from mcp.types import TextContent
        from mcp_server import server

        # Invalid input (pattern constraint violation)
        result = asyncio.run(
            server.handle_call_tool("dr-healthcheck", {"service_name": "evil;rm"})
        )
        assert isinstance(result[0], TextContent)
        parsed = json.loads(result[0].text)
        assert "error" in parsed

    def test_unknown_tool_returns_error(self):
        """Calling a nonexistent tool returns an error, not an exception."""
        from mcp.types import TextContent
        from mcp_server import server

        result = asyncio.run(
            server.handle_call_tool("nonexistent-tool", {})
        )
        assert isinstance(result[0], TextContent)
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "Unknown tool" in parsed["error"]
