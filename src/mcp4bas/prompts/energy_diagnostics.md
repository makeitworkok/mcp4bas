# Prompt: Energy Diagnostics

## Purpose
Use BAS telemetry to identify likely energy waste and produce prioritized corrective actions that are safe for operators to execute.

## Required Inputs
- Site summary (building type, operating schedule, utility tariff context)
- Equipment inventory and control intent (design sequence if available)
- Last 7-30 days of trends (SAT/RAT/OAT, fan speed, valve/damper %, flow, occupancy)
- Active and recent alarms/events

## Workflow
1. Establish expected operating context from schedule and weather.
2. Detect deviations (simultaneous heating/cooling, unstable control, excessive ventilation, overnight drift).
3. Build root-cause hypotheses and list confirming/disconfirming signals.
4. Quantify impact conservatively with explicit assumptions.
5. Recommend actions ranked by impact, confidence, and operational risk.

## Constraints
- Do not suggest writes or setpoint changes without operator confirmation.
- If data quality is weak or missing, say so explicitly and lower confidence.
- Prefer reversible actions first.

## Output Format
Return sections in this order:
1. `Executive Summary`
2. `Findings` (issue, evidence, confidence)
3. `Estimated Impact` (assumptions, range)
4. `Recommended Actions` (top 3, owner, risk)
5. `Follow-up Data Needed`
