from __future__ import annotations

import pytest

from mcp4bas.server import (
    bacnet_get_ip_adapter_mac,
    bacnet_get_schedule,
    bacnet_get_trend,
    create_mcp_server,
    haystack_discover_points,
    haystack_get_point_metadata,
    mqtt_get_latest_points,
    mqtt_ingest_message,
    mqtt_publish_message,
    modbus_read_registers,
    modbus_write,
    read_property,
    snmp_device_health_summary,
    snmp_get,
    snmp_walk,
    who_is,
    write_property,
)
from mcp4bas.tools import core
from mcp4bas.tools.core import default_registry


@pytest.fixture(autouse=True)
def fake_bacnet_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeBacnetConnector:
        def who_is(self) -> dict[str, object]:
            return {
                "status": "ok",
                "target_address": "192.168.1.10",
                "count": 1,
                "devices": [{"device_instance": 1001, "source": "192.168.1.10"}],
                "message": "Received 1 I-Am response(s).",
            }

        def read_property(self, object_id: str, property_name: str) -> dict[str, object]:
            return {
                "status": "ok",
                "object_id": object_id,
                "property": property_name,
                "value": 72.0,
                "target_address": "192.168.1.10",
                "message": "Read completed.",
            }

        def write_property(
            self,
            object_id: str,
            property_name: str,
            value: str | float | int,
            priority: int | None = None,
        ) -> dict[str, object]:
            if object_id == "analog-value,deny":
                return {
                    "status": "error",
                    "message": "BACnet write is blocked.",
                    "audit": {"protocol": "bacnet", "allowed": False},
                }
            return {
                "status": "ok",
                "object_id": object_id,
                "property": property_name,
                "value": value,
                "target_address": "192.168.1.10",
                "message": "Write completed.",
            }

        def read_trend(
            self,
            trend_object_id: str,
            limit: int = 100,
            window_minutes: int | None = None,
            source_object_id: str | None = None,
            source_property: str = "present-value",
        ) -> dict[str, object]:
            if trend_object_id == "trend-log,404":
                return {
                    "status": "error",
                    "operation": "read_trend",
                    "trend_object_id": trend_object_id,
                    "target_address": "192.168.1.10",
                    "errors": ["log-buffer: not found"],
                    "message": "Trend retrieval failed.",
                }

            entries = [
                {
                    "index": 0,
                    "timestamp": "2026-03-04T14:00:00+00:00",
                    "value": 72.1,
                    "status": None,
                },
                {
                    "index": 1,
                    "timestamp": "2026-03-04T13:55:00+00:00",
                    "value": 72.0,
                    "status": None,
                },
            ]
            return {
                "status": "ok",
                "operation": "read_trend",
                "trend_object_id": trend_object_id,
                "target_address": "192.168.1.10",
                "window_minutes": window_minutes,
                "limit": limit,
                "count": min(limit, len(entries)),
                "entries": entries[:limit],
                "metadata": {"record-count": 2, "log-interval": 300},
                "fallback_used": source_object_id is not None and source_property == "present-value",
                "fallback_reason": None,
                "errors": [],
                "message": "Trend retrieval completed with 2 entr(ies).",
            }

        def read_schedule(self, schedule_object_id: str) -> dict[str, object]:
            if schedule_object_id == "schedule,404":
                return {
                    "status": "error",
                    "operation": "read_schedule",
                    "schedule_object_id": schedule_object_id,
                    "target_address": "192.168.1.10",
                    "errors": ["weekly-schedule: not found"],
                    "message": "Schedule retrieval failed.",
                }

            return {
                "status": "ok",
                "operation": "read_schedule",
                "schedule_object_id": schedule_object_id,
                "target_address": "192.168.1.10",
                "weekly_schedule": [
                    {
                        "day": "monday",
                        "events": [
                            {"time": "08:00:00", "value": 72.0},
                            {"time": "17:00:00", "value": 68.0},
                        ],
                    }
                ],
                "exception_schedule": [],
                "effective_period": ["2026-01-01", "2026-12-31"],
                "present_value": 72.0,
                "errors": [],
                "message": "Schedule retrieval completed.",
            }

        def get_ip_adapter_mac(
            self,
            ip_address: str | None = None,
            target_address: str | None = None,
            probe: bool = True,
        ) -> dict[str, object]:
            resolved = ip_address or target_address
            if resolved == "10.0.0.250":
                return {
                    "status": "error",
                    "operation": "get_ip_adapter_mac",
                    "ip_address": resolved,
                    "message": "No adapter MAC entry found in neighbor table for the target IP.",
                }

            return {
                "status": "ok",
                "operation": "get_ip_adapter_mac",
                "ip_address": resolved or "192.168.1.10",
                "mac_address": "00:11:22:33:44:55",
                "mac_candidates": ["00:11:22:33:44:55"],
                "duplicate_entries": False,
                "message": "IP adapter MAC resolved from neighbor table.",
            }

    class FakeModbusConnector:
        def read_registers(self, register_type: str, address: int, count: int) -> dict[str, object]:
            return {
                "status": "ok",
                "protocol": "modbus",
                "operation": "read_registers",
                "target": "192.168.1.50:502",
                "register_type": register_type,
                "address": address,
                "count": count,
                "values": [101 + index for index in range(count)],
                "message": "Read completed.",
            }

        def write_register(self, address: int, value: int) -> dict[str, object]:
            if address == 999:
                return {
                    "status": "error",
                    "message": "Modbus writes are blocked.",
                    "audit": {"protocol": "modbus", "allowed": False},
                }
            return {
                "status": "ok",
                "protocol": "modbus",
                "operation": "write_register",
                "target": "192.168.1.50:502",
                "address": address,
                "value": value,
                "message": "Write completed.",
            }

        def write_coil(self, address: int, value: bool) -> dict[str, object]:
            return {
                "status": "ok",
                "protocol": "modbus",
                "operation": "write_coil",
                "target": "192.168.1.50:502",
                "address": address,
                "value": value,
                "message": "Write completed.",
            }

    class FakeHaystackConnector:
        def discover_points(self, limit: int = 100) -> dict[str, object]:
            if limit == 999:
                return {
                    "status": "error",
                    "protocol": "haystack",
                    "operation": "discover_points",
                    "target": "dataset://test",
                    "count": 0,
                    "points": [],
                    "message": "Haystack integration is disabled.",
                }

            points = [
                {
                    "id": "p:good:1",
                    "tags": {"site": "HQ", "equip": "AHU-1", "point": True, "unit": "degF", "kind": "number"},
                    "tag_validation": {"warnings": []},
                    "confidence_score": 100,
                    "caveat": None,
                }
            ]
            return {
                "status": "ok",
                "protocol": "haystack",
                "operation": "discover_points",
                "target": "dataset://test",
                "count": min(limit, len(points)),
                "points": points[:limit],
                "message": "Discovered 1 Haystack point(s).",
            }

        def get_point_metadata(self, point_id: str) -> dict[str, object]:
            if point_id == "missing":
                return {
                    "status": "error",
                    "protocol": "haystack",
                    "operation": "get_point_metadata",
                    "target": "dataset://test",
                    "point_id": point_id,
                    "message": "Point not found: missing",
                }

            return {
                "status": "ok",
                "protocol": "haystack",
                "operation": "get_point_metadata",
                "target": "dataset://test",
                "point_id": point_id,
                "metadata": {
                    "id": point_id,
                    "tag_validation": {
                        "warnings": [
                            {
                                "level": "missing",
                                "tag": "unit",
                                "message": "Required tag 'unit' is missing or blank.",
                            }
                        ],
                        "missing": ["unit"],
                        "weak": [],
                        "inconsistent": ["unit"],
                        "remediation": ["Add required tag 'unit' with a site-standard value."],
                    },
                    "confidence_score": 65,
                    "caveat": "Low-confidence Haystack metadata detected.",
                },
                "message": "Point metadata fetched.",
            }

    class FakeMqttConnector:
        def __init__(self) -> None:
            self._records: list[dict[str, object]] = []

        def ingest_message(self, topic: str, payload: dict[str, object], source: str = "manual") -> dict[str, object]:
            record = {
                "topic": topic,
                "site": "hq-east",
                "equip": "ahu-1",
                "point": topic.split("/")[-1] if "/" in topic else topic,
                "value": payload.get("value"),
                "timestamp": payload.get("timestamp"),
                "quality": payload.get("quality", "good"),
            }
            self._records.append(record)
            return {
                "status": "ok",
                "protocol": "mqtt",
                "operation": "ingest_message",
                "target": "broker.local:1883",
                "record": record,
                "message": "MQTT message ingested.",
            }

        def get_latest_points(
            self,
            site: str | None = None,
            equip: str | None = None,
            limit: int = 100,
        ) -> dict[str, object]:
            records = list(self._records)
            if site:
                records = [record for record in records if record.get("site") == site]
            if equip:
                records = [record for record in records if record.get("equip") == equip]
            return {
                "status": "ok",
                "protocol": "mqtt",
                "operation": "get_latest_points",
                "target": "broker.local:1883",
                "count": min(limit, len(records)),
                "points": records[:limit],
                "message": "Returned MQTT point(s).",
            }

        def publish_message(
            self,
            topic: str,
            payload: dict[str, object],
            source: str = "mcp_tool",
        ) -> dict[str, object]:
            if topic == "hq-east/deny/zone-temp":
                return {
                    "status": "error",
                    "protocol": "mqtt",
                    "operation": "publish_message",
                    "target": "broker.local:1883",
                    "message": "MQTT publish blocked: Topic not present in MQTT_PUBLISH_ALLOWLIST.",
                    "audit": {"protocol": "mqtt", "allowed": False},
                }

            record = {
                "topic": topic,
                "site": "hq-east",
                "equip": "ahu-1",
                "point": topic.split("/")[-1] if "/" in topic else topic,
                "value": payload.get("value"),
                "timestamp": payload.get("timestamp"),
                "quality": payload.get("quality", "good"),
                "source": source,
            }
            return {
                "status": "ok",
                "protocol": "mqtt",
                "operation": "publish_message",
                "target": "broker.local:1883",
                "record": record,
                "audit": {"protocol": "mqtt", "allowed": True},
                "message": "MQTT publish applied to local runtime state.",
            }

    class FakeSnmpConnector:
        def snmp_get(self, oid: str, host: str | None = None) -> dict[str, object]:
            if oid == "1.3.6.1.9.9.9":
                return {
                    "status": "error",
                    "protocol": "snmp",
                    "operation": "snmp_get",
                    "target": f"{host or 'snmp.local'}:161",
                    "oid": oid,
                    "message": f"OID not found: {oid}",
                }
            return {
                "status": "ok",
                "protocol": "snmp",
                "operation": "snmp_get",
                "target": f"{host or 'snmp.local'}:161",
                "oid": oid,
                "value": 123,
                "message": "SNMP GET completed.",
            }

        def snmp_walk(self, oid_prefix: str, host: str | None = None, limit: int = 100) -> dict[str, object]:
            entries = [
                {"oid": f"{oid_prefix}.1", "value": "eth0"},
                {"oid": f"{oid_prefix}.2", "value": "eth1"},
            ]
            sliced = entries[:limit]
            return {
                "status": "ok",
                "protocol": "snmp",
                "operation": "snmp_walk",
                "target": f"{host or 'snmp.local'}:161",
                "oid_prefix": oid_prefix,
                "count": len(sliced),
                "entries": sliced,
                "message": f"SNMP WALK returned {len(sliced)} entr(ies).",
            }

        def snmp_device_health_summary(self, host: str | None = None, interface_limit: int = 20) -> dict[str, object]:
            return {
                "status": "ok",
                "protocol": "snmp",
                "operation": "snmp_device_health_summary",
                "target": f"{host or 'snmp.local'}:161",
                "uptime_ticks": 987654,
                "interfaces": [
                    {
                        "index": 1,
                        "name": "eth0",
                        "oper_status": 1,
                        "in_errors": 0,
                        "out_errors": 0,
                    }
                ][:interface_limit],
                "warnings": [],
                "elapsed_ms": 12.5,
                "message": "SNMP device health summary completed.",
            }

    monkeypatch.setattr(core, "_BACNET_CONNECTOR", FakeBacnetConnector())
    monkeypatch.setattr(core, "_MODBUS_CONNECTOR", FakeModbusConnector())
    monkeypatch.setattr(core, "_HAYSTACK_CONNECTOR", FakeHaystackConnector())
    monkeypatch.setattr(core, "_MQTT_CONNECTOR", FakeMqttConnector())
    monkeypatch.setattr(core, "_SNMP_CONNECTOR", FakeSnmpConnector())


