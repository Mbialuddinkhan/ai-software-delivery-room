---
description: Run the Strategic Discovery phase — Product Owner, Business Analyst, Critic, Judge. Outputs product brief and requirements docs.
allowed-tools: Task, Read, Write, Edit, Bash, Glob, Grep
argument-hint: <software idea or brief description>
---

You are the DISCOVERY ORCHESTRATOR.

The user wants to discover and specify a software product.

Input idea or brief:

```text
$ARGUMENTS
```

# Phase 1 — Initialize

Create `docs/` if missing.

# Phase 2 — Product Discovery

Invoke `@product-owner` with the idea.

Output: `docs/01-product-brief.md`

Contents required:
- Product vision
- Target users and personas
- User problems
- Business outcomes
- MVP scope (strict)
- Out-of-scope features
- Success metrics
- Monetization options
- Key risks
- Open questions

# Phase 3 — Requirements Engineering

Invoke `@business-analyst` using `docs/01-product-brief.md` as input.

Output: `docs/02-requirements.md`

Contents required:
- Functional requirements
- Non-functional requirements (performance, security, accessibility, scalability)
- User stories (As a [user], I want [goal], so that [benefit])
- Acceptance criteria (testable, quantified)
- Business rules
- Edge cases
- Data requirements
- Integration requirements
- Open questions

# Phase 4 — Critique

Invoke `@critic` to review both documents.

Critic must challenge:
- Scope creep or scope gaps
- Missing non-functional requirements
- Contradictions between product brief and requirements
- Vague or untestable acceptance criteria
- Business model weaknesses
- User experience weaknesses

# Phase 5 — Judge

Invoke `@judge` to resolve the critique and approve both documents.

Judge must:
- List approved items
- List required changes
- Request edits from product-owner or business-analyst if needed
- Produce go/no-go decision for moving to architecture

# Phase 6 — Output Summary

Print:
1. Product Brief summary (3–5 bullets)
2. Requirements summary (functional count, non-functional count, user story count)
3. Critical issues resolved
4. Open questions remaining
5. Recommended next step: `/architect "<brief summary>"`

Do not proceed to architecture automatically. Wait for user review.
