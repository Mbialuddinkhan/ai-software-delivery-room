#!/usr/bin/env python3
"""Synthetic panel for idea validation — ASDR's native take on MiroFish.

Usage:
  python3 panel.py init [--dir D] [--size 12] [--rounds 2] [--followups 3] [--panel-id panel]
  python3 panel.py next [--dir D]            # do the deterministic work, print the next agent task(s)
  python3 panel.py compare DIR_A DIR_B       # two independent panels → panel_variance
  python3 panel.py walkthrough-next [--dir D] [--flows docs/02d-process-flows.md] [--sample 6]

What it borrows from MiroFish, and what it deliberately does not:
  - Ground the world in evidence first: personas cite desk-evidence ids, and any
    quote they carry must appear verbatim in docs/validation/desk-evidence.md.
  - Personas with memory: each persona sees its own earlier answers in round 2
    and in follow-up interviews.
  - One round of social exposure, measured: an anonymised digest of everyone's
    objections (no ids, no counts), then stance changes are counted. No more
    rounds — multi-agent LLM populations drift to consensus and invent
    collective biases.
  - "What if" scenarios on the same panel (price, pitch, a competitor move):
    within-persona comparisons are the most trustworthy thing a synthetic
    panel produces; absolute shares are not.
  - Post-run interviews of the personas with the strongest objections.
  - Report spread and flags (implausible positivity, herding, homogeneity,
    thin segments), not just averages.
  Not borrowed: thousands of agents, simulated social-media mechanics, a
  graph database. A larger crowd of one model is not more evidence.

Layout (all under --dir, default docs/validation/panel/):
  config.json                    written by init
  stimulus.md, scenarios.json    product-owner (scenarios.json optional: base only)
  stimulus-<SC-xx>.md            one per extra scenario
  roster.json                    business-analyst, from seed-for-roster.md + desk evidence
  seed-for-roster.md             generated: the seed without its hypotheses section
  inputs/*.md                    generated: EXACTLY what each panelist is shown
  responses/<scenario>/r1-<P>.json, responses/base/r2-<P>.json   panelist
  digest.md                      generated from base round 1
  followups/selection.json       generated; followups/<P>.json   panelist
  walkthroughs/<P>.json          panelist (discover phase)
Facts are merged into .harness/validation.json under the panel id (default
"panel"), next to MiroFish's "mirofish" key; cite them as
`validation:panel.<dotted.key>`.

`next` prints ONE JSON instruction. Actions: WRITE-STIMULUS, FIX-STIMULUS,
WAIT-DESK, WRITE-ROSTER, FIX-ROSTER, RESPOND (a list of panelist tasks, some of
them fixes), REVISE, FOLLOWUP, DONE. Exit 0 unless usage/config is wrong (1).
Zero dependencies.
"""
import argparse
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validation_questions as vq  # noqa: E402

DEFAULT_DIR = "docs/validation/panel"
SEED = "docs/validation/seed.md"
DESK = "docs/validation/desk-evidence.md"
FACTS = ".harness/validation.json"
MAX_SCENARIOS = 4  # base + 3

NOTE = ("Synthetic opinion from Claude-played personas grounded in our desk evidence. "
        "It surfaces objections, confusion and switching barriers; intent shares are "
        "shaped by the roster quotas and are NOT demand. Compare scenarios within the "
        "same panel; do not read absolute shares.")


# ── helpers ──────────────────────────────────────────────────────────────────

LAST = {"action": None}


def out(action, **kw):
    LAST["action"] = action
    print(json.dumps({"action": action, **kw}, indent=2, ensure_ascii=False))
    return 0


def load_json(p):
    """A JSON object from a file; None if missing; {"__invalid__": why} otherwise."""
    try:
        v = json.loads(Path(p).read_text())
    except FileNotFoundError:
        return None
    except ValueError as e:
        return {"__invalid__": f"not valid JSON: {e}"}
    if not isinstance(v, dict):
        return {"__invalid__": f"expected a JSON object, got {type(v).__name__}"}
    return v


def newer(target, *sources):
    """True if target is missing or older than any existing source."""
    t = Path(target)
    if not t.exists():
        return True
    tm = t.stat().st_mtime
    return any(Path(s).exists() and Path(s).stat().st_mtime > tm for s in sources)


def seed_text():
    p = Path(SEED)
    return p.read_text() if p.exists() else ""


def desk_ids_and_text():
    """Desk row ids, and the text a persona's 'real public quote' may come from."""
    p = Path(DESK)
    if not p.exists():
        return set(), ""
    text = p.read_text()
    return set(re.findall(r"\bD-\d{2,3}\b", text)), vq.desk_quote_text(text)


def seed_segments():
    return sorted(set(re.findall(r"\bS-\d{2}\b", vq.strip_sections(seed_text())[0])))


def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def cfg_path(d):
    return Path(d) / "config.json"


def load_cfg(d):
    c = load_json(cfg_path(d))
    if not c or "__invalid__" in c:
        raise SystemExit(f"ERROR: {cfg_path(d)} missing or invalid — run `panel.py init --dir {d}`")
    return c


# ── scenarios and stimulus ───────────────────────────────────────────────────

def scenarios(d):
    """[(id, stimulus_path, label)], base first. Creates a base-only file if absent."""
    d = Path(d)
    sp = d / "scenarios.json"
    data = load_json(sp)
    if data is None and (d / "stimulus.md").exists():
        data = {"scenarios": [{"id": "base", "stimulus": str(d / "stimulus.md"),
                               "label": "as described"}]}
        sp.write_text(json.dumps(data, indent=2))
    if not data or "__invalid__" in data:
        return None, [data.get("__invalid__")] if data else []
    errs, outl, seen = [], [], set()
    entries = data.get("scenarios", [])
    if not isinstance(entries, list) or not all(isinstance(x, dict) for x in entries):
        return [], ["scenarios.json: 'scenarios' must be a list of {id, stimulus, label} objects"]
    for s in entries:
        sid, stim = s.get("id"), s.get("stimulus")
        if not sid or not stim:
            errs.append(f"scenario entry needs id and stimulus: {s}")
            continue
        if sid in seen:
            errs.append(f"duplicate scenario id {sid}")
        seen.add(sid)
        if sid != "base" and not re.fullmatch(r"SC-\d{2}", sid):
            errs.append(f"scenario id '{sid}' must be 'base' or SC-01…SC-03")
        outl.append((sid, stim, s.get("label", "")))
    if not outl or outl[0][0] != "base":
        errs.append("the first scenario must be 'base'")
    if len(outl) > MAX_SCENARIOS:
        errs.append(f"{len(outl)} scenarios; at most {MAX_SCENARIOS} (base + 3) — each one "
                    "multiplies the panel cost")
    return outl, errs


