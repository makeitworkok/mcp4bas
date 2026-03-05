from __future__ import annotations

from mcp4bas import server
from mcp4bas.tools import core


class _IntegrationBacnetConnector:
    def who_is(self) -> dict[str, object]:
        return {
            "status": "ok",
            "target_address": "192.168.0.147:47808",
            "count": 1,
            "devices": [{"device_instance": 50, "source": "192.168.0.147"}],
            "message": "Received 1 I-Am response(s).",
        }

    def read_property(self, object_id: str, property_name: str) -> dict[str, object]:
        return {
            "status": "ok",
            "object_id": object_id,
            "property": property_name,
            "target_address": "192.168.0.147:47808",
            "value": 70.0,
            "message": "Read completed.",
        }

    def write_property(
        self,
        object_id: str,
        property_name: str,
        value: str | float | int,
        priority: int | None = None,
    ) -> dict[str, object]:
        return {
            "status": "ok",
            "object_id": object_id,
            "property": property_name,
            "target_address": "192.168.0.147:47808",
            "value": value,
            "priority": priority,
            "audit": {"protocol": "bacnet", "allowed": True},
            "message": "Write completed.",
        }


class _IntegrationModbusConnector:
    def read_registers(self, register_type: str, address: int, count: int) -> dict[str, object]:
        return {
            "status": "ok",
            "protocol": "modbus",
            "operation": "read_registers",
            "target": "192.168.0.60:502",
            "register_type": register_type,
            "address": address,
            "count": count,
            "values": [address + offset for offset in range(count)],
            "message": "Read completed.",
        }

    def write_register(self, address: int, value: int) -> dict[str, object]:
        return {
            "status": "ok",
            "protocol": "modbus",
            "operation": "write_register",
            "target": "192.168.0.60:502",
            "address": address,
            "value": value,
            "audit": {"protocol": "modbus", "allowed": True},
            "message": "Write completed.",
        }

    def write_coil(self, address: int, value: bool) -> dict[str, object]:
        return {
            "status": "ok",
            "protocol": "modbus",
            "operation": "write_coil",
            "target": "192.168.0.60:502",
            "address": address,
            "value": value,
            "audit": {"protocol": "modbus", "allowed": True},
            "message": "Write completed.",
        }


class _IntegrationHaystackConnector:
    def discover_points(self, limit: int = 100) -> dict[str, object]:
        points = [
            {
                "id": "point-1",
                "tag_validation": {"warnings": []},
                "confidence_score": 100,
                "caveat": None,
            }
        ]
        return {
            "status": "ok",
            "protocol": "haystack",
            "operation": "discover_points",
            "target": "dataset://integration",
            "count": min(limit, len(points)),
            "points": points[:limit],
            "message": "Discovered 1 Haystack point(s).",
        }

    def get_point_metadata(self, point_id: str) -> dict[str, object]:
        return {
            "status": "ok",
            "protocol": "haystack",
            "operation": "get_point_metadata",
            "target": "dataset://integration",
            "point_id": point_id,
            "metadata": {
                "id": point_id,
                "tag_validation": {"warnings": []},
                "confidence_score": 100,
                "caveat": None,
            },
            "message": "Point metadata fetched.",
        }


