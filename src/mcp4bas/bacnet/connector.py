from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import ipaddress
import os
import platform
import re
import socket
import subprocess
import time
from argparse import Namespace
from dataclasses import dataclass, field
from threading import Thread
from typing import Any, Callable, Literal

from bacpypes3.app import Application
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import Null


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int_optional(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    return int(raw)


def _parse_operation_mode(raw: str | None) -> Literal["read-only", "write-enabled"]:
    value = (raw or "read-only").strip().lower()
    if value == "write-enabled":
        return "write-enabled"
    return "read-only"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return str(value)


def _run_coro_blocking(coro: Any) -> Any:
    result: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - pass through for caller handling
            result["error"] = exc

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        error = result["error"]
        if isinstance(error, Exception):
            raise error
        raise RuntimeError(str(error))
    if "value" not in result:
        raise RuntimeError("BACnet operation did not return a result.")
    return result.get("value")


def _patch_windows_udp_reuse_port() -> None:
    if platform.system().lower() != "windows":
        return

    import bacpypes3.ipv4 as bacnet_ipv4

    ipv4_server_cls = getattr(bacnet_ipv4, "IPv4DatagramServer", None)
    ipv4_protocol = getattr(bacnet_ipv4, "IPv4DatagramProtocol", None)
    if not ipv4_server_cls or not ipv4_protocol:
        return

    if getattr(ipv4_server_cls, "_mcp4bas_windows_patch", False):
        return

    async def retrying_create_datagram_endpoint(
        self,
        loop: asyncio.events.AbstractEventLoop,
        addrTuple: tuple[str, int],
        bind_socket: socket.socket | None = None,
    ) -> Any:
        while True:
            try:
                if bind_socket:
                    return await loop.create_datagram_endpoint(ipv4_protocol, sock=bind_socket)

                try:
                    return await loop.create_datagram_endpoint(
                        ipv4_protocol,
                        local_addr=addrTuple,
                        allow_broadcast=True,
                        reuse_port=True,
                    )
                except ValueError as exc:
                    if "reuse_port" not in str(exc):
                        raise
                    return await loop.create_datagram_endpoint(
                        ipv4_protocol,
                        local_addr=addrTuple,
                        allow_broadcast=True,
                    )
            except OSError:
                await asyncio.sleep(1.0)

    setattr(ipv4_server_cls, "retrying_create_datagram_endpoint", retrying_create_datagram_endpoint)
    setattr(ipv4_server_cls, "_mcp4bas_windows_patch", True)


def _split_host_port(address: str | None) -> tuple[str | None, int]:
    if not address:
        return None, 47808

    host: str | None = address
    port = 47808
    if ":" in address:
        maybe_host, maybe_port = address.rsplit(":", 1)
        host = maybe_host or None
        try:
            port = int(maybe_port)
        except ValueError:
            port = 47808
    return host, port


def _local_ip_for_target(target_host: str | None, target_port: int) -> str | None:
    if not target_host:
        return None

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((target_host, target_port))
            return sock.getsockname()[0]
    except OSError:
        return None


def _directed_broadcast_for_local(local_ip: str | None, prefix: int = 24) -> str | None:
    if not local_ip:
        return None

    try:
        network = ipaddress.ip_network(f"{local_ip}/{prefix}", strict=False)
        return str(network.broadcast_address)
    except ValueError:
        return None


def _parse_allowlist(raw: str | None) -> set[tuple[str, str]]:
    if not raw:
        return set()

    allowed: set[tuple[str, str]] = set()
    for entry in raw.split(";"):
        token = entry.strip()
        if not token or ":" not in token:
            continue
        object_id, property_name = token.split(":", 1)
        allowed.add((object_id.strip(), property_name.strip()))
    return allowed


def _coerce_bacnet_write_value(value: str | float | int) -> str | float | int | Null:
    if isinstance(value, str) and value.strip().lower() in {"null", "none", "relinquish"}:
        return Null(())
    return value


def _normalize_mac_address(raw: str | None) -> str | None:
    if not raw:
        return None

    token = raw.strip().lower()
    if not token:
        return None

    token = token.replace("-", ":")
    if "." in token and ":" not in token:
        compact = token.replace(".", "")
        if len(compact) == 12 and all(char in "0123456789abcdef" for char in compact):
            octets = [compact[index : index + 2] for index in range(0, 12, 2)]
            return ":".join(octet.upper() for octet in octets)
        return None

    parts = token.split(":")
    if len(parts) != 6:
        return None
    if any(len(part) != 2 or any(char not in "0123456789abcdef" for char in part) for part in parts):
        return None

    return ":".join(part.upper() for part in parts)


def _ip_from_target_address(address: str | None) -> str | None:
    if not address:
        return None

    token = address.strip()
    if not token:
        return None

    ipv4_with_port = re.match(r"^(\d+\.\d+\.\d+\.\d+)(?::\d+)?$", token)
    if ipv4_with_port:
        return ipv4_with_port.group(1)

    bracketed_ipv6 = re.match(r"^\[([^\]]+)\](?::\d+)?$", token)
    if bracketed_ipv6:
        return bracketed_ipv6.group(1)

    return token


def _extract_mac_candidates_from_neighbors(table_output: str, ip_address: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    mac_pattern = re.compile(r"([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}|[0-9A-Fa-f]{4}(?:\.[0-9A-Fa-f]{4}){2})")

    for line in table_output.splitlines():
        if ip_address not in line:
            continue
        matches = mac_pattern.findall(line)
        for raw_mac in matches:
            normalized = _normalize_mac_address(raw_mac)
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(normalized)

    return candidates


def _run_command_capture_output(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=4,
    )
    chunks = [completed.stdout.strip(), completed.stderr.strip()]
    return "\n".join(chunk for chunk in chunks if chunk)


def _read_neighbor_table() -> str:
    if platform.system().lower() == "windows":
        return _run_command_capture_output(["arp", "-a"])

    outputs: list[str] = []
    for command in (["ip", "neigh"], ["arp", "-an"], ["arp", "-a"]):
        try:
            output = _run_command_capture_output(list(command))
            if output:
                outputs.append(output)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "\n".join(outputs)


def _probe_ip_address(ip_address: str) -> None:
    command: list[str]
    if platform.system().lower() == "windows":
        command = ["ping", "-n", "1", "-w", "1000", ip_address]
    else:
        command = ["ping", "-c", "1", "-W", "1", ip_address]

    try:
        subprocess.run(command, check=False, capture_output=True, text=True, timeout=4)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return


def _parse_datetime_optional(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None

    token = value.strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(token)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _extract_from_mapping_or_attrs(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        lowered = {str(key).lower(): item for key, item in value.items()}
        for key in keys:
            if key in lowered:
                return lowered[key]

    for key in keys:
        if hasattr(value, key):
            return getattr(value, key)
    return None


def _normalize_trend_entry(entry: Any, index: int) -> dict[str, Any]:
    timestamp_raw = _extract_from_mapping_or_attrs(
        entry,
        (
            "timestamp",
            "time",
            "datetime",
            "date_time",
            "timestampvalue",
        ),
    )
    value_raw = _extract_from_mapping_or_attrs(
        entry,
        (
            "value",
            "logdatum",
            "datum",
            "presentvalue",
        ),
    )
    status_raw = _extract_from_mapping_or_attrs(entry, ("status", "statusflags", "flags"))

    timestamp = None
    parsed = _parse_datetime_optional(_to_jsonable(timestamp_raw))
    if parsed is not None:
        timestamp = parsed.isoformat()

    normalized: dict[str, Any] = {
        "index": index,
        "timestamp": timestamp,
        "value": _to_jsonable(value_raw),
        "status": _to_jsonable(status_raw),
    }

    if normalized["timestamp"] is None and normalized["value"] is None and normalized["status"] is None:
        normalized["raw"] = _to_jsonable(entry)
    return normalized


def _normalize_weekly_schedule(weekly_schedule_raw: Any) -> list[dict[str, Any]]:
    day_names = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    weekly_json = _to_jsonable(weekly_schedule_raw)
    if not isinstance(weekly_json, list):
        return []

    weekly: list[dict[str, Any]] = []
    for index, day_block in enumerate(weekly_json):
        day_name = day_names[index] if index < len(day_names) else f"day_{index + 1}"
        events_raw = day_block if isinstance(day_block, list) else [day_block]
        events: list[dict[str, Any]] = []

        for event in events_raw:
            if isinstance(event, dict):
                lowered = {str(key).lower(): value for key, value in event.items()}
                events.append(
                    {
                        "time": _to_jsonable(
                            lowered.get("time") or lowered.get("starttime") or lowered.get("start_time")
                        ),
                        "value": _to_jsonable(
                            lowered.get("value")
                            or lowered.get("setpoint")
                            or lowered.get("presentvalue")
                            or lowered.get("target")
                        ),
                    }
                )
            elif isinstance(event, list | tuple) and len(event) >= 2:
                events.append({"time": _to_jsonable(event[0]), "value": _to_jsonable(event[1])})
            else:
                events.append({"raw": _to_jsonable(event)})

        weekly.append({"day": day_name, "events": events})

    return weekly


def _normalize_exception_schedule(exception_schedule_raw: Any) -> list[dict[str, Any]]:
    exception_json = _to_jsonable(exception_schedule_raw)
    if not isinstance(exception_json, list):
        return []

    exceptions: list[dict[str, Any]] = []
    for index, block in enumerate(exception_json):
        if isinstance(block, dict):
            lowered = {str(key).lower(): value for key, value in block.items()}
            events_raw = lowered.get("events")
            if not isinstance(events_raw, list):
                events_raw = [events_raw] if events_raw is not None else []
            events = [
                _to_jsonable(event)
                for event in events_raw
            ]
            exceptions.append(
                {
                    "index": index,
                    "name": _to_jsonable(lowered.get("name") or lowered.get("label") or lowered.get("id")),
                    "period": _to_jsonable(
                        lowered.get("period")
                        or lowered.get("date")
                        or lowered.get("calendarentry")
                        or lowered.get("calendar_entry")
                    ),
                    "events": events,
                }
            )
        else:
            exceptions.append({"index": index, "raw": _to_jsonable(block)})

    return exceptions


@dataclass
class BacnetConfig:
    enabled: bool = False
    local_address: str = "host:0"
    network: int = 0
    device_instance: int = 599001
    device_name: str = "MCP4BAS"
    vendor_identifier: int = 999
    target_address: str | None = None
    timeout_seconds: float = 3.0
    retries: int = 1
    write_enabled: bool = False
    operation_mode: Literal["read-only", "write-enabled"] = "read-only"
    dry_run: bool = False
    write_allowlist: set[tuple[str, str]] = field(default_factory=set)
    write_priority_default: int | None = None

    @classmethod
    def from_env(cls) -> BacnetConfig:
        target = os.getenv("BACNET_TARGET_ADDRESS")
        return cls(
            enabled=_env_bool("BACNET_ENABLED", False),
            local_address=os.getenv("BACNET_LOCAL_ADDRESS", "host:0"),
            network=int(os.getenv("BACNET_NETWORK", "0")),
            device_instance=int(os.getenv("BACNET_DEVICE_INSTANCE", "599001")),
            device_name=os.getenv("BACNET_DEVICE_NAME", "MCP4BAS"),
            vendor_identifier=int(os.getenv("BACNET_VENDOR_IDENTIFIER", "999")),
            target_address=target if target else None,
            timeout_seconds=float(os.getenv("BACNET_TIMEOUT_SECONDS", "3.0")),
            retries=max(0, int(os.getenv("BACNET_RETRIES", "1"))),
            write_enabled=_env_bool("BACNET_WRITE_ENABLED", False),
            operation_mode=_parse_operation_mode(os.getenv("BAS_OPERATION_MODE")),
            dry_run=_env_bool("BAS_DRY_RUN", False),
            write_allowlist=_parse_allowlist(os.getenv("BACNET_WRITE_ALLOWLIST")),
            write_priority_default=_env_int_optional("BACNET_WRITE_PRIORITY_DEFAULT"),
        )


@dataclass
class BacnetConnector:
    config: BacnetConfig
    application_factory: Callable[[Namespace], Application] | None = None

    @classmethod
    def from_env(cls) -> BacnetConnector:
        return cls(config=BacnetConfig.from_env())

    def _build_application(self) -> Application:
        _patch_windows_udp_reuse_port()

        app_args = Namespace(
            vendoridentifier=self.config.vendor_identifier,
            instance=self.config.device_instance,
            name=self.config.device_name,
            address=self.config.local_address,
            foreign=None,
            network=self.config.network,
            bbmd=None,
            ttl=30,
        )
        factory = self.application_factory or Application.from_args
        return factory(app_args)

    def _disabled_message(self, operation: str) -> dict[str, Any]:
        return {
            "status": "error",
            "operation": operation,
            "message": (
                "BACnet integration is disabled. Set BACNET_ENABLED=true and configure "
                "BACNET_LOCAL_ADDRESS/BACNET_TARGET_ADDRESS before running live operations."
            ),
        }

    def _build_audit(
        self,
        operation: str,
        allowed: bool,
        reason: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "protocol": "bacnet",
            "operation": operation,
            "mode": self.config.operation_mode,
            "dry_run": self.config.dry_run,
            "allowed": allowed,
            "reason": reason,
            "target": self.config.target_address,
            "request": request,
        }

    def _check_write_policy(self, object_id: str, property_name: str) -> tuple[bool, str]:
        if self.config.operation_mode != "write-enabled":
            return False, "BAS_OPERATION_MODE is read-only"
        if not self.config.write_enabled:
            return False, "BACNET_WRITE_ENABLED is false"
        if self.config.write_allowlist and (object_id, property_name) not in self.config.write_allowlist:
            return False, "Point not present in BACNET_WRITE_ALLOWLIST"
        return True, "allowed"

    def _execute_with_retries(self, operation: str, call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        attempts = self.config.retries + 1
        last_exception: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return call()
            except TimeoutError as exc:
                last_exception = exc
            except Exception as exc:  # pragma: no cover - retry behavior covered by timeout path
                last_exception = exc

            if attempt < attempts:
                time.sleep(min(0.25 * attempt, 1.0))

        message = (
            f"BACnet {operation} failed after {attempts} attempts. "
            f"timeout={self.config.timeout_seconds}s retries={self.config.retries}. "
            f"Last error: {last_exception}"
        )
        return {
            "status": "error",
            "operation": operation,
            "message": message,
            "attempts": attempts,
        }

    def _extract_iam(self, iam: Any) -> dict[str, Any]:
        device_identifier = getattr(iam, "iAmDeviceIdentifier", None)
        device_instance = None
        if isinstance(device_identifier, tuple) and len(device_identifier) > 1:
            device_instance = device_identifier[1]
        return {
            "device_instance": device_instance,
            "source": str(getattr(iam, "pduSource", "unknown")),
            "max_apdu": _to_jsonable(getattr(iam, "maxAPDULengthAccepted", None)),
            "segmentation": _to_jsonable(getattr(iam, "segmentationSupported", None)),
            "vendor_id": _to_jsonable(getattr(iam, "vendorID", None)),
        }

    async def _query_who_is(
        self,
        app: Application,
        address: Address | None,
    ) -> list[dict[str, Any]]:
        raw = await asyncio.wait_for(
            app.who_is(address=address, timeout=self.config.timeout_seconds),
            timeout=self.config.timeout_seconds + 1,
        )
        return [self._extract_iam(entry) for entry in raw]

    def _dedupe_devices(self, devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[tuple[Any, Any], dict[str, Any]] = {}
        for device in devices:
            key = (device.get("device_instance"), device.get("source"))
            deduped[key] = device
        return list(deduped.values())

    async def _who_is_async(self) -> dict[str, Any]:
        app = self._build_application()
        try:
            discovered: list[dict[str, Any]] = []
            steps: list[str] = []
            errors: list[str] = []

            target_host, target_port = _split_host_port(self.config.target_address)

            try:
                discovered.extend(await self._query_who_is(app=app, address=None))
                steps.append("global-broadcast")
            except Exception as exc:
                errors.append(f"global-broadcast failed: {exc}")

            if not discovered:
                local_ip = _local_ip_for_target(target_host, target_port)
                directed_broadcast = _directed_broadcast_for_local(local_ip)
                if directed_broadcast:
                    directed_addr = Address(f"{directed_broadcast}:{target_port}")
                    try:
                        discovered.extend(await self._query_who_is(app=app, address=directed_addr))
                        steps.append(f"directed-broadcast:{directed_addr}")
                    except Exception as exc:
                        errors.append(f"directed-broadcast failed: {exc}")

            if not discovered and self.config.target_address:
                try:
                    discovered.extend(
                        await self._query_who_is(
                            app=app,
                            address=Address(self.config.target_address),
                        )
                    )
                    steps.append(f"direct-target:{self.config.target_address}")
                except Exception as exc:
                    errors.append(f"direct-target failed: {exc}")

            devices = self._dedupe_devices(discovered)
            step_message = ", ".join(steps) if steps else "none"
            error_message = f" errors={'; '.join(errors)}" if errors else ""
            return {
                "status": "ok",
                "operation": "who_is",
                "target_address": self.config.target_address,
                "count": len(devices),
                "devices": devices,
                "message": (
                    f"Received {len(devices)} I-Am response(s). "
                    f"steps={step_message}.{error_message}"
                ),
            }
        finally:
            app.close()

    async def _read_property_async(self, object_id: str, property_name: str) -> dict[str, Any]:
        if not self.config.target_address:
            raise ValueError(
                "BACNET_TARGET_ADDRESS is not configured. Set it to the remote BACnet device "
                "address before using read_property."
            )

        app = self._build_application()
        try:
            value = await asyncio.wait_for(
                app.read_property(
                    address=self.config.target_address,
                    objid=object_id,
                    prop=property_name,
                ),
                timeout=self.config.timeout_seconds,
            )
            return {
                "status": "ok",
                "operation": "read_property",
                "object_id": object_id,
                "property": property_name,
                "target_address": self.config.target_address,
                "value": _to_jsonable(value),
                "message": "Read completed.",
            }
        finally:
            app.close()

    async def _read_trend_async(
        self,
        trend_object_id: str,
        limit: int,
        window_minutes: int | None,
        source_object_id: str | None,
        source_property: str,
    ) -> dict[str, Any]:
        if not self.config.target_address:
            raise ValueError(
                "BACNET_TARGET_ADDRESS is not configured. Set it to the remote BACnet device "
                "address before using read_trend."
            )

        app = self._build_application()
        try:
            metadata: dict[str, Any] = {}
            errors: list[str] = []

            log_buffer_raw: Any | None = None
            for property_name in (
                "log-buffer",
                "record-count",
                "total-record-count",
                "start-time",
                "stop-time",
                "log-interval",
            ):
                try:
                    value = await asyncio.wait_for(
                        app.read_property(
                            address=self.config.target_address,
                            objid=trend_object_id,
                            prop=property_name,
                        ),
                        timeout=self.config.timeout_seconds,
                    )
                    if property_name == "log-buffer":
                        log_buffer_raw = value
                    else:
                        metadata[property_name] = _to_jsonable(value)
                except BaseException as exc:
                    errors.append(f"{property_name}: {exc}")

            entries: list[dict[str, Any]] = []
            if isinstance(log_buffer_raw, list | tuple):
                for index, entry in enumerate(log_buffer_raw):
                    entries.append(_normalize_trend_entry(entry, index=index))

            if window_minutes is not None:
                cutoff = datetime.now(timezone.utc).timestamp() - (window_minutes * 60)
                filtered_entries: list[dict[str, Any]] = []
                for entry in entries:
                    timestamp_value = entry.get("timestamp")
                    parsed = _parse_datetime_optional(timestamp_value)
                    if parsed is not None and parsed.timestamp() >= cutoff:
                        filtered_entries.append(entry)
                entries = filtered_entries

            entries = entries[:limit]

            fallback_used = False
            fallback_reason: str | None = None
            if not entries and source_object_id:
                try:
                    fallback_value = await asyncio.wait_for(
                        app.read_property(
                            address=self.config.target_address,
                            objid=source_object_id,
                            prop=source_property,
                        ),
                        timeout=self.config.timeout_seconds,
                    )
                    entries = [
                        {
                            "index": 0,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "value": _to_jsonable(fallback_value),
                            "status": None,
                            "source": f"fallback:{source_object_id}:{source_property}",
                        }
                    ]
                    fallback_used = True
                    fallback_reason = "Trend log entries unavailable; used source point read fallback."
                except BaseException as exc:
                    errors.append(f"fallback:{source_object_id}:{source_property}: {exc}")

            if not entries and log_buffer_raw is None:
                return {
                    "status": "error",
                    "operation": "read_trend",
                    "trend_object_id": trend_object_id,
                    "target_address": self.config.target_address,
                    "message": "Trend retrieval failed. Unable to read log-buffer from trend object.",
                    "errors": errors,
                }

            return {
                "status": "ok",
                "operation": "read_trend",
                "trend_object_id": trend_object_id,
                "target_address": self.config.target_address,
                "window_minutes": window_minutes,
                "limit": limit,
                "count": len(entries),
                "entries": entries,
                "metadata": metadata,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "errors": errors,
                "message": (
                    f"Trend retrieval completed with {len(entries)} entr(ies)."
                    if not fallback_used
                    else f"Trend retrieval completed using fallback with {len(entries)} entr(ies)."
                ),
            }
        finally:
            app.close()

    async def _read_schedule_async(self, schedule_object_id: str) -> dict[str, Any]:
        if not self.config.target_address:
            raise ValueError(
                "BACNET_TARGET_ADDRESS is not configured. Set it to the remote BACnet device "
                "address before using read_schedule."
            )

        app = self._build_application()
        try:
            errors: list[str] = []

            weekly_schedule_raw: Any | None = None
            exception_schedule_raw: Any | None = None
            effective_period_raw: Any | None = None
            present_value_raw: Any | None = None

            for property_name in (
                "weekly-schedule",
                "exception-schedule",
                "effective-period",
                "present-value",
            ):
                try:
                    value = await asyncio.wait_for(
                        app.read_property(
                            address=self.config.target_address,
                            objid=schedule_object_id,
                            prop=property_name,
                        ),
                        timeout=self.config.timeout_seconds,
                    )
                    if property_name == "weekly-schedule":
                        weekly_schedule_raw = value
                    elif property_name == "exception-schedule":
                        exception_schedule_raw = value
                    elif property_name == "effective-period":
                        effective_period_raw = value
                    elif property_name == "present-value":
                        present_value_raw = value
                except BaseException as exc:
                    errors.append(f"{property_name}: {exc}")

            weekly_schedule = _normalize_weekly_schedule(weekly_schedule_raw)
            exception_schedule = _normalize_exception_schedule(exception_schedule_raw)

            if not weekly_schedule and exception_schedule_raw is None:
                return {
                    "status": "error",
                    "operation": "read_schedule",
                    "schedule_object_id": schedule_object_id,
                    "target_address": self.config.target_address,
                    "message": "Schedule retrieval failed. Unable to read weekly schedule.",
                    "errors": errors,
                }

            return {
                "status": "ok",
                "operation": "read_schedule",
                "schedule_object_id": schedule_object_id,
                "target_address": self.config.target_address,
                "weekly_schedule": weekly_schedule,
                "exception_schedule": exception_schedule,
                "effective_period": _to_jsonable(effective_period_raw),
                "present_value": _to_jsonable(present_value_raw),
                "errors": errors,
                "message": "Schedule retrieval completed.",
            }
        finally:
            app.close()

    async def _write_property_async(
        self,
        object_id: str,
        property_name: str,
        value: str | float | int,
        priority: int | None = None,
    ) -> dict[str, Any]:
        allowed, reason = self._check_write_policy(object_id=object_id, property_name=property_name)
        audit = self._build_audit(
            operation="write_property",
            allowed=allowed,
            reason=reason,
            request={
                "object_id": object_id,
                "property": property_name,
                "value": value,
                "priority": priority,
            },
        )
        if not allowed:
            return {
                "status": "error",
                "operation": "write_property",
                "object_id": object_id,
                "property": property_name,
                "target_address": self.config.target_address,
                "message": f"BACnet write blocked: {reason}.",
                "audit": audit,
            }
        if not self.config.target_address:
            raise ValueError(
                "BACNET_TARGET_ADDRESS is not configured. Set it before using write_property."
            )

        if self.config.dry_run:
            return {
                "status": "ok",
                "operation": "write_property",
                "object_id": object_id,
                "property": property_name,
                "target_address": self.config.target_address,
                "value": _to_jsonable(value),
                "message": "Dry-run enabled; write not sent.",
                "audit": audit,
            }

        app = self._build_application()
        try:
            result = await asyncio.wait_for(
                app.write_property(
                    address=self.config.target_address,
                    objid=object_id,
                    prop=property_name,
                    value=_coerce_bacnet_write_value(value),
                    priority=priority,
                ),
                timeout=self.config.timeout_seconds,
            )
            if result is not None:
                raise RuntimeError(f"write_property returned non-ack response: {result}")

            return {
                "status": "ok",
                "operation": "write_property",
                "object_id": object_id,
                "property": property_name,
                "target_address": self.config.target_address,
                "value": _to_jsonable(value),
                "priority": priority,
                "message": "Write completed.",
                "audit": audit,
            }
        finally:
            app.close()

    def who_is(self) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("who_is")

        return self._execute_with_retries(
            operation="who_is",
            call=lambda: _run_coro_blocking(self._who_is_async()),
        )

    def read_property(self, object_id: str, property_name: str) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("read_property")

        return self._execute_with_retries(
            operation="read_property",
            call=lambda: _run_coro_blocking(self._read_property_async(object_id, property_name)),
        )

    def write_property(
        self,
        object_id: str,
        property_name: str,
        value: str | float | int,
        priority: int | None = None,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("write_property")

        if "," not in object_id:
            raise ValueError("object_id must look like 'analog-value,1'.")
        if not property_name.strip():
            raise ValueError("property_name cannot be empty.")
        effective_priority = priority if priority is not None else self.config.write_priority_default
        if effective_priority is not None and not (1 <= effective_priority <= 16):
            raise ValueError("priority must be between 1 and 16.")

        return self._execute_with_retries(
            operation="write_property",
            call=lambda: _run_coro_blocking(
                self._write_property_async(
                    object_id=object_id,
                    property_name=property_name,
                    value=value,
                    priority=effective_priority,
                )
            ),
        )

    def read_trend(
        self,
        trend_object_id: str,
        limit: int = 100,
        window_minutes: int | None = None,
        source_object_id: str | None = None,
        source_property: str = "present-value",
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("read_trend")

        if "," not in trend_object_id:
            raise ValueError("trend_object_id must look like 'trend-log,1'.")
        if limit < 1:
            raise ValueError("limit must be >= 1.")
        if window_minutes is not None and window_minutes < 1:
            raise ValueError("window_minutes must be >= 1.")
        if source_object_id is not None and "," not in source_object_id:
            raise ValueError("source_object_id must look like 'analog-input,1'.")
        if not source_property.strip():
            raise ValueError("source_property cannot be empty.")

        return self._execute_with_retries(
            operation="read_trend",
            call=lambda: _run_coro_blocking(
                self._read_trend_async(
                    trend_object_id=trend_object_id,
                    limit=limit,
                    window_minutes=window_minutes,
                    source_object_id=source_object_id,
                    source_property=source_property,
                )
            ),
        )

    def read_schedule(self, schedule_object_id: str) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("read_schedule")

        if "," not in schedule_object_id:
            raise ValueError("schedule_object_id must look like 'schedule,1'.")

        return self._execute_with_retries(
            operation="read_schedule",
            call=lambda: _run_coro_blocking(self._read_schedule_async(schedule_object_id=schedule_object_id)),
        )

    def get_ip_adapter_mac(
        self,
        ip_address: str | None = None,
        target_address: str | None = None,
        probe: bool = True,
    ) -> dict[str, Any]:
        resolved_ip = (ip_address or "").strip() or _ip_from_target_address(target_address) or _ip_from_target_address(
            self.config.target_address
        )
        if not resolved_ip:
            return {
                "status": "error",
                "operation": "get_ip_adapter_mac",
                "message": "No IP address provided. Set ip_address or target_address.",
            }

        first_table = _read_neighbor_table()
        candidates = _extract_mac_candidates_from_neighbors(first_table, resolved_ip)

        if not candidates and probe:
            _probe_ip_address(resolved_ip)
            second_table = _read_neighbor_table()
            candidates = _extract_mac_candidates_from_neighbors(second_table, resolved_ip)

        if not candidates:
            return {
                "status": "error",
                "operation": "get_ip_adapter_mac",
                "ip_address": resolved_ip,
                "message": (
                    "No adapter MAC entry found in neighbor table for the target IP. "
                    "Ensure the device is reachable and retry with probe=true."
                ),
            }

        return {
            "status": "ok",
            "operation": "get_ip_adapter_mac",
            "ip_address": resolved_ip,
            "mac_address": candidates[0],
            "mac_candidates": candidates,
            "duplicate_entries": len(candidates) > 1,
            "message": "IP adapter MAC resolved from neighbor table.",
        }