def test_create_server() -> None:
    server = create_mcp_server()
    assert server.name == "mcp4bas"


def test_tools_call_read_property() -> None:
    result = read_property(object_id="analog-value,1", property="present-value")
    assert result["tool"] == "read_property"
    assert result["protocol"] == "bacnet"
    assert result["object_id"] == "analog-value,1"
    assert result["value"] == 72.0


def test_tools_call_who_is() -> None:
    result = who_is()
    assert result["tool"] == "who_is"
    assert result["protocol"] == "bacnet"
    assert result["status"] == "ok"
    assert result["count"] == 1


def test_tools_call_write_property() -> None:
    result = write_property(object_id="analog-value,1", property="present-value", value=72.0)
    assert result["tool"] == "write_property"
    assert result["protocol"] == "bacnet"
    assert result["request"]["value"] == 72.0


def test_tools_call_write_property_blocked() -> None:
    result = write_property(object_id="analog-value,deny", property="present-value", value=72.0)
    assert result["status"] == "error"
    assert result["tool"] == "write_property"
    assert "blocked" in result["message"].lower()
    assert result["audit"]["protocol"] == "bacnet"


def test_tools_call_bacnet_get_trend() -> None:
    result = bacnet_get_trend(
        trend_object_id="trend-log,1",
        limit=1,
        window_minutes=60,
        source_object_id="analog-input,1",
    )
    assert result["tool"] == "bacnet_get_trend"
    assert result["protocol"] == "bacnet"
    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["entries"][0]["value"] == 72.1


