"""Prompt templates used by MCP4BAS workflows."""

PROMPT_ASSETS = [
	{
		"name": "energy_diagnostics",
		"description": "Energy anomaly diagnostics with impact and action prioritization.",
		"path": "prompts/energy_diagnostics.md",
	},
	{
		"name": "comfort_diagnostics",
		"description": "Occupant comfort complaint triage and corrective workflow.",
		"path": "prompts/comfort_diagnostics.md",
	},
	{
		"name": "airside_fault_diagnostics",
		"description": "AHU/VAV airside fault isolation and remediation planning.",
		"path": "prompts/airside_fault_diagnostics.md",
	},
]

__all__ = ["PROMPT_ASSETS"]