def check_stimuli(scs):
    errs = []
    seed = seed_text()
    for sid, stim, _ in scs:
        p = Path(stim)
        if not p.exists() or not p.read_text().strip():
            errs.append(f"{stim}: missing or empty (scenario {sid})")
            continue
        text = p.read_text()
        if "<!--" in text:
            errs.append(f"{stim}: still contains the template's guidance comment — delete it; "
                        "every panelist would read it")
        if re.search(r"<[a-z][^>]{2,}>", text):
            errs.append(f"{stim}: still has an unfilled <placeholder>")
        for problem in vq.leaks(text, seed):
            hint = (" — describe what it does, not the outcome we hope for; a concept card "
                    "that states the hoped-for result primes every persona"
                    if problem.startswith("paraphrases") else
                    " — the panel must not see our hypotheses")
            errs.append(f"{stim}: {problem}{hint}")
    return errs


# ── roster ───────────────────────────────────────────────────────────────────

ROSTER_FIELDS = ("id", "segment", "role", "context", "job_to_be_done",
                 "current_alternative", "budget_authority", "tech_comfort",
                 "temperament", "stance_prior", "constraints", "grounding")


def check_roster(d, size=None):
    r = load_json(Path(d) / "roster.json")
    if r is None:
        return None, ["roster.json missing"]
    if "__invalid__" in r:
        return None, [r["__invalid__"]]
    errs = []
    people = r.get("personas") or []
    if not isinstance(people, list) or not all(isinstance(p, dict) for p in people):
        return None, ["roster.json: 'personas' must be a list of objects"]
    n = len(people)
    if not vq.PANEL_MIN <= n <= vq.PANEL_MAX:
        errs.append(f"{n} personas; the panel must have {vq.PANEL_MIN}–{vq.PANEL_MAX}")
    elif size and n != size:
        errs.append(f"{n} personas; this panel was initialised with --size {size}")
    desk_ids, desk_text = desk_ids_and_text()
    nd = norm(desk_text)
    ids, combos = set(), set()
    enums = {"budget_authority": vq.BUDGET_AUTHORITY, "tech_comfort": vq.TECH_COMFORT,
             "temperament": vq.TEMPERAMENT, "stance_prior": vq.STANCE_PRIOR}
    for i, p in enumerate(people):
        pid = p.get("id") or f"#{i + 1}"
        for f in ROSTER_FIELDS:
            if p.get(f) in (None, "", []):
                errs.append(f"{pid}: missing '{f}'")
        if not re.fullmatch(r"P\d{2}", str(p.get("id", ""))):
            errs.append(f"{pid}: id must be P01, P02, …")
        if pid in ids:
            errs.append(f"{pid}: duplicate id")
        ids.add(pid)
        for f, allowed in enums.items():
            if p.get(f) and p[f] not in allowed:
                errs.append(f"{pid}: {f} '{p[f]}' not one of {list(allowed)}")
        combo = (p.get("segment"), norm(p.get("role", "")), p.get("temperament"))
        if all(combo) and combo in combos:
            errs.append(f"{pid}: same segment, role and temperament as another persona")
        combos.add(combo)
        for g in p.get("grounding") or []:
            if g not in desk_ids:
                errs.append(f"{pid}: grounding '{g}' is not a row id in {DESK}")
        for q in p.get("voice") or []:
            if norm(q) not in nd:
                errs.append(f"{pid}: voice quote not found verbatim in {DESK}: \"{q[:50]}\" — "
                            "quotes must be real; drop it or copy it exactly")
    segs = seed_segments()
    have = {p.get("segment") for p in people}
    for s in segs:
        if s not in have:
            errs.append(f"seed segment {s} has no persona")
    for p in people:
        if segs and p.get("segment") not in segs:
            errs.append(f"{p.get('id')}: segment '{p.get('segment')}' is not in the seed")
    if n:
        share = lambda k: sum(1 for p in people if p.get("stance_prior") == k) / n  # noqa: E731
        for k, lo in vq.QUOTA_MIN.items():
            if share(k) < lo:
                errs.append(f"stance_prior '{k}' is {share(k):.0%} of the panel; at least {lo:.0%}")
        for k, hi in vq.QUOTA_MAX.items():
            if share(k) > hi:
                errs.append(f"stance_prior '{k}' is {share(k):.0%} of the panel; at most {hi:.0%}")
    for p in people:
        for f in ("context", "job_to_be_done", "current_alternative", "constraints"):
            for pat in vq.OPINION_MARKERS:
                m = re.search(pat, str(p.get(f) or ""), re.IGNORECASE)
                if m:
                    errs.append(f"{p.get('id')}: '{f}' states an attitude ('{m.group(0)}') — "
                                "describe the situation (budget, staff, systems, rules they "
                                "work under), not how they feel about tools like this; the "
                                "panel has to find attitudes, not be told them")
                    break
    for problem in vq.leaks(json.dumps(r, ensure_ascii=False), seed_text()):
        errs.append(f"roster.json: {problem}")
    return r, errs


# ── briefs (exactly what a panelist sees) ────────────────────────────────────

STANCE_TEXT = {
    "loyal-to-current": "You are generally loyal to what you use today; switching needs a clear, "
                        "concrete reason and you dislike disruption.",
    "open": "You will look at new options if they solve a real problem for you.",
    "would-never-buy": "You rarely or never pay for tools like this; you get by without them.",
    "early-adopter": "You like trying new tools early, but you have been burned before.",
}


def persona_card(p):
    lines = [
        f"- Role: {p['role']} ({p['context']})",
        f"- What you are trying to get done: {p['job_to_be_done']}",
        f"- What you use today: {p['current_alternative']}",
        f"- Buying: you {'decide' if p['budget_authority'] == 'decides' else 'influence the decision' if p['budget_authority'] == 'influences' else 'have no say in purchases'}",
        f"- Comfort with technology: {p['tech_comfort']}",
        f"- Temperament: {p['temperament']}",
        f"- Constraints: {p['constraints']}",
        f"- Disposition: {STANCE_TEXT[p['stance_prior']]}",
    ]
    voice = p.get("voice") or []
    if voice:
        lines.append("\nThings people in your position have said (real public quotes):")
        lines += [f"> {q}" for q in voice]
    return "\n".join(lines)


