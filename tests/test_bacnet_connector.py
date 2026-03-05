from __future__ import annotations

from bacpypes3.primitivedata import Null

import mcp4bas.bacnet.connector as bacnet_connector_module
from mcp4bas.bacnet.connector import (
    BacnetConfig,
    BacnetConnector,
    _coerce_bacnet_write_value,
    _extract_mac_candidates_from_neighbors,
    _normalize_mac_address,
    _normalize_exception_schedule,
    _normalize_trend_entry,
    _normalize_weekly_schedule,
)


def test_bacnet_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BACNET_ENABLED", "true")
    monkeypatch.setenv("BACNET_LOCAL_ADDRESS", "192.168.1.20/24")
    monkeypatch.setenv("BACNET_TARGET_ADDRESS", "192.168.1.30")
    monkeypatch.setenv("BACNET_NETWORK", "100")
    monkeypatch.setenv("BACNET_DEVICE_INSTANCE", "200001")
    monkeypatch.setenv("BACNET_DEVICE_NAME", "MCP4BAS-Test")
    monkeypatch.setenv("BACNET_VENDOR_IDENTIFIER", "15")
    monkeypatch.setenv("BACNET_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("BACNET_RETRIES", "2")
    monkeypatch.setenv("BACNET_WRITE_ENABLED", "true")

    config = BacnetConfig.from_env()

    assert config.enabled is True
    assert config.local_address == "192.168.1.20/24"
    assert config.target_address == "192.168.1.30"
    assert config.network == 100
    assert config.device_instance == 200001
    assert config.device_name == "MCP4BAS-Test"
    assert config.vendor_identifier == 15
    assert config.timeout_seconds == 1.5
    assert config.retries == 2
    assert config.write_enabled is True


def test_connector_retry_then_success() -> None:
    class RetryConnector(BacnetConnector):
        def __init__(self) -> None:
            super().__init__(
                config=BacnetConfig(
                    enabled=True,
                    retries=2,
                    timeout_seconds=0.1,
                )
            )
            self.calls = 0

        async def _who_is_async(self):
            self.calls += 1
            if self.calls < 3:
                raise TimeoutError("simulated timeout")
            return {
                "status": "ok",
                "operation": "who_is",
                "count": 1,
                "devices": [{"device_instance": 1001}],
                "message": "Received 1 I-Am response(s).",
            }

    connector = RetryConnector()
    result = connector.who_is()

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert connector.calls == 3


def test_connector_disabled_short_circuit() -> None:
    connector = BacnetConnector(config=BacnetConfig(enabled=False))
    result = connector.read_property("analog-value,1", "present-value")

    assert result["status"] == "error"
    assert "BACNET_ENABLED=true" in result["message"]


def test_bacnet_write_blocked_by_mode_and_allowlist() -> None:
    connector = BacnetConnector(
        config=BacnetConfig(
            enabled=True,
            operation_mode="read-only",
            write_enabled=True,
            write_allowlist={("analog-value,1", "present-value")},
            target_address="192.168.1.30",
        )
    )

    result = connector.write_property("analog-value,2", "present-value", 70.0)

    assert result["status"] == "error"
    assert "blocked" in result["message"].lower()
    assert result["audit"]["protocol"] == "bacnet"


def test_bacnet_write_dry_run() -> None:
    connector = BacnetConnector(
        config=BacnetConfig(
            enabled=True,
            operation_mode="write-enabled",
            write_enabled=True,
            dry_run=True,
            write_allowlist={("analog-value,1", "present-value")},
            target_address="192.168.1.30",
        )
    )

    result = connector.write_property("analog-value,1", "present-value", 70.0)

    assert result["status"] == "ok"
    assert "dry-run" in result["message"].lower()
    assert result["audit"]["allowed"] is True


def test_coerce_bacnet_write_value_null_tokens() -> None:
    value_null = _coerce_bacnet_write_value("null")
    value_relinquish = _coerce_bacnet_write_value("relinquish")
    value_numeric = _coerce_bacnet_write_value(72.5)

    assert isinstance(value_null, Null)
    assert isinstance(value_relinquish, Null)
    assert value_numeric == 72.5


def test_normalize_trend_entry_extracts_common_fields() -> None:
    entry = {
        "timestamp": "2026-03-04T14:15:00Z",
        "value": 72.5,
        "statusFlags": {"inAlarm": False},
    }

    normalized = _normalize_trend_entry(entry, index=0)

    assert normalized["index"] == 0
    assert normalized["timestamp"] == "2026-03-04T14:15:00+00:00"
    assert normalized["value"] == 72.5


def test_normalize_weekly_schedule_maps_days_and_events() -> None:
    weekly_raw = [
        [{"time": "08:00:00", "value": 72.0}, {"time": "17:00:00", "value": 68.0}],
        [],
        [],
        [],
        [],
        [],
        [],
    ]

    weekly = _normalize_weekly_schedule(weekly_raw)

    assert len(weekly) == 7
    assert weekly[0]["day"] == "monday"
    assert weekly[0]["events"][0]["time"] == "08:00:00"
    assert weekly[0]["events"][0]["value"] == 72.0


def test_normalize_exception_schedule_maps_blocks() -> None:
    exception_raw = [
        {
            "name": "Holiday",
            "period": ["2026-12-25", "2026-12-25"],
            "events": [{"time": "00:00:00", "value": 65.0}],
        }
    ]

    exceptions = _normalize_exception_schedule(exception_raw)

    assert len(exceptions) == 1
    assert exceptions[0]["name"] == "Holiday"
    assert exceptions[0]["events"][0]["value"] == 65.0


def test_bacnet_trend_and_schedule_disabled_short_circuit() -> None:
    connector = BacnetConnector(config=BacnetConfig(enabled=False))

    trend_result = connector.read_trend(trend_object_id="trend-log,1")
    schedule_result = connector.read_schedule(schedule_object_id="schedule,1")

    assert trend_result["status"] == "error"
    assert schedule_result["status"] == "error"
    assert trend_result["operation"] == "read_trend"
    assert schedule_result["operation"] == "read_schedule"


def test_normalize_mac_address_variants() -> None:
    assert _normalize_mac_address("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert _normalize_mac_address("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
    assert _normalize_mac_address("aabb.ccdd.eeff") == "AA:BB:CC:DD:EE:FF"
    assert _normalize_mac_address("invalid") is None


def test_extract_mac_candidates_dedupes_neighbors() -> None:
    table = """
Interface: 192.168.0.97 --- 0x9
  Internet Address      Physical Address      Type
  192.168.0.147         00-11-22-33-44-55     dynamic
192.168.0.147 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE
192.168.0.147 dev eth1 lladdr 66:77:88:99:AA:BB STALE
"""
    candidates = _extract_mac_candidates_from_neighbors(table, "192.168.0.147")
    assert candidates == ["00:11:22:33:44:55", "66:77:88:99:AA:BB"]


def test_get_ip_adapter_mac_success_after_probe(monkeypatch) -> None:
    table_reads = iter(
        [
            "",
            "192.168.0.147 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE",
        ]
    )

    def fake_read_neighbor_table() -> str:
        return next(table_reads)

    probe_calls: list[str] = []

    def fake_probe(ip_address: str) -> None:
        probe_calls.append(ip_address)

    monkeypatch.setattr(bacnet_connector_module, "_read_neighbor_table", fake_read_neighbor_table)
    monkeypatch.setattr(bacnet_connector_module, "_probe_ip_address", fake_probe)

    connector = BacnetConnector(config=BacnetConfig(enabled=True, target_address="192.168.0.147:47808"))
    result = connector.get_ip_adapter_mac(probe=True)

    assert result["status"] == "ok"
    assert result["ip_address"] == "192.168.0.147"
    assert result["mac_address"] == "00:11:22:33:44:55"
    assert probe_calls == ["192.168.0.147"]


def test_get_ip_adapter_mac_not_found(monkeypatch) -> None:
    monkeypatch.setattr(bacnet_connector_module, "_read_neighbor_table", lambda: "")
    monkeypatch.setattr(bacnet_connector_module, "_probe_ip_address", lambda _ip: None)

    connector = BacnetConnector(config=BacnetConfig(enabled=True, target_address="192.168.0.147:47808"))
    result = connector.get_ip_adapter_mac(ip_address="192.168.0.147", probe=False)

    assert result["status"] == "error"
    assert "No adapter MAC entry found" in result["message"]
