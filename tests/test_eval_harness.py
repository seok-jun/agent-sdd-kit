from __future__ import annotations

import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
    remove_workspace,
    run_process,
    skill_trigger_evidence,
    snapshot_workspace,
    write_artifacts,
)
from scripts.run_evals import aggregate, baseline_deltas, command_version


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
        self.assertNotIn("--ephemeral", command)
        self.assertIn("workspace-write", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertNotIn("--full-auto", command)
        self.assertIn("gpt-test", command)
        self.assertNotIn("test prompt", command)

    def test_codex_command_pins_default_model(self) -> None:
        command = codex.build_command("test prompt")
        model_index = command.index("--model")
        self.assertEqual(command[model_index + 1], codex.DEFAULT_MODEL)

    def test_claude_command_is_streamed_and_non_persistent(self) -> None:
        command = claude.build_command("test prompt", "sonnet")
        self.assertIn("stream-json", command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("dontAsk", command)
        allowed = command[command.index("--allowedTools") + 1]
        self.assertEqual(allowed.split(",")[0:4], ["Skill", "Read", "Glob", "Grep"])
        self.assertEqual(command[-2:], ["--", "test prompt"])
        self.assertIn("--strict-mcp-config", command)
        self.assertNotIn("--dangerously-skip-permissions", command)

    def test_run_process_closes_stdin(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="out", stderr="")
        with (
            patch(
                "evals.harness.core.shutil.which",
                return_value=r"C:\\tools\\agent.cmd",
            ),
            patch("evals.harness.core.subprocess.run", return_value=completed) as mocked,
        ):
            run_process(["agent"], Path("."), 10)
        self.assertEqual(mocked.call_args.args[0], [r"C:\\tools\\agent.cmd"])
        self.assertIs(mocked.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(mocked.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(mocked.call_args.kwargs["errors"], "replace")

    def test_run_process_sends_unicode_input_as_utf8_stdin(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="out", stderr="")
        prompt = "$sdd-doc-scaffold Skill을 사용해서 문서 골격을 만들어줘."
        with (
            patch(
                "evals.harness.core.shutil.which",
                return_value=r"C:\\tools\\codex.cmd",
            ),
            patch("evals.harness.core.subprocess.run", return_value=completed) as mocked,
        ):
            run_process(["codex", "exec"], Path("."), 10, input_text=prompt)
        self.assertEqual(
            mocked.call_args.args[0],
            [r"C:\\tools\\codex.cmd", "exec"],
        )
        self.assertEqual(mocked.call_args.kwargs["input"], prompt)
        self.assertNotIn("stdin", mocked.call_args.kwargs)
        self.assertEqual(mocked.call_args.kwargs["encoding"], "utf-8")

    def test_run_process_reports_missing_cli(self) -> None:
        with patch("evals.harness.core.shutil.which", return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, "CLI not found: missing-agent"):
                run_process(["missing-agent"], Path("."), 10)

    def test_command_version_uses_resolved_windows_shim(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="1.2.3\n", stderr="")
        with (
            patch("scripts.run_evals.shutil.which", return_value=r"C:\\tools\\codex.cmd"),
            patch("scripts.run_evals.subprocess.run", return_value=completed) as mocked,
        ):
            self.assertEqual(command_version("codex"), "1.2.3")
        self.assertEqual(mocked.call_args.args[0], [r"C:\\tools\\codex.cmd", "--version"])
        self.assertEqual(mocked.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(mocked.call_args.kwargs["errors"], "replace")

    def test_remove_workspace_retries_readonly_path(self) -> None:
        retry = Mock()
        with (
            patch("evals.harness.core.shutil.rmtree") as rmtree,
            patch("evals.harness.core.os.chmod") as chmod,
        ):
            remove_workspace(Path("workspace"))
            handler = rmtree.call_args.kwargs["onerror"]
            handler(retry, "workspace/.git/objects/readonly", None)
        chmod.assert_called_once_with("workspace/.git/objects/readonly", stat.S_IWRITE)
        retry.assert_called_once_with("workspace/.git/objects/readonly")

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

    def test_prepare_workspace_copies_external_skill_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "skills/demo").mkdir(parents=True)
            (root / "shared.md").write_text("shared\n", encoding="utf-8")
            (root / "skills/demo/SKILL.md").write_text(
                "---\nname: demo\ndescription: demo\n---\n[shared](../../shared.md)\n",
                encoding="utf-8",
            )
            fixture = root / "fixture/base"
            fixture.mkdir(parents=True)
            workspace = prepare_workspace(root, "demo", fixture.parent, "codex")
            self.assertEqual(
                (workspace / ".agents/shared.md").read_text(encoding="utf-8"),
                "shared\n",
            )

    def test_prepare_workspace_rejects_missing_skill_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "skills/demo").mkdir(parents=True)
            (root / "skills/demo/SKILL.md").write_text(
                "---\nname: demo\ndescription: demo\n---\n[missing](../../missing.md)\n",
                encoding="utf-8",
            )
            fixture = root / "fixture/base"
            fixture.mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):
                prepare_workspace(root, "demo", fixture.parent, "codex")

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

    def test_trigger_detector_uses_only_normalized_activation_events(self) -> None:
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
        self.assertIsNone(skill_trigger_evidence(windows))
        skill_tool = RunContext(
            skill="demo",
            case={"expected_checks": ["skill_triggered"]},
            harness="claude",
            workspace=Path("."),
            agent=AgentResult([], 0, "", "", "", [{"name": "Skill", "input": {"skill": "demo"}}], {}),
            changed_paths=[],
            diff="",
        )
        self.assertIsNotNone(skill_trigger_evidence(skill_tool))

    def test_claude_parser_joins_messages_and_keeps_diagnostics(self) -> None:
        stdout = "\n".join(
            json.dumps(event)
            for event in [
                {"type": "system", "subtype": "init", "skills": ["demo"]},
                {"type": "assistant", "message": {"content": [
                    {"type": "text", "text": "first"},
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "demo"}},
                ]}},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "second"}]}},
                {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}},
                {"type": "result", "result": "last only", "usage": {"input_tokens": 2}, "permission_denials": [{"tool": "WebFetch"}]},
            ]
        )
        response, trace, usage, denials, rate_events, errors = claude._parse(stdout)
        self.assertEqual(response, "first\n\nsecond")
        self.assertEqual(trace[0]["input"]["skill"], "demo")
        self.assertEqual(usage["input_tokens"], 2)
        self.assertEqual(denials, [{"tool": "WebFetch"}])
        self.assertEqual(len(rate_events), 1)
        self.assertEqual(errors, [])

    def test_claude_parser_rejects_non_allowed_rate_limit(self) -> None:
        event = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}
        *_, errors = claude._parse(json.dumps(event))
        self.assertTrue(errors)

    def test_codex_parser_joins_messages_and_reads_rollout_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sessions = Path(temp) / "sessions/2026/07/22"
            sessions.mkdir(parents=True)
            thread_id = "019-demo-thread"
            rollout = sessions / f"rollout-2026-{thread_id}.jsonl"
            rollout.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "world_state", "payload": {"host_skills": [{"name": "not-activation"}]}}),
                        json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<skill><name>demo</name><path>C:\\\\demo</path></skill>"}]}}),
                    ]
                ),
                encoding="utf-8",
            )
            stdout = "\n".join(
                [
                    json.dumps({"type": "thread.started", "thread_id": thread_id}),
                    json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "first"}}),
                    json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "second"}}),
                    json.dumps({"type": "turn.completed", "usage": {"input_tokens": 3}}),
                ]
            )
            response, trace, usage, raw_rollout, errors = codex._parse(
                stdout, "demo", Path(temp) / "sessions"
            )
            self.assertEqual(response, "first\n\nsecond")
            self.assertEqual(usage["input_tokens"], 3)
            self.assertIn("response_item", raw_rollout)
            self.assertEqual(trace[-1]["input"]["skill"], "demo")
            self.assertEqual(errors, [])

    def test_codex_rollout_missing_is_adapter_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            stdout = json.dumps({"type": "thread.started", "thread_id": "missing"})
            *_, errors = codex._parse(stdout, "demo", Path(temp))
            self.assertTrue(errors)

    def test_diagnostic_artifacts_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            agent = AgentResult(
                [],
                0,
                "trace\n",
                "",
                "response",
                [],
                {},
                permission_denials=[{"tool": "WebFetch"}],
                rate_limit_events=[{"type": "rate_limit_event"}],
                rollout="rollout\n",
            )
            context = RunContext("demo", {"id": "case"}, "codex", root, agent, [], "")
            write_artifacts(root / "artifacts", context, {"passed": True, "checks": {}})
            self.assertTrue((root / "artifacts/codex-rollout.jsonl").is_file())
            self.assertTrue((root / "artifacts/permission-denials.json").is_file())
            self.assertTrue((root / "artifacts/rate-limit-events.json").is_file())

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

    def test_repository_discovery_is_harness_tool_based(self) -> None:
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
                [{"item": {"type": "command_execution", "command": "Get-ChildItem"}}],
                {},
            ),
            changed_paths=[],
            diff="",
        )
        self.assertFalse(evaluate(safe, registry)["passed"])
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

    def test_sdd_outcome_checks_read_created_files(self) -> None:
        root = Path(__file__).resolve().parents[1]
        registry = load_check_registry(root / "evals/sdd-doc-scaffold/checks.py")
        expected = [
            "docs/payment-recovery-sdd/README.md",
            "docs/payment-recovery-sdd/01-as-is-flow.md",
        ]
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            output = workspace / "docs/payment-recovery-sdd"
            output.mkdir(parents=True)
            (output / "README.md").write_text(
                "# payment-recovery SDD\n\n"
                "| 항목 | 값 |\n|---|---|\n"
                "| 문서 종류 | README |\n| 선행 문서 | 없음 |\n"
                "| 후속 문서 | [01-as-is-flow.md](./01-as-is-flow.md) |\n"
                "| 관련 코드 | src/main/java/example/order |\n\n## 목적\n",
                encoding="utf-8",
            )
            (output / "01-as-is-flow.md").write_text(
                "# payment-recovery - 현행 흐름\n\n"
                "| 항목 | 값 |\n|---|---|\n"
                "| 문서 종류 | as-is |\n| 선행 문서 | [README.md](./README.md) |\n"
                "| 후속 문서 | 미정 |\n"
                "| 관련 코드 | src/main/java/example/order |\n\n## 처리 흐름\n",
                encoding="utf-8",
            )
            case = {
                "expected_stage_files": expected,
                "expected_checks": [
                    "stage1_files_created",
                    "relation_block_present",
                    "relative_links_resolve",
                    "no_undeclared_files",
                ],
            }
            context = RunContext(
                "sdd-doc-scaffold",
                case,
                "codex",
                workspace,
                AgentResult([], 0, "", "", "ignored response", [], {}),
                expected,
                "",
            )
            result = evaluate(context, registry)
            self.assertTrue(result["passed"], result)

            context.changed_paths.append("docs/payment-recovery-sdd/undeclared.md")
            self.assertFalse(registry["no_undeclared_files"](context).passed)


if __name__ == "__main__":
    unittest.main()