RULES = """Rules: you are this person, not an assistant. You owe the product nothing.
Most people ignore most new products; your default is what you use today unless
this clearly beats it for you. Answer from your situation, budget and habits.
Say "I don't know" when you would not know. Never mention being an AI or a persona."""


def response_schema(scenario, rnd, persona, extra=False):
    s = {
        "persona": persona, "scenario": scenario, "round": rnd,
        "answers": [f"<answer to question {i + 1}>" for i in range(len(vq.DEFAULT_QUESTIONS))],
        "intent": "|".join(vq.INTENT),
        "price_reaction": "|".join(vq.PRICE_REACTION),
        "fair_price": None,
        "objection_category": "|".join(vq.OBJECTION_CATEGORIES),
        "objection": "<your single biggest reason not to use it>",
        "switch_trigger": "<what would make you switch, or 'nothing'>",
        "quote": "<one sentence in your own voice>",
    }
    if extra:
        s["changed"] = "true|false — did your view change after reading what others said?"
        s["why"] = "<why it changed, or why not>"
    return json.dumps(s, indent=2)


PRICE_NOTE = ("`fair_price` is a plain number in the stimulus currency per the stimulus "
              "period (e.g. 25 — no quotes, no currency sign), or null if you would not "
              "pay anything.")


def coerce_price(v):
    """A price the panelist wrote as text ("$19", "19/month", "1,200") -> number.

    The first real run had panelists quote the number as a string; asking for a
    re-do costs a full agent call, and the value was never in doubt.
    """
    if v is None or isinstance(v, bool):
        return v if v is None else "invalid"
    if isinstance(v, (int, float)):
        return v
    euro = re.fullmatch(r"\s*[^\d\-]{0,4}?\s*(\d{1,3}(?:\.\d{3})+)\s*(?:[a-zA-Z$€£.]{0,8})?"
                        r"\s*(?:(?:/|per)\s*\w+)?\s*", str(v))
    if euro:                      # "€1.200" — dots as thousands separators
        return int(euro.group(1).replace(".", ""))
    m = re.fullmatch(r"\s*[^\d\-]{0,4}?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?"
                     r"\s*(?:[a-zA-Z$€£.]{0,8})?\s*(?:(?:/|per)\s*\w+)?\s*", str(v))
    if not m:
        return "invalid" if str(v).strip().lower() not in ("null", "none", "") else None
    whole = m.group(1).replace(",", "")
    return float(f"{whole}.{m.group(2)}") if m.group(2) else int(whole)


def coerce_bool(v):
    if isinstance(v, bool):
        return v
    if str(v).strip().lower() in ("true", "yes"):
        return True
    if str(v).strip().lower() in ("false", "no"):
        return False
    return v


BRIEF_LEAKS = []


def write_brief(path, title, body):
    """Write a panelist's brief only when its content changes, so its mtime
    marks the last real change and answers written before it can be told apart.
    Every brief is checked for our hypotheses before any panelist can read it."""
    path = Path(path)
    text = f"# Panel brief — {title}\n\n{body}\n"
    if path.exists() and path.read_text() == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def note_brief(brief, *team_parts):
    """Check what WE put into a panelist's brief — every call, not only when it
    is rewritten — for our hypotheses and template guidance.

    Round-1 briefs are entirely ours. Round-2 and follow-up briefs also carry
    the panel's own earlier answers and digest: those are not checked (a
    persona raising a hypothesis unprompted is the signal we want, and nobody
    could "fix" it), so pass the team-written parts instead.
    """
    b = Path(brief)
    if team_parts:
        text = "\n".join(team_parts)
    elif b.exists():
        text = b.read_text()
    else:
        return
    for problem in vq.leaks(text, seed_text(), brief=True):
        BRIEF_LEAKS.append(f"{b}: {problem}")


def stale(outp, brief):
    """An answer written before its brief last changed answers a different card."""
    o, b = Path(outp), Path(brief)
    return o.exists() and b.exists() and b.stat().st_mtime > o.stat().st_mtime


STALE = ("stale: this persona's brief changed after the answer was written "
         "(roster, stimulus, digest or earlier answers changed) — answer again from the "
         "current input file")


def questions_block():
    return "\n".join(f"{i + 1}. {q}" for i, q in enumerate(vq.DEFAULT_QUESTIONS))


def brief_r1(d, p, sid, stim, outp):
    body = (f"You are persona {p['id']}.\n\n{persona_card(p)}\n\n{RULES}\n\n"
            f"## What you are shown\n\n{Path(stim).read_text().strip()}\n\n"
            f"## Questions\n\n{questions_block()}\n\n"
            f"## Write\n\nWrite ONLY this JSON, filled in, to `{outp}`:\n\n```json\n"
            f"{response_schema(sid, 1, p['id'])}\n```\n\n{PRICE_NOTE}\n")
    return body


def brief_r2(d, p, stim, r1_path, digest_path, outp):
    body = (f"You are persona {p['id']}.\n\n{persona_card(p)}\n\n{RULES}\n\n"
            f"## What you were shown\n\n{Path(stim).read_text().strip()}\n\n"
            f"## Your own earlier answers\n\n```json\n{Path(r1_path).read_text().strip()}\n```\n\n"
            f"## What other people said (anonymous, in no particular order)\n\n"
            f"{Path(digest_path).read_text().strip()}\n\n"
            "Answer the same questions again as yourself. Change your view only if something "
            "above would really change it for someone in your situation.\n\n"
            f"## Questions\n\n{questions_block()}\n\n"
            f"## Write\n\nWrite ONLY this JSON, filled in, to `{outp}`:\n\n```json\n"
            f"{response_schema('base', 2, p['id'], extra=True)}\n```\n\n{PRICE_NOTE}\n")
    return body


