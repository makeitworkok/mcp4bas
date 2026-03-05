from __future__ import annotations

import argparse
import importlib
import logging
import sys
from typing import Any

from mcp4bas.tools.core import default_registry


def _resolve_fastmcp() -> type:
    for module_path in ("mcp.server.fastmcp", "fastmcp"):
        try:
            module = importlib.import_module(module_path)
            return getattr(module, "FastMCP")
        except (ModuleNotFoundError, AttributeError):
            continue
    raise RuntimeError(
        "FastMCP is not available. Install dependencies with `pip install -r dev-requirements.txt`."
    )


FastMCP = _resolve_fastmcp()

_REGISTRY = default_registry()

_LOGGER = logging.getLogger("mcp4bas.server")
if not _LOGGER.handlers:
    _handler = logging.StreamHandler(stream=sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    _LOGGER.addHandler(_handler)
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False

mcp = FastMCP("mcp4bas", instructions="MCP server for BAS operations.")


@mcp.tool(description="Discover BACnet devices on network")
def who_is() -> dict[str, Any]:
    _LOGGER.info("tool=who_is request={}")
    return _REGISTRY.call(name="who_is", arguments={})


@mcp.tool(description="Read a BACnet object property")
def read_property(object_id: str, property: str = "present-value") -> dict[str, Any]:
    _LOGGER.info(
        "tool=read_property request=%s",
        {"object_id": object_id, "property": property},
    )
    return _REGISTRY.call(
        name="read_property",
        arguments={"object_id": object_id, "property": property},
    )


@mcp.tool(description="Write a BACnet object property")
def write_property(
    object_id: str,
    property: str,
    value: str | float | int,
    priority: int | None = None,
) -> dict[str, Any]:
    _LOGGER.info(
        "tool=write_property request=%s",
        {"object_id": object_id, "property": property, "value": value, "priority": priority},
    )
    return _REGISTRY.call(
        name="write_property",
        arguments={
            "object_id": object_id,
            "property": property,
            "value": value,
            "priority": priority,
        },
    )


@mcp.tool(description="Read BACnet trend log entries with optional window and fallback")
def bacnet_get_trend(
    trend_object_id: str,
    limit: int = 100,
    window_minutes: int | None = None,
    source_object_id: str | None = None,
    source_property: str = "present-value",
) -> dict[str, Any]:
    _LOGGER.info(
        "tool=bacnet_get_trend request=%s",
        {
            "trend_object_id": trend_object_id,
            "limit": limit,
            "window_minutes": window_minutes,
            "source_object_id": source_object_id,
            "source_property": source_property,
        },
    )
    return _REGISTRY.call(
        name="bacnet_get_trend",
        arguments={
            "trend_object_id": trend_object_id,
            "limit": limit,
            "window_minutes": window_minutes,
            "source_object_id": source_object_id,
            "source_property": source_property,
        },
    )


@mcp.tool(description="Read BACnet weekly and exception schedules")
def bacnet_get_schedule(schedule_object_id: str) -> dict[str, Any]:
    _LOGGER.info(
        "tool=bacnet_get_schedule request=%s",
        {"schedule_object_id": schedule_object_id},
    )
    return _REGISTRY.call(
        name="bacnet_get_schedule",
        arguments={"schedule_object_id": schedule_object_id},
    )


@mcp.tool(description="Resolve adapter MAC address for an IP-connected BAS target")
def bacnet_get_ip_adapter_mac(
    ip_address: str | None = None,
    target_address: str | None = None,
    probe: bool = True,
) -> dict[str, Any]:
    _LOGGER.info(
        "tool=bacnet_get_ip_adapter_mac request=%s",
        {
            "ip_address": ip_address,
            "target_address": target_address,
            "probe": probe,
        },
    )
    return _REGISTRY.call(
        name="bacnet_get_ip_adapter_mac",
        arguments={
            "ip_address": ip_address,
            "target_address": target_address,
            "probe": probe,
        },
    )


@mcp.tool(description="Read Modbus holding or input registers")
def modbus_read_registers(
    register_type: str,
    address: int,
    count: int = 1,
) -> dict[str, Any]:
    _LOGGER.info(
        "tool=modbus_read_registers request=%s",
        {"register_type": register_type, "address": address, "count": count},
    )
    return _REGISTRY.call(
        name="modbus_read_registers",
        arguments={"register_type": register_type, "address": address, "count": count},
    )


@mcp.tool(description="Write Modbus register or coil")
def modbus_write(
    write_type: str,
    address: int,
    value: int | bool,
) -> dict[str, Any]:
    _LOGGER.info(
        "tool=modbus_write request=%s",
        {"write_type": write_type, "address": address, "value": value},
    )
    return _REGISTRY.call(
        name="modbus_write",
        arguments={"write_type": write_type, "address": address, "value": value},
    )


@mcp.tool(description="Discover Haystack points (dataset/API) with tag validation")
def haystack_discover_points(limit: int = 100) -> dict[str, Any]:
    _LOGGER.info(
        "tool=haystack_discover_points request=%s",
        {"limit": limit},
    )
    return _REGISTRY.call(
        name="haystack_discover_points",
        arguments={"limit": limit},
    )


@mcp.tool(description="Fetch Haystack point metadata with tag validation output")
def haystack_get_point_metadata(point_id: str) -> dict[str, Any]:
    _LOGGER.info(
        "tool=haystack_get_point_metadata request=%s",
        {"point_id": point_id},
    )
    return _REGISTRY.call(
        name="haystack_get_point_metadata",
        arguments={"point_id": point_id},
    )


@mcp.tool(description="Ingest MQTT telemetry payload for normalization and validation")
def mqtt_ingest_message(topic: str, payload: dict[str, Any], source: str = "manual") -> dict[str, Any]:
    _LOGGER.info(
        "tool=mqtt_ingest_message request=%s",
        {"topic": topic, "source": source},
    )
    return _REGISTRY.call(
        name="mqtt_ingest_message",
        arguments={"topic": topic, "payload": payload, "source": source},
    )


@mcp.tool(description="Get latest normalized MQTT telemetry points")
def mqtt_get_latest_points(site: str | None = None, equip: str | None = None, limit: int = 100) -> dict[str, Any]:
    _LOGGER.info(
        "tool=mqtt_get_latest_points request=%s",
        {"site": site, "equip": equip, "limit": limit},
    )
    return _REGISTRY.call(
        name="mqtt_get_latest_points",
        arguments={"site": site, "equip": equip, "limit": limit},
    )


@mcp.tool(description="Publish MQTT payload with write safety controls")
def mqtt_publish_message(topic: str, payload: dict[str, Any], source: str = "mcp_tool") -> dict[str, Any]:
    _LOGGER.info(
        "tool=mqtt_publish_message request=%s",
        {"topic": topic, "source": source},
    )
    return _REGISTRY.call(
        name="mqtt_publish_message",
        arguments={"topic": topic, "payload": payload, "source": source},
    )


@mcp.tool(description="Read a single SNMP OID from target host")
def snmp_get(oid: str, host: str | None = None) -> dict[str, Any]:
    _LOGGER.info(
        "tool=snmp_get request=%s",
        {"oid": oid, "host": host},
    )
    return _REGISTRY.call(
        name="snmp_get",
        arguments={"oid": oid, "host": host},
    )


@mcp.tool(description="Read SNMP OID subtree entries with output limit")
def snmp_walk(oid_prefix: str, host: str | None = None, limit: int = 100) -> dict[str, Any]:
    _LOGGER.info(
        "tool=snmp_walk request=%s",
        {"oid_prefix": oid_prefix, "host": host, "limit": limit},
    )
    return _REGISTRY.call(
        name="snmp_walk",
        arguments={"oid_prefix": oid_prefix, "host": host, "limit": limit},
    )


@mcp.tool(description="Summarize SNMP device uptime and interface health")
def snmp_device_health_summary(host: str | None = None, interface_limit: int = 20) -> dict[str, Any]:
    _LOGGER.info(
        "tool=snmp_device_health_summary request=%s",
        {"host": host, "interface_limit": interface_limit},
    )
    return _REGISTRY.call(
        name="snmp_device_health_summary",
        arguments={"host": host, "interface_limit": interface_limit},
    )


def create_mcp_server() -> Any:
    return mcp


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MCP4BAS using the official FastMCP server.")
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
