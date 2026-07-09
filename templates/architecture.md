# Architecture

<!-- Save as: docs/03-architecture.md · Written by: solution-architect
Prefer boring, maintainable choices; every major trade-off gets an ADR.
A hidden assumption here becomes a torn-down sprint later — surface them. -->

## 1. Architecture overview

<One paragraph + system context diagram (ASCII or Mermaid).>

## 2. Module boundaries and responsibilities

<Modules/services, one line of responsibility each.>

## 3. Database design

<Tables/collections, key fields, relationships, indexes.>

## 4. API design

<Endpoints: method, path, request/response shape, auth requirement.>

## 5. Authentication and authorization

<Who can do what, session/token model, role model.>

## 6. Error handling strategy

<Uniform pattern: how errors are raised, logged, and shown to users.>

## 7. Scalability strategy

<What breaks first at 10x load and the planned answer.>

## 8. Deployment architecture

<Environments, what runs where.>

## 9. Trade-off analysis

<The 2-3 decisions that could have gone another way, and why they didn't.>

## 10. Architecture decision records

<ADR-01... use .harness/templates/adr-template.md format inline.>

## 11. Conventions for the build

<File layout, naming, test framework, lint rules — the generator follows
these verbatim, so be concrete.>
