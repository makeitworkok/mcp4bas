from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_operation_mode(raw: str | None) -> Literal["read-only", "write-enabled"]:
    value = (raw or "read-only").strip().lower()
    if value == "write-enabled":
        return "write-enabled"
    return "read-only"


def _parse_allowlist(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {item.strip() for item in raw.split(";") if item.strip()}


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _split_topic(topic: str) -> tuple[str | None, str | None, str | None, list[str]]:
    parts = [segment for segment in topic.split("/") if segment]
    if len(parts) < 3:
        return None, None, None, parts
    return parts[-3], parts[-2], parts[-1], parts


def validate_mqtt_message(
    topic: str,
    payload: dict[str, Any],
    *,
    topic_prefix: str | None = None,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    missing: list[str] = []
    weak: list[str] = []
    inconsistent: list[str] = []
    remediation: list[str] = []

    site, equip, point, parts = _split_topic(topic)
    if len(parts) < 3:
        missing.append("topic_segments")
        warnings.append(
            {
                "level": "missing",
                "field": "topic",
                "message": "Topic must include at least site/equip/point segments.",
            }
        )
        remediation.append("Adopt topic format like '<site>/<equip>/<point>'.")

    prefix = (topic_prefix or "").strip("/")
    if prefix and not topic.startswith(prefix + "/") and topic != prefix:
        weak.append("topic_prefix")
        warnings.append(
            {
                "level": "weak",
                "field": "topic_prefix",
                "message": f"Topic does not match configured prefix '{prefix}'.",
            }
        )
        remediation.append("Align publisher topics with configured MQTT_TOPIC_PREFIX.")

    required_fields = ("value", "timestamp")
    for field_name in required_fields:
        if field_name not in payload or _is_blank(payload.get(field_name)):
            missing.append(field_name)
            warnings.append(
                {
                    "level": "missing",
                    "field": field_name,
                    "message": f"Required payload field '{field_name}' is missing or blank.",
                }
            )
            remediation.append(f"Include payload field '{field_name}' in MQTT message body.")

    quality_value = payload.get("quality")
    if isinstance(quality_value, str) and quality_value.strip().lower() in {"bad", "fault", "invalid"}:
        inconsistent.append("quality")
        warnings.append(
            {
                "level": "inconsistent",
                "field": "quality",
                "message": "Payload quality indicates bad/fault state.",
            }
        )
        remediation.append("Investigate data source quality before relying on this point.")

    score = 100
    score -= 20 * len(missing)
    score -= 10 * len(weak)
    score -= 15 * len(inconsistent)
    score = max(score, 0)

    caveat = None
    if warnings:
        caveat = "Low-confidence MQTT context detected. Insights may be degraded until schema issues are remediated."

    return {
        "site": site,
        "equip": equip,
        "point": point,
        "required_fields": list(required_fields),
        "warnings": warnings,
        "missing": missing,
        "weak": weak,
        "inconsistent": inconsistent,
        "remediation": sorted(set(remediation)),
        "confidence_score": score,
        "caveat": caveat,
    }


@dataclass
class MqttConfig:
    enabled: bool = False
    broker: str = "127.0.0.1"
    port: int = 1883
    tls_enabled: bool = False
    username: str | None = None
    password: str | None = None
    client_id: str = "mcp4bas"
    topic_prefix: str | None = None
    schema_version: str = "v0.1"
    dataset_path: str = "resources/mqtt_messages.json"
    operation_mode: Literal["read-only", "write-enabled"] = "read-only"
    dry_run: bool = False
    write_enabled: bool = False
    publish_allowlist: set[str] = field(default_factory=set)
    runtime: Literal["simulated", "paho"] = "simulated"

    @classmethod
    def from_env(cls) -> "MqttConfig":
        runtime_raw = os.getenv("MQTT_RUNTIME", "simulated").strip().lower()
        runtime: Literal["simulated", "paho"] = "paho" if runtime_raw == "paho" else "simulated"
        return cls(
            enabled=_env_bool("MQTT_ENABLED", False),
            broker=os.getenv("MQTT_BROKER", "127.0.0.1"),
            port=int(os.getenv("MQTT_PORT", "1883")),
            tls_enabled=_env_bool("MQTT_TLS_ENABLED", False),
            username=os.getenv("MQTT_USERNAME", "").strip() or None,
            password=os.getenv("MQTT_PASSWORD", "").strip() or None,
            client_id=os.getenv("MQTT_CLIENT_ID", "mcp4bas"),
            topic_prefix=os.getenv("MQTT_TOPIC_PREFIX", "").strip() or None,
            schema_version=os.getenv("MQTT_SCHEMA_VERSION", "v0.1"),
            dataset_path=os.getenv("MQTT_DATASET_PATH", "resources/mqtt_messages.json"),
            operation_mode=_parse_operation_mode(os.getenv("BAS_OPERATION_MODE")),
            dry_run=_env_bool("BAS_DRY_RUN", False),
            write_enabled=_env_bool("MQTT_WRITE_ENABLED", False),
            publish_allowlist=_parse_allowlist(os.getenv("MQTT_PUBLISH_ALLOWLIST")),
            runtime=runtime,
        )


@dataclass
class MqttConnector:
    config: MqttConfig
    _latest_by_topic: dict[str, dict[str, Any]] = field(default_factory=dict)
    _seeded: bool = False

    @classmethod
    def from_env(cls) -> "MqttConnector":
        return cls(config=MqttConfig.from_env())

    def _disabled_message(self, operation: str) -> dict[str, Any]:
        return {
            "status": "error",
            "protocol": "mqtt",
            "operation": operation,
            "target": f"{self.config.broker}:{self.config.port}",
            "message": "MQTT integration is disabled. Set MQTT_ENABLED=true before running operations.",
        }

    def _resolve_dataset_path(self) -> Path:
        path = Path(self.config.dataset_path)
        if path.is_absolute():
            return path
        return _resource_root() / path

    def _seed_from_dataset_if_needed(self) -> None:
        if self._seeded:
            return

        self._seeded = True

        dataset_path = self._resolve_dataset_path()
        if not dataset_path.exists():
            return

        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
        rows: list[dict[str, Any]]
        if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
            rows = [dict(item) for item in payload["messages"]]
        elif isinstance(payload, list):
            rows = [dict(item) for item in payload]
        else:
            rows = []

        for row in rows:
            topic = str(row.get("topic", ""))
            body = row.get("payload")
            if topic and isinstance(body, dict):
                normalized = self._normalize_record(topic=topic, payload=body, source="dataset")
                self._latest_by_topic[topic] = normalized

    def _normalize_record(self, topic: str, payload: dict[str, Any], source: str) -> dict[str, Any]:
        validation = validate_mqtt_message(topic, payload, topic_prefix=self.config.topic_prefix)

        return {
            "topic": topic,
            "site": validation.get("site"),
            "equip": validation.get("equip"),
            "point": validation.get("point"),
            "value": payload.get("value"),
            "unit": payload.get("unit"),
            "timestamp": payload.get("timestamp"),
            "quality": payload.get("quality", "unknown"),
            "source": payload.get("source", source),
            "schema_version": self.config.schema_version,
            "payload": payload,
            "schema_validation": {
                "warnings": validation["warnings"],
                "missing": validation["missing"],
                "weak": validation["weak"],
                "inconsistent": validation["inconsistent"],
                "remediation": validation["remediation"],
            },
            "confidence_score": validation["confidence_score"],
            "caveat": validation["caveat"],
        }

    def _check_publish_policy(self, topic: str) -> tuple[bool, str]:
        if self.config.operation_mode != "write-enabled":
            return False, "BAS_OPERATION_MODE is read-only"
        if not self.config.write_enabled:
            return False, "MQTT_WRITE_ENABLED is false"
        if self.config.publish_allowlist and topic not in self.config.publish_allowlist:
            return False, "Topic not present in MQTT_PUBLISH_ALLOWLIST"
        return True, "allowed"

    def _build_audit(
        self,
        operation: str,
        allowed: bool,
        reason: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "protocol": "mqtt",
            "operation": operation,
            "mode": self.config.operation_mode,
            "dry_run": self.config.dry_run,
            "allowed": allowed,
            "reason": reason,
            "target": f"{self.config.broker}:{self.config.port}",
            "request": request,
            "runtime": self.config.runtime,
        }

    def ingest_message(self, topic: str, payload: dict[str, Any], source: str = "manual") -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("ingest_message")

        self._seed_from_dataset_if_needed()
        normalized = self._normalize_record(topic=topic, payload=payload, source=source)

        self._latest_by_topic[topic] = normalized

        return {
            "status": "ok",
            "protocol": "mqtt",
            "operation": "ingest_message",
            "target": f"{self.config.broker}:{self.config.port}",
            "record": normalized,
            "message": "MQTT message ingested.",
        }

    def get_latest_points(
        self,
        site: str | None = None,
        equip: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("get_latest_points")

        self._seed_from_dataset_if_needed()
        values = list(self._latest_by_topic.values())

        if site:
            values = [item for item in values if str(item.get("site", "")) == site]
        if equip:
            values = [item for item in values if str(item.get("equip", "")) == equip]

        values.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        sliced = values[: max(1, limit)]

        return {
            "status": "ok",
            "protocol": "mqtt",
            "operation": "get_latest_points",
            "target": f"{self.config.broker}:{self.config.port}",
            "count": len(sliced),
            "points": sliced,
            "message": f"Returned {len(sliced)} MQTT point(s).",
        }

    def publish_message(
        self,
        topic: str,
        payload: dict[str, Any],
        source: str = "mcp_tool",
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("publish_message")

        allowed, reason = self._check_publish_policy(topic=topic)
        audit = self._build_audit(
            operation="publish_message",
            allowed=allowed,
            reason=reason,
            request={"topic": topic, "payload": payload, "source": source},
        )

        if not allowed:
            return {
                "status": "error",
                "protocol": "mqtt",
                "operation": "publish_message",
                "target": f"{self.config.broker}:{self.config.port}",
                "message": f"MQTT publish blocked: {reason}.",
                "audit": audit,
            }

        self._seed_from_dataset_if_needed()
        normalized = self._normalize_record(topic=topic, payload=payload, source=source)

        if self.config.dry_run:
            return {
                "status": "ok",
                "protocol": "mqtt",
                "operation": "publish_message",
                "target": f"{self.config.broker}:{self.config.port}",
                "record": normalized,
                "audit": audit,
                "message": "Dry-run enabled; publish not sent.",
            }

        self._latest_by_topic[topic] = normalized
        return {
            "status": "ok",
            "protocol": "mqtt",
            "operation": "publish_message",
            "target": f"{self.config.broker}:{self.config.port}",
            "record": normalized,
            "audit": audit,
            "message": "MQTT publish applied to local runtime state.",
        }
