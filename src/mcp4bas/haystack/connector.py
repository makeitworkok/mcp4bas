from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.error import URLError
from urllib.request import Request, urlopen


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[1]


@dataclass
class HaystackConfig:
    enabled: bool = False
    mode: Literal["dataset", "api"] = "dataset"
    dataset_path: str = "resources/haystack_points.json"
    endpoint: str | None = None
    auth_token: str | None = None
    timeout_seconds: float = 5.0
    project_filters: set[str] = field(default_factory=set)
    site_filters: set[str] = field(default_factory=set)

    @classmethod
    def from_env(cls) -> HaystackConfig:
        mode_raw = os.getenv("HAYSTACK_MODE", "dataset").strip().lower()
        mode: Literal["dataset", "api"] = "api" if mode_raw == "api" else "dataset"
        endpoint = os.getenv("HAYSTACK_ENDPOINT", "").strip() or None
        auth_token = os.getenv("HAYSTACK_AUTH_TOKEN", "").strip() or None
        dataset_path = os.getenv("HAYSTACK_DATASET_PATH", "resources/haystack_points.json").strip()
        return cls(
            enabled=_env_bool("HAYSTACK_ENABLED", False),
            mode=mode,
            dataset_path=dataset_path,
            endpoint=endpoint,
            auth_token=auth_token,
            timeout_seconds=float(os.getenv("HAYSTACK_TIMEOUT_SECONDS", "5.0")),
            project_filters=_env_set("HAYSTACK_PROJECT_FILTERS"),
            site_filters=_env_set("HAYSTACK_SITE_FILTERS"),
        )


def _normalize_tags(point: dict[str, Any]) -> dict[str, Any]:
    tags_raw = point.get("tags")
    if isinstance(tags_raw, dict):
        return dict(tags_raw)

    tags = {k: v for k, v in point.items() if k not in {"id", "dis", "site", "project", "tags"}}
    if "site" in point:
        tags.setdefault("site", point["site"])
    if "project" in point:
        tags.setdefault("project", point["project"])
    return tags


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


REQUIRED_TAGS = ("site", "equip", "point", "unit", "kind")


def validate_haystack_tags(tags: dict[str, Any]) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    missing: list[str] = []
    weak: list[str] = []
    inconsistent: list[str] = []
    remediation: list[str] = []

    for tag in REQUIRED_TAGS:
        if tag not in tags or _is_blank(tags.get(tag)):
            missing.append(tag)
            warnings.append(
                {
                    "level": "missing",
                    "tag": tag,
                    "message": f"Required tag '{tag}' is missing or blank.",
                }
            )
            remediation.append(f"Add required tag '{tag}' with a site-standard value.")

    weak_markers = {"unknown", "n/a", "na", "tbd", "todo", "none"}
    for key, value in tags.items():
        if isinstance(value, str) and value.strip().lower() in weak_markers:
            weak.append(key)
            warnings.append(
                {
                    "level": "weak",
                    "tag": key,
                    "message": f"Tag '{key}' has weak placeholder value '{value}'.",
                }
            )
            remediation.append(f"Replace placeholder value for '{key}' with an operationally meaningful value.")

    kind = str(tags.get("kind", "")).strip().lower()
    unit_present = not _is_blank(tags.get("unit"))
    if kind in {"bool", "boolean"} and unit_present:
        inconsistent.append("unit")
        warnings.append(
            {
                "level": "inconsistent",
                "tag": "unit",
                "message": "Boolean points usually should not declare engineering unit.",
            }
        )
        remediation.append("Remove 'unit' for boolean points unless site convention explicitly requires it.")
    if kind in {"number", "numeric", "float", "int"} and not unit_present:
        inconsistent.append("unit")
        warnings.append(
            {
                "level": "inconsistent",
                "tag": "unit",
                "message": "Numeric points should include a unit for diagnostics quality.",
            }
        )
        remediation.append("Add a valid engineering unit for numeric points.")

    score = 100
    score -= 20 * len(missing)
    score -= 10 * len(weak)
    score -= 15 * len(inconsistent)
    score = max(score, 0)

    caveat = None
    if warnings:
        caveat = (
            "Low-confidence Haystack metadata detected. Diagnostics output may be degraded until tags are remediated."
        )

    return {
        "required_tags": list(REQUIRED_TAGS),
        "warnings": warnings,
        "missing": missing,
        "weak": weak,
        "inconsistent": inconsistent,
        "remediation": sorted(set(remediation)),
        "confidence_score": score,
        "caveat": caveat,
    }


