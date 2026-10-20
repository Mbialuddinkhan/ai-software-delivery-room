#!/usr/bin/env python3
"""v3.8 microservices and cloud: the user decides the architecture and the
portability strategy with costs in front of them; services stay independent
and connected only by tested contracts; ASDR tests on the cloud the user chose,
with approval, a time-to-live and a teardown, and proves cloud = local."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
T = REPO / "templates"

EVID = 'docs/01-product-brief.md: "quote"'
CRIT = "\n".join(f"| C{i} | criterion {i} | {s} | {EVID if s else '—'} |"
                 for i, s in enumerate([2, 2, 2, 1, 0, 1, 1, 1], 1))
OPTION = """### Option {L} — {title}

- Pros: fast to build
- Cons: harder to scale one part
- Business impact: first release in 3 months; lower running cost; one team
- Build cost: USD {b} (estimate)
- Run cost per month: USD {r} (estimate)
- When it wins: one team, one release cadence
"""


def arch_doc(rec="B", decision="B", by="Bilal Khan, 2026-10-20", c1_evidence=True):
    crit = CRIT if c1_evidence else CRIT.replace('| C1 | criterion 1 | 2 | docs/01-product-brief.md: "quote" |',
                                                 "| C1 | criterion 1 | 2 | <…> |")
    side = "\n".join(f"| {r} | a | b | c |" for r in ("Time to first release", "Build cost (estimate)", "Run cost per month (estimate)"))
    return f"""# Architecture options — Shop

## 01 · What drives the choice

| # | Criterion | Score | Evidence (document + quoted line) |
|---|---|---|---|
{crit}

## 02 · Options

{OPTION.format(L="A", title="Modular monolith with service-ready boundaries", b="40k–60k", r="300–600")}
{OPTION.format(L="B", title="Microservices", b="90k–140k", r="900–1,600")}
## 03 · Side by side

| | A · Modular monolith | B · Microservices | C |
|---|---|---|---|
{side}

Assumptions behind the figures: 5,000 users, USD 4k per person-week, AWS calculator Oct 2026

## 04 · Recommendation

Recommended: {rec} — scores favour it.

## 05 · Decision

- Decision: {decision}
- Decided by: {by}
- Services (Option B): 2
"""


def port_doc(decision="S2", prod="aws, azure", source="AWS Pricing Calculator and Azure MCP Server, 2026-10-20",
             aws_db="Amazon RDS for PostgreSQL", block="relational-db"):
    return f"""# Portability and cloud services — Shop

- Test cloud (chosen at the start, .harness/cloud.json): aws

## 01 · Building blocks this product needs

| Block | Needed for | Portable choice | AWS | Azure | GCP | Local (standalone) |
|---|---|---|---|---|---|---|
| {block} | orders | PostgreSQL | {aws_db} | Azure Database for PostgreSQL – Flexible Server | n/a | postgres container |
| events | order placed | CloudEvents over NATS | Amazon EventBridge | Azure Event Grid | n/a | nats container |

## 02 · Strategies

### S1 — Portable core

- Pros: easy to move
- Cons: more to run ourselves
- Business impact: lowest exit cost
- Monthly run cost: AWS USD 700–1,100 · Azure USD 750–1,200 (estimates)

### S2 — Native services behind adapters

- Pros: managed services
- Cons: one adapter per cloud
- Business impact: least operations work
- Monthly run cost: AWS USD 600–950 · Azure USD 650–1,000 (estimates)

## 03 · Cost comparison

| Strategy | AWS / month | Azure / month | GCP / month | Build effort | Cost of moving cloud later | Effort to operate |
|---|---|---|---|---|---|---|
| S1 | 700–1,100 | 750–1,200 | n/a | M | low | high |
| S2 | 600–950 | 650–1,000 | n/a | M | medium | low |

- Assumptions: 5,000 users, 2 environments, one region each
- Prices from: {source}

## 04 · Recommendation

