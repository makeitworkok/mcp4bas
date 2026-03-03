<a id="top"></a>

# MCP4BAS 🏢🤖

**MCP4BAS** helps AI assistants connect to building systems so teams can troubleshoot faster, operate smarter, and save energy. ⚡

🚀 **Coming soon:** deeper BACnet support, early Modbus integrations, and smarter diagnostics workflows. [See planned features ↓](#planned-features)

## Why this matters

- 🧩 Building data is often scattered across tools and vendors
- ⏱️ Troubleshooting takes too long when context is fragmented
- 🌍 Better BAS visibility can improve comfort and reduce energy waste

## What MCP4BAS aims to do

- 🔌 Connect AI workflows to BAS protocols like BACnet and Modbus
- 📡 Expand toward MQTT-based telemetry and edge integration workflows
- 🏙️ Expand toward Niagara connectivity through Haystack-friendly integration
- 🛠️ Expose safe, clear actions through MCP tools
- 📈 Support better daily operations with reusable prompts and context

<a id="planned-features"></a>

## Planned features 🗺️

- 🔎 Device discovery and point reads/writes for BACnet
- 🔁 Early Modbus support for common field integrations
- 📨 MQTT connector path for telemetry ingestion and controlled publish workflows
- 🧷 Niagara connector path using Project Haystack conventions
- 🧠 Reusable diagnostics prompts for comfort and energy issues
- 📊 Trend-aware insights to help surface anomalies faster
- 🔐 Permission-aware actions and audit-friendly control workflows

## MQTT caveat ⚠️

MQTT integrations are only as useful as their topic and payload standards. MCP4BAS will assume a defined topic convention and validated payload schema so points can be mapped reliably to site/equipment context. Therefore, MCP-side schema and quality checks for MQTT messages, with operator-visible caveats when context is incomplete.

## Niagara + Haystack caveat ⚠️

Niagara/Haystack workflows assume your site has solid Haystack tagging in place. Point quality and diagnostics quality depend heavily on consistent, meaningful tags. MCP ingestion will include tag validation checks so missing/weak tags can be flagged early (instead of silently producing low-confidence results).

[Back to top ↑](#top)

## Current status 🚧

MCP4BAS is in active development and already includes a working server foundation with early tool stubs. The next phase is deeper protocol integrations and production safety controls.

## Get involved 🙌

- ⭐ Star the project to follow progress
- 💡 Open an issue with ideas or use cases
- 🔧 Contribute with PRs as the roadmap grows

## Looking for setup details?

Technical notes, setup steps, project layout, and quickstart commands live in [NOTES.md](NOTES.md).