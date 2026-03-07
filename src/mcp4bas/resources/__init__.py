"""Resource templates exposed via MCP resources."""

RESOURCE_ASSETS = [
	{
		"name": "equipment_summary",
		"description": "Equipment inventory summary schema for diagnostics context.",
		"path": "resources/equipment_summary.json",
	},
	{
		"name": "trend_summary",
		"description": "Trend aggregation summary schema for diagnostics context.",
		"path": "resources/trend_summary.json",
	},
]

__all__ = ["RESOURCE_ASSETS"]