def brief_followup(p, stim, answers_paths, outp, objection):
    probes = [q.replace("{objection}", objection or "(your objection)") for q in vq.FOLLOWUP_PROBES]
    prev = "\n\n".join(f"```json\n{Path(a).read_text().strip()}\n```" for a in answers_paths)
    schema = json.dumps({"persona": p["id"],
                         "answers": [f"<answer to probe {i + 1}>" for i in range(len(probes))],
                         "root_cause": "<the real reason behind your objection, in one sentence>",
                         "would_try_if": "<the one condition that would get you to try it>"},
                        indent=2)
    return (f"You are persona {p['id']}.\n\n{persona_card(p)}\n\n{RULES}\n\n"
            f"## What you were shown\n\n{Path(stim).read_text().strip()}\n\n"
            f"## Your earlier answers\n\n{prev}\n\n"
            "An interviewer is following up with you. Answer in your own words; be specific "
            "about your situation.\n\n## Probes\n\n"
            + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(probes))
            + f"\n\n## Write\n\nWrite ONLY this JSON, filled in, to `{outp}`:\n\n```json\n{schema}\n```\n")


# ── response checks ──────────────────────────────────────────────────────────

def check_response(path, persona, scenario, rnd):
    r = load_json(path)
    if r is None:
        return None, ["missing"]
    if "__invalid__" in r:
        return None, [r["__invalid__"]]
    errs = []
    if r.get("persona") != persona:
        errs.append(f"persona is '{r.get('persona')}', expected '{persona}'")
    if r.get("scenario") != scenario:
        errs.append(f"scenario is '{r.get('scenario')}', expected '{scenario}'")
    if r.get("round") != rnd:
        errs.append(f"round is {r.get('round')!r}, expected {rnd}")
    ans = r.get("answers")
    if not isinstance(ans, list) or len(ans) != len(vq.DEFAULT_QUESTIONS) or \
            any(not str(a).strip() or "<answer" in str(a) for a in ans):
        errs.append(f"answers must be {len(vq.DEFAULT_QUESTIONS)} non-empty strings")
    for f, allowed in (("intent", vq.INTENT), ("price_reaction", vq.PRICE_REACTION),
                       ("objection_category", vq.OBJECTION_CATEGORIES)):
        if r.get(f) not in allowed:
            errs.append(f"{f} '{r.get(f)}' not one of {list(allowed)}")
    fp = coerce_price(r.get("fair_price"))
    if fp == "invalid":
        errs.append("fair_price must be a number or null")
    else:
        r["fair_price"] = fp
    for f in ("objection", "switch_trigger", "quote"):
        if not str(r.get(f) or "").strip() or str(r.get(f)).startswith("<"):
            errs.append(f"'{f}' is empty")
    if rnd == 2:
        r["changed"] = coerce_bool(r.get("changed"))
        if not isinstance(r.get("changed"), bool):
            errs.append("'changed' must be true or false")
        if r.get("changed") and not str(r.get("why") or "").strip():
            errs.append("'why' is required when changed is true")
    return r, errs


def check_followup(path, persona):
    r = load_json(path)
    if r is None:
        return None, ["missing"]
    if "__invalid__" in r:
        return None, [r["__invalid__"]]
    errs = []
    if r.get("persona") != persona:
        errs.append(f"persona is '{r.get('persona')}', expected '{persona}'")
    ans = r.get("answers")
    if not isinstance(ans, list) or len(ans) != len(vq.FOLLOWUP_PROBES) or \
            any(not str(a).strip() or "<answer" in str(a) for a in ans):
        errs.append(f"answers must be {len(vq.FOLLOWUP_PROBES)} non-empty strings")
    for f in ("root_cause", "would_try_if"):
        if not str(r.get(f) or "").strip() or str(r.get(f)).startswith("<"):
            errs.append(f"'{f}' is empty")
    return r, errs


# ── digest, follow-up selection, aggregation ─────────────────────────────────

DIGEST_HEAD = "What other people on the panel said (anonymous, shuffled):\n\n"


def digest_items(responses):
    items = {}
    for r in responses:
        items[r["persona"]] = f"- {str(r['objection']).strip()} — \"{str(r['quote']).strip()}\""
    return items


def shuffled(lines):
    return sorted(lines, key=lambda s: hashlib.sha1(s.encode()).hexdigest())


def build_digest(d, responses):
    """digest.md (everyone, for the record) and digests/<P>.md (everyone but P:
    a persona reading its own objection as someone else's inflates agreement)."""
    items = digest_items(responses)
    Path(d, "digest.md").write_text(DIGEST_HEAD + "\n".join(shuffled(items.values())) + "\n")
    dd = Path(d, "digests")
    dd.mkdir(parents=True, exist_ok=True)
    for pid in items:
        others = [v for k, v in items.items() if k != pid]
        text = DIGEST_HEAD + "\n".join(shuffled(others)) + "\n"
        f = dd / f"{pid}.md"
        if not f.exists() or f.read_text() != text:
            f.write_text(text)


def pick_followups(final, k):
    score = {"no": 2, "maybe": 1, "yes": 0}
    ranked = sorted(final, key=lambda r: (-(score[r["intent"]] + (r["price_reaction"] == "would-not-pay")),
                                          r["persona"]))
    picked, cats = [], set()
    for r in ranked:
        if len(picked) >= k:
            break
        if r["objection_category"] not in cats:
            picked.append(r)
            cats.add(r["objection_category"])
    for r in ranked:
        if len(picked) >= k:
            break
        if r not in picked:
            picked.append(r)
    return [{"persona": r["persona"], "intent": r["intent"],
             "objection_category": r["objection_category"], "objection": r["objection"]}
            for r in picked]


def summarize(responses, roster_by_id):
    n = len(responses)
    count = lambda f, allowed: {a: sum(1 for r in responses if r.get(f) == a) for a in allowed}  # noqa: E731
    prices = sorted(float(r["fair_price"]) for r in responses
                    if isinstance(r.get("fair_price"), (int, float)) and r["fair_price"] > 0)
    by_seg = {}
    for r in responses:
        seg = roster_by_id.get(r["persona"], {}).get("segment", "?")
        by_seg.setdefault(seg, {a: 0 for a in vq.INTENT})[r["intent"]] += 1
    s = {"n": n, "intent": count("intent", vq.INTENT),
         "price_reaction": count("price_reaction", vq.PRICE_REACTION),
         "objection_category": count("objection_category", vq.OBJECTION_CATEGORIES),
         "fair_price": {**({"n": len(prices), "median": statistics.median(prices),
                             "min": prices[0], "max": prices[-1]} if prices else {"n": 0}),
                        "would_pay_nothing": sum(1 for r in responses
                                                 if r.get("price_reaction") == "would-not-pay"
                                                 or not r.get("fair_price")),
                        "note": "what personas called fair — not willingness to pay"},
         "intent_by_segment": by_seg}
    if n:
        s["share"] = {a: round(v / n, 3) for a, v in s["intent"].items()}
    return s


