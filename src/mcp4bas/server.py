"""MCP4BAS Orchestrator Server.

Starts the mcp4bas orchestrator, which:
  1. Discovers the local network context ("where am I?")
  2. Spawns configured sibling MCP servers as stdio subprocesses
  3. Proxies all sibling tools through this single MCP connection
  4. Exposes its own ``get_network_context`` tool

Configure siblings via environment variables::

    MCP4BAS_SIBLING_BACNET="python -m mcp4bacnet"
    MCP4BAS_SIBLING_MODBUS="python -m mcp4modbus"

See ``src/mcp4bas/config.py`` for full configuration reference.
"""
from __future__ import annotations

import argparse
import importlib
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from mcp4bas.config import OrchestratorConfig
from mcp4bas.network import discover_network_context, select_primary_interface
from mcp4bas.proxy import OrchestratorProxy


def _resolve_fastmcp() -> type:
    for module_path in ("mcp.server.fastmcp", "fastmcp"):
        try:
            module = importlib.import_module(module_path)
            return getattr(module, "FastMCP")
        except (ModuleNotFoundError, AttributeError):
            continue
    raise RuntimeError(
        "FastMCP is not available. Install with `pip install mcp[cli]`."
    )


_LOGGER = logging.getLogger("mcp4bas.server")
if not _LOGGER.handlers:
    _handler = logging.StreamHandler(stream=sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    _LOGGER.addHandler(_handler)
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False

FastMCP = _resolve_fastmcp()

# Module-level proxy holder — populated during lifespan startup
_proxy: OrchestratorProxy | None = None


@asynccontextmanager
async def _lifespan(server: Any) -> AsyncGenerator[None, None]:
    """Orchestrator startup: discover network, spawn siblings, register tools."""
    global _proxy

    # Step 1: Discover network context
    contexts = discover_network_context()
    primary = select_primary_interface(contexts)

    if primary:
        _LOGGER.info(
            "network_context ip=%s cidr=%s iface=%s",
            primary.ip_address,
            primary.cidr,
            primary.interface,
        )
    else:
        _LOGGER.warning("network_context could not be determined")

    # Step 2: Load sibling config and start proxy
    config = OrchestratorConfig.from_env()

    if not config.siblings:
        _LOGGER.info(
            "no_siblings_configured — set MCP4BAS_SIBLING_<NAME>=<command> to add servers"
        )

    proxy = OrchestratorProxy(config, primary)
    discovered_tools = await proxy.start()
    _proxy = proxy

    # Step 3: Dynamically register proxy tools on this FastMCP instance
    for tool in discovered_tools:
        tool_name = tool.name
        tool_description = tool.description or tool_name

        def _make_handler(name: str):
            async def _handler(**kwargs: Any) -> dict[str, Any]:
                if _proxy is None:
                    return {"status": "error", "message": "Proxy not initialized"}
                return await _proxy.call_tool(name, kwargs)

            _handler.__name__ = name
            _handler.__doc__ = tool_description
            return _handler

        server.add_tool(
            _make_handler(tool_name),
            name=tool_name,
            description=tool_description,
        )

    _LOGGER.info("orchestrator_ready tools=%d", len(discovered_tools))

    yield  # Server is live

    # Shutdown
    await proxy.stop()
    _proxy = None


mcp = FastMCP(
    "mcp4bas",
    instructions=(
        "MCP4BAS orchestrator. Routes building automation protocol tool calls "
        "to specialist sibling MCP servers (BACnet, Modbus, MQTT, Haystack, SNMP). "
        "Use get_network_context to inspect the server's network position."
    ),
    lifespan=_lifespan,
)


@mcp.tool(description="Return the network interfaces discovered on this machine at startup")
def get_network_context() -> dict[str, Any]:
    """Report the local network context used to configure sibling servers."""
    _LOGGER.info("tool=get_network_context")
    contexts = discover_network_context()
    primary = select_primary_interface(contexts)
    return {
        "status": "ok",
        "tool": "get_network_context",
        "primary": primary.as_dict() if primary else None,
        "all_interfaces": [ctx.as_dict() for ctx in contexts],
        "message": (
            f"Found {len(contexts)} interface(s). "
            f"Primary: {primary.ip_address if primary else 'none'} "
            f"({primary.cidr if primary else 'unknown'})."
        ),
    }


def create_mcp_server() -> Any:
    return mcp


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run MCP4BAS orchestrator using FastMCP."
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Transport to run the MCP server with",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Deprecated alias for --transport stdio",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    transport = "stdio" if args.stdio else args.transport
    _LOGGER.info("starting_server transport=%s", transport)
    server = create_mcp_server()
    server.run(transport=transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
