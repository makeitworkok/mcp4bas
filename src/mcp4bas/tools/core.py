from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from mcp4bas.bacnet import BacnetConnector
from mcp4bas.haystack import HaystackConnector
from mcp4bas.mqtt import MqttConnector
from mcp4bas.modbus import ModbusConnector
from mcp4bas.snmp import SnmpConnector


class ToolError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ToolErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    tool: str | None = None
    error: ToolError


class WhoIsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadPropertyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_id: str
    property: str = "present-value"

    @field_validator("object_id")
    @classmethod
    def validate_object_id(cls, value: str) -> str:
        if "," not in value:
            raise ValueError("object_id must look like 'analog-value,1'.")
        return value


class WritePropertyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_id: str
    property: str
    value: str | float | int
    priority: int | None = None

    @field_validator("object_id")
    @classmethod
    def validate_object_id(cls, value: str) -> str:
        if "," not in value:
            raise ValueError("object_id must look like 'analog-value,1'.")
        return value

    @field_validator("property")
    @classmethod
    def validate_property(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("property cannot be empty.")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: int | None) -> int | None:
        if value is not None and not (1 <= value <= 16):
            raise ValueError("priority must be between 1 and 16.")
        return value


class WhoIsResponse(BaseModel):
    status: Literal["ok"] = "ok"
    tool: Literal["who_is"] = "who_is"
    protocol: Literal["bacnet"] = "bacnet"
    operation: Literal["who_is"] = "who_is"
    target: str | None = None
    count: int = 0
    devices: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class ReadPropertyResponse(BaseModel):
    status: Literal["ok"] = "ok"
    tool: Literal["read_property"] = "read_property"
    protocol: Literal["bacnet"] = "bacnet"
    operation: Literal["read_property"] = "read_property"
    target: str | None = None
    object_id: str
    property: str
    value: Any | None = None
    message: str


class WritePropertyResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["write_property"] = "write_property"
    protocol: Literal["bacnet"] = "bacnet"
    operation: Literal["write_property"] = "write_property"
    target: str | None = None
    request: WritePropertyRequest
    audit: dict[str, Any] | None = None
    message: str


class BacnetGetTrendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trend_object_id: str
    limit: int = 100
    window_minutes: int | None = None
    source_object_id: str | None = None
    source_property: str = "present-value"

    @field_validator("trend_object_id")
    @classmethod
    def validate_trend_object_id(cls, value: str) -> str:
        if "," not in value:
            raise ValueError("trend_object_id must look like 'trend-log,1'.")
        return value

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("limit must be >= 1.")
        return value

    @field_validator("window_minutes")
    @classmethod
    def validate_window_minutes(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("window_minutes must be >= 1.")
        return value

    @field_validator("source_object_id")
    @classmethod
    def validate_source_object_id(cls, value: str | None) -> str | None:
        if value is not None and "," not in value:
            raise ValueError("source_object_id must look like 'analog-input,1'.")
        return value

    @field_validator("source_property")
    @classmethod
    def validate_source_property(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_property cannot be empty.")
        return value


class BacnetGetTrendResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["bacnet_get_trend"] = "bacnet_get_trend"
    protocol: Literal["bacnet"] = "bacnet"
    operation: Literal["read_trend"] = "read_trend"
    target: str | None = None
    request: BacnetGetTrendRequest
    count: int = 0
    entries: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    fallback_used: bool = False
    fallback_reason: str | None = None
    errors: list[str] = Field(default_factory=list)
    message: str


class BacnetGetScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_object_id: str

    @field_validator("schedule_object_id")
    @classmethod
    def validate_schedule_object_id(cls, value: str) -> str:
        if "," not in value:
            raise ValueError("schedule_object_id must look like 'schedule,1'.")
        return value


class BacnetGetScheduleResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["bacnet_get_schedule"] = "bacnet_get_schedule"
    protocol: Literal["bacnet"] = "bacnet"
    operation: Literal["read_schedule"] = "read_schedule"
    target: str | None = None
    request: BacnetGetScheduleRequest
    weekly_schedule: list[dict[str, Any]] = Field(default_factory=list)
    exception_schedule: list[dict[str, Any]] = Field(default_factory=list)
    effective_period: Any | None = None
    present_value: Any | None = None
    errors: list[str] = Field(default_factory=list)
    message: str


class BacnetGetIpAdapterMacRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip_address: str | None = None
    target_address: str | None = None
    probe: bool = True

    @model_validator(mode="after")
    def validate_source(self) -> "BacnetGetIpAdapterMacRequest":
        if (self.ip_address and self.ip_address.strip()) or (self.target_address and self.target_address.strip()):
            return self
        raise ValueError("Provide ip_address or target_address.")


class BacnetGetIpAdapterMacResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["bacnet_get_ip_adapter_mac"] = "bacnet_get_ip_adapter_mac"
    protocol: Literal["network"] = "network"
    operation: Literal["get_ip_adapter_mac"] = "get_ip_adapter_mac"
    request: BacnetGetIpAdapterMacRequest
    ip_address: str | None = None
    mac_address: str | None = None
    mac_candidates: list[str] = Field(default_factory=list)
    duplicate_entries: bool = False
    message: str


class ModbusReadRegistersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    register_type: Literal["holding", "input"]
    address: int
    count: int = 1

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: int) -> int:
        if value < 0:
            raise ValueError("address must be >= 0.")
        return value

    @field_validator("count")
    @classmethod
    def validate_count(cls, value: int) -> int:
        if value < 1:
            raise ValueError("count must be >= 1.")
        return value


class ModbusReadRegistersResponse(BaseModel):
    status: Literal["ok"] = "ok"
    tool: Literal["modbus_read_registers"] = "modbus_read_registers"
    protocol: Literal["modbus"] = "modbus"
    operation: Literal["read_registers"] = "read_registers"
    target: str
    register_type: Literal["holding", "input"]
    address: int
    count: int
    values: list[int]
    message: str


class ModbusWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    write_type: Literal["register", "coil"]
    address: int
    value: int | bool

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: int) -> int:
        if value < 0:
            raise ValueError("address must be >= 0.")
        return value


class ModbusWriteResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["modbus_write"] = "modbus_write"
    protocol: Literal["modbus"] = "modbus"
    operation: Literal["write_register", "write_coil"]
    target: str
    request: ModbusWriteRequest
    audit: dict[str, Any] | None = None
    message: str


class HaystackDiscoverPointsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = 100

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("limit must be >= 1.")
        return value


class HaystackDiscoverPointsResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["haystack_discover_points"] = "haystack_discover_points"
    protocol: Literal["haystack"] = "haystack"
    operation: Literal["discover_points"] = "discover_points"
    target: str | None = None
    count: int = 0
    points: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class HaystackGetPointMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point_id: str

    @field_validator("point_id")
    @classmethod
    def validate_point_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("point_id cannot be empty.")
        return value


class HaystackGetPointMetadataResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["haystack_get_point_metadata"] = "haystack_get_point_metadata"
    protocol: Literal["haystack"] = "haystack"
    operation: Literal["get_point_metadata"] = "get_point_metadata"
    target: str | None = None
    point_id: str
    metadata: dict[str, Any] | None = None
    message: str


class MqttIngestMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    payload: dict[str, Any]
    source: str = "manual"

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("topic cannot be empty.")
        return value


class MqttIngestMessageResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["mqtt_ingest_message"] = "mqtt_ingest_message"
    protocol: Literal["mqtt"] = "mqtt"
    operation: Literal["ingest_message"] = "ingest_message"
    target: str | None = None
    record: dict[str, Any] | None = None
    message: str


class MqttGetLatestPointsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site: str | None = None
    equip: str | None = None
    limit: int = 100

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("limit must be >= 1.")
        return value


class MqttGetLatestPointsResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["mqtt_get_latest_points"] = "mqtt_get_latest_points"
    protocol: Literal["mqtt"] = "mqtt"
    operation: Literal["get_latest_points"] = "get_latest_points"
    target: str | None = None
    count: int = 0
    points: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class MqttPublishMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    payload: dict[str, Any]
    source: str = "mcp_tool"

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("topic cannot be empty.")
        return value


class MqttPublishMessageResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["mqtt_publish_message"] = "mqtt_publish_message"
    protocol: Literal["mqtt"] = "mqtt"
    operation: Literal["publish_message"] = "publish_message"
    target: str | None = None
    record: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    message: str


class SnmpGetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oid: str
    host: str | None = None

    @field_validator("oid")
    @classmethod
    def validate_oid(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("oid cannot be empty.")
        return value


class SnmpGetResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["snmp_get"] = "snmp_get"
    protocol: Literal["snmp"] = "snmp"
    operation: Literal["snmp_get"] = "snmp_get"
    target: str | None = None
    request: SnmpGetRequest
    oid: str
    value: Any | None = None
    message: str


class SnmpWalkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oid_prefix: str
    host: str | None = None
    limit: int = 100

    @field_validator("oid_prefix")
    @classmethod
    def validate_oid_prefix(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("oid_prefix cannot be empty.")
        return value

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("limit must be >= 1.")
        return value


class SnmpWalkResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["snmp_walk"] = "snmp_walk"
    protocol: Literal["snmp"] = "snmp"
    operation: Literal["snmp_walk"] = "snmp_walk"
    target: str | None = None
    request: SnmpWalkRequest
    count: int = 0
    entries: list[dict[str, Any]] = Field(default_factory=list)
    message: str


class SnmpDeviceHealthSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    interface_limit: int = 20

    @field_validator("interface_limit")
    @classmethod
    def validate_interface_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("interface_limit must be >= 1.")
        return value


class SnmpDeviceHealthSummaryResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    tool: Literal["snmp_device_health_summary"] = "snmp_device_health_summary"
    protocol: Literal["snmp"] = "snmp"
    operation: Literal["snmp_device_health_summary"] = "snmp_device_health_summary"
    target: str | None = None
    request: SnmpDeviceHealthSummaryRequest
    uptime_ticks: int | float | str | None = None
    interfaces: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    elapsed_ms: float | None = None
    message: str


ToolHandler = Callable[[BaseModel], BaseModel]

_BACNET_CONNECTOR: BacnetConnector | None = None
_MODBUS_CONNECTOR: ModbusConnector | None = None
_HAYSTACK_CONNECTOR: HaystackConnector | None = None
_MQTT_CONNECTOR: MqttConnector | None = None
_SNMP_CONNECTOR: SnmpConnector | None = None


def _get_bacnet_connector() -> BacnetConnector:
    if _BACNET_CONNECTOR is not None:
        return _BACNET_CONNECTOR
    return BacnetConnector.from_env()


def _get_modbus_connector() -> ModbusConnector:
    if _MODBUS_CONNECTOR is not None:
        return _MODBUS_CONNECTOR
    return ModbusConnector.from_env()


def _get_haystack_connector() -> HaystackConnector:
    if _HAYSTACK_CONNECTOR is not None:
        return _HAYSTACK_CONNECTOR
    return HaystackConnector.from_env()


def _get_mqtt_connector() -> MqttConnector:
    global _MQTT_CONNECTOR
    if _MQTT_CONNECTOR is not None:
        return _MQTT_CONNECTOR
    _MQTT_CONNECTOR = MqttConnector.from_env()
    return _MQTT_CONNECTOR


def _get_snmp_connector() -> SnmpConnector:
    global _SNMP_CONNECTOR
    if _SNMP_CONNECTOR is not None:
        return _SNMP_CONNECTOR
    _SNMP_CONNECTOR = SnmpConnector.from_env()
    return _SNMP_CONNECTOR


@dataclass
class Tool:
    name: str
    description: str
    request_model: type[BaseModel]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": tool.name, "description": tool.description}
            for tool in self._tools.values()
        ]

    def call(self, name: str | None, arguments: dict[str, Any]) -> dict[str, Any]:
        if not name or name not in self._tools:
            return ToolErrorResponse(
                tool=name,
                error=ToolError(
                    code="unknown_tool",
                    message=f"Unknown tool: {name}",
                ),
            ).model_dump(mode="json")

        tool = self._tools[name]
        try:
            request = tool.request_model.model_validate(arguments)
            result = tool.handler(request)
            return result.model_dump(mode="json")
        except ValidationError as exc:
            validation_errors: list[dict[str, Any]] = []
            for error in exc.errors(include_url=False):
                item = dict(error)
                if "ctx" in item and isinstance(item["ctx"], dict) and "error" in item["ctx"]:
                    item["ctx"] = {
                        **item["ctx"],
                        "error": str(item["ctx"]["error"]),
                    }
                validation_errors.append(item)

            return ToolErrorResponse(
                tool=name,
                error=ToolError(
                    code="invalid_arguments",
                    message="Invalid tool arguments",
                    details={"validation_errors": validation_errors},
                ),
            ).model_dump(mode="json")
        except Exception as exc:
            return ToolErrorResponse(
                tool=name,
                error=ToolError(
                    code="internal_error",
                    message=str(exc),
                ),
            ).model_dump(mode="json")


def _who_is_tool(arguments: BaseModel) -> WhoIsResponse:
    _ = arguments
    result = _get_bacnet_connector().who_is()
    if result.get("status") != "ok":
        raise RuntimeError(result.get("message", "who_is failed"))

    return WhoIsResponse(
        target=result.get("target_address"),
        count=int(result.get("count", 0)),
        devices=list(result.get("devices", [])),
        message=str(result.get("message", "Discovery completed.")),
    )


def _read_property_tool(arguments: BaseModel) -> ReadPropertyResponse:
    request = ReadPropertyRequest.model_validate(arguments.model_dump())
    result = _get_bacnet_connector().read_property(
        object_id=request.object_id,
        property_name=request.property,
    )
    if result.get("status") != "ok":
        raise RuntimeError(result.get("message", "read_property failed"))

    return ReadPropertyResponse(
        target=result.get("target_address"),
        object_id=request.object_id,
        property=request.property,
        value=result.get("value"),
        message=str(result.get("message", "Read completed.")),
    )


def _write_property_tool(arguments: BaseModel) -> WritePropertyResponse:
    request = WritePropertyRequest.model_validate(arguments.model_dump())
    result = _get_bacnet_connector().write_property(
        object_id=request.object_id,
        property_name=request.property,
        value=request.value,
        priority=request.priority,
    )
    return WritePropertyResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target_address"),
        request=request,
        audit=result.get("audit"),
        message=str(result.get("message", "Write completed.")),
    )