class _IntegrationMqttConnector:
    def __init__(self) -> None:
        self._records: list[dict[str, object]] = []

    def ingest_message(self, topic: str, payload: dict[str, object], source: str = "manual") -> dict[str, object]:
        record = {
            "topic": topic,
            "site": "hq-east",
            "equip": "ahu-1",
            "point": topic.split("/")[-1],
            "value": payload.get("value"),
            "timestamp": payload.get("timestamp"),
            "source": source,
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
        records = list(self._records)[:limit]
        return {
            "status": "ok",
            "protocol": "mqtt",
            "operation": "get_latest_points",
            "target": "broker.local:1883",
            "count": len(records),
            "points": records,
            "message": "Returned MQTT point(s).",
        }

    def publish_message(
        self,
        topic: str,
        payload: dict[str, object],
        source: str = "mcp_tool",
    ) -> dict[str, object]:
        record = {
            "topic": topic,
            "site": "hq-east",
            "equip": "ahu-1",
            "point": topic.split("/")[-1],
            "value": payload.get("value"),
            "timestamp": payload.get("timestamp"),
            "source": source,
        }
        self._records.append(record)
        return {
            "status": "ok",
            "protocol": "mqtt",
            "operation": "publish_message",
            "target": "broker.local:1883",
            "record": record,
            "audit": {"protocol": "mqtt", "allowed": True},
            "message": "MQTT publish applied to local runtime state.",
        }


class _IntegrationSnmpConnector:
    def snmp_get(self, oid: str, host: str | None = None) -> dict[str, object]:
        return {
            "status": "ok",
            "protocol": "snmp",
            "operation": "snmp_get",
            "target": f"{host or 'snmp.local'}:161",
            "oid": oid,
            "value": 100,
            "message": "SNMP GET completed.",
        }

    def snmp_walk(self, oid_prefix: str, host: str | None = None, limit: int = 100) -> dict[str, object]:
        entries = [{"oid": f"{oid_prefix}.1", "value": "eth0"}]
        return {
            "status": "ok",
            "protocol": "snmp",
            "operation": "snmp_walk",
            "target": f"{host or 'snmp.local'}:161",
            "oid_prefix": oid_prefix,
            "count": min(limit, len(entries)),
            "entries": entries[:limit],
            "message": "SNMP WALK returned 1 entr(ies).",
        }

    def snmp_device_health_summary(self, host: str | None = None, interface_limit: int = 20) -> dict[str, object]:
        return {
            "status": "ok",
            "protocol": "snmp",
            "operation": "snmp_device_health_summary",
            "target": f"{host or 'snmp.local'}:161",
            "uptime_ticks": 1000,
            "interfaces": [{"index": 1, "name": "eth0", "oper_status": 1, "in_errors": 0, "out_errors": 0}],
            "warnings": [],
            "elapsed_ms": 5.0,
            "message": "SNMP device health summary completed.",
        }


def test_integration_server_uses_lazy_adapter_resolution(monkeypatch) -> None:
    core._BACNET_CONNECTOR = None
    core._MODBUS_CONNECTOR = None
    core._HAYSTACK_CONNECTOR = None
    core._MQTT_CONNECTOR = None
    core._SNMP_CONNECTOR = None

    monkeypatch.setattr(core.BacnetConnector, "from_env", lambda: _IntegrationBacnetConnector())
    monkeypatch.setattr(core.ModbusConnector, "from_env", lambda: _IntegrationModbusConnector())
    monkeypatch.setattr(core.HaystackConnector, "from_env", lambda: _IntegrationHaystackConnector())
    monkeypatch.setattr(core.MqttConnector, "from_env", lambda: _IntegrationMqttConnector())
    monkeypatch.setattr(core.SnmpConnector, "from_env", lambda: _IntegrationSnmpConnector())

    who = server.who_is()
    read = server.read_property(object_id="analog-value,1", property="present-value")
    write = server.write_property(
        object_id="analog-value,1",
        property="present-value",
        value=75,
        priority=8,
    )
    modbus_read = server.modbus_read_registers(register_type="holding", address=10, count=2)
    modbus_write = server.modbus_write(write_type="coil", address=7, value=True)
    haystack_discover = server.haystack_discover_points(limit=10)
    haystack_metadata = server.haystack_get_point_metadata(point_id="point-1")
    mqtt_ingest = server.mqtt_ingest_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 71.5, "timestamp": "2026-03-03T09:00:00Z", "quality": "good"},
    )
    mqtt_latest = server.mqtt_get_latest_points(site="hq-east", equip="ahu-1", limit=10)
    mqtt_publish = server.mqtt_publish_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 72.0, "timestamp": "2026-03-03T09:01:00Z", "quality": "good"},
    )
    snmp_get_result = server.snmp_get(oid="1.3.6.1.2.1.1.3.0", host="192.168.0.147")
    snmp_walk_result = server.snmp_walk(oid_prefix="1.3.6.1.2.1.2.2.1.2", host="192.168.0.147", limit=5)
    snmp_health = server.snmp_device_health_summary(host="192.168.0.147", interface_limit=5)

    assert who["status"] == "ok"
    assert read["value"] == 70.0
    assert write["request"]["priority"] == 8
    assert modbus_read["values"] == [10, 11]
    assert modbus_write["operation"] == "write_coil"
    assert haystack_discover["count"] == 1
    assert haystack_metadata["metadata"]["id"] == "point-1"
    assert mqtt_ingest["record"]["point"] == "zone-temp"
    assert mqtt_latest["count"] == 1
    assert mqtt_publish["audit"]["allowed"] is True
    assert snmp_get_result["value"] == 100
    assert snmp_walk_result["count"] == 1
    assert snmp_health["uptime_ticks"] == 1000
