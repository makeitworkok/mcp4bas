from __future__ import annotations

from mcp4bas.snmp.connector import SnmpConfig, SnmpConnector


def test_snmp_disabled_message() -> None:
    connector = SnmpConnector(config=SnmpConfig(enabled=False))
    result = connector.snmp_get(oid="1.3.6.1.2.1.1.3.0")

    assert result["status"] == "error"
    assert "disabled" in result["message"].lower()


def test_snmp_simulated_get_and_walk() -> None:
    connector = SnmpConnector(
        config=SnmpConfig(
            enabled=True,
            runtime="simulated",
            host="192.168.0.147",
        )
    )

    get_result = connector.snmp_get(oid="1.3.6.1.2.1.1.3.0")
    walk_result = connector.snmp_walk(oid_prefix="1.3.6.1.2.1.2.2.1.2", limit=10)

    assert get_result["status"] == "ok"
    assert get_result["value"] == 987654
    assert walk_result["status"] == "ok"
    assert walk_result["count"] == 2


def test_snmp_simulated_get_unknown_oid() -> None:
    connector = SnmpConnector(
        config=SnmpConfig(
            enabled=True,
            runtime="simulated",
            host="192.168.0.147",
        )
    )

    result = connector.snmp_get(oid="1.3.6.1.9.9.9")

    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


def test_snmp_device_health_summary() -> None:
    connector = SnmpConnector(
        config=SnmpConfig(
            enabled=True,
            runtime="simulated",
            host="192.168.0.147",
        )
    )

    result = connector.snmp_device_health_summary(interface_limit=5)

    assert result["status"] == "ok"
    assert result["uptime_ticks"] == 987654
    assert len(result["interfaces"]) == 2
    assert isinstance(result["warnings"], list)
