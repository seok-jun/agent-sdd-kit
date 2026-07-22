from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evals.harness import claude, codex
from evals.harness.core import (
    AgentResult,
    RunContext,
    changed_since,
    collect_changes,
    common_registry,
    evaluate,
    load_check_registry,
    prepare_workspace,
    skill_trigger_evidence,
    snapshot_workspace,
)
from scripts.run_evals import aggregate, baseline_deltas


class HarnessTests(unittest.TestCase):
    def test_summary_aggregation_separates_harnesses(self) -> None:
        results = [
            {"harness": "codex", "skill": "demo", "status": "pass"},
            {"harness": "codex", "skill": "demo", "status": "fail"},
            {"harness": "claude", "skill": "demo", "status": "pass"},
        ]
        summary = aggregate(results, "harness", "skill")
        self.assertEqual(summary["codex/demo"]["pass_rate"], 0.5)
        self.assertEqual(summary["claude/demo"]["pass_rate"], 1.0)

    def test_codex_command_is_machine_readable_and_automated(self) -> None:
        command = codex.build_command("test prompt", "gpt-test")
        self.assertEqual(command[:3], ["codex", "exec", "--json"])
        self.assertIn("--ephemeral", command)
        self.assertIn("workspace-write", command)
        self.assertNotIn("--full-auto", command)
        self.assertIn("gpt-test", command)

    def test_claude_command_is_streamed_and_non_persistent(self) -> None:
        command = claude.build_command("test prompt", "sonnet")
        self.assertIn("stream-json", command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("dontAsk", command)
        self.assertEqual(command[command.index("-p") + 1], "test prompt")
        allowed = command[command.index("--allowedTools") + 1 :]
        self.assertEqual(allowed[0:4], ["Skill", "Read", "Glob", "Grep"])
        self.assertNotIn("test prompt", allowed)
        self.assertIn("--strict-mcp-config", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_fixture_baseline_excludes_skill_and_keeps_overlay_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "skills/demo").mkdir(parents=True)
            (root / "skills/demo/SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
            fixture = root / "fixture"
            (fixture / "base/src").mkdir(parents=True)
            (fixture / "worktree/src").mkdir(parents=True)
            (fixture / "base/src/value.txt").write_text("before\n", encoding="utf-8")
            (fixture / "worktree/src/value.txt").write_text("after\n", encoding="utf-8")
            workspace = prepare_workspace(root, "demo", fixture, "codex")
            self.assertTrue((workspace / ".agents/skills/demo/SKILL.md").is_file())
            paths, diff = collect_changes(workspace)
            self.assertEqual(paths, ["src/value.txt"])
            self.assertIn("-before", diff)
            self.assertIn("+after", diff)
            before_agent = snapshot_workspace(workspace)
            (workspace / "agent-output.txt").write_text("created\n", encoding="utf-8")
            self.assertEqual(changed_since(before_agent, snapshot_workspace(workspace)), ["agent-output.txt"])
            paths, diff = collect_changes(workspace)
            self.assertIn("agent-output.txt", paths)
            self.assertIn("+created", diff)

    def test_common_checks_use_tool_events_not_prompt_text(self) -> None:
        context = RunContext(
            skill="demo",
            case={"expected_checks": ["skill_not_triggered"]},
            harness="codex",
            workspace=Path("."),
            agent=AgentResult([], 0, "prompt mentions demo", "", "", [], {}),
            changed_paths=[],
            diff="",
        )
        result = evaluate(context, common_registry())
        self.assertTrue(result["passed"])

    def test_trigger_detector_handles_windows_paths_and_skill_tool(self) -> None:
        windows = RunContext(
            skill="demo",
            case={"expected_checks": ["skill_triggered"]},
            harness="claude",
            workspace=Path("."),
            agent=AgentResult(
                [], 0, "", "", "", [{"name": "Read", "input": {"file_path": r"C:\repo\.claude\skills\demo\SKILL.md"}}], {}
            ),
            changed_paths=[],
            diff="",
        )
        self.assertIsNotNone(skill_trigger_evidence(windows))
        skill_tool = RunContext(
            skill="demo",
            case={"expected_checks": ["skill_triggered"]},
            harness="claude",
            workspace=Path("."),
            agent=AgentResult([], 0, "", "", "", [{"name": "Skill", "input": {"command": "demo"}}], {}),
            changed_paths=[],
            diff="",
        )
        self.assertIsNotNone(skill_trigger_evidence(skill_tool))

    def test_confirmation_check_rejects_incidental_korean_word(self) -> None:
        context = RunContext(
            skill="demo",
            case={"expected_checks": ["asks_for_confirmation"]},
            harness="codex",
            workspace=Path("."),
            agent=AgentResult([], 0, "", "", "코드를 확인했습니다. 아래와 같이 수정했습니다.", [], {}),
            changed_paths=[],
            diff="",
        )
        self.assertFalse(evaluate(context, common_registry())["passed"])

    def test_baseline_delta_only_compares_shared_checks(self) -> None:
        checks = [
            {"harness": "codex", "skill": "demo", "condition": "with-skill", "check_id": "behavior", "pass_rate": 0.75},
            {"harness": "codex", "skill": "demo", "condition": "without-skill", "check_id": "behavior", "pass_rate": 0.25},
            {"harness": "codex", "skill": "demo", "condition": "with-skill", "check_id": "skill_triggered", "pass_rate": 1.0},
        ]
        deltas = baseline_deltas(checks)
        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0]["delta"], 0.5)

    def test_repository_discovery_uses_tool_events_without_ls_substring_false_positive(self) -> None:
        registry = load_check_registry(Path("evals/sdd-doc-scaffold/checks.py"))
        safe = RunContext(
            skill="demo",
            case={"expected_checks": ["no_repository_discovery"]},
            harness="codex",
            workspace=Path("."),
            agent=AgentResult(
                [],
                0,
                "",
                "",
                "",
                [{"item": {"type": "command_execution", "command": "printf 'details complete'"}}],
                {},
            ),
            changed_paths=[],
            diff="",
        )
        self.assertTrue(evaluate(safe, registry)["passed"])
        discovery = RunContext(
            skill="demo",
            case={"expected_checks": ["no_repository_discovery"]},
            harness="claude",
            workspace=Path("."),
            agent=AgentResult([], 0, "", "", "", [{"name": "Glob", "input": {"pattern": "**/*"}}], {}),
            changed_paths=[],
            diff="",
        )
        self.assertFalse(evaluate(discovery, registry)["passed"])


class PromptSetTests(unittest.TestCase):
    def test_prompt_sets_use_executable_check_ids(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for source in (root / "evals").glob("*/prompts.json"):
            payload = json.loads(source.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(payload["cases"]), 10)
            for case in payload["cases"]:
                self.assertIn("prompt", case)
                self.assertIn("should_trigger", case)
                self.assertTrue(case["expected_checks"])
                self.assertNotIn("behaviors", case)


if __name__ == "__main__":
    unittest.main()
