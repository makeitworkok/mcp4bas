# Prompt: Comfort Diagnostics

## Purpose
Diagnose occupant comfort complaints using BAS trends, zone context, and equipment behavior while minimizing operational risk.

## Required Inputs
- Complaint details (zone, time window, symptom: hot/cold/humidity/airflow)
- Zone and AHU trends for the complaint window and preceding baseline period
- Schedule/occupancy information
- Relevant alarms, overrides, and recent maintenance notes

## Workflow
1. Define the complaint interval and baseline interval.
2. Compare zone condition vs setpoints, deadbands, and occupancy mode.
3. Trace likely upstream causes (VAV command/feedback mismatch, AHU SAT drift, valve/damper limits, static pressure instability).
4. Differentiate one-off disturbance vs repeatable control issue.
5. Recommend lowest-risk corrective actions and verification checks.

## Constraints
- Do not perform writes directly; produce operator-approved actions only.
- Flag uncertainty when trends are sparse or contradictory.
- Prefer checks that can be validated in one shift.

## Output Format
1. `Complaint Summary`
2. `Most Likely Causes` (with evidence)
3. `Immediate Checks` (safe and reversible)
4. `Corrective Actions` (priority + risk)
5. `Verification Plan`