def test_tools_call_bacnet_get_trend_error() -> None:
    result = bacnet_get_trend(trend_object_id="trend-log,404")
    assert result["tool"] == "bacnet_get_trend"
    assert result["status"] == "error"
    assert "failed" in result["message"].lower()


def test_tools_call_bacnet_get_schedule() -> None:
    result = bacnet_get_schedule(schedule_object_id="schedule,1")
    assert result["tool"] == "bacnet_get_schedule"
    assert result["protocol"] == "bacnet"
    assert result["status"] == "ok"
    assert result["weekly_schedule"][0]["day"] == "monday"


def test_tools_call_bacnet_get_schedule_error() -> None:
    result = bacnet_get_schedule(schedule_object_id="schedule,404")
    assert result["tool"] == "bacnet_get_schedule"
    assert result["status"] == "error"
    assert "failed" in result["message"].lower()


def test_tools_call_bacnet_get_ip_adapter_mac() -> None:
    result = bacnet_get_ip_adapter_mac(ip_address="192.168.1.10", probe=True)
    assert result["tool"] == "bacnet_get_ip_adapter_mac"
    assert result["protocol"] == "network"
    assert result["status"] == "ok"
    assert result["mac_address"] == "00:11:22:33:44:55"


def test_tools_call_bacnet_get_ip_adapter_mac_error() -> None:
    result = bacnet_get_ip_adapter_mac(ip_address="10.0.0.250", probe=False)
    assert result["tool"] == "bacnet_get_ip_adapter_mac"
    assert result["status"] == "error"
    assert "no adapter mac" in result["message"].lower()


