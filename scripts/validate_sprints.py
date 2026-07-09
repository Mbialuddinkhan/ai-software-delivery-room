#!/usr/bin/env python3
"""Validate sprints.json against the ASDR schema.

Usage: python3 validate_sprints.py [path-to-sprints.json]

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


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sprints.json")
    errors = []

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
               if isinstance(s, dict) and len(set(s) - {"id", "goal", "status"}) > 0]
    if unknown:
        errors.append(f"ERROR: extra fields found on {unknown}; only id, goal, status are allowed")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"OK: {len(sprints)} sprints valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
