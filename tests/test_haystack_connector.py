from __future__ import annotations

from mcp4bas.haystack import HaystackConfig, HaystackConnector, validate_haystack_tags


def test_haystack_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("HAYSTACK_ENABLED", "true")
    monkeypatch.setenv("HAYSTACK_MODE", "api")
    monkeypatch.setenv("HAYSTACK_ENDPOINT", "https://haystack.local/api/points")
    monkeypatch.setenv("HAYSTACK_AUTH_TOKEN", "token-abc")
    monkeypatch.setenv("HAYSTACK_TIMEOUT_SECONDS", "6.5")
    monkeypatch.setenv("HAYSTACK_PROJECT_FILTERS", "HQ-Retrofit,Legacy-Wing")
    monkeypatch.setenv("HAYSTACK_SITE_FILTERS", "HQ-East,HQ-West")

    config = HaystackConfig.from_env()

    assert config.enabled is True
    assert config.mode == "api"
    assert config.endpoint == "https://haystack.local/api/points"
    assert config.auth_token == "token-abc"
    assert config.timeout_seconds == 6.5
    assert config.project_filters == {"HQ-Retrofit", "Legacy-Wing"}
    assert config.site_filters == {"HQ-East", "HQ-West"}


def test_haystack_discover_points_from_local_dataset(monkeypatch) -> None:
    monkeypatch.setenv("HAYSTACK_ENABLED", "true")
    monkeypatch.setenv("HAYSTACK_MODE", "dataset")
    monkeypatch.setenv("HAYSTACK_DATASET_PATH", "resources/haystack_points.json")

    connector = HaystackConnector.from_env()
    result = connector.discover_points(limit=10)

    assert result["status"] == "ok"
    assert result["protocol"] == "haystack"
    assert result["count"] == 4
    assert len(result["points"]) == 4


def test_haystack_get_point_metadata_not_found(monkeypatch) -> None:
    monkeypatch.setenv("HAYSTACK_ENABLED", "true")
    monkeypatch.setenv("HAYSTACK_MODE", "dataset")
    monkeypatch.setenv("HAYSTACK_DATASET_PATH", "resources/haystack_points.json")

    connector = HaystackConnector.from_env()
    result = connector.get_point_metadata("point:does-not-exist")

    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


def test_tag_validation_quality_difference_strong_vs_weak() -> None:
    strong_tags = {
        "site": "HQ-East",
        "equip": "AHU-1",
        "point": True,
        "unit": "degF",
        "kind": "number",
        "zone": True,
        "temp": True,
    }
    weak_tags = {
        "site": "",
        "equip": "",
        "point": True,
        "kind": "number",
        "unit": "unknown",
    }

    strong = validate_haystack_tags(strong_tags)
    weak = validate_haystack_tags(weak_tags)

    assert strong["confidence_score"] > weak["confidence_score"]
    assert strong["caveat"] is None
    assert weak["caveat"] is not None
    assert weak["remediation"]