ORD = {"no": 0, "maybe": 1, "yes": 2}


def aggregate(d, cfg, roster, scs, results, followups):
    """results: {scenario: {round: {persona: response}}}"""
    by_id = {p["id"]: p for p in roster["personas"]}
    n = len(by_id)
    panel = {"status": "complete", "evidence_class": "simulated", "note": NOTE,
             "personas": n, "rounds": cfg["rounds"],
             "segments": {}, "scenarios": {}, "deltas": {}, "flags": {}}
    for p in roster["personas"]:
        panel["segments"][p["segment"]] = panel["segments"].get(p["segment"], 0) + 1
    for sid, _, label in scs:
        entry = {"label": label}
        for rnd, resp in sorted(results.get(sid, {}).items()):
            entry[f"r{rnd}"] = summarize(list(resp.values()), by_id)
        if sid == "base" and 2 in results.get("base", {}):
            r1, r2 = results["base"][1], results["base"][2]
            declared = sum(1 for r in r2.values() if r.get("changed"))
            moved = sum(1 for p in r2 if p in r1 and r2[p]["intent"] != r1[p]["intent"])
            entry["changed_declared"] = declared
            entry["intent_changed"] = moved
            entry["intent_changed_share"] = round(moved / n, 3) if n else 0
        panel["scenarios"][sid] = entry
    base1 = results.get("base", {}).get(1, {})
    for sid, _, _ in scs[1:]:
        alt = results.get(sid, {}).get(1, {})
        common = [p for p in alt if p in base1]
        if not common:
            continue
        share = lambda resp, key, val: sum(1 for p in common if resp[p][key] == val) / len(common)  # noqa: E731
        shift = {"more_positive": 0, "same": 0, "more_negative": 0}
        for p in common:
            dlt = ORD[alt[p]["intent"]] - ORD[base1[p]["intent"]]
            shift["more_positive" if dlt > 0 else "more_negative" if dlt < 0 else "same"] += 1
        obj = {c: sum(1 for p in common if alt[p]["objection_category"] == c)
               - sum(1 for p in common if base1[p]["objection_category"] == c)
               for c in vq.OBJECTION_CATEGORIES}
        panel["deltas"][sid] = {
            "vs": "base", "personas": len(common),
            "yes_share_pp": round(100 * (share(alt, "intent", "yes") - share(base1, "intent", "yes")), 1),
            "no_share_pp": round(100 * (share(alt, "intent", "no") - share(base1, "intent", "no")), 1),
            "would_not_pay_pp": round(100 * (share(alt, "price_reaction", "would-not-pay")
                                             - share(base1, "price_reaction", "would-not-pay")), 1),
            "same_persona_shift": shift,
            # Fewer movers than this and the shift is indistinguishable from one
            # persona answering differently on another day.
            "within_noise": (shift["more_positive"] + shift["more_negative"])
            < max(vq.NOISE_MIN_PERSONAS, round(vq.NOISE_SHARE * len(common))),
            "objection_category_change": {c: v for c, v in obj.items() if v},
        }
    flags = panel["flags"]
    b1 = panel["scenarios"].get("base", {}).get("r1", {})
    if b1.get("n"):
        flags["implausible_positivity"] = b1["share"]["yes"] >= vq.FLAG_POSITIVITY_YES_SHARE
        top_intent = max(b1["intent"].values()) / b1["n"]
        top_obj = max(b1["objection_category"].values()) / b1["n"]
        flags["homogeneous"] = (top_intent >= vq.FLAG_HOMOGENEOUS_SHARE
                                or top_obj >= vq.FLAG_HOMOGENEOUS_OBJECTION)
    base_entry = panel["scenarios"].get("base", {})
    if "intent_changed_share" in base_entry:
        flags["herding"] = base_entry["intent_changed_share"] > vq.FLAG_HERDING_CHANGED_SHARE
        # Nobody moved at all: round 2 added no information (and may show the
        # "stay put" instruction outweighing the digest). Say so; don't read it
        # as conviction.
        flags["static_round2"] = (base_entry["intent_changed"] == 0
                                  and base_entry["changed_declared"] == 0)
    flags["thin_segments"] = sorted(s for s, c in panel["segments"].items()
                                    if c < vq.FLAG_THIN_SEGMENT)
    # Echo: objections that restate the persona's own card.
    base_stim = Path(scs[0][1]).read_text() if scs and Path(scs[0][1]).exists() else ""
    stim_words = vq.content_tokens(base_stim)
    echoes = []
    for pid, resp in sorted(results.get("base", {}).get(1, {}).items()):
        p = by_id.get(pid)
        if not p:
            continue
        card = " ".join([str(p.get("constraints", "")), str(p.get("current_alternative", "")),
                         str(p.get("job_to_be_done", ""))] + list(p.get("voice") or []))
        obj = vq.content_tokens(resp.get("objection")) - stim_words
        shared = obj & (vq.content_tokens(card) - stim_words)
        if obj and len(shared) >= vq.ECHO_MIN_SHARED and len(shared) / len(obj) >= vq.ECHO_OVERLAP:
            echoes.append(pid)
    panel["echo"] = {"personas": echoes,
                     "share": round(len(echoes) / n, 3) if n else 0,
                     "rule": (f"objection shares >= {vq.ECHO_OVERLAP:.0%} of its content words "
                              f"(and >= {vq.ECHO_MIN_SHARED}) with the persona's own card, "
                              "ignoring words in the stimulus")}
    if b1.get("n"):
        flags["echo_heavy"] = panel["echo"]["share"] >= vq.FLAG_ECHO_SHARE
    panel["followups"] = {"count": len(followups),
                          "personas": [f["persona"] for f in followups],
                          "files": [str(Path(d, "followups", f"{f['persona']}.json")) for f in followups]}
    merge_facts(cfg.get("facts", FACTS), cfg["panel_id"], panel)
    return panel


