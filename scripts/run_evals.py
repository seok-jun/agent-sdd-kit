#!/usr/bin/env python3
"""Run isolated, multi-trial Skill evals through Codex and/or Claude Code."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.harness import claude, codex  # noqa: E402
from evals.harness.core import (  # noqa: E402
    AgentResult,
    RunContext,
    changed_since,
    collect_changes,
    evaluate,
    load_check_registry,
    prepare_workspace,
    snapshot_workspace,
    write_artifacts,
)

ADAPTERS = {"codex": codex, "claude": claude}
TRIGGER_CHECKS = {"skill_triggered", "skill_not_triggered"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", action="append", help="Skill name; repeatable. Default: all")
    parser.add_argument("--harness", choices=["codex", "claude", "both"], default="both")
    parser.add_argument("--case", action="append", help="Case id; repeatable")
    parser.add_argument("--category", choices=["trigger", "non-trigger", "procedure"])
    parser.add_argument("--trials", type=int, help="Override prompt-set default (3-5)")
    parser.add_argument("--timeout", type=int, default=900, help="Seconds per agent run")
    parser.add_argument("--codex-model")
    parser.add_argument("--claude-model")
    parser.add_argument("--without-skill", action="store_true", help="Run a skill-unloaded baseline")
    parser.add_argument("--dry-run", action="store_true", help="Prepare commands but do not call an agent")
    parser.add_argument("--keep-workspaces", action="store_true")
    parser.add_argument("--artifacts", type=Path, default=ROOT / "evals" / "artifacts")
    return parser.parse_args()


def load_prompt_sets(selected: list[str] | None) -> list[tuple[Path, dict[str, Any]]]:
    sources = sorted((ROOT / "evals").glob("*/prompts.json"))
    if selected:
        wanted = set(selected)
        sources = [source for source in sources if source.parent.name in wanted]
        missing = wanted - {source.parent.name for source in sources}
        if missing:
            raise SystemExit(f"Unknown skill(s): {', '.join(sorted(missing))}")
    return [(source, json.loads(source.read_text(encoding="utf-8"))) for source in sources]


def select_cases(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    cases = payload["cases"]
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case["id"] in wanted]
    if args.category:
        cases = [case for case in cases if case["category"] == args.category]
    return cases


def baseline_case(case: dict[str, Any]) -> dict[str, Any]:
    adjusted = copy.deepcopy(case)
    adjusted["expected_checks"] = [
        check for check in adjusted["expected_checks"] if check not in TRIGGER_CHECKS
    ]
    return adjusted


def dry_result(command: list[str]) -> AgentResult:
    return AgentResult(command, 0, "", "", "", [], {}, False)


def aggregate(results: list[dict[str, Any]], *keys: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        label = "/".join(str(result[key]) for key in keys)
        groups.setdefault(label, []).append(result)
    return {
        label: {
            "passed": sum(1 for result in group if result["passed"]),
            "total": len(group),
            "pass_rate": sum(1 for result in group if result["passed"]) / len(group),
        }
        for label, group in sorted(groups.items())
    }


def main() -> int:
    args = parse_args()
    if args.trials is not None and not 1 <= args.trials <= 5:
        raise SystemExit("--trials must be between 1 and 5")
    harnesses = list(ADAPTERS) if args.harness == "both" else [args.harness]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary: list[dict[str, Any]] = []

    for source, payload in load_prompt_sets(args.skill):
        skill = payload["skill"]
        registry = load_check_registry(source.parent / "checks.py")
        for harness in harnesses:
            adapter = ADAPTERS[harness]
            model = args.codex_model if harness == "codex" else args.claude_model
            for case in select_cases(payload, args):
                trials = args.trials or payload["defaults"]["trials"]
                fixture_name = case.get("fixture", payload["defaults"]["fixture"])
                fixture_root = source.parent / "fixtures" / fixture_name
                for trial in range(1, trials + 1):
                    workspace = prepare_workspace(
                        ROOT,
                        skill,
                        fixture_root,
                        harness,
                        install_skill=not args.without_skill,
                    )
                    before_agent = snapshot_workspace(workspace)
                    try:
                        command = adapter.build_command(case["prompt"], model)
                        if args.dry_run:
                            print(json.dumps({"workspace": str(workspace), "command": command}, ensure_ascii=False))
                            agent = dry_result(command)
                            evaluation = {"passed": True, "checks": {}}
                        else:
                            agent = adapter.run(case["prompt"], workspace, args.timeout, model)
                            _, diff = collect_changes(workspace)
                            changed_paths = changed_since(before_agent, snapshot_workspace(workspace))
                            effective_case = baseline_case(case) if args.without_skill else case
                            context = RunContext(
                                skill=skill,
                                case=effective_case,
                                harness=harness,
                                workspace=workspace,
                                agent=agent,
                                changed_paths=changed_paths,
                                diff=diff,
                            )
                            evaluation = evaluate(context, registry)
                            artifact_dir = (
                                args.artifacts
                                / run_id
                                / ("without-skill" if args.without_skill else "with-skill")
                                / harness
                                / skill
                                / case["id"]
                                / f"trial-{trial}"
                            )
                            write_artifacts(artifact_dir, context, evaluation)
                        summary.append(
                            {
                                "skill": skill,
                                "harness": harness,
                                "case_id": case["id"],
                                "trial": trial,
                                "passed": evaluation["passed"],
                            }
                        )
                        status = "DRY" if args.dry_run else ("PASS" if evaluation["passed"] else "FAIL")
                        print(f"[{status}] {harness}/{skill}/{case['id']} trial {trial}")
                    finally:
                        if args.keep_workspaces:
                            print(f"workspace kept: {workspace}")
                        elif workspace.name.startswith("agent-sdd-eval-"):
                            shutil.rmtree(workspace)

    if args.dry_run:
        return 0
    passed = sum(1 for result in summary if result["passed"])
    total = len(summary)
    by_harness = aggregate(summary, "harness")
    by_harness_and_skill = aggregate(summary, "harness", "skill")
    summary_path = args.artifacts / run_id / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "passed": passed,
                "total": total,
                "pass_rate": passed / total if total else 0.0,
                "by_harness": by_harness,
                "by_harness_and_skill": by_harness_and_skill,
                "runs": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Result: {passed}/{total} trials passed. Summary: {summary_path}")
    for label, result in by_harness_and_skill.items():
        print(f"  {label}: {result['passed']}/{result['total']} ({result['pass_rate']:.1%})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
