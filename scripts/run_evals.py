#!/usr/bin/env python3
"""Run isolated, multi-trial Skill evals through Codex and/or Claude Code."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
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
    remove_workspace,
    snapshot_workspace,
    write_artifacts,
)
from scripts.validate_eval_specs import ValidationError, validate_spec  # noqa: E402

ADAPTERS = {"codex": codex, "claude": claude}
TRIGGER_CHECKS = {"skill_triggered", "skill_not_triggered"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", action="append", help="Skill name; repeatable. Default: all")
    parser.add_argument("--harness", choices=["codex", "claude", "both"], default="both")
    parser.add_argument("--case", action="append", help="Case id; repeatable")
    parser.add_argument(
        "--category", choices=["trigger", "non-trigger", "procedure", "outcome"]
    )
    parser.add_argument("--trials", type=int, help="Override prompt-set default (3-5)")
    parser.add_argument("--timeout", type=int, default=900, help="Seconds per agent run")
    parser.add_argument("--codex-model")
    parser.add_argument("--claude-model")
    parser.add_argument("--without-skill", action="store_true", help="Run a skill-unloaded baseline")
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Run with and without the Skill under one run id and report per-check deltas",
    )
    parser.add_argument("--dry-run", action="store_true", help="Prepare commands but do not call an agent")
    parser.add_argument("--keep-workspaces", action="store_true")
    parser.add_argument(
        "--allow-global-skill",
        action="store_true",
        help="Allow a same-named user Skill that can contaminate the result",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.0,
        help="Exit 1 when the measured condition is below this 0-1 threshold",
    )
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
            "passed": sum(1 for result in group if result["status"] == "pass"),
            "failed": sum(1 for result in group if result["status"] == "fail"),
            "errors": sum(1 for result in group if result["status"] == "error"),
            "total": len(group),
            "pass_rate": (
                sum(1 for result in group if result["status"] == "pass")
                / sum(1 for result in group if result["status"] in {"pass", "fail"})
                if any(result["status"] in {"pass", "fail"} for result in group)
                else None
            ),
        }
        for label, group in sorted(groups.items())
    }


def aggregate_checks(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[bool]] = {}
    for result in results:
        if result["status"] == "error":
            continue
        for check_id, check in result["checks"].items():
            key = (result["harness"], result["skill"], result["condition"], check_id)
            groups.setdefault(key, []).append(bool(check["passed"]))
    return [
        {
            "harness": key[0],
            "skill": key[1],
            "condition": key[2],
            "check_id": key[3],
            "passed": sum(values),
            "total": len(values),
            "pass_rate": sum(values) / len(values),
        }
        for key, values in sorted(groups.items())
    ]


def baseline_deltas(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {
        (row["harness"], row["skill"], row["check_id"], row["condition"]): row
        for row in checks
    }
    keys = sorted({key[:3] for key in indexed})
    deltas: list[dict[str, Any]] = []
    for harness, skill, check_id in keys:
        with_skill = indexed.get((harness, skill, check_id, "with-skill"))
        without_skill = indexed.get((harness, skill, check_id, "without-skill"))
        if not with_skill or not without_skill:
            continue
        deltas.append(
            {
                "harness": harness,
                "skill": skill,
                "check_id": check_id,
                "with_skill_pass_rate": with_skill["pass_rate"],
                "without_skill_pass_rate": without_skill["pass_rate"],
                "delta": with_skill["pass_rate"] - without_skill["pass_rate"],
            }
        )
    return deltas


def _flatten_numbers(value: Any, prefix: str = "") -> dict[str, float]:
    if isinstance(value, bool):
        return {}
    if isinstance(value, (int, float)):
        return {prefix or "value": float(value)}
    if not isinstance(value, dict):
        return {}
    flattened: dict[str, float] = {}
    for key, child in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else str(key)
        flattened.update(_flatten_numbers(child, child_prefix))
    return flattened


def aggregate_usage(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for result in results:
        label = f"{result['harness']}/{result['condition']}"
        group = totals.setdefault(label, {})
        for key, value in _flatten_numbers(result["usage"]).items():
            group[key] = group.get(key, 0.0) + value
    return totals


def command_version(binary: str) -> str | None:
    executable = shutil.which(binary)
    if executable is None:
        return None
    completed = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    text = (completed.stdout or completed.stderr).strip()
    return text or None


def repository_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def skill_digest(skill: str) -> str:
    root = ROOT / "skills" / skill
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def global_skill_paths(skill: str, harness: str) -> list[Path]:
    homes = (
        [Path.home() / ".agents/skills", Path.home() / ".codex/skills"]
        if harness == "codex"
        else [Path.home() / ".claude/skills"]
    )
    return [home / skill for home in homes if (home / skill).exists()]


def main() -> int:
    args = parse_args()
    if args.without_skill and args.compare_baseline:
        raise SystemExit("--without-skill and --compare-baseline cannot be combined")
    if args.trials is not None and not 1 <= args.trials <= 5:
        raise SystemExit("--trials must be between 1 and 5")
    if not 0.0 <= args.min_pass_rate <= 1.0:
        raise SystemExit("--min-pass-rate must be between 0 and 1")
    harnesses = list(ADAPTERS) if args.harness == "both" else [args.harness]
    conditions = (
        ["with-skill", "without-skill"]
        if args.compare_baseline
        else ["without-skill" if args.without_skill else "with-skill"]
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    summary: list[dict[str, Any]] = []
    prompt_sets = load_prompt_sets(args.skill)

    try:
        for source, _ in prompt_sets:
            validate_spec(source)
    except ValidationError as exc:
        raise SystemExit(f"Invalid eval spec: {exc}") from exc

    selected: list[tuple[Path, dict[str, Any], str, dict[str, Any], int, str]] = []
    for source, payload in prompt_sets:
        cases = select_cases(payload, args)
        trials = args.trials or payload["defaults"]["trials"]
        for harness in harnesses:
            conflicts = global_skill_paths(payload["skill"], harness)
            if conflicts and not args.allow_global_skill:
                rendered = ", ".join(str(path) for path in conflicts)
                raise SystemExit(
                    f"Global Skill collision for {harness}/{payload['skill']}: {rendered}. "
                    "Remove it or pass --allow-global-skill to accept contaminated results."
                )
            for case in cases:
                for trial in range(1, trials + 1):
                    for condition in conditions:
                        selected.append((source, payload, harness, case, trial, condition))

    if not selected:
        raise SystemExit("No eval cases selected")
    if not args.dry_run:
        missing = [harness for harness in harnesses if shutil.which(harness) is None]
        if missing:
            raise SystemExit(f"Missing CLI(s): {', '.join(missing)}")
    cli_versions = {harness: command_version(harness) for harness in harnesses}
    print(
        f"Planned agent calls: {len(selected)} "
        f"(up to {len(selected) * args.timeout} timeout-seconds, executed serially)."
    )

    for source, payload, harness, case, trial, condition in selected:
        skill = payload["skill"]
        registry = load_check_registry(source.parent / "checks.py")
        adapter = ADAPTERS[harness]
        model = (
            args.codex_model or codex.DEFAULT_MODEL
            if harness == "codex"
            else args.claude_model
        )
        fixture_name = case.get("fixture", payload["defaults"]["fixture"])
        fixture_root = source.parent / "fixtures" / fixture_name
        try:
            workspace = prepare_workspace(
                ROOT,
                skill,
                fixture_root,
                harness,
                install_skill=condition == "with-skill",
            )
        except (OSError, RuntimeError, ValueError) as exc:
            error = f"workspace preparation failed: {exc}"
            print(f"[ERROR] {condition}/{harness}/{skill}/{case['id']} trial {trial}: {error}")
            if args.dry_run:
                return 2
            summary.append(
                {
                    "skill": skill,
                    "harness": harness,
                    "condition": condition,
                    "case_id": case["id"],
                    "should_trigger": case["should_trigger"],
                    "trial": trial,
                    "status": "error",
                    "passed": False,
                    "error": error,
                    "checks": {},
                    "usage": {},
                }
            )
            continue
        before_agent = snapshot_workspace(workspace)
        try:
            command = adapter.build_command(case["prompt"], model)
            if args.dry_run:
                print(
                    json.dumps(
                        {"condition": condition, "workspace": str(workspace), "command": command},
                        ensure_ascii=False,
                    )
                )
                agent = dry_result(command)
                evaluation = {"passed": True, "checks": {}}
                run_status = "pass"
                error = None
            else:
                agent = adapter.run(
                    case["prompt"], workspace, args.timeout, model, skill=skill
                )
                _, diff = collect_changes(workspace)
                changed_paths = changed_since(before_agent, snapshot_workspace(workspace))
                effective_case = baseline_case(case) if condition == "without-skill" else case
                context = RunContext(
                    skill=skill,
                    case=effective_case,
                    harness=harness,
                    workspace=workspace,
                    agent=agent,
                    changed_paths=changed_paths,
                    diff=diff,
                )
                if agent.timed_out or agent.exit_code != 0 or agent.adapter_errors:
                    error = (
                        f"exit_code={agent.exit_code}, timed_out={agent.timed_out}, "
                        f"adapter_errors={agent.adapter_errors}"
                    )
                    evaluation = {"passed": False, "checks": {}, "error": error}
                    run_status = "error"
                else:
                    error = None
                    evaluation = evaluate(context, registry)
                    run_status = "pass" if evaluation["passed"] else "fail"
                artifact_dir = (
                    args.artifacts
                    / run_id
                    / condition
                    / harness
                    / skill
                    / case["id"]
                    / f"trial-{trial}"
                )
                write_artifacts(
                    artifact_dir,
                    context,
                    {**evaluation, "status": run_status},
                    {
                        "condition": condition,
                        "requested_model": model,
                        "model": model,
                        "cli_version": cli_versions[harness],
                        "prompt_set_version": payload["version"],
                        "timeout_seconds": args.timeout,
                        "trial": trial,
                    },
                )
            summary.append(
                {
                    "skill": skill,
                    "harness": harness,
                    "condition": condition,
                    "case_id": case["id"],
                    "should_trigger": case["should_trigger"],
                    "trial": trial,
                    "status": run_status,
                    "passed": run_status == "pass",
                    "error": error,
                    "checks": evaluation["checks"],
                    "usage": agent.usage,
                    "model": model,
                }
            )
            display = "DRY" if args.dry_run else run_status.upper()
            print(f"[{display}] {condition}/{harness}/{skill}/{case['id']} trial {trial}")
        finally:
            if args.keep_workspaces:
                print(f"workspace kept: {workspace}")
            elif workspace.name.startswith("agent-sdd-eval-"):
                remove_workspace(workspace)

    if args.dry_run:
        return 0
    passed = sum(1 for result in summary if result["status"] == "pass")
    failed = sum(1 for result in summary if result["status"] == "fail")
    errors = sum(1 for result in summary if result["status"] == "error")
    total = len(summary)
    by_harness = aggregate(summary, "harness")
    by_harness_and_skill = aggregate(summary, "condition", "harness", "skill")
    per_check = aggregate_checks(summary)
    trigger_gates: list[dict[str, Any]] = []
    infrastructure_errors: list[str] = []
    for harness in harnesses:
        for _, payload in prompt_sets:
            runs = [
                result
                for result in summary
                if result["condition"] == "with-skill"
                and result["harness"] == harness
                and result["skill"] == payload["skill"]
                and result["should_trigger"]
                and result["status"] != "error"
            ]
            detected = any(
                result["checks"].get("skill_triggered", {}).get("passed") for result in runs
            )
            status = "not-selected" if not runs else ("pass" if detected else "error")
            trigger_gates.append(
                {"harness": harness, "skill": payload["skill"], "status": status}
            )
            if runs and not detected:
                infrastructure_errors.append(
                    f"Trigger detector found no marker for {harness}/{payload['skill']}"
                )
    if any(condition == "with-skill" for condition in conditions) and all(
        gate["status"] == "not-selected" for gate in trigger_gates
    ):
        print("WARNING: no trigger case was selected; trigger parser integrity was not verified.")

    summary_path = args.artifacts / run_id / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "total": total,
                "pass_rate": passed / (passed + failed) if passed + failed else None,
                "conditions": conditions,
                "timeout_seconds": args.timeout,
                "requested_trials": args.trials,
                "effective_trials": {
                    payload["skill"]: args.trials or payload["defaults"]["trials"]
                    for _, payload in prompt_sets
                },
                "min_pass_rate": args.min_pass_rate,
                "repository_commit": repository_commit(),
                "prompt_set_versions": {
                    payload["skill"]: payload["version"] for _, payload in prompt_sets
                },
                "skill_sha256": {
                    payload["skill"]: skill_digest(payload["skill"])
                    for _, payload in prompt_sets
                },
                "cli_versions": cli_versions,
                "requested_models": {
                    "codex": args.codex_model or codex.DEFAULT_MODEL,
                    "claude": args.claude_model,
                },
                "models": {
                    "codex": args.codex_model or codex.DEFAULT_MODEL,
                    "claude": args.claude_model,
                },
                "by_harness": by_harness,
                "by_harness_and_skill": by_harness_and_skill,
                "per_check": per_check,
                "baseline_deltas": baseline_deltas(per_check),
                "usage_totals": aggregate_usage(summary),
                "trigger_detector_gates": trigger_gates,
                "infrastructure_errors": infrastructure_errors,
                "runs": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Result: {passed} passed, {failed} failed, {errors} errors. Summary: {summary_path}"
    )
    for label, result in by_harness_and_skill.items():
        rate = "n/a" if result["pass_rate"] is None else f"{result['pass_rate']:.1%}"
        print(
            f"  {label}: {result['passed']} pass, {result['failed']} fail, "
            f"{result['errors']} error ({rate})"
        )
    if errors or infrastructure_errors:
        return 2
    measured_condition = "with-skill" if "with-skill" in conditions else conditions[0]
    measured = [result for result in summary if result["condition"] == measured_condition]
    measured_passed = sum(1 for result in measured if result["status"] == "pass")
    measured_failed = sum(1 for result in measured if result["status"] == "fail")
    pass_rate = measured_passed / (measured_passed + measured_failed)
    return 0 if pass_rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
