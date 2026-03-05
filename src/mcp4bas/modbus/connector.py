from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pymodbus.client import ModbusTcpClient


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_write_allowlist(raw: str | None) -> set[tuple[str, int]]:
    if not raw:
        return set()

    allowed: set[tuple[str, int]] = set()
    for entry in raw.split(";"):
        token = entry.strip()
        if not token or ":" not in token:
            continue
        write_type, address = token.split(":", 1)
        write_type_normalized = write_type.strip().lower()
        if write_type_normalized not in {"register", "coil"}:
            continue
        try:
            allowed.add((write_type_normalized, int(address.strip())))
        except ValueError:
            continue
    return allowed


def _parse_operation_mode(raw: str | None) -> Literal["read-only", "write-enabled"]:
    value = (raw or "read-only").strip().lower()
    if value == "write-enabled":
        return "write-enabled"
    return "read-only"


@dataclass
class ModbusConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 502
    unit_id: int = 1
    timeout_seconds: float = 3.0
    retries: int = 1
    write_enabled: bool = False
    operation_mode: Literal["read-only", "write-enabled"] = "read-only"
    dry_run: bool = False
    write_allowlist: set[tuple[str, int]] = field(default_factory=set)

    @classmethod
    def from_env(cls) -> ModbusConfig:
        return cls(
            enabled=_env_bool("MODBUS_ENABLED", False),
            host=os.getenv("MODBUS_HOST", "127.0.0.1"),
            port=int(os.getenv("MODBUS_PORT", "502")),
            unit_id=int(os.getenv("MODBUS_UNIT_ID", "1")),
            timeout_seconds=float(os.getenv("MODBUS_TIMEOUT_SECONDS", "3.0")),
            retries=max(0, int(os.getenv("MODBUS_RETRIES", "1"))),
            write_enabled=_env_bool("MODBUS_WRITE_ENABLED", False),
            operation_mode=_parse_operation_mode(os.getenv("BAS_OPERATION_MODE")),
            dry_run=_env_bool("BAS_DRY_RUN", False),
            write_allowlist=_parse_write_allowlist(os.getenv("MODBUS_WRITE_ALLOWLIST")),
        )


