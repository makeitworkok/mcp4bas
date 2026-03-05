from __future__ import annotations

from mcp4bas.mqtt import MqttConfig, MqttConnector, validate_mqtt_message


def test_mqtt_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("MQTT_BROKER", "broker.local")
    monkeypatch.setenv("MQTT_PORT", "1884")
    monkeypatch.setenv("MQTT_TLS_ENABLED", "true")
    monkeypatch.setenv("MQTT_CLIENT_ID", "mcp4bas-test")
    monkeypatch.setenv("MQTT_TOPIC_PREFIX", "site-a")

    config = MqttConfig.from_env()

    assert config.enabled is True
    assert config.broker == "broker.local"
    assert config.port == 1884
    assert config.tls_enabled is True
    assert config.client_id == "mcp4bas-test"
    assert config.topic_prefix == "site-a"


def test_validate_mqtt_message_scores_weak_payload() -> None:
    result = validate_mqtt_message(
        topic="site-a/ahu-1/zone-temp",
        payload={"value": 72.0, "timestamp": ""},
        topic_prefix="site-a",
    )

    assert result["confidence_score"] < 100
    assert "timestamp" in result["missing"]
    assert result["caveat"] is not None


def test_mqtt_connector_ingest_and_query(monkeypatch) -> None:
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("MQTT_DATASET_PATH", "resources/mqtt_messages.json")

    connector = MqttConnector.from_env()

    ingest = connector.ingest_message(
        topic="hq-east/ahu-2/discharge-temp",
        payload={
            "value": 55.1,
            "unit": "degF",
            "timestamp": "2026-03-03T09:02:00Z",
            "quality": "good",
        },
    )
    assert ingest["status"] == "ok"
    assert ingest["record"]["point"] == "discharge-temp"

    latest = connector.get_latest_points(site="hq-east", equip="ahu-2", limit=10)
    assert latest["status"] == "ok"
    assert latest["count"] >= 1
    assert any(item["point"] == "discharge-temp" for item in latest["points"])


def test_mqtt_publish_blocked_by_mode(monkeypatch) -> None:
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("BAS_OPERATION_MODE", "read-only")
    monkeypatch.setenv("MQTT_WRITE_ENABLED", "true")

    connector = MqttConnector.from_env()
    result = connector.publish_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 72.0, "timestamp": "2026-03-03T09:10:00Z", "quality": "good"},
    )

    assert result["status"] == "error"
    assert "blocked" in result["message"].lower()
    assert result["audit"]["allowed"] is False


def test_mqtt_publish_dry_run(monkeypatch) -> None:
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("BAS_OPERATION_MODE", "write-enabled")
    monkeypatch.setenv("BAS_DRY_RUN", "true")
    monkeypatch.setenv("MQTT_WRITE_ENABLED", "true")
    monkeypatch.setenv("MQTT_PUBLISH_ALLOWLIST", "hq-east/ahu-1/zone-temp")

    connector = MqttConnector.from_env()
    result = connector.publish_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 72.0, "timestamp": "2026-03-03T09:10:00Z", "quality": "good"},
    )

    assert result["status"] == "ok"
    assert "dry-run" in result["message"].lower()
    assert result["audit"]["allowed"] is True


def test_mqtt_publish_allowlist_enforced(monkeypatch) -> None:
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("BAS_OPERATION_MODE", "write-enabled")
    monkeypatch.setenv("BAS_DRY_RUN", "false")
    monkeypatch.setenv("MQTT_WRITE_ENABLED", "true")
    monkeypatch.setenv("MQTT_PUBLISH_ALLOWLIST", "hq-east/ahu-1/supply-temp")

    connector = MqttConnector.from_env()
    result = connector.publish_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 72.0, "timestamp": "2026-03-03T09:10:00Z", "quality": "good"},
    )

    assert result["status"] == "error"
    assert "allowlist" in result["message"].lower()


def test_mqtt_publish_updates_latest_points(monkeypatch) -> None:
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("BAS_OPERATION_MODE", "write-enabled")
    monkeypatch.setenv("BAS_DRY_RUN", "false")
    monkeypatch.setenv("MQTT_WRITE_ENABLED", "true")
    monkeypatch.setenv("MQTT_PUBLISH_ALLOWLIST", "hq-east/ahu-1/zone-temp")

    connector = MqttConnector.from_env()
    publish = connector.publish_message(
        topic="hq-east/ahu-1/zone-temp",
        payload={"value": 73.3, "timestamp": "2026-03-03T09:11:00Z", "quality": "good"},
    )

    latest = connector.get_latest_points(site="hq-east", equip="ahu-1", limit=10)

    assert publish["status"] == "ok"
    assert publish["audit"]["allowed"] is True
    assert any(item.get("value") == 73.3 for item in latest["points"])
