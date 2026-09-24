#!/usr/bin/env python3
"""Build the dependency/knowledge graph into .harness/traceability.json.

Usage:
  python3 build_graph.py [--root .] [--matrix .harness/traceability.json]
                         [--contracts .harness/contracts]

This is the "knowledge and dependency graph" — as a FILE a script maintains,
not as an agent that remembers. A script cannot hallucinate an edge; an agent
can, and a single agent summarising state for everyone else propagates one bad
derivation into every downstream brief.

It EXTENDS the existing v3.1 traceability matrix rather than creating a second
structure beside it (two structures always drift apart). It adds a `graph`
section:

    modules              module -> files, imports, importers
    file_to_requirements file  -> [req ids]   (via the sprints that touch it)
    file_to_criteria     file  -> [criterion ids from contracts]
    fixture_risk         test file -> risk tokens (shared/global state)
    dependents           file  -> files that import it (blast radius)

Everything is derived from the repo and the contracts. Re-runnable, idempotent,
cheap; safe to run in CI on every commit.
"""
import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rb", ".java", ".rs"}
JS_EXT = [".ts", ".tsx", ".js", ".jsx"]
FACT_REF = re.compile(r"facts:[A-Za-z0-9_./\[\]-]+")
SKIP = {".git", "node_modules", "dist", "build", ".next", "coverage",
        "__pycache__", ".venv", "venv", ".harness"}

IMPORT_PATTERNS = [
    re.compile(r"""^\s*import\s+.*?\s+from\s+['"](.+?)['"]""", re.M),
    re.compile(r"""^\s*(?:const|let|var)\s+.*?=\s*require\(['"](.+?)['"]\)""", re.M),
    re.compile(r"""^\s*from\s+([\w.]+)\s+import\s+""", re.M),
    re.compile(r"""^\s*import\s+([\w.]+)\s*$""", re.M),
]
# Tokens that indicate globally-shared or contended fixture state. These are the
# exact defect classes seen in the field: a globally-unique PhoneNumber leaking
# between files, a contended slotKey, and FK-ordered deletes.
FIXTURE_RISK = {
    "global-unique": re.compile(r"\b(PhoneNumber|email|slug|username|externalId)\b"),
    "contended-key": re.compile(r"\b(slotKey|lockKey|idempotencyKey|bookingKey)\b"),
    "fk-order": re.compile(r"\b(deleteMany|truncate|clearFixtureRows|ON DELETE)\b"),
    "afterAll-cleanup": re.compile(r"\bafterAll\s*\("),
    "absolute-count": re.compile(r"\b(count|length)\s*\)?\s*(?:===|toBe|toEqual)\s*\d+"),
}
CRITERION = re.compile(r"^\s*(\d+)\.\s+(.*)$", re.M)
CATEGORY = re.compile(r"^###\s+(.*?)\s*$", re.M)
FILE_REF = re.compile(r"([\w./-]+\.(?:ts|tsx|js|jsx|py|go|rb|java|rs|sql))")


def iter_code_files(root):
    for p in Path(root).rglob("*"):
        if p.is_file() and p.suffix in CODE_EXT and not any(x in p.parts for x in SKIP):
            yield p


def module_of(rel):
    """Module = the directory path; good enough and stable across languages."""
    d = str(Path(rel).parent)
    return "." if d == "" else d


def _first_known(cands, known):
    for c in cands:
        norm = posixpath.normpath(c)
        if norm.startswith("../"):
            continue  # escaped the repo root
        if norm in known:
            return norm
    return None


