from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    evidence: str


@dataclass
class AgentResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    response: str
    tool_trace: list[dict[str, Any]]
    usage: dict[str, Any]
    timed_out: bool = False


@dataclass
class RunContext:
    skill: str
    case: dict[str, Any]
    harness: str
    workspace: Path
    agent: AgentResult
    changed_paths: list[str]
    diff: str


Check = Callable[[RunContext], CheckResult]


def run_process(command: list[str], cwd: Path, timeout: int) -> tuple[int, str, str, bool]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "NO_COLOR": "1"},
        )
        return completed.returncode, completed.stdout, completed.stderr, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return 124, stdout, stderr, True


def git(workspace: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=workspace, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def _copy_contents(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def prepare_workspace(
    repo_root: Path,
    skill: str,
    fixture_root: Path,
    harness: str,
    install_skill: bool = True,
    destination: Path | None = None,
) -> Path:
    workspace = destination or Path(tempfile.mkdtemp(prefix=f"agent-sdd-eval-{skill}-"))
    workspace.mkdir(parents=True, exist_ok=True)
    _copy_contents(fixture_root / "base", workspace)

    if install_skill:
        source_skill = repo_root / "skills" / skill
        if not (source_skill / "SKILL.md").is_file():
            raise FileNotFoundError(f"Skill not found: {source_skill}")
        skill_home = ".codex/skills" if harness == "codex" else ".claude/skills"
        shutil.copytree(source_skill, workspace / skill_home / skill)

    git(workspace, "init", "-q", "-b", "main")
    git(workspace, "config", "user.name", "Skill Eval")
    git(workspace, "config", "user.email", "skill-eval@example.invalid")
    git(workspace, "add", ".")
    git(workspace, "commit", "-q", "-m", "eval fixture baseline", "--allow-empty")

    _copy_contents(fixture_root / "worktree", workspace)
    return workspace


def collect_changes(workspace: Path) -> tuple[list[str], str]:
    tracked = git(workspace, "diff", "--name-only", "HEAD").splitlines()
    untracked = git(workspace, "ls-files", "--others", "--exclude-standard").splitlines()
    paths = sorted({path.strip() for path in [*tracked, *untracked] if path.strip()})
    diff = git(workspace, "diff", "--binary", "HEAD")
    if untracked:
        diff += "\n# Untracked files\n" + "\n".join(sorted(untracked)) + "\n"
    return paths, diff


def snapshot_workspace(workspace: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in workspace.rglob("*"):
        if not path.is_file() or ".git" in path.relative_to(workspace).parts:
            continue
        relative = path.relative_to(workspace).as_posix()
        snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def changed_since(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )


def load_check_registry(checks_path: Path) -> dict[str, Check]:
    module_name = f"agent_sdd_eval_checks_{checks_path.parent.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, checks_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import checks from {checks_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = getattr(module, "CHECK_REGISTRY", None)
    if not isinstance(registry, dict) or not registry:
        raise ValueError(f"{checks_path}: CHECK_REGISTRY must be a non-empty dict")
    return registry


def evaluate(context: RunContext, registry: dict[str, Check]) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}
    for check_id in context.case["expected_checks"]:
        result = registry[check_id](context)
        results[check_id] = asdict(result)
    return {
        "passed": all(result["passed"] for result in results.values()),
        "checks": results,
    }


def write_artifacts(
    artifact_dir: Path,
    context: RunContext,
    evaluation: dict[str, Any],
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "trace.jsonl").write_text(context.agent.stdout, encoding="utf-8")
    (artifact_dir / "stderr.txt").write_text(context.agent.stderr, encoding="utf-8")
    (artifact_dir / "response.md").write_text(context.agent.response, encoding="utf-8")
    (artifact_dir / "workspace.diff").write_text(context.diff, encoding="utf-8")
    payload = {
        "skill": context.skill,
        "case_id": context.case["id"],
        "harness": context.harness,
        "command": context.agent.command,
        "exit_code": context.agent.exit_code,
        "timed_out": context.agent.timed_out,
        "usage": context.agent.usage,
        "changed_paths": context.changed_paths,
        **evaluation,
    }
    (artifact_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def project_paths(paths: list[str]) -> list[str]:
    return [
        path
        for path in paths
        if not path.startswith((".codex/skills/", ".claude/skills/"))
    ]


def tool_trace_text(context: RunContext) -> str:
    return json.dumps(context.agent.tool_trace, ensure_ascii=False).lower()


def common_registry() -> dict[str, Check]:
    def agent_exit_zero(context: RunContext) -> CheckResult:
        return CheckResult(
            context.agent.exit_code == 0 and not context.agent.timed_out,
            f"exit_code={context.agent.exit_code}, timed_out={context.agent.timed_out}",
        )

    def skill_triggered(context: RunContext) -> CheckResult:
        trace = tool_trace_text(context)
        skill = context.skill.lower()
        markers = [
            f"{skill}/skill.md",
            f"\\{skill}\\skill.md",
            f'"skill": "{skill}"',
            f'"skill":"{skill}"',
            f'"name": "{skill}"',
        ]
        matched = next((marker for marker in markers if marker in trace), None)
        return CheckResult(matched is not None, f"trace marker={matched or 'not found'}")

    def skill_not_triggered(context: RunContext) -> CheckResult:
        triggered = skill_triggered(context)
        return CheckResult(not triggered.passed, triggered.evidence)

    def no_project_files_changed(context: RunContext) -> CheckResult:
        paths = project_paths(context.changed_paths)
        return CheckResult(not paths, f"changed={paths}")

    def no_code_modified(context: RunContext) -> CheckResult:
        code_suffixes = {".java", ".kt", ".py", ".js", ".ts", ".tsx", ".sql"}
        paths = [p for p in project_paths(context.changed_paths) if Path(p).suffix in code_suffixes]
        return CheckResult(not paths, f"code changes={paths}")

    def no_sdd_modified(context: RunContext) -> CheckResult:
        paths = [
            p
            for p in project_paths(context.changed_paths)
            if "-sdd/" in p.lower() or "/sdd/" in p.lower()
        ]
        return CheckResult(not paths, f"SDD changes={paths}")

    def asks_for_confirmation(context: RunContext) -> CheckResult:
        response = context.agent.response
        markers = ["확인", "결정", "알려", "입력", "승인"]
        matched = [marker for marker in markers if marker in response]
        return CheckResult(bool(matched), f"confirmation markers={matched}")

    return {
        "agent_exit_zero": agent_exit_zero,
        "skill_triggered": skill_triggered,
        "skill_not_triggered": skill_not_triggered,
        "no_project_files_changed": no_project_files_changed,
        "no_code_modified": no_code_modified,
        "no_sdd_modified": no_sdd_modified,
        "asks_for_confirmation": asks_for_confirmation,
    }