def test_registry_unknown_tool_has_consistent_error() -> None:
    registry = default_registry()
    result = registry.call(name="not_a_tool", arguments={})
    assert result["status"] == "error"
    assert result["error"]["code"] == "unknown_tool"


def test_registry_validation_error_has_consistent_error() -> None:
    registry = default_registry()
    result = registry.call(name="read_property", arguments={})
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"
    assert "validation_errors" in result["error"]["details"]


def test_registry_validation_error_for_write_priority_bounds() -> None:
    registry = default_registry()
    result = registry.call(
        name="write_property",
        arguments={
            "object_id": "analog-value,1",
            "property": "present-value",
            "value": 75,
            "priority": 17,
        },
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"


def test_registry_validation_error_for_bacnet_get_trend_limit() -> None:
    registry = default_registry()
    result = registry.call(
        name="bacnet_get_trend",
        arguments={"trend_object_id": "trend-log,1", "limit": 0},
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"


def test_registry_validation_error_for_bacnet_get_schedule_object_id() -> None:
    registry = default_registry()
    result = registry.call(
        name="bacnet_get_schedule",
        arguments={"schedule_object_id": "bad-id"},
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"


def test_registry_validation_error_for_bacnet_get_ip_adapter_mac_source() -> None:
    registry = default_registry()
    result = registry.call(
        name="bacnet_get_ip_adapter_mac",
        arguments={"probe": True},
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"


def test_tools_call_modbus_read_registers() -> None:
    result = modbus_read_registers(register_type="holding", address=10, count=2)
    assert result["tool"] == "modbus_read_registers"
    assert result["protocol"] == "modbus"
    assert result["values"] == [101, 102]


def test_tools_call_modbus_write_register() -> None:
    result = modbus_write(write_type="register", address=20, value=12)
    assert result["tool"] == "modbus_write"
    assert result["operation"] == "write_register"
    assert result["request"]["value"] == 12


def test_tools_call_modbus_write_error() -> None:
    result = modbus_write(write_type="register", address=999, value=1)
    assert result["status"] == "error"
    assert result["tool"] == "modbus_write"
    assert "blocked" in result["message"].lower()


def test_registry_validation_error_for_modbus_read_count() -> None:
    registry = default_registry()
    result = registry.call(
        name="modbus_read_registers",
        arguments={"register_type": "holding", "address": 10, "count": 0},
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"


def test_tools_call_haystack_discover_points() -> None:
    result = haystack_discover_points(limit=10)
    assert result["tool"] == "haystack_discover_points"
    assert result["protocol"] == "haystack"
    assert result["status"] == "ok"
    assert result["count"] == 1
    assert "tag_validation" in result["points"][0]


def test_tools_call_haystack_get_point_metadata() -> None:
    result = haystack_get_point_metadata(point_id="p:weak:1")
    assert result["tool"] == "haystack_get_point_metadata"
    assert result["protocol"] == "haystack"
    assert result["status"] == "ok"
    assert result["metadata"]["confidence_score"] == 65
    assert result["metadata"]["tag_validation"]["missing"] == ["unit"]


def test_tools_call_haystack_get_point_metadata_not_found() -> None:
    result = haystack_get_point_metadata(point_id="missing")
    assert result["status"] == "error"
    assert result["tool"] == "haystack_get_point_metadata"
    assert "not found" in result["message"].lower()


def test_registry_validation_error_for_haystack_limit() -> None:
    registry = default_registry()
    result = registry.call(
        name="haystack_discover_points",
        arguments={"limit": 0},
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"


def test_tools_call_mqtt_ingest_message() -> None:
    result = mqtt_ingest_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 72.1, "timestamp": "2026-03-03T09:02:00Z", "quality": "good"},
    )
    assert result["tool"] == "mqtt_ingest_message"
    assert result["protocol"] == "mqtt"
    assert result["status"] == "ok"
    assert result["record"]["point"] == "zone-temp"


def test_tools_call_mqtt_get_latest_points() -> None:
    mqtt_ingest_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 72.1, "timestamp": "2026-03-03T09:02:00Z", "quality": "good"},
    )
    result = mqtt_get_latest_points(site="hq-east", equip="ahu-1", limit=10)
    assert result["tool"] == "mqtt_get_latest_points"
    assert result["protocol"] == "mqtt"
    assert result["status"] == "ok"
    assert result["count"] >= 1


def test_tools_call_mqtt_publish_message() -> None:
    result = mqtt_publish_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 73.1, "timestamp": "2026-03-03T09:05:00Z", "quality": "good"},
    )
    assert result["tool"] == "mqtt_publish_message"
    assert result["protocol"] == "mqtt"
    assert result["status"] == "ok"
    assert result["audit"]["allowed"] is True