def mark_reopened(d):
    """`next` asked for more work after a DONE: the stored results describe a
    panel that no longer exists, so they may not be cited as complete."""
    if LAST["action"] in (None, "DONE"):
        return
    c = load_json(cfg_path(d))
    if not c or "__invalid__" in c:
        return
    facts = load_json(c.get("facts", FACTS)) or {}
    entry = facts.get(c["panel_id"])
    if isinstance(entry, dict) and entry.get("status") == "complete":
        entry["status"] = "stale"
        entry["stale_reason"] = f"panel reopened ({LAST['action']}); run next until DONE"
        merge_facts(c.get("facts", FACTS), c["panel_id"], entry)


def merge_facts(path, key, value):
    p = Path(path)
    facts = load_json(p) or {}
    if "__invalid__" in facts:
        facts = {}
    facts[key] = value
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(facts, indent=2, ensure_ascii=False))


# ── the state machine ────────────────────────────────────────────────────────

def cmd_next(d):
    cfg = load_cfg(d)
    d = Path(d)
    scs, errs = scenarios(d)
    if scs is None and not errs:
        return out("WRITE-STIMULUS", agent="product-owner", mode="STIMULUS",
                   outputs=[str(d / "stimulus.md"), str(d / "scenarios.json") + " (optional)"],
                   templates=[".harness/templates/panel-stimulus.md",
                              ".harness/templates/panel-scenarios.json"],
                   inputs=[SEED],
                   reason="No stimulus yet: write the neutral concept card the panel is shown.")
    errs = errs + (check_stimuli(scs) if scs else [])
    if errs:
        return out("FIX-STIMULUS", agent="product-owner", mode="STIMULUS", errors=errs)

    if not Path(DESK).exists():
        return out("WAIT-DESK", reason=f"{DESK} does not exist yet. Personas are grounded in desk "
                   "evidence, so run the DESK stage first, then call next again.")

    seed_for_roster = d / "seed-for-roster.md"
    if newer(seed_for_roster, SEED):
        seed_for_roster.write_text(vq.strip_sections(seed_text())[0])
    desk_for_roster = d / "desk-for-roster.md"
    if newer(desk_for_roster, DESK):
        desk_for_roster.write_text(vq.desk_for_roster(Path(DESK).read_text()))
    roster, rerrs = check_roster(d, cfg.get("size"))
    if roster is None and rerrs == ["roster.json missing"]:
        return out("WRITE-ROSTER", agent="business-analyst", mode="PANEL",
                   outputs=[str(d / "roster.json")], template=".harness/templates/panel-roster.json",
                   inputs=[str(seed_for_roster), str(desk_for_roster)], size=cfg["size"],
                   reason="Build the panel from the seed (hypotheses removed) and the desk evidence.")
    if rerrs:
        return out("FIX-ROSTER", agent="business-analyst", mode="PANEL",
                   output=str(d / "roster.json"), errors=rerrs)

    people = roster["personas"]
    results, tasks = {}, []
    for sid, stim, _ in scs:
        results[sid] = {1: {}}
        for p in people:
            outp = d / "responses" / sid / f"r1-{p['id']}.json"
            brief = d / "inputs" / f"{sid}-r1-{p['id']}.md"
            if newer(brief, stim, d / "roster.json"):
                write_brief(brief, f"{sid} round 1", brief_r1(d, p, sid, stim, outp))
            note_brief(brief)
            r, e = check_response(outp, p["id"], sid, 1)
            if not e and stale(outp, brief):
                e = [STALE]
            if e:
                tasks.append({"persona": p["id"], "scenario": sid, "round": 1, "input": str(brief),
                              "output": str(outp), **({"fix": e} if e != ["missing"] else {})})
            else:
                results[sid][1][p["id"]] = r
    if BRIEF_LEAKS:
        return out("FIX-LEAK", agent="product-owner|business-analyst|product-manager",
                   errors=sorted(set(BRIEF_LEAKS)),
                   reason="A panelist brief would show our hypotheses or template guidance. "
                          "Fix the source it came from — the stimulus (product-owner, "
                          "STIMULUS), the roster (business-analyst, PANEL) or the process "
                          "flows (product-manager) — then call next again. No panelist runs "
                          "until every brief is clean.")
    if tasks:
        return out("RESPOND", agent="panelist", tasks=tasks,
                   reason=f"{len(tasks)} round-1 answer(s) missing or invalid. Give each panelist "
                          "ONLY its input file; run them in parallel batches.")

    base_stim = scs[0][1]
    if cfg["rounds"] == 2:
        digest = d / "digest.md"
        r1_files = [d / "responses" / "base" / f"r1-{p['id']}.json" for p in people]
        if newer(digest, *r1_files, d / "roster.json") or not (d / "digests").exists():
            build_digest(d, list(results["base"][1].values()))
        results["base"][2] = {}
        for p in people:
            outp = d / "responses" / "base" / f"r2-{p['id']}.json"
            brief = d / "inputs" / f"base-r2-{p['id']}.md"
            r1p = d / "responses" / "base" / f"r1-{p['id']}.json"
            own_digest = d / "digests" / f"{p['id']}.md"
            if newer(brief, own_digest, r1p, base_stim, d / "roster.json"):
                write_brief(brief, "base round 2",
                            brief_r2(d, p, base_stim, r1p, own_digest, outp))
            note_brief(brief, persona_card(p), Path(base_stim).read_text())
            r, e = check_response(outp, p["id"], "base", 2)
            if not e and stale(outp, brief):
                e = [STALE]
            if e:
                tasks.append({"persona": p["id"], "scenario": "base", "round": 2,
                              "input": str(brief), "output": str(outp),
                              **({"fix": e} if e != ["missing"] else {})})
            else:
                results["base"][2][p["id"]] = r
        if BRIEF_LEAKS:
            return out("FIX-LEAK", agent="product-owner|business-analyst|product-manager",
                   errors=sorted(set(BRIEF_LEAKS)),
                       reason="A round-2 brief would show our hypotheses; fix its source.")
        if tasks:
            return out("REVISE", agent="panelist", tasks=tasks,
                       reason=f"{len(tasks)} round-2 answer(s) missing or invalid.")

    final_round = 2 if cfg["rounds"] == 2 else 1
    sel_path = d / "followups" / "selection.json"
    final_files = [d / "responses" / "base" / f"r{final_round}-{p['id']}.json" for p in people]
    if newer(sel_path, *final_files, d / "roster.json"):
        sel_path.parent.mkdir(parents=True, exist_ok=True)
        sel_path.write_text(json.dumps(pick_followups(
            list(results["base"][final_round].values()), min(cfg["followups"], len(people))),
            indent=2, ensure_ascii=False))
    by_id = {p["id"]: p for p in people}
    selection = [f for f in json.loads(sel_path.read_text()) if f.get("persona") in by_id]
    for f in selection:
        pid = f["persona"]
        outp = d / "followups" / f"{pid}.json"
        brief = d / "inputs" / f"followup-{pid}.md"
        prev = [d / "responses" / "base" / f"r{k}-{pid}.json" for k in range(1, final_round + 1)]
        if newer(brief, sel_path, d / "roster.json", *prev):
            write_brief(brief, "follow-up interview",
                        brief_followup(by_id[pid], base_stim, prev, outp, f["objection"]))
        note_brief(brief, persona_card(by_id[pid]), Path(base_stim).read_text())
        _, e = check_followup(outp, pid)
        if not e and stale(outp, brief):
            e = [STALE]
        if e:
            tasks.append({"persona": pid, "mode": "FOLLOWUP", "input": str(brief), "output": str(outp),
                          **({"fix": e} if e != ["missing"] else {})})
    if BRIEF_LEAKS:
        return out("FIX-LEAK", agent="product-owner|business-analyst|product-manager",
                   errors=sorted(set(BRIEF_LEAKS)),
                   reason="A follow-up brief would show our hypotheses; fix its source.")
    if tasks:
        return out("FOLLOWUP", agent="panelist", tasks=tasks,
                   reason="Interview the personas with the strongest objections.")

    panel = aggregate(d, cfg, roster, scs, results, selection)
    raised = [k for k, v in panel["flags"].items() if v]
    return out("DONE", facts=cfg.get("facts", FACTS), key=cfg["panel_id"], flags_raised=raised,
               reason="Panel complete. The synthesis must address every raised flag in §7 and "
                      "compare scenarios only within this panel.")


