#!/usr/bin/env python3
"""Shared vocabulary for idea validation (panel.py and mirofish_validate.py).

One place for the questions and the closed lists, so the native panel and a
MiroFish run ask exactly the same things and their answers stay comparable.
Import with the script directory on sys.path (both scripts do this).
"""
import math
import re as _re
from urllib.parse import urlsplit

# Asked of every persona (panel) and every sampled agent (MiroFish).
DEFAULT_QUESTIONS = [
    "In one or two sentences: what is your honest first reaction to this product?",
    "Would you use it in the next three months? Answer yes, maybe or no, then say why.",
    "At the stated price, would you pay for it? Answer yes, maybe or no, then say "
    "what price would feel fair.",
    "What is the single biggest reason you would NOT use it?",
    "What do you use today instead, and what would make you switch?",
]

# Follow-up interview of the personas with the strongest objections
# (MiroFish's post-run interviews, kept small and pointed).
FOLLOWUP_PROBES = [
    "Walk me through how you handle this today, step by step. Where does it hurt, if anywhere?",
    "You said your biggest reason not to use it was: \"{objection}\". What is behind that?",
    "What would have to be true — about the product, the price or the people behind it — "
    "for you to try it for a month?",
    "Who else would have a say in this decision, and what would they object to?",
]

INTENT = ("yes", "maybe", "no")
PRICE_REACTION = ("cheap", "fair", "expensive", "would-not-pay")
OBJECTION_CATEGORIES = (
    "price", "switching-cost", "trust-privacy", "not-my-problem",
    "missing-capability", "timing-budget", "complexity", "other",
)
BUDGET_AUTHORITY = ("decides", "influences", "none")
TECH_COMFORT = ("low", "medium", "high")
TEMPERAMENT = ("sceptical", "pragmatic", "cost-driven", "risk-averse",
               "curious", "indifferent", "impatient")
# The persona's starting stance toward ANY new product in this category.
STANCE_PRIOR = ("loyal-to-current", "open", "would-never-buy", "early-adopter")
SEVERITY = ("low", "med", "high")

# Roster quotas (shares of the panel). They push against the documented
# acquiescence/positivity bias of LLM personas.
QUOTA_MIN = {"loyal-to-current": 0.25, "would-never-buy": 0.15}
QUOTA_MAX = {"early-adopter": 0.20}
PANEL_MIN, PANEL_MAX = 8, 30

# Flags raised by aggregation; the synthesis must answer every raised flag.
FLAG_POSITIVITY_YES_SHARE = 0.70   # r1 'yes' share at or above → implausible_positivity
FLAG_HERDING_CHANGED_SHARE = 0.30  # r2 stance changes above → herding
FLAG_HOMOGENEOUS_SHARE = 0.85      # one intent value at or above → homogeneous
FLAG_HOMOGENEOUS_OBJECTION = 0.60  # one objection category at or above → homogeneous
FLAG_THIN_SEGMENT = 2              # fewer personas than this in a segment → thin_segment
# A scenario shift is "within noise" when fewer personas moved than this
# (absolute floor, or share of the panel) — a heuristic, not a test.
NOISE_MIN_PERSONAS = 2
NOISE_SHARE = 0.15

# Echo: an objection that mostly restates the persona's own card (its
# constraints, current tool, job, or a grounding quote) is the roster talking,
# not the panel finding something. Measured on content words that are NOT in
# the stimulus, so shared product vocabulary does not count.
ECHO_OVERLAP = 0.5                 # share of the objection's content words found in the card
ECHO_MIN_SHARED = 3
FLAG_ECHO_SHARE = 0.34             # echoing objections at or above this share → echo_heavy

# A roster field that states an attitude plants the answer. The panel must
# find attitudes; the roster describes situations (budget, staff, systems,
# rules they work under). Heuristic markers, checked on the persona fields.
OPINION_MARKERS = (
    r"\bwon'?t\b", r"\bwill not\b", r"\bwould not\b", r"\bwouldn'?t\b",
    r"\bdoes(?: not|n'?t) (?:want|trust|like|believe)\b",
    r"\bdo(?: not|n'?t) (?:want|trust|like|believe)\b",
    r"\brefuses?\b", r"\bdistrusts?\b", r"\breads as\b", r"\bsees? (?:it|them|this|these|tools?|software|bots?) as\b",
    r"\bsk?ceptical of\b", r"\bskeptical of\b", r"\bhates?\b", r"\bdislikes?\b",
    r"\bnot interested\b", r"\bunwilling\b", r"\bwary of\b",
)

_STOP = set("""that this with what from have will would they their there your about which
when were been into only than then them these those also just more most very some such
each other over does doesn't don't can't cannot still even make makes made need needs
being because while where after before every without""".split())


def content_tokens(text):
    """Lower-case content words (4+ letters, crude plural strip), minus stopwords."""
    out = set()
    for w in _re.findall(r"[a-zA-Z][a-zA-Z'\-]+", (text or "").lower()):
        w = w.strip("'-")
        if len(w) < 4 or w in _STOP:
            continue
        if w.endswith("s") and len(w) > 4:
            w = w[:-1]
        out.add(w)
    return out