Recommended: S2 on aws — fewer things to run.

## 05 · Decision

- Decision: {decision}
- Production cloud(s): {prod}
- Decided by: Bilal Khan, 2026-10-20
"""


def svc_doc(orders_owns="orders, baskets", catalog_owns="products", catalog_calls="none", ct1=True,
            standalone="compose profile orders: own postgres + catalog mock", aws_adapter="Amazon RDS for PostgreSQL"):
    ct = ("| CT-01 | svc-catalog | svc-orders | http | contracts/catalog.openapi.yaml | TC-21 |\n" if ct1 else "")
    return f"""# Services — Shop

## 01 · Services

| Service | Responsibility | Owns data | Calls (sync) | Publishes | Consumes | Standalone run |
|---|---|---|---|---|---|---|
| svc-catalog | products and prices | {catalog_owns} | {catalog_calls} | catalog.price-changed | none | compose profile catalog: own postgres |
| svc-orders | baskets and orders | {orders_owns} | svc-catalog | order.placed | catalog.price-changed | {standalone} |

## 02 · Contracts

| ID | Provider | Consumer | Kind | Contract file | Test case |
|---|---|---|---|---|---|
{ct}| CT-02 | svc-catalog | svc-orders | event: catalog.price-changed | contracts/catalog-events.asyncapi.yaml | TC-22 |

## 03 · Adapters

