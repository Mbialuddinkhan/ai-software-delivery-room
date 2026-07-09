# DevOps Plan

<!-- Save as: docs/06-devops.md (architecture phase) or
docs/09-devops-readiness.md (release gate) · Written by: devops
Config via environment variables only; a deployment guide without a
rollback section is incomplete by definition. -->

## 1. Container strategy

<Dockerfile approach, docker-compose services.>

## 2. Environment configuration

<.env.example contents — every variable, with a comment, no real values.>

## 3. CI pipeline

<Workflow steps: install, lint, test, build. Failing tests block merge.>

## 4. Deployment guide

<Exact commands to deploy, per environment.>

## 5. Observability

<Logs, metrics, alerts: what is collected and where to look when it breaks.>

## 6. Backup plan

<What is backed up, how often, restore procedure.>

## 7. Rollback plan

<Exact steps to return to the previous working version.>

## 8. Production checklist

<Checkbox list — every item verifiable, no judgment calls.>
