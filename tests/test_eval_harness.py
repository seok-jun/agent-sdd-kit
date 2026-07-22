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
    prepare_workspace,
    snapshot_workspace,
)
from scripts.run_evals import aggregate


class HarnessTests(unittest.TestCase):
    def test_summary_aggregation_separates_harnesses(self) -> None:
        results = [
            {"harness": "codex", "skill": "demo", "passed": True},
            {"harness": "codex", "skill": "demo", "passed": False},
            {"harness": "claude", "skill": "demo", "passed": True},
        ]
        summary = aggregate(results, "harness", "skill")
        self.assertEqual(summary["codex/demo"]["pass_rate"], 0.5)
        self.assertEqual(summary["claude/demo"]["pass_rate"], 1.0)

    def test_codex_command_is_machine_readable_and_automated(self) -> None:
        command = codex.build_command("test prompt", "gpt-test")
        self.assertEqual(command[:4], ["codex", "exec", "--json", "--full-auto"])
        self.assertIn("gpt-test", command)

    def test_claude_command_is_streamed_and_non_persistent(self) -> None:
        command = claude.build_command("test prompt", "sonnet")
        self.assertIn("stream-json", command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("dontAsk", command)
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
            paths, diff = collect_changes(workspace)
            self.assertEqual(paths, ["src/value.txt"])
            self.assertIn("-before", diff)
            self.assertIn("+after", diff)
            before_agent = snapshot_workspace(workspace)
            (workspace / "agent-output.txt").write_text("created\n", encoding="utf-8")
            self.assertEqual(changed_since(before_agent, snapshot_workspace(workspace)), ["agent-output.txt"])

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
