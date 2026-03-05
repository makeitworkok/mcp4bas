from __future__ import annotations

import json
from pathlib import Path

from mcp4bas.mqtt import MqttConnector


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mqtt_good_bad_payloads.json"


def _load() -> dict[str, list[dict[str, object]]]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def test_mqtt_fixture_good_vs_bad_confidence(monkeypatch) -> None:
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("MQTT_TOPIC_PREFIX", "hq-east")

    connector = MqttConnector.from_env()
    fixtures = _load()

    good_scores: list[int] = []
    bad_scores: list[int] = []

    for item in fixtures["good"]:
        result = connector.ingest_message(
            topic=str(item["topic"]),
            payload=dict(item["payload"]),
            source="fixture",
        )
        good_scores.append(int(result["record"]["confidence_score"]))

    for item in fixtures["bad"]:
        result = connector.ingest_message(
            topic=str(item["topic"]),
            payload=dict(item["payload"]),
            source="fixture",
        )
        bad_scores.append(int(result["record"]["confidence_score"]))

    assert min(good_scores) > max(bad_scores)


def test_mqtt_fixture_publish_safety(monkeypatch) -> None:
    monkeypatch.setenv("MQTT_ENABLED", "true")
    monkeypatch.setenv("BAS_OPERATION_MODE", "write-enabled")
    monkeypatch.setenv("BAS_DRY_RUN", "false")
    monkeypatch.setenv("MQTT_WRITE_ENABLED", "true")
    monkeypatch.setenv("MQTT_PUBLISH_ALLOWLIST", "hq-east/ahu-1/zone-temp")

    connector = MqttConnector.from_env()
    fixtures = _load()

    allowed = connector.publish_message(
        topic=str(fixtures["good"][0]["topic"]),
        payload=dict(fixtures["good"][0]["payload"]),
        source="fixture-publish",
    )
    blocked = connector.publish_message(
        topic=str(fixtures["bad"][0]["topic"]),
        payload=dict(fixtures["bad"][0]["payload"]),
        source="fixture-publish",
    )

    assert allowed["status"] == "ok"
    assert allowed["audit"]["allowed"] is True
    assert blocked["status"] == "error"
    assert blocked["audit"]["allowed"] is False