@dataclass
class HaystackConnector:
    config: HaystackConfig

    @classmethod
    def from_env(cls) -> HaystackConnector:
        return cls(config=HaystackConfig.from_env())

    def _disabled_message(self, operation: str) -> dict[str, Any]:
        return {
            "status": "error",
            "operation": operation,
            "message": (
                "Haystack integration is disabled. Set HAYSTACK_ENABLED=true and configure "
                "HAYSTACK_MODE/HAYSTACK_DATASET_PATH or HAYSTACK_ENDPOINT before running operations."
            ),
        }

    def _resolve_dataset_path(self) -> Path:
        path = Path(self.config.dataset_path)
        if path.is_absolute():
            return path
        return _resource_root() / path

    def _load_dataset_points(self) -> list[dict[str, Any]]:
        dataset_path = self._resolve_dataset_path()
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("points"), list):
            return [dict(item) for item in payload["points"]]
        if isinstance(payload, list):
            return [dict(item) for item in payload]
        raise ValueError("Haystack dataset must be a list of points or an object with a 'points' list.")

    def _load_api_points(self) -> list[dict[str, Any]]:
        if not self.config.endpoint:
            raise ValueError("HAYSTACK_ENDPOINT is required when HAYSTACK_MODE=api.")

        request = Request(self.config.endpoint, method="GET")
        request.add_header("Accept", "application/json")
        if self.config.auth_token:
            request.add_header("Authorization", f"Bearer {self.config.auth_token}")

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"Haystack API request failed: {exc}") from exc

        if isinstance(payload, dict) and isinstance(payload.get("points"), list):
            return [dict(item) for item in payload["points"]]
        if isinstance(payload, list):
            return [dict(item) for item in payload]
        raise ValueError("Haystack API response must be a list of points or an object with a 'points' list.")

    def _load_points(self) -> list[dict[str, Any]]:
        if self.config.mode == "api":
            return self._load_api_points()
        return self._load_dataset_points()

    def _apply_filters(self, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = points
        if self.config.project_filters:
            filtered = [
                point
                for point in filtered
                if str(point.get("project") or _normalize_tags(point).get("project", ""))
                in self.config.project_filters
            ]
        if self.config.site_filters:
            filtered = [
                point
                for point in filtered
                if str(point.get("site") or _normalize_tags(point).get("site", "")) in self.config.site_filters
            ]
        return filtered

    def _summarize_point(self, point: dict[str, Any]) -> dict[str, Any]:
        tags = _normalize_tags(point)
        validation = validate_haystack_tags(tags)
        return {
            "id": point.get("id"),
            "dis": point.get("dis") or tags.get("dis") or point.get("id"),
            "site": point.get("site") or tags.get("site"),
            "project": point.get("project") or tags.get("project"),
            "kind": tags.get("kind"),
            "unit": tags.get("unit"),
            "tags": tags,
            "tag_validation": {
                "warnings": validation["warnings"],
                "missing": validation["missing"],
                "weak": validation["weak"],
                "inconsistent": validation["inconsistent"],
                "remediation": validation["remediation"],
            },
            "confidence_score": validation["confidence_score"],
            "caveat": validation["caveat"],
        }

    def discover_points(self, limit: int = 100) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("discover_points")

        points = self._apply_filters(self._load_points())
        summaries = [self._summarize_point(point) for point in points[: max(1, limit)]]
        return {
            "status": "ok",
            "protocol": "haystack",
            "operation": "discover_points",
            "target": self.config.endpoint or str(self._resolve_dataset_path()),
            "count": len(summaries),
            "points": summaries,
            "message": f"Discovered {len(summaries)} Haystack point(s).",
        }

    def get_point_metadata(self, point_id: str) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("get_point_metadata")

        points = self._apply_filters(self._load_points())
        for point in points:
            candidate_id = str(point.get("id") or _normalize_tags(point).get("id") or "")
            if candidate_id == point_id:
                summary = self._summarize_point(point)
                return {
                    "status": "ok",
                    "protocol": "haystack",
                    "operation": "get_point_metadata",
                    "target": self.config.endpoint or str(self._resolve_dataset_path()),
                    "point_id": point_id,
                    "metadata": summary,
                    "message": "Point metadata fetched.",
                }

        return {
            "status": "error",
            "protocol": "haystack",
            "operation": "get_point_metadata",
            "target": self.config.endpoint or str(self._resolve_dataset_path()),
            "point_id": point_id,
            "message": f"Point not found: {point_id}",
        }
