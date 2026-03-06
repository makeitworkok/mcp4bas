"""Tests for the mcp4bas orchestrator server."""
from __future__ import annotations

from mcp4bas.server import create_mcp_server, get_network_context


def test_create_server() -> None:
    server = create_mcp_server()
    assert server.name == "mcp4bas"


def test_get_network_context_returns_ok() -> None:
    result = get_network_context()
    assert result["status"] == "ok"
    assert result["tool"] == "get_network_context"
    assert "all_interfaces" in result
    assert isinstance(result["all_interfaces"], list)
    assert "message" in result


def test_get_network_context_primary_field() -> None:
    result = get_network_context()
    # primary may be None in some CI environments, but the key must exist
    assert "primary" in result