# Seed sections never shown to a simulation or a persona: our own test
# criteria would become their beliefs (LLM respondents can infer and confirm
# a researcher's hypotheses).
STRIP_HEADING = _re.compile(r"hypothes", _re.IGNORECASE)
# H-01, H-1, H01, H1 — any spelling of a hypothesis id.
# "H1 2027" / "H2 FY26" are half-years, not hypotheses.
HYPOTHESIS_ID = _re.compile(r"\bH-?\d{1,2}\b(?!\s*(?:FY)?'?\d{2,4}\b)")


def strip_sections(markdown):
    """Drop every markdown section whose heading mentions hypotheses.

    Returns (text, removed_headings). A section runs to the next heading of
    the same or a higher level.
    """
    out, removed, skip_level = [], [], None
    for line in markdown.splitlines(keepends=True):
        m = _re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and STRIP_HEADING.search(m.group(2)):
                skip_level = level
                removed.append(m.group(2).strip())
                continue
        if skip_level is None:
            out.append(line)
    return "".join(out), removed


def _norm(s):
    return _re.sub(r"\s+", " ", str(s)).strip().lower()


def hypothesis_texts(seed_markdown):
    """Hypothesis and refutation strings from the seed's hypotheses table."""
    texts = []
    in_section = False
    for line in seed_markdown.splitlines():
        m = _re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            in_section = bool(STRIP_HEADING.search(m.group(2)))
            continue
        if in_section and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and HYPOTHESIS_ID.fullmatch(cells[0] or ""):
                texts += [c for c in cells[1:] if len(_norm(c)) >= 20]
    return texts


def leaks(text, seed_markdown, brief=False):
    """Problems if `text` carries hypothesis ids or hypothesis wording.

    Exact wording, and paraphrase: a single line sharing most of a
    hypothesis's content words. `brief=True` also rejects HTML comments,
    which in our templates carry guidance a persona must not see.
    """
    found = []
    m = HYPOTHESIS_ID.search(text)
    if m:
        found.append(f"contains a hypothesis id ('{m.group(0)}')")
    if brief and "<!--" in text:
        found.append("contains an HTML comment (template guidance)")
    nt = _norm(text)
    lines = [content_tokens(line) for line in _re.split(r"[\n.;!?]+", text)]
    for h in hypothesis_texts(seed_markdown):
        if _norm(h) in nt:
            found.append(f"repeats hypothesis wording: \"{h[:60]}\"")
            continue
        ht = content_tokens(h)
        if len(ht) < 4:
            continue
        need = max(4, math.ceil(PARAPHRASE_SHARE * len(ht)))
        if any(len(ht & lt) >= need for lt in lines):
            found.append(f"paraphrases a hypothesis: \"{h[:60]}\"")
    return found


PARAPHRASE_SHARE = 0.6   # of a hypothesis's content words, on one line → paraphrase


def _table_rows(markdown):
    for line in markdown.splitlines():
        t = line.strip()
        if t.startswith("|") and t.endswith("|"):
            yield [c.strip() for c in t.strip("|").split("|")]


def desk_for_roster(desk_markdown):
    """The desk evidence as the roster builder may see it: no hypothesis
    column, no Gaps section, no HTML comments — only what the sources show."""
    text = _re.sub(r"<!--.*?-->", "", desk_markdown, flags=_re.DOTALL)
    out, drop_col, skip_level = [], None, None
    for line in text.splitlines():
        m = _re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and _re.search(r"\bgaps?\b", m.group(2), _re.IGNORECASE):
                skip_level = level
                continue
        if skip_level is not None:
            continue
        t = line.strip()
        if t.startswith("|") and t.endswith("|"):
            cells = [c.strip() for c in t.strip("|").split("|")]
            if drop_col is None or len(cells) <= (drop_col or 0):
                hdr = [i for i, c in enumerate(cells) if _re.search(r"hypothes", c, _re.IGNORECASE)]
                if hdr:
                    drop_col = hdr[0]
            if drop_col is not None and drop_col < len(cells):
                cells = cells[:drop_col] + cells[drop_col + 1:]
            line = "| " + " | ".join(cells) + " |"
        out.append(line)
    return "\n".join(out) + "\n"


def desk_quote_text(desk_markdown):
    """The text a 'real public quote' may come from: the 'What it shows'
    cells (or, if that header is missing, every cell but id/URL/date/
    hypothesis) of the desk evidence tables — not Gaps, not comments."""
    cells_out, col = [], None
    for cells in _table_rows(desk_for_roster(desk_markdown)):
        idx = [i for i, c in enumerate(cells) if _re.search(r"what it shows", c, _re.IGNORECASE)]
        if idx:
            col = idx[0]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if col is not None and col < len(cells):
            cells_out.append(cells[col])
        elif col is None:
            cells_out += cells[1:]
    return "\n".join(cells_out)


def same_endpoint(a, b):
    """True when two URLs name the same local service (localhost == 127.0.0.1 == ::1)."""
    def key(u):
        p = urlsplit(str(u or "").strip())
        host = (p.hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            host = "127.0.0.1"
        return (p.scheme or "http", host, p.port or (443 if p.scheme == "https" else 80))
    return bool(a) and bool(b) and key(a) == key(b)