@dataclass
class ModbusConnector:
    config: ModbusConfig
    client_factory: Callable[[ModbusConfig], ModbusTcpClient] | None = None

    @classmethod
    def from_env(cls) -> ModbusConnector:
        return cls(config=ModbusConfig.from_env())

    def _create_client(self) -> ModbusTcpClient:
        if self.client_factory:
            return self.client_factory(self.config)
        return ModbusTcpClient(
            host=self.config.host,
            port=self.config.port,
            timeout=self.config.timeout_seconds,
        )

    def _disabled_message(self, operation: str) -> dict[str, Any]:
        return {
            "status": "error",
            "protocol": "modbus",
            "operation": operation,
            "target": f"{self.config.host}:{self.config.port}",
            "message": (
                "Modbus integration is disabled. Set MODBUS_ENABLED=true and configure "
                "MODBUS_HOST/MODBUS_PORT before running live operations."
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
            "protocol": "modbus",
            "operation": operation,
            "mode": self.config.operation_mode,
            "dry_run": self.config.dry_run,
            "allowed": allowed,
            "reason": reason,
            "target": f"{self.config.host}:{self.config.port}",
            "request": request,
        }

    def _check_write_policy(self, write_type: Literal["register", "coil"], address: int) -> tuple[bool, str]:
        if self.config.operation_mode != "write-enabled":
            return False, "BAS_OPERATION_MODE is read-only"
        if not self.config.write_enabled:
            return False, "MODBUS_WRITE_ENABLED is false"
        if self.config.write_allowlist and (write_type, address) not in self.config.write_allowlist:
            return False, "Register/coil not present in MODBUS_WRITE_ALLOWLIST"
        return True, "allowed"

    def _execute_with_retries(self, operation: str, call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        attempts = self.config.retries + 1
        last_exception: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return call()
            except Exception as exc:
                last_exception = exc

            if attempt < attempts:
                time.sleep(min(0.25 * attempt, 1.0))

        return {
            "status": "error",
            "protocol": "modbus",
            "operation": operation,
            "target": f"{self.config.host}:{self.config.port}",
            "message": (
                f"Modbus {operation} failed after {attempts} attempts. "
                f"timeout={self.config.timeout_seconds}s retries={self.config.retries}. "
                f"Last error: {last_exception}"
            ),
            "attempts": attempts,
        }

    def read_registers(
        self,
        register_type: Literal["holding", "input"],
        address: int,
        count: int = 1,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("read_registers")

        if count < 1:
            raise ValueError("count must be >= 1")

        def _do_read() -> dict[str, Any]:
            client = self._create_client()
            try:
                if not client.connect():
                    raise ConnectionError("Unable to connect to Modbus TCP server.")

                if register_type == "holding":
                    response = client.read_holding_registers(
                        address=address,
                        count=count,
                        device_id=self.config.unit_id,
                    )
                elif register_type == "input":
                    response = client.read_input_registers(
                        address=address,
                        count=count,
                        device_id=self.config.unit_id,
                    )
                else:
                    raise ValueError("register_type must be 'holding' or 'input'.")

                if response.isError():
                    return {
                        "status": "error",
                        "protocol": "modbus",
                        "operation": "read_registers",
                        "target": f"{self.config.host}:{self.config.port}",
                        "message": f"Device returned Modbus error: {response}",
                    }

                values = [int(value) for value in getattr(response, "registers", [])]
                return {
                    "status": "ok",
                    "protocol": "modbus",
                    "operation": "read_registers",
                    "target": f"{self.config.host}:{self.config.port}",
                    "unit_id": self.config.unit_id,
                    "register_type": register_type,
                    "address": address,
                    "count": count,
                    "values": values,
                    "message": "Read completed.",
                }
            finally:
                client.close()

        return self._execute_with_retries(operation="read_registers", call=_do_read)

    def write_register(self, address: int, value: int) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("write_register")
        allowed, reason = self._check_write_policy(write_type="register", address=address)
        audit = self._build_audit(
            operation="write_register",
            allowed=allowed,
            reason=reason,
            request={"address": address, "value": value},
        )
        if not allowed:
            return {
                "status": "error",
                "protocol": "modbus",
                "operation": "write_register",
                "target": f"{self.config.host}:{self.config.port}",
                "message": f"Modbus write blocked: {reason}.",
                "audit": audit,
            }

        if self.config.dry_run:
            return {
                "status": "ok",
                "protocol": "modbus",
                "operation": "write_register",
                "target": f"{self.config.host}:{self.config.port}",
                "unit_id": self.config.unit_id,
                "address": address,
                "value": value,
                "message": "Dry-run enabled; write not sent.",
                "audit": audit,
            }

        def _do_write() -> dict[str, Any]:
            client = self._create_client()
            try:
                if not client.connect():
                    raise ConnectionError("Unable to connect to Modbus TCP server.")

                response = client.write_register(
                    address=address,
                    value=value,
                    device_id=self.config.unit_id,
                )
                if response.isError():
                    return {
                        "status": "error",
                        "protocol": "modbus",
                        "operation": "write_register",
                        "target": f"{self.config.host}:{self.config.port}",
                        "message": f"Device returned Modbus error: {response}",
                    }

                return {
                    "status": "ok",
                    "protocol": "modbus",
                    "operation": "write_register",
                    "target": f"{self.config.host}:{self.config.port}",
                    "unit_id": self.config.unit_id,
                    "address": address,
                    "value": value,
                    "message": "Write completed.",
                    "audit": audit,
                }
            finally:
                client.close()

        return self._execute_with_retries(operation="write_register", call=_do_write)

    def write_coil(self, address: int, value: bool) -> dict[str, Any]:
        if not self.config.enabled:
            return self._disabled_message("write_coil")
        allowed, reason = self._check_write_policy(write_type="coil", address=address)
        audit = self._build_audit(
            operation="write_coil",
            allowed=allowed,
            reason=reason,
            request={"address": address, "value": value},
        )
        if not allowed:
            return {
                "status": "error",
                "protocol": "modbus",
                "operation": "write_coil",
                "target": f"{self.config.host}:{self.config.port}",
                "message": f"Modbus write blocked: {reason}.",
                "audit": audit,
            }

        if self.config.dry_run:
            return {
                "status": "ok",
                "protocol": "modbus",
                "operation": "write_coil",
                "target": f"{self.config.host}:{self.config.port}",
                "unit_id": self.config.unit_id,
                "address": address,
                "value": value,
                "message": "Dry-run enabled; write not sent.",
                "audit": audit,
            }

        def _do_write() -> dict[str, Any]:
            client = self._create_client()
            try:
                if not client.connect():
                    raise ConnectionError("Unable to connect to Modbus TCP server.")

                response = client.write_coil(
                    address=address,
                    value=value,
                    device_id=self.config.unit_id,
                )
                if response.isError():
                    return {
                        "status": "error",
                        "protocol": "modbus",
                        "operation": "write_coil",
                        "target": f"{self.config.host}:{self.config.port}",
                        "message": f"Device returned Modbus error: {response}",
                    }

                return {
                    "status": "ok",
                    "protocol": "modbus",
                    "operation": "write_coil",
                    "target": f"{self.config.host}:{self.config.port}",
                    "unit_id": self.config.unit_id,
                    "address": address,
                    "value": value,
                    "message": "Write completed.",
                    "audit": audit,
                }
            finally:
                client.close()

        return self._execute_with_retries(operation="write_coil", call=_do_write)
