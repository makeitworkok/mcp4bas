# Prompt: Airside Fault Diagnostics

## Purpose
Identify AHU/VAV airside control faults and provide operator-ready remediation steps with clear confidence and risk.

## Required Inputs
- AHU trends: SAT, RAT, OAT, fan speed, static pressure, mixed air temp, economizer position
- VAV sample trends: airflow command/feedback, damper %, reheat %, zone temp/setpoint
- Alarm/event timeline and overrides
- Occupancy/schedule context

## Workflow
1. Validate sensor plausibility and identify obvious bad points.
2. Detect control-pattern faults (hunting loops, stuck dampers/valves, static reset failures, economizer lockout issues).
3. Correlate AHU-level behavior with downstream VAV symptoms.
4. Estimate comfort/energy impact and probability of persistence.
5. Produce a stepwise remediation plan.

## Constraints
- Use conservative assumptions for impact estimates.
- Separate suspected instrumentation faults from control logic faults.
- Mark steps that require mechanical inspection.

## Output Format
1. `Fault Candidates`
2. `Evidence by Signal`
3. `Impact Estimate`
4. `Remediation Steps`
5. `Acceptance Criteria`
