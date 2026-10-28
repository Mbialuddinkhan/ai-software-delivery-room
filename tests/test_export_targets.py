#!/usr/bin/env python3
"""v4.1: ASDR exported to Codex CLI (skills + custom-agent TOML) and Gemini CLI
(an extension with skills, subagents and commands). The formats checked here
are the ones the CLIs load: Codex custom agents (name, description,
developer_instructions; optional model and [features]) and Gemini's strict
subagent frontmatter (kind, name, description, tools, model, max_turns,
timeout_mins). Both were also loaded by the real CLIs when this was written
(Codex 0.165 listed the 19 roles and 8 skills; Gemini 0.66 loaded 19 agents and
8 skills from the extension)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
VERSION = json.loads((REPO / ".claude-plugin/plugin.json").read_text())["version"]
ROLES = sorted(p.stem for p in (REPO / "agents").glob("*.md"))
SKILLS = sorted(p.parent.name for p in (REPO / "skills").glob("*/SKILL.md"))
GEMINI_KEYS = {"kind", "name", "description", "display_name", "tools", "mcp_servers", "model", "temperature",
               "max_turns", "timeout_mins"}
GEMINI_TOOLS = {"read_file", "read_many_files", "list_directory", "write_file", "replace", "run_shell_command",
                "glob", "grep_search", "google_web_search", "web_fetch"}
try:
    import tomllib
except ImportError:                    # Python < 3.11
    tomllib = None


def run(args, cwd=None, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=300)


def front(text):
    assert text.startswith("---\n"), text[:40]
    fm, body = text[4:].split("\n---\n", 1)
    keys = [ln.split(":", 1)[0] for ln in fm.splitlines() if ln and not ln.startswith((" ", "-"))]
    return fm, keys, body


def exported(name):
    return name if name == "asdr" else f"asdr-{name}"


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-export-"))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def export(self, host, *extra, out=None):
        out = out or self.d / host
        r = run([str(S / "export_targets.py"), host, "--out", str(out), *extra])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return out, r


class TestSkills(Base):
    def test_both_hosts_get_every_skill_renamed_and_adapted(self):
        for host in ("codex", "gemini"):
            out, _ = self.export(host)
            dirs = sorted(p.name for p in (out / "skills").iterdir())
            self.assertEqual(dirs, sorted(exported(s) for s in SKILLS))
            for d in dirs:
                text = (out / "skills" / d / "SKILL.md").read_text()
                fm, keys, body = front(text)
                name = re.search(r"^name: (.+)$", fm, re.M).group(1)
                self.assertEqual(name, d, "Agent Skills: name must match the folder")
                self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
                self.assertLessEqual(len(name), 64)
                desc = json.loads(re.search(r"^description: (.+)$", fm, re.M).group(1))
                self.assertTrue(0 < len(desc) <= 1024, d)
                self.assertNotIn("<example>", desc)
                self.assertIn(f'version: "{VERSION}"', fm)
                self.assertIn(f"Running in {'Codex CLI' if host == 'codex' else 'Gemini CLI'}", body)
                self.assertIn("**PLUGIN_ROOT** is", body)
                self.assertIn("Claude-only features", body)
                for m in re.findall(r"skills/([a-z][a-z0-9-]*)/SKILL\.md", body):
                    self.assertTrue(m == "asdr" or m.startswith("asdr-"), f"{d}: unprefixed path skills/{m}/")
            self.assertTrue((out / "skills/asdr/references").is_dir(), "skill resources travel with the skill")

    def test_runtime_is_complete_and_initialises_a_project(self):
        out, _ = self.export("codex")
        for p in ("scripts/init_asdr.py", "scripts/entry_point.py", "templates", ".claude-plugin/plugin.json",
                  "CHANGELOG.md", "LICENSE"):
            self.assertTrue((out / p).exists(), p)
        self.assertFalse(list(out.rglob("__pycache__")))
        proj = self.d / "proj"
        proj.mkdir()
        r = run([str(out / "scripts/init_asdr.py"), "--source", str(out)], cwd=proj)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((proj / ".harness/scripts/entry_point.py").is_file())
        self.assertTrue((proj / ".harness/templates").is_dir())


class TestCodexAgents(Base):
    def test_one_valid_agent_per_role(self):
        out, _ = self.export("codex")
        files = sorted(p.name for p in (out / "agents").glob("*.toml"))
        self.assertEqual(files, sorted(f"asdr-{r}.toml" for r in ROLES))
        for r in ROLES:
            text = (out / "agents" / f"asdr-{r}.toml").read_text()
            self.assertIn("exported by ASDR", text.splitlines()[0])
            self.assertNotIn("\nmodel = ", text, "no model is named unless --models is given")
            if tomllib:
                doc = tomllib.loads(text)
                self.assertEqual(doc["name"], f"asdr-{r}")
                self.assertTrue(doc["description"])
                self.assertIn("Codex custom agent exported from ASDR", doc["developer_instructions"])
                self.assertGreater(len(doc["developer_instructions"]), 500)
            else:
                self.assertIn(f'name = "asdr-{r}"', text)
                self.assertEqual(text.count("'''"), 2)
        judge = (out / "agents/asdr-judge.toml").read_text()
        gen = (out / "agents/asdr-generator.toml").read_text()
        # Codex reads files through its shell, so no role loses it; a Claude role without Bash is told to read only.
        self.assertNotIn("shell_tool", judge + gen)
        self.assertIn("use shell commands here only to read and search files", judge)
        self.assertNotIn("only to read and search", gen)
        self.assertTrue((out / "plugin.json").is_file())
        self.assertEqual(json.loads((out / "plugin.json").read_text())["version"], VERSION)

    def test_model_plan_maps_to_host_models(self):
        out, _ = self.export("codex", "--plan", "economy", "--models", "opus=big-model,sonnet=mid-model,haiku=small-model")
        def model(role):
            m = re.search(r'^model = "(.+)"$', (out / "agents" / f"asdr-{role}.toml").read_text(), re.M)
            return m.group(1) if m else None
        self.assertEqual(model("critic"), "big-model")
        self.assertEqual(model("evaluator"), "big-model")
        self.assertEqual(model("product-owner"), "mid-model")
        self.assertEqual(model("panelist"), "small-model")
        self.assertIn("**economy** plan", (out / "skills/asdr/SKILL.md").read_text())

    def test_bad_models_spec_is_rejected(self):
        r = run([str(S / "export_targets.py"), "codex", "--out", str(self.d / "x"), "--models", "gpt=foo"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--models takes tier=model pairs", r.stdout + r.stderr)


class TestGemini(Base):
    def test_extension_agents_and_commands(self):
        out, _ = self.export("gemini")
        ext = json.loads((out / "gemini-extension.json").read_text())
        self.assertEqual(ext["name"], "asdr")
        self.assertEqual(ext["version"], VERSION)
        self.assertEqual(ext["contextFileName"], "GEMINI.md")
        self.assertTrue((out / "GEMINI.md").is_file())
        agents = sorted(p.name for p in (out / "agents").glob("*.md"))
        self.assertEqual(agents, sorted(f"asdr-{r}.md" for r in ROLES))
        for r in ROLES:
            fm, keys, body = front((out / "agents" / f"asdr-{r}.md").read_text())
            self.assertTrue(set(keys) <= GEMINI_KEYS, f"{r}: Gemini rejects unknown keys: {set(keys) - GEMINI_KEYS}")
            self.assertRegex(re.search(r"^name: (.+)$", fm, re.M).group(1), r"^[a-z0-9-_]+$")
            tools = re.findall(r"^  - (.+)$", fm, re.M)
            self.assertTrue(tools and set(tools) <= GEMINI_TOOLS, f"{r}: {tools}")
            self.assertIn("kind: local", fm)
            self.assertIn("Gemini CLI subagent exported from ASDR", body)
        gen, _k, _b = front((out / "agents/asdr-generator.md").read_text())
        judge, _k, _b = front((out / "agents/asdr-judge.md").read_text())
        self.assertIn("run_shell_command", gen)
        self.assertNotIn("run_shell_command", judge)
        self.assertIn("max_turns: 300", gen)
        owner, _k, _b = front((out / "agents/asdr-product-owner.md").read_text())
        self.assertIn("google_web_search", owner)
        cmds = sorted(str(p.relative_to(out / "commands")) for p in (out / "commands").rglob("*.toml"))
        self.assertIn("asdr.toml", cmds)
        self.assertIn(os.path.join("asdr", "validate.toml"), cmds)
        self.assertEqual(len(cmds), len(SKILLS))
        for c in (out / "commands").rglob("*.toml"):
            t = c.read_text()
            self.assertIn("{{args}}", t)
            if tomllib:
                self.assertIn("prompt", tomllib.loads(t))

    def test_install_without_the_cli_explains_instead_of_failing(self):
        out = self.d / "g"
        r = run([str(S / "export_targets.py"), "gemini", "--out", str(out), "--install"],
                env={"PATH": str(self.d / "nobin")})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("gemini CLI not found; run: gemini extensions install", r.stdout)


class TestCodexInstall(Base):
    def install(self, *extra):
        h = self.d / "home"
        return run([str(S / "export_targets.py"), "codex", "--install", "--root", str(h / ".asdr/codex"),
                    "--skills-home", str(h / ".agents/skills"), "--codex-home", str(h / ".codex"), *extra],
                   env={"HOME": str(h), "TMPDIR": str(self.d)}), h

    def test_install_places_bundle_skills_and_agents(self):
        r, h = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((h / ".asdr/codex/scripts/init_asdr.py").is_file())
        self.assertEqual(sorted(p.name for p in (h / ".agents/skills").iterdir()), sorted(exported(s) for s in SKILLS))
        self.assertEqual(len(list((h / ".codex/agents").glob("asdr-*.toml"))), len(ROLES))
        skill = (h / ".agents/skills/asdr/SKILL.md").read_text()
        self.assertIn(str(h / ".asdr/codex"), skill, "PLUGIN_ROOT points at the installed bundle")
        self.assertFalse([p for p in self.d.iterdir() if p.name.startswith("asdr-codex-")], "temp copy removed")
        r2, _ = self.install()
        self.assertEqual(r2.returncode, 0, "re-installing over our own files works")

    def test_install_never_overwrites_files_it_did_not_write(self):
        h = self.d / "home"
        foreign = h / ".agents/skills/asdr"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("---\nname: asdr\ndescription: someone else's\n---\n")
        (h / ".codex/agents").mkdir(parents=True)
        (h / ".codex/agents/asdr-critic.toml").write_text('name = "asdr-critic"\n')
        r, _ = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED", r.stdout)
        self.assertIn("someone else's", (foreign / "SKILL.md").read_text())
        self.assertEqual((h / ".codex/agents/asdr-critic.toml").read_text(), 'name = "asdr-critic"\n')
        r, _ = self.install("--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Running in Codex CLI", (foreign / "SKILL.md").read_text())

    def test_refuses_a_foreign_output_folder(self):
        out = self.d / "busy"
        out.mkdir()
        (out / "keep.txt").write_text("mine")
        r = run([str(S / "export_targets.py"), "codex", "--out", str(out)])
        self.assertEqual(r.returncode, 1)
        self.assertTrue((out / "keep.txt").exists())


class TestParsing(unittest.TestCase):
    def test_tools_flow_list_block_list_and_absent(self):
        sys.path.insert(0, str(S))
        import export_targets as ex
        self.assertEqual(ex.parse_tools('name: x\ntools: ["Read", "Bash"]'), ["Read", "Bash"])
        self.assertEqual(ex.parse_tools("name: x\ntools: Read, Grep"), ["Read", "Grep"])
        self.assertEqual(ex.parse_tools("name: x\ntools:\n  - Read\n  - 'Write'\nmodel: opus"), ["Read", "Write"])
        self.assertIsNone(ex.parse_tools("name: x\nmodel: opus"), "no key = every tool")


class TestInstallSafety(Base):
    """Found in review: --force once let --root wipe ~/.codex (auth, sessions)."""

    def codex(self, root, *extra, home=None):
        h = home or self.d / "home"
        h.mkdir(parents=True, exist_ok=True)
        return run([str(S / "export_targets.py"), "codex", "--install", "--root", str(root),
                    "--skills-home", str(h / ".agents/skills"), "--codex-home", str(h / ".codex"), *extra],
                   env={"HOME": str(h), "TMPDIR": str(self.d)})

    def codex_home(self):
        h = self.d / "home"
        (h / ".codex/sessions").mkdir(parents=True)
        (h / ".codex/auth.json").write_text("{\"token\": \"keep\"}")
        (h / ".codex/config.toml").write_text("model = \"x\"\n")
        return h

    def test_root_equal_to_or_containing_codex_home_is_refused_even_with_force(self):
        h = self.codex_home()
        for root in (h / ".codex", h, h / ".codex/inside"):
            r = self.codex(root, "--force")
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("REFUSED", r.stdout)
            self.assertEqual((h / ".codex/auth.json").read_text(), '{"token": "keep"}')
            self.assertTrue((h / ".codex/sessions").is_dir())
            self.assertNotIn("Traceback", r.stderr)
        self.assertFalse([p for p in self.d.iterdir() if p.name.startswith("asdr-codex-")], "temp bundle cleaned up")

    def test_an_empty_root_folder_is_used(self):
        h = self.d / "home"
        (h / ".asdr/codex").mkdir(parents=True)
        r = self.codex(h / ".asdr/codex")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((h / ".asdr/codex/scripts/init_asdr.py").is_file())

    def test_foreign_root_is_never_replaced_and_nothing_else_installs(self):
        h = self.d / "home"
        root = h / "projects/mine"
        (root / "skills/other").mkdir(parents=True)
        (root / "notes.txt").write_text("mine")
        r = self.codex(root, "--force")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual((root / "notes.txt").read_text(), "mine")
        self.assertFalse((h / ".agents/skills").exists(), "no skill is installed when the root is refused")
        self.assertNotIn("Traceback", r.stderr)

    def test_relative_root_is_made_absolute(self):
        h = self.d / "home"
        h.mkdir()
        r = subprocess.run([sys.executable, str(S / "export_targets.py"), "codex", "--install", "--root", "rel/bundle",
                            "--skills-home", str(h / ".agents/skills"), "--codex-home", str(h / ".codex")],
                           cwd=h, capture_output=True, text=True, env={**os.environ, "HOME": str(h), "TMPDIR": str(self.d)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"`{(h / 'rel/bundle').resolve()}`", (h / ".agents/skills/asdr/SKILL.md").read_text())

    def test_output_folder_rules(self):
        f = self.d / "afile"
        f.write_text("x")
        r = run([str(S / "export_targets.py"), "codex", "--out", str(f)])
        self.assertEqual(r.returncode, 1)
        self.assertIn("is a file or a link", r.stdout)
        cx, _ = self.export("codex")
        r = run([str(S / "export_targets.py"), "gemini", "--out", str(cx)])
        self.assertEqual(r.returncode, 1, "a Codex export is not a Gemini one")
        self.assertTrue((cx / "agents/asdr-judge.toml").exists())
        half = self.d / "half"                      # a failed export left only its marker
        half.mkdir()
        (half / ".asdr-export.json").write_text(json.dumps({"exported_by": "ASDR", "host": "codex"}))
        (half / "junk").write_text("partial")
        self.export("codex", out=half)
        self.assertFalse((half / "junk").exists())


class TestGeminiInstall(Base):
    def fake_gemini(self, rc=0):
        b = self.d / "bin"
        b.mkdir(exist_ok=True)
        g = b / "gemini"
        g.write_text(f"#!/bin/sh\necho \"$@\" >> {self.d}/gemini.log\nexit {rc}\n")
        g.chmod(0o755)
        return {"PATH": f"{b}:/usr/bin:/bin", "HOME": str(self.d / "home")}

    def test_reinstall_uninstalls_our_extension_first(self):
        env = self.fake_gemini()
        ext = self.d / "home/.gemini/extensions/asdr"
        ext.mkdir(parents=True)
        (ext / ".asdr-export.json").write_text(json.dumps({"exported_by": "ASDR", "host": "gemini"}))
        r = run([str(S / "export_targets.py"), "gemini", "--out", str(self.d / "g"), "--install"], env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = (self.d / "gemini.log").read_text().splitlines()
        self.assertEqual(log[0], "extensions uninstall asdr")
        self.assertTrue(log[1].startswith("extensions install ") and log[1].endswith("--consent"))

    def test_a_failed_install_is_an_error(self):
        env = self.fake_gemini(rc=3)
        r = run([str(S / "export_targets.py"), "gemini", "--out", str(self.d / "g"), "--install"], env=env)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("exited 3", r.stdout)

    def test_a_foreign_asdr_extension_is_left_alone(self):
        env = self.fake_gemini()
        ext = self.d / "home/.gemini/extensions/asdr"
        ext.mkdir(parents=True)
        (ext / "gemini-extension.json").write_text('{"name": "asdr"}')
        r = run([str(S / "export_targets.py"), "gemini", "--out", str(self.d / "g"), "--install"], env=env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("did not write", r.stdout)
        self.assertFalse((self.d / "gemini.log").exists(), "gemini is not called")


class TestDocs(unittest.TestCase):
    def test_readme_and_changelog_describe_the_export(self):
        self.assertIn("export_targets.py", (REPO / "README.md").read_text())
        self.assertIn("export_targets.py", (REPO / "CHANGELOG.md").read_text())


if __name__ == "__main__":
    unittest.main()
