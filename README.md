# MCP4BAS – Model Context Protocol for Building Automation Systems

An open-source MCP server that connects AI agents (Claude, etc.) to building automation networks.

🚧 **Work in Progress:** This project is actively being built — stay tuned for updates! 👀✨

## Why?

Building automation data is rich, but hard to access and act on quickly across fragmented tools and protocols.

MCP4BAS aims to bridge that gap by exposing BAS context through a standard MCP interface so AI agents can safely assist with day-to-day operations.

### Rationale

- 🧩 **Fragmented systems:** BAS teams often juggle BACnet/Modbus points, trend tools, schedules, and alarms across separate interfaces.
- ⏱️ **Slow troubleshooting:** Root-cause analysis is time-consuming when technicians must manually gather point history and equipment context.
- 🗣️ **Low accessibility:** Non-specialists struggle to query systems without deep BMS tool knowledge.
- 🔁 **Reactive workflows:** Many sites still respond after comfort or energy issues occur instead of preventing them.

### What this enables

- ⚡ Faster diagnostics with natural-language queries over live and historical BAS data
- 🌱 Better energy optimization through continuous, context-aware recommendations
- 🛠️ More effective maintenance with earlier fault signals and clearer operator guidance
- 🤖 Safer AI automation by routing actions through explicit tools, permissions, and audit-friendly interfaces

## Planned Features

- 🔌 BACnet and Modbus connectivity adapters
- 📡 Real-time sensor/actuator read-write tools
- 📈 Trend history access for analytics and insights
- 🗓️ Schedule and setpoint management
- 🔐 Secure auth and role-based access controls

## Contributing

🤝 Contributions are welcome as this project evolves.

- ⭐ Star the project to follow progress
- 🐛 Open an issue for bugs or feature ideas
- 🔧 Submit a pull request when you’re ready