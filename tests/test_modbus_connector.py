from __future__ import annotations

from mcp4bas.modbus.connector import ModbusConfig, ModbusConnector


class _OkResponse:
    def __init__(self, registers=None, error: bool = False) -> None:
        self.registers = registers or []
        self._error = error

    def isError(self) -> bool:
        return self._error


class _FakeClient:
    def __init__(self, connect_ok: bool = True) -> None:
        self._connect_ok = connect_ok

    def connect(self) -> bool:
        return self._connect_ok

    def close(self) -> None:
        return None

    def read_holding_registers(self, address: int, *, count: int, device_id: int):
        return _OkResponse(registers=[address + i for i in range(count)])

    def read_input_registers(self, address: int, *, count: int, device_id: int):
        return _OkResponse(registers=[200 + address + i for i in range(count)])

    def write_register(self, address: int, value: int, *, device_id: int):
        return _OkResponse()

    def write_coil(self, address: int, value: bool, *, device_id: int):
        return _OkResponse()


def test_modbus_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("MODBUS_ENABLED", "true")
    monkeypatch.setenv("MODBUS_HOST", "192.168.1.40")
    monkeypatch.setenv("MODBUS_PORT", "1502")
    monkeypatch.setenv("MODBUS_UNIT_ID", "3")
    monkeypatch.setenv("MODBUS_TIMEOUT_SECONDS", "1.2")
    monkeypatch.setenv("MODBUS_RETRIES", "2")
    monkeypatch.setenv("MODBUS_WRITE_ENABLED", "true")

    config = ModbusConfig.from_env()

    assert config.enabled is True
    assert config.host == "192.168.1.40"
    assert config.port == 1502
    assert config.unit_id == 3
    assert config.timeout_seconds == 1.2
    assert config.retries == 2
    assert config.write_enabled is True


def test_modbus_read_registers_holding() -> None:
    connector = ModbusConnector(
        config=ModbusConfig(enabled=True, host="192.168.1.40", port=502, unit_id=1),
        client_factory=lambda cfg: _FakeClient(connect_ok=True),
    )

    result = connector.read_registers(register_type="holding", address=10, count=3)
    assert result["status"] == "ok"
    assert result["protocol"] == "modbus"
    assert result["values"] == [10, 11, 12]


def test_modbus_read_registers_input() -> None:
    connector = ModbusConnector(
        config=ModbusConfig(enabled=True, host="192.168.1.40", port=502, unit_id=1),
        client_factory=lambda cfg: _FakeClient(connect_ok=True),
    )

    result = connector.read_registers(register_type="input", address=5, count=2)
    assert result["status"] == "ok"
    assert result["values"] == [205, 206]


def test_modbus_write_guarded() -> None:
    connector = ModbusConnector(
        config=ModbusConfig(enabled=True, write_enabled=False, operation_mode="write-enabled"),
        client_factory=lambda cfg: _FakeClient(connect_ok=True),
    )

    result = connector.write_register(address=1, value=7)
    assert result["status"] == "error"
    assert "blocked" in result["message"].lower()


def test_modbus_write_allowlist_block() -> None:
    connector = ModbusConnector(
        config=ModbusConfig(
            enabled=True,
            operation_mode="write-enabled",
            write_enabled=True,
            write_allowlist={("register", 5)},
        ),
        client_factory=lambda cfg: _FakeClient(connect_ok=True),
    )

    result = connector.write_register(address=10, value=1)
    assert result["status"] == "error"
    assert "allowlist" in result["message"].lower()


def test_modbus_write_dry_run() -> None:
    connector = ModbusConnector(
        config=ModbusConfig(
            enabled=True,
            operation_mode="write-enabled",
            write_enabled=True,
            dry_run=True,
            write_allowlist={("coil", 7)},
        ),
        client_factory=lambda cfg: _FakeClient(connect_ok=True),
    )

    result = connector.write_coil(address=7, value=True)
    assert result["status"] == "ok"
    assert "dry-run" in result["message"].lower()
    assert result["audit"]["protocol"] == "modbus"
