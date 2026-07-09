# Security Review

<!-- Save as: docs/05-security.md (architecture phase) or
docs/09-security-review-final.md (release gate) · Written by: security-compliance
Assume hostile inputs everywhere. Critical/high findings are release
blockers — say so explicitly in section 12. -->

## 1. Threat model

<STRIDE or equivalent: actor, asset, attack, impact.>

## 2. Data classification

<What data is sensitive, where it lives, who may see it.>

## 3. Authentication risks

## 4. Authorization risks

<Per protected resource: what enforces access, what happens if it fails.>

## 5. API security risks

<Input validation, rate limiting, injection surfaces.>

## 6. Prompt injection risks (if AI features exist)

<Untrusted content reaching model context, tool-call abuse paths.>

## 7. Dependency risks

<Known CVEs, unpinned versions, supply-chain exposure.>

## 8. Secrets management

<Where secrets live; confirm none are in source.>

## 9. Logging and audit requirements

<What must be logged for sensitive actions, without logging secrets/PII.>

## 10. Recommended controls

<Numbered, each mapped to a risk above.>

## 11. Security acceptance checklist

<Checkbox list the evaluator can verify per sprint.>

## 12. Release-blocking issues

<Critical/high findings. Empty list = explicitly write "None".>
