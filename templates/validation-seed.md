# Validation Seed

<!-- Save as: docs/validation/seed.md · Written by: product-owner (SEED mode)
This is the world the simulation is built from. MiroFish extracts entities
and relationships from it and generates personas, so write it as a factual
briefing about the MARKET, not a pitch for the product. Name segments,
roles, competitors and channels concretely — a vague seed produces vague
agents. Never put real private individuals, customer data, credentials or
anything confidential in here: the file is sent to the user's LLM provider
and to Zep Cloud (or the local graph store of an offline fork). -->

## 1. The idea (verbatim)

<The user's idea exactly as given.>

## 2. The offer

- What it does, in two sentences: <…>
- Price and model: <e.g. $29/month per seat; free tier up to …>
- Where and how it launches: <channel, region, language>

## 3. Segments

<Two to five segments. For each: who they are (role, company size, region),
the job they are trying to get done, what they use today, how they decide
to buy, and who influences them.>

| Segment | Role / context | Job to be done | Uses today | Buys how | Influenced by |
|---|---|---|---|---|---|
| S-01 | <…> | <…> | <…> | <…> | <…> |

## 4. Alternatives and competitors

| Alternative | Price | Why people choose it | Known complaints |
|---|---|---|---|
| <…> | <…> | <…> | <…> |

## 5. Market context

<Facts that shape reactions: regulation, recent news, seasonality, budget
pressure, platform rules. Cite a source for every number (URL or "user").>

## 6. Hypotheses to test

<Three to seven falsifiable claims. Each has the signal that would refute it.
These ids carry into docs/00a-idea-validation.md. This section is NOT uploaded
to MiroFish (mirofish_validate.py strips it), so the personas are not built
from our own answer key; keep every hypothesis here and nowhere else in the seed.>

| Id | Hypothesis | Refuted if |
|---|---|---|
| H-01 | <e.g. "Agency owners in S-01 see lead-response speed as a top-3 problem"> | <e.g. "fewer than a third of S-01 agents raise it unprompted or rate it important"> |