def _bacnet_get_trend_tool(arguments: BaseModel) -> BacnetGetTrendResponse:
    request = BacnetGetTrendRequest.model_validate(arguments.model_dump())
    result = _get_bacnet_connector().read_trend(
        trend_object_id=request.trend_object_id,
        limit=request.limit,
        window_minutes=request.window_minutes,
        source_object_id=request.source_object_id,
        source_property=request.source_property,
    )
    return BacnetGetTrendResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target_address"),
        request=request,
        count=int(result.get("count", 0)),
        entries=list(result.get("entries", [])),
        metadata=dict(result.get("metadata", {})),
        fallback_used=bool(result.get("fallback_used", False)),
        fallback_reason=result.get("fallback_reason"),
        errors=[str(error) for error in result.get("errors", [])],
        message=str(result.get("message", "Trend retrieval completed.")),
    )


def _bacnet_get_schedule_tool(arguments: BaseModel) -> BacnetGetScheduleResponse:
    request = BacnetGetScheduleRequest.model_validate(arguments.model_dump())
    result = _get_bacnet_connector().read_schedule(schedule_object_id=request.schedule_object_id)
    return BacnetGetScheduleResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target_address"),
        request=request,
        weekly_schedule=list(result.get("weekly_schedule", [])),
        exception_schedule=list(result.get("exception_schedule", [])),
        effective_period=result.get("effective_period"),
        present_value=result.get("present_value"),
        errors=[str(error) for error in result.get("errors", [])],
        message=str(result.get("message", "Schedule retrieval completed.")),
    )


def _bacnet_get_ip_adapter_mac_tool(arguments: BaseModel) -> BacnetGetIpAdapterMacResponse:
    request = BacnetGetIpAdapterMacRequest.model_validate(arguments.model_dump())
    result = _get_bacnet_connector().get_ip_adapter_mac(
        ip_address=request.ip_address,
        target_address=request.target_address,
        probe=request.probe,
    )
    return BacnetGetIpAdapterMacResponse(
        status="ok" if result.get("status") == "ok" else "error",
        request=request,
        ip_address=result.get("ip_address"),
        mac_address=result.get("mac_address"),
        mac_candidates=[str(value) for value in result.get("mac_candidates", [])],
        duplicate_entries=bool(result.get("duplicate_entries", False)),
        message=str(result.get("message", "MAC lookup completed.")),
    )


def _modbus_read_registers_tool(arguments: BaseModel) -> ModbusReadRegistersResponse:
    request = ModbusReadRegistersRequest.model_validate(arguments.model_dump())
    result = _get_modbus_connector().read_registers(
        register_type=request.register_type,
        address=request.address,
        count=request.count,
    )
    if result.get("status") != "ok":
        raise RuntimeError(result.get("message", "modbus_read_registers failed"))

    return ModbusReadRegistersResponse(
        target=str(result.get("target", "")),
        register_type=request.register_type,
        address=request.address,
        count=request.count,
        values=[int(v) for v in result.get("values", [])],
        message=str(result.get("message", "Read completed.")),
    )


