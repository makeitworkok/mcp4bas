from __future__ import annotations

import importlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return str(value)


@dataclass
class SnmpConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 161
    timeout_seconds: float = 3.0
    retries: int = 1
    runtime: Literal["simulated", "pysnmp"] = "simulated"
    version: Literal["v3", "v2c"] = "v3"
    v3_username: str | None = None
    v3_auth_protocol: Literal["SHA", "MD5"] = "SHA"
    v3_auth_key: str | None = None
    v3_priv_protocol: Literal["AES", "DES"] = "AES"
    v3_priv_key: str | None = None
    community: str | None = None
    dataset_path: str = "resources/snmp_dataset.json"

    @classmethod
    def from_env(cls) -> "SnmpConfig":
        runtime_raw = os.getenv("SNMP_RUNTIME", "simulated").strip().lower()
        runtime: Literal["simulated", "pysnmp"] = "pysnmp" if runtime_raw == "pysnmp" else "simulated"

        version_raw = os.getenv("SNMP_VERSION", "v3").strip().lower()
        version: Literal["v3", "v2c"] = "v2c" if version_raw == "v2c" else "v3"

        auth_protocol_raw = os.getenv("SNMP_V3_AUTH_PROTOCOL", "SHA").strip().upper()
        auth_protocol: Literal["SHA", "MD5"] = "MD5" if auth_protocol_raw == "MD5" else "SHA"

        priv_protocol_raw = os.getenv("SNMP_V3_PRIV_PROTOCOL", "AES").strip().upper()
        priv_protocol: Literal["AES", "DES"] = "DES" if priv_protocol_raw == "DES" else "AES"

        return cls(
            enabled=_env_bool("SNMP_ENABLED", False),
            host=os.getenv("SNMP_HOST", "127.0.0.1"),
            port=int(os.getenv("SNMP_PORT", "161")),
            timeout_seconds=float(os.getenv("SNMP_TIMEOUT_SECONDS", "3.0")),
            retries=max(0, int(os.getenv("SNMP_RETRIES", "1"))),
            runtime=runtime,
            version=version,
            v3_username=os.getenv("SNMP_V3_USERNAME", "").strip() or None,
            v3_auth_protocol=auth_protocol,
            v3_auth_key=os.getenv("SNMP_V3_AUTH_KEY", "").strip() or None,
            v3_priv_protocol=priv_protocol,
            v3_priv_key=os.getenv("SNMP_V3_PRIV_KEY", "").strip() or None,
            community=os.getenv("SNMP_COMMUNITY", "").strip() or None,
            dataset_path=os.getenv("SNMP_DATASET_PATH", "resources/snmp_dataset.json"),
        )


