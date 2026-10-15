# Technical assessment — <System>

<!-- docs/assess/technical.md — solution-architect, with security-compliance and devops sections.
Appears in Part B of the report. Plain language; cite path:line for every claim.
Mermaid diagrams render in the report. -->

## 01 Architecture

<Components, how they talk, where data lives, coupling, single points of failure. One Mermaid diagram.>

## 02 Code health

<Hotspots from evidence/scan-summary.md (complexity × change frequency), duplication, dead code, typing, tests.>

## 03 Security design

<Authentication, authorisation per route, input handling, secrets handling, dependencies — as reviewed in the code.
State what was confirmed in code; scanner hits that were false alarms are listed in 06.>

## 04 Performance

## 05 Operations

<Build, deploy, backups, monitoring, environments.>

## 06 Scanner triage

<Per tool: hits, how many confirmed, how many false alarms and why.>

## 07 Limits