# ── walkthrough (discover phase): personas walk the process flows ───────────

def flow_ids(path):
    return sorted(set(re.findall(r"\bPF-\d{2}\b", Path(path).read_text())) - {"PF-00"})


def walk_sample(people, k):
    by_seg = {}
    for p in people:
        by_seg.setdefault(p["segment"], []).append(p)
    picked, i = [], 0
    while len(picked) < min(k, len(people)):
        for seg in sorted(by_seg):
            if i < len(by_seg[seg]) and len(picked) < k:
                picked.append(by_seg[seg][i])
        i += 1
    return sorted(picked, key=lambda p: p["id"])


def check_walkthrough(path, persona, flows):
    r = load_json(path)
    if r is None:
        return None, ["missing"]
    if "__invalid__" in r:
        return None, [r["__invalid__"]]
    errs = []
    if r.get("persona") != persona:
        errs.append(f"persona is '{r.get('persona')}', expected '{persona}'")
    seen = set()
    flows_in = r.get("flows") or []
    if not isinstance(flows_in, list) or not all(isinstance(f, dict) for f in flows_in) or \
            not all(isinstance(st, dict) for f in flows_in for st in (f.get("steps") or [])):
        return None, ["'flows' must be a list of objects, each with a list of step objects"]
    for f in flows_in:
        fid = f.get("flow_id")
        if fid not in flows:
            errs.append(f"flow_id '{fid}' is not in the process flows")
        seen.add(fid)
        for s in f.get("steps") or []:
            if not str(s.get("step") or "").strip():
                errs.append(f"{fid}: a step has no 'step' text")
            if not isinstance(s.get("ok"), bool) or not isinstance(s.get("would_abandon"), bool):
                errs.append(f"{fid}: 'ok' and 'would_abandon' must be true/false")
            if not s.get("ok") and s.get("severity") not in vq.SEVERITY:
                errs.append(f"{fid}: a step that is not ok needs severity {list(vq.SEVERITY)}")
    for fid in flows:
        if fid not in seen:
            errs.append(f"flow {fid} not walked")
    return r, errs