@dataclass
class SnmpConnector:
    config: SnmpConfig
    _dataset_cache: dict[str, Any] | None = field(default=None, init=False)

    @classmethod
    def from_env(cls) -> "SnmpConnector":
        return cls(config=SnmpConfig.from_env())

    def _disabled_message(self, operation: str) -> dict[str, Any]:
        return {
            "status": "error",
            "protocol": "snmp",
            "operation": operation,
            "target": f"{self.config.host}:{self.config.port}",
            "message": "SNMP integration is disabled. Set SNMP_ENABLED=true before running operations.",
        }

    def _resolve_target_host(self, host: str | None) -> str:
        value = (host or "").strip()
        return value or self.config.host

    def _resolve_dataset_path(self) -> Path:
        path = Path(self.config.dataset_path)
        if path.is_absolute():
            return path
        return _resource_root() / path

    def _load_dataset(self) -> dict[str, Any]:
        if self._dataset_cache is not None:
            return self._dataset_cache

        dataset_path = self._resolve_dataset_path()
        if not dataset_path.exists():
            self._dataset_cache = {"devices": []}
            return self._dataset_cache

        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {"devices": []}
        if not isinstance(payload.get("devices"), list):
            payload["devices"] = []

        self._dataset_cache = payload
        return payload

    def _find_device_dataset(self, host: str) -> dict[str, Any] | None:
        dataset = self._load_dataset()
        for item in dataset.get("devices", []):
            if not isinstance(item, dict):
                continue
            if str(item.get("host", "")).strip() == host:
                return item
        return None

    def _simulated_get(self, host: str, oid: str) -> tuple[bool, Any]:
        device = self._find_device_dataset(host)
        if not device:
            return False, None
        oids = device.get("oids")
        if not isinstance(oids, dict):
            return False, None
        if oid not in oids:
            return False, None
        return True, oids[oid]

    def _simulated_walk(self, host: str, oid_prefix: str) -> list[dict[str, Any]]:
        device = self._find_device_dataset(host)
        if not device:
            return []
        walks = device.get("walks")
        if not isinstance(walks, dict):
            return []

        entries_raw = walks.get(oid_prefix)
        if not isinstance(entries_raw, list):
            return []

        entries: list[dict[str, Any]] = []
        for item in entries_raw:
            if not isinstance(item, dict):
                continue
            oid = str(item.get("oid", "")).strip()
            if not oid:
                continue
            entries.append({"oid": oid, "value": _to_jsonable(item.get("value"))})
        return entries

    def _pysnmp_security_profile(self) -> Any:
        try:
            pysnmp_hlapi = importlib.import_module("pysnmp.hlapi")
        except ModuleNotFoundError as exc:
            raise RuntimeError("pysnmp is required for SNMP_RUNTIME=pysnmp") from exc

        CommunityData = getattr(pysnmp_hlapi, "CommunityData")
        UsmUserData = getattr(pysnmp_hlapi, "UsmUserData")
        usmAesCfb128Protocol = getattr(pysnmp_hlapi, "usmAesCfb128Protocol")
        usmDESPrivProtocol = getattr(pysnmp_hlapi, "usmDESPrivProtocol")
        usmHMACMD5AuthProtocol = getattr(pysnmp_hlapi, "usmHMACMD5AuthProtocol")
        usmHMACSHAAuthProtocol = getattr(pysnmp_hlapi, "usmHMACSHAAuthProtocol")

        if self.config.version == "v2c":
            if not self.config.community:
                raise ValueError("SNMP_COMMUNITY is required for SNMP_VERSION=v2c")
            return CommunityData(self.config.community)

        if not self.config.v3_username:
            raise ValueError("SNMP_V3_USERNAME is required for SNMP_VERSION=v3")

        auth_protocol = usmHMACSHAAuthProtocol if self.config.v3_auth_protocol == "SHA" else usmHMACMD5AuthProtocol
        priv_protocol = usmAesCfb128Protocol if self.config.v3_priv_protocol == "AES" else usmDESPrivProtocol

        if self.config.v3_auth_key and self.config.v3_priv_key:
            return UsmUserData(
                userName=self.config.v3_username,
                authKey=self.config.v3_auth_key,
                privKey=self.config.v3_priv_key,
                authProtocol=auth_protocol,
                privProtocol=priv_protocol,
            )
        if self.config.v3_auth_key:
            return UsmUserData(
                userName=self.config.v3_username,
                authKey=self.config.v3_auth_key,
                authProtocol=auth_protocol,
            )
        return UsmUserData(userName=self.config.v3_username)

    def _pysnmp_get(self, host: str, oid: str) -> tuple[bool, Any]:
        pysnmp_hlapi = importlib.import_module("pysnmp.hlapi")
        ContextData = getattr(pysnmp_hlapi, "ContextData")
        ObjectIdentity = getattr(pysnmp_hlapi, "ObjectIdentity")
        ObjectType = getattr(pysnmp_hlapi, "ObjectType")
        SnmpEngine = getattr(pysnmp_hlapi, "SnmpEngine")
        UdpTransportTarget = getattr(pysnmp_hlapi, "UdpTransportTarget")
        getCmd = getattr(pysnmp_hlapi, "getCmd")

        security = self._pysnmp_security_profile()

        error_indication, error_status, _error_index, var_binds = next(
            getCmd(
                SnmpEngine(),
                security,
                UdpTransportTarget((host, self.config.port), timeout=self.config.timeout_seconds, retries=self.config.retries),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
        )
        if error_indication:
            raise RuntimeError(str(error_indication))
        if error_status:
            raise RuntimeError(str(error_status))
        if not var_binds:
            return False, None

        _name, value = var_binds[0]
        return True, _to_jsonable(value)

    def _pysnmp_walk(self, host: str, oid_prefix: str, limit: int) -> list[dict[str, Any]]:
        pysnmp_hlapi = importlib.import_module("pysnmp.hlapi")
        ContextData = getattr(pysnmp_hlapi, "ContextData")
        ObjectIdentity = getattr(pysnmp_hlapi, "ObjectIdentity")
        ObjectType = getattr(pysnmp_hlapi, "ObjectType")
        SnmpEngine = getattr(pysnmp_hlapi, "SnmpEngine")
        UdpTransportTarget = getattr(pysnmp_hlapi, "UdpTransportTarget")
        nextCmd = getattr(pysnmp_hlapi, "nextCmd")

        security = self._pysnmp_security_profile()

        entries: list[dict[str, Any]] = []
        for error_indication, error_status, _error_index, var_binds in nextCmd(
            SnmpEngine(),
            security,
            UdpTransportTarget((host, self.config.port), timeout=self.config.timeout_seconds, retries=self.config.retries),
            ContextData(),
            ObjectType(ObjectIdentity(oid_prefix)),
            lexicographicMode=False,
        ):
            if error_indication:
                raise RuntimeError(str(error_indication))
            if error_status:
                raise RuntimeError(str(error_status))

            for name, value in var_binds:
                oid = str(name)
                if not oid.startswith(oid_prefix + ".") and oid != oid_prefix:
                    return entries
                entries.append({"oid": oid, "value": _to_jsonable(value)})
                if len(entries) >= limit:
                    return entries

        return entries

    def snmp_get(self, oid: str, host: str | None = None) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("snmp_get")

        target_host = self._resolve_target_host(host)
        if not oid.strip():
            raise ValueError("oid cannot be empty.")

        try:
            if self.config.runtime == "simulated":
                found, value = self._simulated_get(target_host, oid)
            else:
                found, value = self._pysnmp_get(target_host, oid)

            if not found:
                return {
                    "status": "error",
                    "protocol": "snmp",
                    "operation": "snmp_get",
                    "target": f"{target_host}:{self.config.port}",
                    "oid": oid,
                    "message": f"OID not found: {oid}",
                }

            return {
                "status": "ok",
                "protocol": "snmp",
                "operation": "snmp_get",
                "target": f"{target_host}:{self.config.port}",
                "oid": oid,
                "value": _to_jsonable(value),
                "message": "SNMP GET completed.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "protocol": "snmp",
                "operation": "snmp_get",
                "target": f"{target_host}:{self.config.port}",
                "oid": oid,
                "message": f"SNMP GET failed: {exc}",
            }

    def snmp_walk(self, oid_prefix: str, host: str | None = None, limit: int = 100) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("snmp_walk")

        target_host = self._resolve_target_host(host)
        if not oid_prefix.strip():
            raise ValueError("oid_prefix cannot be empty.")
        if limit < 1:
            raise ValueError("limit must be >= 1.")

        try:
            if self.config.runtime == "simulated":
                entries = self._simulated_walk(target_host, oid_prefix)
            else:
                entries = self._pysnmp_walk(target_host, oid_prefix, limit)

            sliced = entries[:limit]
            return {
                "status": "ok",
                "protocol": "snmp",
                "operation": "snmp_walk",
                "target": f"{target_host}:{self.config.port}",
                "oid_prefix": oid_prefix,
                "count": len(sliced),
                "entries": sliced,
                "message": f"SNMP WALK returned {len(sliced)} entr(ies).",
            }
        except Exception as exc:
            return {
                "status": "error",
                "protocol": "snmp",
                "operation": "snmp_walk",
                "target": f"{target_host}:{self.config.port}",
                "oid_prefix": oid_prefix,
                "message": f"SNMP WALK failed: {exc}",
            }

    def snmp_device_health_summary(self, host: str | None = None, interface_limit: int = 20) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("snmp_device_health_summary")

        target_host = self._resolve_target_host(host)
        if interface_limit < 1:
            raise ValueError("interface_limit must be >= 1.")

        start = time.time()

        uptime = self.snmp_get("1.3.6.1.2.1.1.3.0", host=target_host)
        names = self.snmp_walk("1.3.6.1.2.1.2.2.1.2", host=target_host, limit=interface_limit)
        status = self.snmp_walk("1.3.6.1.2.1.2.2.1.8", host=target_host, limit=interface_limit)
        in_errors = self.snmp_walk("1.3.6.1.2.1.2.2.1.14", host=target_host, limit=interface_limit)
        out_errors = self.snmp_walk("1.3.6.1.2.1.2.2.1.20", host=target_host, limit=interface_limit)

        if uptime.get("status") != "ok":
            return {
                "status": "error",
                "protocol": "snmp",
                "operation": "snmp_device_health_summary",
                "target": f"{target_host}:{self.config.port}",
                "message": uptime.get("message", "Unable to read device uptime."),
            }

        interfaces: list[dict[str, Any]] = []

        names_by_index: dict[str, Any] = {}
        for entry in names.get("entries", []):
            oid = str(entry.get("oid", ""))
            idx = oid.rsplit(".", 1)[-1]
            names_by_index[idx] = entry.get("value")

        status_by_index: dict[str, Any] = {}
        for entry in status.get("entries", []):
            oid = str(entry.get("oid", ""))
            idx = oid.rsplit(".", 1)[-1]
            status_by_index[idx] = entry.get("value")

        in_errors_by_index: dict[str, Any] = {}
        for entry in in_errors.get("entries", []):
            oid = str(entry.get("oid", ""))
            idx = oid.rsplit(".", 1)[-1]
            in_errors_by_index[idx] = entry.get("value")

        out_errors_by_index: dict[str, Any] = {}
        for entry in out_errors.get("entries", []):
            oid = str(entry.get("oid", ""))
            idx = oid.rsplit(".", 1)[-1]
            out_errors_by_index[idx] = entry.get("value")

        indices = sorted(set(names_by_index) | set(status_by_index) | set(in_errors_by_index) | set(out_errors_by_index))

        warnings: list[str] = []
        for index in indices[:interface_limit]:
            index_text = str(index)
            oper_value = status_by_index.get(index)
            in_error_value = in_errors_by_index.get(index, 0)
            out_error_value = out_errors_by_index.get(index, 0)
            interface = {
                "index": int(index_text) if index_text.isdigit() else index,
                "name": names_by_index.get(index),
                "oper_status": oper_value,
                "in_errors": in_error_value,
                "out_errors": out_error_value,
            }
            interfaces.append(interface)

            oper_int: int | None = None
            if isinstance(oper_value, (int, float, str)):
                try:
                    oper_int = int(oper_value)
                except (TypeError, ValueError):
                    oper_int = None
            if oper_int is not None and oper_int != 1:
                warnings.append(f"Interface {interface['name'] or index} oper_status={oper_int}")

            in_error_int: int | None = None
            if isinstance(in_error_value, (int, float, str)):
                try:
                    in_error_int = int(in_error_value)
                except (TypeError, ValueError):
                    in_error_int = None

            out_error_int: int | None = None
            if isinstance(out_error_value, (int, float, str)):
                try:
                    out_error_int = int(out_error_value)
                except (TypeError, ValueError):
                    out_error_int = None

            if (in_error_int is not None and in_error_int > 0) or (out_error_int is not None and out_error_int > 0):
                warnings.append(
                    f"Interface {interface['name'] or index} errors in={in_error_value} out={out_error_value}"
                )

        elapsed_ms = round((time.time() - start) * 1000, 1)

        return {
            "status": "ok",
            "protocol": "snmp",
            "operation": "snmp_device_health_summary",
            "target": f"{target_host}:{self.config.port}",
            "uptime_ticks": uptime.get("value"),
            "interfaces": interfaces,
            "warnings": warnings,
            "elapsed_ms": elapsed_ms,
            "message": "SNMP device health summary completed.",
        }
