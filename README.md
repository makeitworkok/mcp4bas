<a id="top"></a>

# MCP4BAS 🏢🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python >=3.10](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](pyproject.toml)
[![Claude Code: Ready](https://img.shields.io/badge/Claude%20Code-Ready-7C3AED)](https://docs.anthropic.com/en/docs/claude-code/overview)
[![Code Scanning](https://github.com/makeitworkok/mcp4bas/actions/workflows/codeql.yml/badge.svg)](https://github.com/makeitworkok/mcp4bas/security/code-scanning)
[![Dependabot](https://img.shields.io/badge/dependabot-enabled-success)](https://github.com/makeitworkok/mcp4bas/network/updates)
[![Secret Scanning](https://img.shields.io/badge/secret%20scanning-enabled-success)](https://github.com/makeitworkok/mcp4bas/security/secret-scanning)

**MCP4BAS** is a Model Context Protocol (MCP) server for building automation workflows.

It provides protocol-aware tools for BACnet, Modbus, Haystack, MQTT, and SNMP with safety controls for write operations.

## Why this matters

- 🧩 Building data is often scattered across tools and vendors
- ⏱️ Troubleshooting takes too long when context is fragmented
- 🌍 Better BAS visibility can improve comfort and reduce energy waste

## What MCP4BAS does now

- 🔌 BACnet discovery, point reads/writes, trend/schedule retrieval, and IP adapter MAC lookup
- 🔁 Modbus register reads and guarded write paths
- 🏙️ Haystack point discovery + metadata fetch with tag quality scoring
- 📨 MQTT telemetry ingest/query plus controlled publish with audit envelope
- 🧪 SNMP read-only `get`, `walk`, and health summary tooling
- 🔐 Global safety controls (`read-only`/`write-enabled`, dry-run, allowlists, audit metadata)

## Tool surface (current)

### BACnet

- `who_is`
- `read_property`
- `write_property`
- `bacnet_get_trend`
- `bacnet_get_schedule`
- `bacnet_get_ip_adapter_mac`

### Modbus

- `modbus_read_registers`
- `modbus_write`

### Haystack

- `haystack_discover_points`
- `haystack_get_point_metadata`

### MQTT

- `mqtt_ingest_message`
- `mqtt_get_latest_points`
- `mqtt_publish_message`

### SNMP (read-only MVP)

- `snmp_get`
- `snmp_walk`
- `snmp_device_health_summary`

## Safety model

- Default operation is read-only.
- Writes require explicit write-enabled mode and per-protocol allowlists.
- Dry-run mode validates and audits write requests without sending them.
- Write responses include audit context (`mode`, `dry_run`, `allowed`, `reason`, `target`, `request`).

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r dev-requirements.txt
python -m mcp4bas.server --transport stdio
```

## Validation status

- Automated quality pipeline is in place (`pytest`, `mypy`, `ruff`, CI workflow).
- Live BACnet validation has been exercised for discovery, reads, controlled writes, priority write/relinquish, and rollback behavior.
- Haystack and MQTT tool paths are validated with local datasets and integration tests.
- SNMP read-only MVP is implemented with test coverage.

## MQTT caveat ⚠️

MQTT quality depends on consistent topic and payload conventions. MCP4BAS validates topic/payload completeness and returns confidence/caveat metadata when context is weak.

## Niagara + Haystack caveat ⚠️

Haystack workflows depend on tagging quality. Missing/weak/inconsistent tags reduce confidence and are surfaced in tool responses with remediation hints.

[Back to top ↑](#top)

## Roadmap

- Expand live rollout coverage for Haystack and MQTT environments.
- Extend SNMP validation against live devices.
- Continue publish-batch hardening for public release cadence.

## Get involved 🙌

- ⭐ Star the project to follow progress
- 💡 Open an issue with ideas or use cases
- 🔧 Contribute with PRs as the roadmap grows