def test_tools_call_mqtt_publish_message_blocked() -> None:
    result = mqtt_publish_message(
        topic="hq-east/deny/zone-temp",
        payload={"value": 73.1, "timestamp": "2026-03-03T09:05:00Z", "quality": "good"},
    )
    assert result["tool"] == "mqtt_publish_message"
    assert result["status"] == "error"
    assert "blocked" in result["message"].lower()
    assert result["audit"]["protocol"] == "mqtt"


def test_registry_validation_error_for_mqtt_publish_topic() -> None:
    registry = default_registry()
    result = registry.call(
        name="mqtt_publish_message",
        arguments={"topic": "", "payload": {"value": 1, "timestamp": "2026-03-03T09:05:00Z"}},
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"


def test_tools_call_snmp_get() -> None:
    result = snmp_get(oid="1.3.6.1.2.1.1.3.0", host="192.168.0.147")
    assert result["tool"] == "snmp_get"
    assert result["protocol"] == "snmp"
    assert result["status"] == "ok"
    assert result["value"] == 123


def test_tools_call_snmp_get_error() -> None:
    result = snmp_get(oid="1.3.6.1.9.9.9")
    assert result["tool"] == "snmp_get"
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


def test_tools_call_snmp_walk() -> None:
    result = snmp_walk(oid_prefix="1.3.6.1.2.1.2.2.1.2", limit=1)
    assert result["tool"] == "snmp_walk"
    assert result["status"] == "ok"
    assert result["count"] == 1


def test_tools_call_snmp_device_health_summary() -> None:
    result = snmp_device_health_summary(host="192.168.0.147", interface_limit=5)
    assert result["tool"] == "snmp_device_health_summary"
    assert result["status"] == "ok"
    assert result["uptime_ticks"] == 987654


def test_registry_validation_error_for_snmp_walk_limit() -> None:
    registry = default_registry()
    result = registry.call(
        name="snmp_walk",
        arguments={"oid_prefix": "1.3.6", "limit": 0},
    )
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_arguments"