def _modbus_write_tool(arguments: BaseModel) -> ModbusWriteResponse:
    request = ModbusWriteRequest.model_validate(arguments.model_dump())

    if request.write_type == "register":
        result = _get_modbus_connector().write_register(address=request.address, value=int(request.value))
    else:
        result = _get_modbus_connector().write_coil(address=request.address, value=bool(request.value))

    return ModbusWriteResponse(
        status="ok" if result.get("status") == "ok" else "error",
        operation=("write_register" if request.write_type == "register" else "write_coil"),
        target=str(result.get("target", "")),
        request=request,
        audit=result.get("audit"),
        message=str(result.get("message", "Write completed.")),
    )


def _haystack_discover_points_tool(arguments: BaseModel) -> HaystackDiscoverPointsResponse:
    request = HaystackDiscoverPointsRequest.model_validate(arguments.model_dump())
    result = _get_haystack_connector().discover_points(limit=request.limit)
    return HaystackDiscoverPointsResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target"),
        count=int(result.get("count", 0)),
        points=list(result.get("points", [])),
        message=str(result.get("message", "Discovery completed.")),
    )


def _haystack_get_point_metadata_tool(arguments: BaseModel) -> HaystackGetPointMetadataResponse:
    request = HaystackGetPointMetadataRequest.model_validate(arguments.model_dump())
    result = _get_haystack_connector().get_point_metadata(point_id=request.point_id)
    return HaystackGetPointMetadataResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target"),
        point_id=request.point_id,
        metadata=result.get("metadata"),
        message=str(result.get("message", "Point metadata fetched.")),
    )


def _mqtt_ingest_message_tool(arguments: BaseModel) -> MqttIngestMessageResponse:
    request = MqttIngestMessageRequest.model_validate(arguments.model_dump())
    result = _get_mqtt_connector().ingest_message(
        topic=request.topic,
        payload=request.payload,
        source=request.source,
    )
    return MqttIngestMessageResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target"),
        record=result.get("record"),
        message=str(result.get("message", "MQTT message ingested.")),
    )


def _mqtt_get_latest_points_tool(arguments: BaseModel) -> MqttGetLatestPointsResponse:
    request = MqttGetLatestPointsRequest.model_validate(arguments.model_dump())
    result = _get_mqtt_connector().get_latest_points(
        site=request.site,
        equip=request.equip,
        limit=request.limit,
    )
    return MqttGetLatestPointsResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target"),
        count=int(result.get("count", 0)),
        points=list(result.get("points", [])),
        message=str(result.get("message", "Returned MQTT points.")),
    )


def _mqtt_publish_message_tool(arguments: BaseModel) -> MqttPublishMessageResponse:
    request = MqttPublishMessageRequest.model_validate(arguments.model_dump())
    result = _get_mqtt_connector().publish_message(
        topic=request.topic,
        payload=request.payload,
        source=request.source,
    )
    return MqttPublishMessageResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target"),
        record=result.get("record"),
        audit=result.get("audit"),
        message=str(result.get("message", "MQTT publish completed.")),
    )


def _snmp_get_tool(arguments: BaseModel) -> SnmpGetResponse:
    request = SnmpGetRequest.model_validate(arguments.model_dump())
    result = _get_snmp_connector().snmp_get(oid=request.oid, host=request.host)
    return SnmpGetResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target"),
        request=request,
        oid=request.oid,
        value=result.get("value"),
        message=str(result.get("message", "SNMP GET completed.")),
    )


def _snmp_walk_tool(arguments: BaseModel) -> SnmpWalkResponse:
    request = SnmpWalkRequest.model_validate(arguments.model_dump())
    result = _get_snmp_connector().snmp_walk(
        oid_prefix=request.oid_prefix,
        host=request.host,
        limit=request.limit,
    )
    return SnmpWalkResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target"),
        request=request,
        count=int(result.get("count", 0)),
        entries=list(result.get("entries", [])),
        message=str(result.get("message", "SNMP WALK completed.")),
    )