def cmd_walkthrough(d, flows_path, sample):
    if not cfg_path(d).exists():
        return out("SKIP", reason="No validation panel in this project (run the `validate` "
                   "skill first); walkthrough skipped.")
    cfg = load_cfg(d)
    d = Path(d)
    roster, rerrs = check_roster(d, cfg.get("size"))
    if rerrs:
        return out("SKIP", reason="No valid validation panel in this project (run the `validate` "
                   f"skill first); walkthrough skipped. Roster problems: {rerrs[:3]}")
    if not Path(flows_path).exists():
        return out("SKIP", reason=f"{flows_path} does not exist yet.")
    flows = flow_ids(flows_path)
    people = walk_sample(roster["personas"], sample)
    tasks, results = [], {}
    schema = json.dumps({"persona": "<id>", "flows": [{"flow_id": "PF-01", "steps": [
        {"step": "<step as named in the flow>", "ok": True, "friction": None, "severity": None,
         "would_abandon": False}]}]}, indent=2)
    for p in people:
        outp = d / "walkthroughs" / f"{p['id']}.json"
        brief = d / "inputs" / f"walkthrough-{p['id']}.md"
        if newer(brief, flows_path, d / "roster.json"):
            write_brief(brief, "process-flow walkthrough",
                        f"You are persona {p['id']}.\n\n{persona_card(p)}\n\n{RULES}\n\n"
                        "## What you are doing\n\nBelow are the journeys of a product you are "
                        "trying out. Walk each journey step by step as yourself. At each step say "
                        "whether it would work for you; if not, what gets in the way, how bad it "
                        "is, and whether you would give up there.\n\n"
                        f"## The journeys\n\n{Path(flows_path).read_text().strip()}\n\n"
                        f"## Write\n\nWalk every flow ({', '.join(flows)}). Write ONLY JSON "
                        f"of this shape to `{outp}` (persona '{p['id']}'):\n\n```json\n{schema}\n```\n")
        note_brief(brief, persona_card(p), Path(flows_path).read_text())
        r, e = check_walkthrough(outp, p["id"], flows)
        if not e and stale(outp, brief):
            e = [STALE]
        if e:
            tasks.append({"persona": p["id"], "mode": "WALKTHROUGH", "input": str(brief),
                          "output": str(outp), **({"fix": e} if e != ["missing"] else {})})
        else:
            results[p["id"]] = r
    if BRIEF_LEAKS:
        return out("FIX-LEAK", agent="product-owner|business-analyst|product-manager",
                   errors=sorted(set(BRIEF_LEAKS)),
                   reason="A walkthrough brief would show our hypotheses or template guidance: "
                          "fix the process flows (product-manager) or the roster.")
    if tasks:
        return out("WALKTHROUGH", agent="panelist", tasks=tasks,
                   reason=f"{len(tasks)} walkthrough(s) missing or invalid.")
    summary = {"status": "complete", "evidence_class": "simulated", "personas": len(results),
               "note": "Personas walking the documented flows. Finds friction to fix in the "
                       "flows; does not predict real usage.", "flows": {}}
    md = ["# Persona walkthrough of the process flows", "",
          "Generated by `panel.py walkthrough-next`. Simulated; use it to find friction, "
          "not to predict usage.", ""]
    for fid in flows:
        steps = {}
        abandon = set()
        for pid, r in results.items():
            for f in r["flows"]:
                if f["flow_id"] != fid:
                    continue
                for s in f["steps"]:
                    key = norm(s["step"])
                    e = steps.setdefault(key, {"step": s["step"], "friction": 0, "high": 0,
                                               "abandon": 0, "notes": []})
                    if not s["ok"]:
                        e["friction"] += 1
                        e["high"] += s.get("severity") == "high"
                        if s.get("friction"):
                            e["notes"].append(f"{pid}: {s['friction']}")
                    if s["would_abandon"]:
                        e["abandon"] += 1
                        abandon.add(pid)
        worst = sorted(steps.values(), key=lambda e: (-e["abandon"], -e["high"], -e["friction"]))
        summary["flows"][fid] = {"personas_abandoning": len(abandon),
                                 "steps_with_friction": sum(1 for e in steps.values() if e["friction"]),
                                 "worst_steps": [{k: e[k] for k in ("step", "friction", "high", "abandon")}
                                                 for e in worst[:3] if e["friction"] or e["abandon"]]}
        md.append(f"## {fid} — {len(abandon)} of {len(results)} personas would give up")
        for e in worst:
            if e["friction"] or e["abandon"]:
                md.append(f"- **{e['step']}** — friction {e['friction']}, high {e['high']}, "
                          f"abandon {e['abandon']}")
                md += [f"  - {n}" for n in e["notes"][:4]]
        md.append("")
    Path(d, "walkthrough-summary.md").write_text("\n".join(md))
    merge_facts(cfg.get("facts", FACTS), "walkthrough", summary)
    return out("DONE", summary=str(d / "walkthrough-summary.md"), facts_key="walkthrough",
               reason="Send the summary to the product-manager as input to the flows.")


# ── compare two independent panels ───────────────────────────────────────────

def cmd_compare(a, b):
    if Path(a).resolve() == Path(b).resolve():
        print("ERROR: compare needs two different panel folders")
        return 1
    ca, cb = load_cfg(a), load_cfg(b)
    if ca["panel_id"] == cb["panel_id"] and ca.get("facts", FACTS) == cb.get("facts", FACTS):
        print("ERROR: both folders write the same panel id to the same facts file — "
              "initialise the second panel with its own --panel-id")
        return 1
    pa = (load_json(ca.get("facts", FACTS)) or {}).get(ca["panel_id"])
    pb = (load_json(cb.get("facts", FACTS)) or {}).get(cb["panel_id"])
    if not pa or not pb or pa.get("status") != "complete" or pb.get("status") != "complete":
        print("ERROR: both panels must be complete (run `next` until DONE on each)")
        return 1
    ra, rb = pa["scenarios"]["base"]["r1"], pb["scenarios"]["base"]["r1"]
    top = lambda r: {c for c, _ in sorted(r["objection_category"].items(),  # noqa: E731
                                           key=lambda kv: -kv[1])[:3] if _}
    ta, tb = top(ra), top(rb)
    var = {"panels": [ca["panel_id"], cb["panel_id"]],
           "yes_share_abs_diff_pp": round(100 * abs(ra["share"]["yes"] - rb["share"]["yes"]), 1),
           "no_share_abs_diff_pp": round(100 * abs(ra["share"]["no"] - rb["share"]["no"]), 1),
           "top3_objection_overlap": round(len(ta & tb) / len(ta | tb), 2) if ta | tb else None}
    merge_facts(ca.get("facts", FACTS), "panel_variance", var)
    print(json.dumps(var, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--dir", default=DEFAULT_DIR)
    i.add_argument("--size", type=int, default=12)
    i.add_argument("--rounds", type=int, choices=[1, 2], default=2)
    i.add_argument("--followups", type=int, default=3)
    i.add_argument("--panel-id", default="panel")
    i.add_argument("--facts", default=FACTS)
    n = sub.add_parser("next")
    n.add_argument("--dir", default=DEFAULT_DIR)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    w = sub.add_parser("walkthrough-next")
    w.add_argument("--dir", default=DEFAULT_DIR)
    w.add_argument("--flows", default="docs/02d-process-flows.md")
    w.add_argument("--sample", type=int, default=6)
    a = ap.parse_args()

    if a.cmd == "init":
        if not vq.PANEL_MIN <= a.size <= vq.PANEL_MAX:
            print(f"ERROR: --size must be {vq.PANEL_MIN}–{vq.PANEL_MAX}")
            return 1
        d = Path(a.dir)
        d.mkdir(parents=True, exist_ok=True)
        cfg = {"panel_id": a.panel_id, "size": a.size, "rounds": a.rounds,
               "followups": max(0, a.followups), "facts": a.facts}
        cfg_path(d).write_text(json.dumps(cfg, indent=2))
        merge_facts(a.facts, a.panel_id, {"status": "incomplete", "evidence_class": "simulated",
                                          "note": NOTE})
        print(json.dumps({"initialized": str(d), **cfg}, indent=2))
        return 0
    if a.cmd == "next":
        code = cmd_next(a.dir)
        mark_reopened(a.dir)
        return code
    if a.cmd == "compare":
        return cmd_compare(a.a, a.b)
    if a.cmd == "walkthrough-next":
        return cmd_walkthrough(a.dir, a.flows, a.sample)
    return 1


if __name__ == "__main__":
    sys.exit(main())
