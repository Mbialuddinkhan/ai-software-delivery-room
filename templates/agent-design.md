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
