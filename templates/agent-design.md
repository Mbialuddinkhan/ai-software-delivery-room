# AI / Agent Design

<!-- Save as: docs/04-agent-design.md · Written by: ai-architect
Only produced when the product itself contains AI/LLM/agent features.
Every AI decision must be traceable and every agent permission bounded. -->

## 1. Agent list and responsibilities

<One line per agent: name, single responsibility.>

## 2. Input/output schemas

<JSON schema per agent boundary. Prefer structured outputs everywhere.>

## 3. Tools per agent (least privilege)

<Agent → allowed tools table, with why each tool is needed.>

## 4. Memory model

<What is remembered, where, for how long.>

## 5. Orchestration graph

<Diagram or list: who calls whom, in what order, on what condition.>

## 6. Prompt strategy

<System prompt approach, few-shot use, output constraints.>

## 7. Hallucination controls

<Grounding, citations, refusal rules, validation of model claims.>

## 8. Human-in-the-loop checkpoints

<Where a human must approve before the system acts.>

## 9. Model fallback strategy

<What happens when the primary model fails or degrades.>

## 10. Cost controls

<Token budgets, caching, model routing by task difficulty.>

## 11. Evaluation strategy

<How agent quality is measured before and after release.>

## 12. Auditability

<What is logged per AI decision: input, output, model, timestamp, actor.>

## 13. Runtime and deployment (per agent)

<!-- Where each agent executes is a DESIGN decision, not a devops detail.
Agents are stateful, bursty, call out to model APIs, and may execute code
or tool output they did not write. Fill 13.1 first, then the four runtime
blocks in 13.2 for every agent listed in §1. Downstream consumers:
devops (docs/06) reads Task + Model + 13.3; security-compliance (docs/05)
reads Gateway. The critic treats a missing or unjustified tier as a
mandatory finding. -->

### 13.1 Tier decision table

One row per agent from §1. Every "yes" carries the requirement ID (FR/NFR/EC)
that forces it; a "yes" with no ID is not a yes.

| Agent | Executes untrusted code or tool output? | Long-lived state or human wait >60s? | Egress must be allowlisted? | Peak concurrent sessions (`facts:` key or REQ id) | Tier | Justification (one line) |
|---|---|---|---|---|---|---|
| <agent> | no / yes (REQ-xx) | no / yes (REQ-xx) | no / yes (REQ-xx) | <n> | T1 / T2 / T3 | <why the LOWER tier does not satisfy the constraints> |

Tiers (pick the LOWEST tier whose constraints the agent satisfies):

- **T1 — in-process / serverless function.** Stateless per call, no code
  execution, egress = model API + the product's own services. Default.
- **T2 — container worker.** Queue-fed, stateful within a job, retries and
  idempotency required, still no untrusted code execution.
- **T3 — sandboxed actor runtime.** Executes untrusted code or tool output,
  needs hard CPU/memory limits, a network fence, and checkpoint/suspend
  while waiting on models or humans. Candidates: AX (google/ax, Apache-2.0,
  self-hosted on Kubernetes + Agent Substrate; API `v1alpha1` — alpha) or a
  hosted sandbox service of the E2B / Modal / Daytona class. Reference spec:
  `.harness/templates/agent-runtime.yaml`.

Rules:
- T3 requires a "yes" in column 1 or column 3. Otherwise it is
  over-engineering and the critic will flag it.
- "Future scale" is not a justification. Column 4 must cite a measured
  fact or a requirement ID.
- A "yes" in column 1 with tier T1 is a Critical finding: untrusted code
  in the caller's process.

### 13.2 Runtime blocks (one set per agent)

These four blocks are the design vocabulary regardless of tier (they are
AX's primitives; for T1/T2 the right-hand mapping says what they become).

#### <agent name>

**Task — isolation and limits**
- CPU / memory ceiling: <values>
- Wall-clock timeout per invocation: <seconds>
- Suspend/resume needed: <no / yes — trigger: human approval wait, tool
  call >Ns, model latency>
- Disposal: <what state must survive teardown and where it persists (→ §4)>
- T1/T2 mapping: function timeout + memory / container `resources`, job TTL

**Workspace — what the agent needs mounted**
- Git repos + branch: <none / repo@branch>
- MCP / tool servers: <name — endpoint — auth method>
- Skills / prompt assets: <paths>
- Setup: <deterministic script preferred; a generative "goal" setup is
  allowed only if a post-setup test verifies the environment>
- T1/T2 mapping: image layers / deployment package

**Gateway — network policy**
- Egress allowlist (default deny):

  | Host:port | Purpose | Credential injected by gateway? |
  |---|---|---|
  | <api.model.example:443> | model API | yes — <secret name> |

- Credential injection: <which secrets the gateway adds so the agent never
  holds a raw key>
- If T1/T2 cannot enforce default-deny: <what does — VPC egress rules,
  security group, egress proxy — or "accepted risk", cross-referenced in
  §12 and docs/05-security.md>
- T1/T2 mapping: VPC / security groups / egress proxy / IAM

**Model — config in one place**
- Model ID + pinned version: <id@version>
- Parameters: <temperature, max_tokens, …>
- Fallback model: <id> (→ §9)
- Secret reference: <name in secret store — never the value>
- T1/T2 mapping: env var + secrets-manager reference

### 13.3 Deployment topology

- Placement: one line per agent — cloud / region / cluster or function
  platform.
- Scaling signal and hard cap: <queue depth, concurrent sessions → cap n>
- Cost model: idle vs active cost per agent per hour; for T3, the expected
  idle fraction and what suspend/resume saves (cite `facts:` or mark as
  estimate).
- Rollout: how a new agent version reaches production (canary %, shadow
  mode) and the rollback trigger.
- Observability handoff: the signals devops must scrape per agent
  (latency p95, error rate, token spend, sandbox restarts) → docs/06.