| Service | Block | Port (interface in the code) | Local | AWS | Azure | GCP |
|---|---|---|---|---|---|---|
| svc-catalog | relational-db | ProductRepository | postgres container | Amazon RDS for PostgreSQL | Azure Database for PostgreSQL – Flexible Server | n/a |
| svc-orders | relational-db | OrderRepository | postgres container | {aws_adapter} | Azure Database for PostgreSQL – Flexible Server | n/a |
"""


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=300)


def last(stdout, tag):
    return json.loads([x for x in stdout.splitlines() if x.startswith(tag + ": ")][-1][len(tag) + 2:])


class Proj(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-cloud-"))
        (self.d / "docs").mkdir()
        (self.d / ".harness/templates/cloud").mkdir(parents=True)
        shutil.copy(T / "cloud/catalogue.json", self.d / ".harness/templates/cloud/catalogue.json")
        (self.d / ".harness/cloud.json").write_text(json.dumps({"test_cloud": "aws"}))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, rel, text):
        p = self.d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


class TestArchitectureOptions(Proj):
    def check(self, text):
        self.write("docs/03c-architecture-options.md", text)
        r = run([str(S / "validate_architecture_options.py")], self.d)
        return r, last(r.stdout, "ARCH-OPTIONS")

    def test_decided_records_the_style(self):
        r, res = self.check(arch_doc())
        self.assertEqual(r.returncode, 0, r.stdout)
        a = json.loads((self.d / ".harness/architecture.json").read_text())
        self.assertEqual((a["option"], a["style"], a["score"], a["rule"]), ("B", "microservices", 10, "microservices"))

    def test_pending_waits_for_the_user(self):
        r, res = self.check(arch_doc(decision="pending"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("ask the user to choose", r.stdout)
        self.assertFalse((self.d / ".harness/architecture.json").exists())

    def test_score_needs_evidence_and_decider(self):
        r, _ = self.check(arch_doc(c1_evidence=False))
        self.assertEqual(r.returncode, 1)
        self.assertIn("C1: a score above 0 needs evidence", r.stdout)
        r, _ = self.check(arch_doc(by="<name>, <date>"))
        self.assertIn("record who decided", r.stdout)

    def test_recommendation_against_the_rule_warns(self):
        r, _ = self.check(arch_doc(rec="A", decision="A"))
        self.assertEqual(r.returncode, 0)
        self.assertIn("differs from the criteria rule", r.stdout)

    def test_the_bare_template_fails(self):
        shutil.copy(T / "architecture-options.md", self.d / "docs/03c-architecture-options.md")
        r = run([str(S / "validate_architecture_options.py")], self.d)
        self.assertEqual(r.returncode, 1)


class TestPortability(Proj):
    def check(self, text):
        self.write("docs/03d-portability.md", text)
        r = run([str(S / "validate_portability.py")], self.d)
        return r, last(r.stdout, "PORTABILITY")

    def test_decided_records_clouds_and_blocks(self):
        r, res = self.check(port_doc())
        self.assertEqual(r.returncode, 0, r.stdout)
        p = json.loads((self.d / ".harness/portability.json").read_text())
        self.assertEqual((p["strategy"], p["production_clouds"], p["test_cloud"]), ("S2", ["aws", "azure"], "aws"))
        self.assertIn("relational-db", p["blocks"])

    def test_pending_waits(self):
        r, _ = self.check(port_doc(decision="pending"))
        self.assertEqual(r.returncode, 2)

    def test_prices_need_source_and_date(self):
        r, _ = self.check(port_doc(source="a website"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("where the prices came from", r.stdout)

    def test_production_cloud_needs_a_service(self):
        r, _ = self.check(port_doc(aws_db="<…>"))
        self.assertIn("no AWS service", r.stdout)

    def test_unknown_block_warns(self):
        r, _ = self.check(port_doc(block="quantum-db"))
        self.assertIn("not in the catalogue", r.stdout)


class TestServices(Proj):
    def setUp(self):
        super().setUp()
        self.write(".harness/architecture.json", json.dumps({"style": "microservices"}))
        self.write(".harness/portability.json", json.dumps({"production_clouds": ["aws", "azure"]}))
        self.write("docs/02e-test-cases.md", "### TC-21 · catalog contract\n### TC-22 · price event\n")
        self.write("contracts/catalog.openapi.yaml", "openapi: 3.1.0\n")
        self.write("contracts/catalog-events.asyncapi.yaml", "asyncapi: 3.0.0\n")

    def check(self, text, *extra):
        self.write("docs/03e-services.md", text)
        r = run([str(S / "validate_services.py"), *extra], self.d)
        return r, last(r.stdout, "SERVICES")

    def test_valid_catalogue(self):
        r, res = self.check(svc_doc(), "--gate")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((res["services"], res["contracts"], res["sync_edges"]),
                         (["svc-catalog", "svc-orders"], ["CT-01", "CT-02"], 1))

    def test_skipped_for_a_monolith(self):
        self.write(".harness/architecture.json", json.dumps({"style": "modular-monolith"}))
        r, res = self.check(svc_doc(orders_owns="products"))
        self.assertEqual(r.returncode, 0)
        self.assertTrue(res["skipped"])

    def test_shared_table_missing_contract_cycle_standalone_adapter(self):
        cases = [
            (dict(orders_owns="orders, products"), "owned by both"),
            (dict(ct1=False), "svc-orders → svc-catalog: synchronous call with no http contract"),
            (dict(catalog_calls="svc-orders"), "synchronous call cycle"),
            (dict(standalone="<…>"), "describe how it runs standalone"),
            (dict(aws_adapter="n/a"), "no AWS adapter"),
        ]
        for kw, needle in cases:
            r, _ = self.check(svc_doc(**kw))
            self.assertEqual(r.returncode, 1, kw)
            self.assertIn(needle, r.stdout, kw)

    def test_contract_files_and_test_cases_are_hard_only_at_the_gate(self):
        (self.d / "contracts/catalog.openapi.yaml").unlink()
        r, _ = self.check(svc_doc())
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARN: CT-01: contract file", r.stdout)
        r, _ = self.check(svc_doc(), "--gate")
        self.assertEqual(r.returncode, 1)

    def test_contracts_are_testable_items(self):
        sample = REPO / "examples/sample-app/docs"
        for f in sample.glob("02*.md"):
            shutil.copy(f, self.d / "docs" / f.name)
        self.write("docs/03e-services.md", svc_doc())
        r = run([str(S / "validate_product_map.py"), "--docs", "docs", "--require-coverage", "--no-write"], self.d)
        self.assertIn("CT-01", r.stdout)


class TestTestCloud(Proj):
    def test_preflight_none_and_not_ready(self):
        self.write(".harness/cloud.json", json.dumps({"test_cloud": "none"}))
        r = run([str(S / "cloud_preflight.py")], self.d)
        self.assertTrue(last(r.stdout, "CLOUD-PREFLIGHT")["ready"] or "docker" in r.stdout)
        self.write(".harness/cloud.json", json.dumps({"test_cloud": "gcp", "region": "<e.g.>", "ttl_hours": 8}))
        empty = self.d / "nobin"
        empty.mkdir()
        r = run([str(S / "cloud_preflight.py")], self.d, env={"PATH": str(empty)})
        res = last(r.stdout, "CLOUD-PREFLIGHT")
        self.assertFalse(res["ready"])
        joined = " ".join(res["reasons"])
        for needle in ("gcloud CLI not installed", "set region", "set budget_usd_per_day", "terraform or tofu"):
            self.assertIn(needle, joined)

    def test_environment_ledger(self):
        env = [str(S / "cloud_env.py")]
        r = run(env + ["create", "--name", "t1", "--cloud", "aws", "--approved-by", " "], self.d)
        self.assertEqual(r.returncode, 1)
        r = run(env + ["create", "--name", "t1", "--cloud", "aws", "--approved-by", "Bilal, 2026-10-20",
                       "--ttl-hours", "0.00001", "--stack", "infra/envs/test-aws"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(run(env + ["create", "--name", "t1", "--cloud", "aws", "--approved-by", "x"], self.d).returncode, 1)
        time.sleep(0.1)
        r = run(env + ["list", "--overdue"], self.d)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(last(r.stdout, "CLOUD-ENVS")["overdue"], ["t1"])
        run(env + ["destroyed", "--name", "t1"], self.d)
        r = run(env + ["list", "--overdue"], self.d)
        self.assertEqual((r.returncode, last(r.stdout, "CLOUD-ENVS")["running"]), (0, []))

    def summary(self, label, url, statuses, commit="abc1234"):
        d = self.d / ".harness/test-results" / label
        d.mkdir(parents=True, exist_ok=True)
        (d / "summary.json").write_text(json.dumps({
            "label": label, "commit": commit, "finished_at": "2026-10-20T10:00:00+00:00",
            "environment": {"base_url": url},
            "suites": [{"name": "pw", "cases": [{"classname": "c", "name": n, "status": s} for n, s in statuses.items()]}]}))

    def test_cloud_parity(self):
        self.summary("local", "http://localhost:3000", {"[TC-01] a": "passed", "[TC-02] b": "passed", "[TC-03] c": "failed"})
        self.summary("cloud-aws", "https://test.example.com", {"[TC-01] a": "passed", "[TC-02] b": "passed"})
        r = run([str(S / "cloud_parity.py"), "--local", "local", "--cloud", "cloud-aws"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("1 test(s) fail locally", r.stdout)
        self.summary("cloud-aws", "https://test.example.com", {"[TC-01] a": "failed"})
        r = run([str(S / "cloud_parity.py"), "--local", "local", "--cloud", "cloud-aws"], self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("passes locally, failed on the cloud", r.stdout)
        self.assertIn("missing on the cloud", r.stdout)
        self.summary("cloud-aws", "http://localhost:3000", {"[TC-01] a": "passed", "[TC-02] b": "passed"}, commit="zzz9999")
        r = run([str(S / "cloud_parity.py"), "--local", "local", "--cloud", "cloud-aws"], self.d)
        self.assertIn("did not target a cloud URL", r.stdout)
        self.assertIn("different commits", r.stdout)
        self.assertFalse(json.loads((self.d / ".harness/cloud-parity.json").read_text())["ok"])

    def test_dashboard_shows_cloud_state(self):
        self.write(".harness/architecture.json", json.dumps({"style": "microservices"}))
        run([str(S / "cloud_env.py"), "create", "--name", "asdr-test-1", "--cloud", "aws", "--approved-by", "B, today",
             "--ttl-hours", "0.00001"], self.d)
        time.sleep(0.1)
        r = run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        h = (self.d / "docs/dashboard/index.html").read_text()
        self.assertIn("past its time-to-live", h)
        self.assertIn("architecture: <b>microservices", h)
        self.assertIn("AT RISK", h)


class TestVendorToolsAndSetup(unittest.TestCase):
    def test_detects_vendor_mcp_servers(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-comp-"))
        try:
            (d / ".mcp.json").write_text(json.dumps({"mcpServers": {
                "azure": {"command": "npx", "args": ["-y", "@azure/mcp@latest", "server", "start"]},
                "tf": {"command": "docker", "args": ["run", "hashicorp/terraform-mcp-server"]}}}))
            r = run([str(S / "detect_companions.py"), "--write", "c.json"], d, env={"HOME": str(d)})
            c = json.loads((d / "c.json").read_text())["cloud"]
            self.assertTrue(c["azure"]["agent_tools"])
            self.assertTrue(c["terraform"]["agent_tools"])
            self.assertEqual(c["aws"]["agent_tools"], [])
            self.assertIn("mcp__aws", c["note"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_init_seeds_cloud_settings(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-init-"))
        try:
            r = run([str(S / "init_asdr.py"), "--source", str(REPO)], d)
            self.assertEqual(r.returncode, 0, r.stdout)
            c = json.loads((d / ".harness/cloud.json").read_text())
            self.assertEqual(c["test_cloud"], "none")
            keys = " ".join(c) + " " + " ".join(c.get("tags", {}))          # no credential field at all
            for word in ("password", "secret", "token", "key_id", "access_key"):
                self.assertNotIn(word, keys.lower())
            for f in ("cloud/catalogue.json", "microservices/README.md", "architecture-options.md", "portability.md",
                      "services.md"):
                self.assertTrue((d / ".harness/templates" / f).is_file(), f)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_catalogue_is_complete(self):
        cat = json.loads((T / "cloud/catalogue.json").read_text())
        self.assertGreaterEqual(len(cat["blocks"]), 15)
        for name, b in cat["blocks"].items():
            for k in ("need", "portable", "aws", "azure", "gcp", "local"):
                self.assertTrue(b.get(k), f"{name}.{k}")
        self.assertEqual(set(cat["vendor_agent_tools"]), {"aws", "azure", "gcp", "terraform"})

    def test_skills_and_agents_carry_the_flow(self):
        asdr = (REPO / "skills/asdr/SKILL.md").read_text()
        for needle in ("Which cloud should ASDR deploy to for testing?", "validate_architecture_options.py",
                       "validate_portability.py", "validate_services.py", "cloud_parity.py", "cloud_env.py create",
                       "No design starts before the user has decided"):
            self.assertIn(needle, asdr)
        self.assertIn("cloud_env.py list", (REPO / "skills/release/SKILL.md").read_text())
        self.assertIn("cloud_env.py list --overdue", (REPO / "skills/riskgate/SKILL.md").read_text())
        for agent, needle in (("solution-architect", "Architecture options — the user decides first"),
                              ("devops", "cloud_env.py create --approved-by"), ("critic", "ASDR could apply to production"),
                              ("evaluator", "validate_services.py --gate"), ("generator", "ports (interfaces)"),
                              ("planner", "walking"), ("risk-manager", "cloud-parity.json"),
                              ("security-compliance", "least-privilege roles")):
            self.assertIn(needle, (REPO / "agents" / f"{agent}.md").read_text(), agent)


if __name__ == "__main__":
    unittest.main()
