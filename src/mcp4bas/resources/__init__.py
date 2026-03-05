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
	{
		"name": "snmp_dataset",
		"description": "Baseline SNMP OID dataset for read-only simulation and testing.",
		"path": "resources/snmp_dataset.json",
	},
]

__all__ = ["RESOURCE_ASSETS"]
