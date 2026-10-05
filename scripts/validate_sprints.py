#!/usr/bin/env python3
"""Validate sprints.json against the ASDR schema.

Usage: python3 validate_sprints.py [path-to-sprints.json] [--flows docs/02d-process-flows.md]

Since v3.4 each sprint also lists the process flows it delivers
("flows": ["PF-01"]). When the flows document exists (it does after
discovery), every sprint must name at least one flow, every named flow must
exist, and every Must flow must be delivered by some sprint — so the build
is planned as slices through whole user journeys, not as disconnected pieces.
Projects without a flows document keep the old three-field schema.

Exit 0 = valid. Exit 1 = invalid; every problem is printed as one line
starting with "ERROR:" so the orchestrator can feed the list back to the
planner verbatim.
"""
import json
import re
import sys
from pathlib import Path

VALID_STATUSES = {"pending", "active", "done", "torn-down"}
ID_PATTERN = re.compile(r"^sprint-\d{2}$")

# Words the planner is forbidden to use: sprint goals must describe what a
# USER can see and do, never how it is built. Word-boundary matched,
# case-insensitive.
#
# This is a HIGH-PRECISION denylist on purpose: it lists tokens that are
# almost never part of a legitimate user-visible outcome (framework and
# product proper nouns, file extensions, unmistakable infrastructure terms).
# Everyday words that merely sound technical in some contexts — "queue",
# "cache", "python" (the animal), "backend" — are deliberately NOT here,
# because on a capable planner they produce more false rejections than real
# catches. The planner's own self-check and the "user-visible outcome"
# instruction are the primary guard; this list is a narrow backstop against
# obvious implementation leakage.
TECH_TERMS = [
    "react", "next\\.js", "nextjs", "vue", "angular", "svelte", "tailwind",
    "shadcn", "fastapi", "django", "flask", "express", "node\\.js", "nodejs",
    "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis", "qdrant",
    "supabase", "prisma", "kafka",
    "docker", "kubernetes", "terraform", "aws", "gcp", "azure", "vercel",
    "endpoint", "middleware", "webhook", "graphql",
    "rest api", "typescript", "javascript", "oauth", "jwt",
    "langgraph", "langchain", "api route", "/api/", "\\.py", "\\.ts", "\\.tsx",
    "\\.js", "github actions", "ci/cd", "microservice",
]
TECH_RE = re.compile(r"\b(" + "|".join(TECH_TERMS) + r")\b", re.IGNORECASE)

# Sentence delimiter: a .!? followed by whitespace or end-of-string. Requiring
# the trailing whitespace stops version strings like "v2.0" from being counted
# as two sentences.
SENTENCE_RE = re.compile(r"[.!?]+(?:\s+|$)")


FLOW_ID = re.compile(r"^PF-\d+$")


def flow_catalogue(path: Path) -> dict:
    """{flow id: priority} from the process-flows doc, or {} if absent."""
    if not path.is_file():
        return {}
    text = path.read_text(errors="ignore")
    flows = {}
    heads = list(re.finditer(r"^#{2,3}\s+(PF-\d+)\b", text, re.MULTILINE))
    for i, m in enumerate(heads):
        if m.group(1) == "PF-00":
            continue
        body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        pr = re.search(r"^\s*[-*]\s*Priority\s*:\s*(\w+)", body, re.MULTILINE | re.IGNORECASE)
        flows[m.group(1)] = (pr.group(1).lower() if pr else "")
    return flows


def main() -> int:
    args = [a for a in sys.argv[1:]]
    flows_path = Path("docs/02d-process-flows.md")
    if "--flows" in args:
        i = args.index("--flows")
        flows_path = Path(args[i + 1])
        del args[i:i + 2]
    path = Path(args[0]) if args else Path("sprints.json")
    errors = []
    catalogue = flow_catalogue(flows_path)

    if not path.exists():
        print(f"ERROR: {path} does not exist")
        return 1
    try:
        sprints = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: {path} is not valid JSON: {e}")
        return 1

    if not isinstance(sprints, list):
        print("ERROR: sprints.json must be a JSON array")
        return 1
    if not 1 <= len(sprints) <= 6:
        errors.append(f"ERROR: expected 1-6 sprints, found {len(sprints)}")

    seen_ids = set()
    for i, s in enumerate(sprints):
        label = f"sprint at index {i}"
        if not isinstance(s, dict):
            errors.append(f"ERROR: {label} is not an object")
            continue
        for field in ("id", "goal", "status"):
            if field not in s:
                errors.append(f"ERROR: {label} is missing required field '{field}'")
        sid = s.get("id", "")
        if sid:
            label = sid
            if not ID_PATTERN.match(sid):
                errors.append(f"ERROR: {label}: id must match sprint-NN (e.g. sprint-01)")
            if sid in seen_ids:
                errors.append(f"ERROR: duplicate sprint id {sid}")
            seen_ids.add(sid)
        status = s.get("status", "")
        if status and status not in VALID_STATUSES:
            errors.append(
                f"ERROR: {label}: status '{status}' invalid; "
                f"must be one of {sorted(VALID_STATUSES)}"
            )
        goal = s.get("goal", "")
        if goal:
            sentences = [x for x in SENTENCE_RE.split(goal.strip()) if x]
            if len(sentences) > 2:
                errors.append(
                    f"ERROR: {label}: goal has {len(sentences)} sentences; max is 2"
                )
            hits = sorted({m.group(0).lower() for m in TECH_RE.finditer(goal)})
            if hits:
                errors.append(
                    f"ERROR: {label}: goal contains technical terms {hits}; "
                    "rewrite as a user-visible outcome with no implementation detail"
                )

    unknown = [s.get("id", f"index {i}") for i, s in enumerate(sprints)
               if isinstance(s, dict) and len(set(s) - {"id", "goal", "status", "flows"}) > 0]
    if unknown:
        errors.append(f"ERROR: extra fields found on {unknown}; only id, goal, status, flows are allowed")

    delivered = set()
    for i, s in enumerate(sprints):
        if not isinstance(s, dict):
            continue
        label = s.get("id") or f"sprint at index {i}"
        fl = s.get("flows")
        if fl is None:
            if catalogue:
                errors.append(f"ERROR: {label}: no 'flows' list — name the process flow(s) from "
                              f"{flows_path} this sprint delivers (e.g. [\"PF-01\"])")
            continue
        if not isinstance(fl, list) or not fl or not all(isinstance(x, str) and FLOW_ID.match(x) for x in fl):
            errors.append(f"ERROR: {label}: 'flows' must be a non-empty list of ids like \"PF-01\"")
            continue
        for x in fl:
            if catalogue and x not in catalogue:
                errors.append(f"ERROR: {label}: flow {x} is not in {flows_path}")
            delivered.add(x)
    missing = sorted(f for f, pr in catalogue.items() if pr == "must" and f not in delivered)
    if missing:
        errors.append(f"ERROR: Must flow(s) {missing} are not delivered by any sprint — every "
                      "Must journey needs a sprint that makes it work end to end")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"OK: {len(sprints)} sprints valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
