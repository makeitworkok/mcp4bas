"""MCP4BAS Orchestrator Server.

Starts the mcp4bas orchestrator, which:
  1. Performs full network discovery at startup ("where am I?")
     -- detects IP, subnet, gateway; pings gateway; falls back to nmap if needed
  2. Caches the network result to ~/.mcp4bas/network_cache.json
  3. Spawns configured sibling MCP servers as stdio subprocesses
  4. Proxies all sibling tools through this single MCP connection
  5. Watches for subnet changes every 10 min; auto-restarts BACnet sibling on change
  6. Exposes a get_network_context tool that always returns live network state

Configure siblings via environment variables:

    MCP4BAS_SIBLING_BACNET="python -m mcp4bacnet"
    MCP4BAS_SIBLING_MODBUS="python -m mcp4modbus"

Other environment variables:

    MCP4BAS_VERBOSE=1            Enable verbose probe/cache logging
    MCP4BAS_NETWORK_CACHE=<path> Override network cache file path

See src/mcp4bas/config.py for full configuration reference.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from mcp4bas.config import OrchestratorConfig
from mcp4bas.network import (
    NetworkDiscovery,
    NetworkWatcher,
    _VERBOSE as _NET_VERBOSE,
    discover_network,
    discover_network_context,
    startup_network_check,
)
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

# Module-level state -- populated during lifespan startup
_proxy: OrchestratorProxy | None = None
_watcher: NetworkWatcher | None = None
_verbose: bool = _NET_VERBOSE


@asynccontextmanager
async def _lifespan(server: Any) -> AsyncGenerator[None, None]:
    """Orchestrator startup: discover network, spawn siblings, register tools."""
    global _proxy, _watcher

    # Step 1 -- network discovery (cache-aware, gateway probe, nmap fallback)
    discovery = startup_network_check(verbose=_verbose)

    _LOGGER.info(
        "network_context ip=%s subnet=%s gateway=%s iface=%s status=%s fallback=%s",
        discovery.ip_address,
        discovery.subnet,
        discovery.gateway,
        discovery.interface,
        discovery.status,
        discovery.fallback_used,
    )

    if discovery.fallback_used:
        _LOGGER.warning(
            "network_fallback_active -- BACnet broadcasts may not reach devices. "
            "Set MCP4BAS_SIBLING_BACNET and verify network connectivity."
        )

    # Step 2 -- load sibling config and start proxy
    config = OrchestratorConfig.from_env()

    if not config.siblings:
        _LOGGER.info(
            "no_siblings_configured -- set MCP4BAS_SIBLING_<NAME>=<command> to add servers"
        )

    proxy = OrchestratorProxy(config, discovery)
    discovered_tools = await proxy.start()
    _proxy = proxy

    # Step 3 -- subnet change watcher (restarts BACnet sibling on network move)
    async def _on_network_change(new_discovery: NetworkDiscovery) -> None:
        _LOGGER.warning(
            "subnet_changed old=%s new=%s gateway=%s -- restarting BACnet sibling",
            discovery.subnet,
            new_discovery.subnet,
            new_discovery.gateway,
        )
        if _proxy is not None:
            ok = await _proxy.restart_sibling("bacnet", new_discovery)
            if ok:
                _LOGGER.info("bacnet_sibling_restarted subnet=%s", new_discovery.subnet)
            else:
                _LOGGER.error(
                    "bacnet_sibling_restart_failed -- BACnet may be unreachable on new subnet"
                )

    watcher = NetworkWatcher(interval_sec=600, on_change=_on_network_change)
    await watcher.start()
    _watcher = watcher

    # Step 4 -- register proxy tools dynamically
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
    await watcher.stop()
    _watcher = None
    await proxy.stop()
    _proxy = None


mcp = FastMCP(
    "mcp4bas",
    instructions=(
        "MCP4BAS orchestrator. Routes building automation protocol tool calls "
        "to specialist sibling MCP servers (BACnet, Modbus, MQTT, Haystack, SNMP). "
        "Use get_network_context to inspect the server live network position "
        "including subnet, gateway, and whether a fallback is active."
    ),
    lifespan=_lifespan,
)


@mcp.tool(
    description=(
        "Return live network context for this machine -- subnet, gateway, interface, "
        "status (known/new), and whether the fallback subnet is active. "
        "Always reflects current state; re-runs discovery on each call."
    )
)
def get_network_context() -> dict[str, Any]:
    """Report the live network context.  Re-runs discovery on each invocation."""
    _LOGGER.info("tool=get_network_context")
    discovery = discover_network(verbose=_verbose)
    contexts = discover_network_context()
    return {
        "status": "ok",
        "tool": "get_network_context",
        "discovery": discovery.as_dict(),
        "all_interfaces": [ctx.as_dict() for ctx in contexts],
        "message": (
            f"Subnet: {discovery.subnet} | "
            f"Gateway: {discovery.gateway or 'unknown'} | "
            f"Status: {discovery.status} | "
            f"Fallback: {discovery.fallback_used}"
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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose network probe and cache logging",
    )
    return parser


def main() -> int:
    global _verbose
    args = build_arg_parser().parse_args()
    transport = "stdio" if args.stdio else args.transport
    if args.verbose:
        _verbose = True
        logging.getLogger("mcp4bas.network").setLevel(logging.DEBUG)
    _LOGGER.info("starting_server transport=%s verbose=%s", transport, _verbose)
    server = create_mcp_server()
    server.run(transport=transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