def _snmp_device_health_summary_tool(arguments: BaseModel) -> SnmpDeviceHealthSummaryResponse:
    request = SnmpDeviceHealthSummaryRequest.model_validate(arguments.model_dump())
    result = _get_snmp_connector().snmp_device_health_summary(
        host=request.host,
        interface_limit=request.interface_limit,
    )
    elapsed_raw = result.get("elapsed_ms")
    elapsed_ms: float | None = None
    if isinstance(elapsed_raw, (int, float)):
        elapsed_ms = float(elapsed_raw)
    return SnmpDeviceHealthSummaryResponse(
        status="ok" if result.get("status") == "ok" else "error",
        target=result.get("target"),
        request=request,
        uptime_ticks=result.get("uptime_ticks"),
        interfaces=list(result.get("interfaces", [])),
        warnings=[str(item) for item in result.get("warnings", [])],
        elapsed_ms=elapsed_ms,
        message=str(result.get("message", "SNMP device health summary completed.")),
    )


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="who_is",
            description="Discover BACnet devices on network",
            request_model=WhoIsRequest,
            handler=_who_is_tool,
        )
    )
    registry.register(
        Tool(
            name="read_property",
            description="Read a BACnet object property",
            request_model=ReadPropertyRequest,
            handler=_read_property_tool,
        )
    )
    registry.register(
        Tool(
            name="write_property",
            description="Write a BACnet object property",
            request_model=WritePropertyRequest,
            handler=_write_property_tool,
        )
    )
    registry.register(
        Tool(
            name="bacnet_get_trend",
            description="Read BACnet trend log entries with optional window and fallback",
            request_model=BacnetGetTrendRequest,
            handler=_bacnet_get_trend_tool,
        )
    )
    registry.register(
        Tool(
            name="bacnet_get_schedule",
            description="Read BACnet weekly and exception schedule details",
            request_model=BacnetGetScheduleRequest,
            handler=_bacnet_get_schedule_tool,
        )
    )
    registry.register(
        Tool(
            name="bacnet_get_ip_adapter_mac",
            description="Resolve adapter MAC address for an IP-connected BAS target",
            request_model=BacnetGetIpAdapterMacRequest,
            handler=_bacnet_get_ip_adapter_mac_tool,
        )
    )
    registry.register(
        Tool(
            name="modbus_read_registers",
            description="Read Modbus holding or input registers",
            request_model=ModbusReadRegistersRequest,
            handler=_modbus_read_registers_tool,
        )
    )
    registry.register(
        Tool(
            name="modbus_write",
            description="Write Modbus register or coil",
            request_model=ModbusWriteRequest,
            handler=_modbus_write_tool,
        )
    )
    registry.register(
        Tool(
            name="haystack_discover_points",
            description="Discover Haystack points with tag validation metadata",
            request_model=HaystackDiscoverPointsRequest,
            handler=_haystack_discover_points_tool,
        )
    )
    registry.register(
        Tool(
            name="haystack_get_point_metadata",
            description="Fetch Haystack point metadata with tag validation",
            request_model=HaystackGetPointMetadataRequest,
            handler=_haystack_get_point_metadata_tool,
        )
    )
    registry.register(
        Tool(
            name="mqtt_ingest_message",
            description="Ingest MQTT telemetry payload for normalization and validation",
            request_model=MqttIngestMessageRequest,
            handler=_mqtt_ingest_message_tool,
        )
    )
    registry.register(
        Tool(
            name="mqtt_get_latest_points",
            description="Get latest normalized MQTT telemetry points",
            request_model=MqttGetLatestPointsRequest,
            handler=_mqtt_get_latest_points_tool,
        )
    )
    registry.register(
        Tool(
            name="mqtt_publish_message",
            description="Publish MQTT payload with write safety controls and audit",
            request_model=MqttPublishMessageRequest,
            handler=_mqtt_publish_message_tool,
        )
    )
    registry.register(
        Tool(
            name="snmp_get",
            description="Read a single SNMP OID from target host",
            request_model=SnmpGetRequest,
            handler=_snmp_get_tool,
        )
    )
    registry.register(
        Tool(
            name="snmp_walk",
            description="Read SNMP OID subtree entries with output limit",
            request_model=SnmpWalkRequest,
            handler=_snmp_walk_tool,
        )
    )
    registry.register(
        Tool(
            name="snmp_device_health_summary",
            description="Summarize SNMP device uptime and interface health",
            request_model=SnmpDeviceHealthSummaryRequest,
            handler=_snmp_device_health_summary_tool,
        )
    )
    return registry