def resolve(spec, importer, root, known):
    """Resolve an import specifier to a repo path, best-effort.

    Handles three families, all of which the field data showed being missed:
      JS/TS relative   './x', '../db/lead'   -> normalised path + ext/index
      Python relative  '.utils', '..pkg.mod' -> leading dots climb directories
      Python absolute  'pkg.utils'           -> tried from the repo root and
                                                from every ancestor of the
                                                importer (src/ layouts)
    Third-party and stdlib specifiers resolve to nothing, which is correct: they
    are not edges inside the repository. Paths are normalised with
    posixpath.normpath so '../' segments collapse instead of being mangled.
    """
    importer_dir = posixpath.dirname(importer)
    is_py = importer.endswith(".py")

    if spec.startswith(("./", "../")) or spec in (".", ".."):
        base = posixpath.join(importer_dir, spec) if importer_dir else spec
        cands = [base] + [f"{base}{e}" for e in JS_EXT + [".py"]] + \
                [f"{base}/index{e}" for e in JS_EXT] + [f"{base}/__init__.py"]
        return _first_known(cands, known)

    if is_py and spec.startswith("."):
        dots = len(spec) - len(spec.lstrip("."))
        rest = spec[dots:].replace(".", "/")
        base = importer_dir
        for _ in range(dots - 1):
            base = posixpath.dirname(base)
        target = posixpath.join(base, rest) if rest else base
        cands = [f"{target}.py", f"{target}/__init__.py"] if rest else \
                [f"{target}/__init__.py"]
        return _first_known(cands, known)

    if is_py and re.fullmatch(r"[\w.]+", spec):
        rest = spec.replace(".", "/")
        roots = [""]
        d = importer_dir
        while d:
            roots.append(d)
            d = posixpath.dirname(d)
        cands = []
        for r in roots:
            t = posixpath.join(r, rest) if r else rest
            cands += [f"{t}.py", f"{t}/__init__.py"]
        return _first_known(cands, known)

    return None  # bare JS specifier: third-party package


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--matrix", default=".harness/traceability.json")
    ap.add_argument("--contracts", default=".harness/contracts")
    args = ap.parse_args()

    root = Path(args.root)
    files = [str(p.relative_to(root)).replace("\\", "/") for p in iter_code_files(root)]
    known = set(files)

    modules, imports, dependents, fixture_risk = {}, {}, {}, {}

    for rel in files:
        text = ""
        try:
            text = (root / rel).read_text(errors="ignore")
        except OSError:
            pass

        modules.setdefault(module_of(rel), {"files": [], "depends_on": set()})
        modules[module_of(rel)]["files"].append(rel)

        deps = []
        for pat in IMPORT_PATTERNS:
            for spec in pat.findall(text):
                tgt = resolve(spec, rel, root, known)
                if tgt and tgt != rel:
                    deps.append(tgt)
                    dependents.setdefault(tgt, set()).add(rel)
                    modules[module_of(rel)]["depends_on"].add(module_of(tgt))
        if deps:
            imports[rel] = sorted(set(deps))

        low = rel.lower()
        if any(k in low for k in ("test", "spec", "e2e", "cypress", "fixture")):
            hits = [name for name, pat in FIXTURE_RISK.items() if pat.search(text)]
            if hits:
                fixture_risk[rel] = sorted(hits)

    for m in modules.values():
        m["files"] = sorted(m["files"])
        m["depends_on"] = sorted(x for x in m["depends_on"] if x)

    # Criteria -> files, from every contract.
    file_to_criteria = {}
    cdir = Path(args.contracts)
    if cdir.is_dir():
        for c in sorted(cdir.glob("contract-*.md")):
            sprint = c.stem.replace("contract-", "")
            body = re.sub(r"<!--.*?-->", "", c.read_text(errors="ignore"), flags=re.DOTALL)
            cat = None
            for line in body.splitlines():
                h = CATEGORY.match(line)
                if h:
                    cat = h.group(1)
                    continue
                m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
                if m and cat:
                    cid = f"{sprint}#{cat}:{m.group(1)}"
                    # Strip `facts:<key>` citations first: a key like
                    # `facts:diff.src/pay.ts.net_nonblank` otherwise reads as
                    # a file called `diff.src/pay.ts` (same fix as the pack
                    # builder and the pre-flight linter).
                    scan = FACT_REF.sub(" ", m.group(2))
                    for f in set(FILE_REF.findall(scan)):
                        file_to_criteria.setdefault(f, []).append(cid)

    # Requirements -> files, inherited through the sprints that touch each file.
    mpath = Path(args.matrix)
    matrix = {"version": 1, "outcomes": [], "use_cases": [], "requirements": []}
    if mpath.exists():
        try:
            matrix = json.loads(mpath.read_text())
        except ValueError:
            print(f"WARN: {mpath} unreadable; writing a fresh matrix skeleton")

    sprint_to_reqs = {}
    for r in matrix.get("requirements", []):
        for s in r.get("sprints", []) or []:
            sprint_to_reqs.setdefault(s, []).append(r.get("req_id"))

    file_to_requirements = {}
    for f, cids in file_to_criteria.items():
        reqs = set()
        for cid in cids:
            reqs.update(sprint_to_reqs.get(cid.split("#")[0], []))
        if reqs:
            file_to_requirements[f] = sorted(x for x in reqs if x)

    matrix["graph"] = {
        "generated_by": "build_graph.py",
        "modules": modules,
        "imports": imports,
        "dependents": {k: sorted(v) for k, v in dependents.items()},
        "file_to_criteria": {k: sorted(set(v)) for k, v in file_to_criteria.items()},
        "file_to_requirements": file_to_requirements,
        "fixture_risk": fixture_risk,
    }

    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n")

    print(f"OK: graph written to {mpath}")
    print(f"  files={len(files)} modules={len(modules)} "
          f"edges={sum(len(v) for v in imports.values())} "
          f"criteria-linked files={len(file_to_criteria)} "
          f"fixture-risk files={len(fixture_risk)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
