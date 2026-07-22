from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse


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
    adapter_errors: list[str] = field(default_factory=list)
    permission_denials: list[Any] = field(default_factory=list)
    rate_limit_events: list[dict[str, Any]] = field(default_factory=list)
    rollout: str = ""


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


def run_process(
    command: list[str],
    cwd: Path,
    timeout: int,
    input_text: str | None = None,
) -> tuple[int, str, str, bool]:
    executable = shutil.which(command[0])
    if executable is None:
        raise FileNotFoundError(f"CLI not found: {command[0]}")
    resolved_command = [executable, *command[1:]]
    try:
        process_options: dict[str, Any] = {
            "cwd": cwd,
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": timeout,
            "check": False,
            "env": {**os.environ, "NO_COLOR": "1"},
        }
        if input_text is None:
            process_options["stdin"] = subprocess.DEVNULL
        else:
            process_options["input"] = input_text
        completed = subprocess.run(resolved_command, **process_options)
        return completed.returncode, completed.stdout, completed.stderr, False
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return 124, stdout, stderr, True


def _remove_readonly(func: Callable[..., Any], path: str, _exc_info: Any) -> None:
    """Retry Windows cleanup after clearing Git's read-only file attribute."""

    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_workspace(workspace: Path) -> None:
    shutil.rmtree(workspace, onerror=_remove_readonly)


def git(workspace: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout or ""


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


MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)")


def _copy_skill_with_references(repo_root: Path, source_skill: Path, target_skill: Path) -> None:
    """Copy a Skill and every local file linked directly from SKILL.md.

    Relative links keep the same relationship to the installed SKILL.md. This
    supports repositories that keep shared references outside a Skill folder,
    while rejecting missing files and paths that escape the repository or the
    disposable eval workspace.
    """

    shutil.copytree(source_skill, target_skill)
    source_manifest = source_skill / "SKILL.md"
    target_manifest = target_skill / "SKILL.md"
    repo_root = repo_root.resolve()
    workspace = target_skill.parents[2].resolve()

    for match in MARKDOWN_LINK.finditer(source_manifest.read_text(encoding="utf-8")):
        raw_target = match.group(1).strip("<>")
        if re.match(r"^[A-Za-z]:[\\/]", raw_target):
            raise ValueError(f"Absolute Skill reference is not portable: {raw_target}")
        parsed = urlparse(raw_target)
        if parsed.scheme or raw_target.startswith("#"):
            continue
        path_text = unquote(parsed.path)
        if not path_text:
            continue
        if Path(path_text).is_absolute():
            raise ValueError(f"Absolute Skill reference is not portable: {raw_target}")

        source_reference = (source_manifest.parent / path_text).resolve()
        try:
            source_reference.relative_to(repo_root)
        except ValueError as exc:
            raise ValueError(f"Skill reference escapes repository: {raw_target}") from exc
        if not source_reference.is_file():
            raise FileNotFoundError(f"Skill reference not found: {raw_target} -> {source_reference}")

        target_reference = (target_manifest.parent / path_text).resolve()
        try:
            target_reference.relative_to(workspace)
        except ValueError as exc:
            raise ValueError(f"Installed Skill reference escapes workspace: {raw_target}") from exc
        target_reference.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_reference, target_reference)


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
        skill_home = ".agents/skills" if harness == "codex" else ".claude/skills"
        try:
            _copy_skill_with_references(
                repo_root, source_skill, workspace / skill_home / skill
            )
        except Exception:
            if destination is None and workspace.name.startswith("agent-sdd-eval-"):
                remove_workspace(workspace)
            raise

    git(workspace, "init", "-q", "-b", "main")
    git(workspace, "config", "user.name", "Skill Eval")
    git(workspace, "config", "user.email", "skill-eval@example.invalid")
    git(workspace, "add", ".")
    git(workspace, "commit", "-q", "-m", "eval fixture baseline", "--allow-empty")

    _copy_contents(fixture_root / "worktree", workspace)
    return workspace


def collect_changes(workspace: Path) -> tuple[list[str], str]:
    # Intent-to-add makes new files visible in the normal diff without staging
    # their contents. Eval workspaces are disposable, so mutating their index is
    # safe and lets workspace.diff contain the artifacts under evaluation.
    git(workspace, "add", "--intent-to-add", "--", ".")
    paths = sorted(
        path.strip()
        for path in git(workspace, "diff", "--name-only", "HEAD").splitlines()
        if path.strip()
    )
    diff = git(workspace, "diff", "--binary", "HEAD")
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
    metadata: dict[str, Any] | None = None,
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "trace.jsonl").write_text(context.agent.stdout, encoding="utf-8")
    (artifact_dir / "stderr.txt").write_text(context.agent.stderr, encoding="utf-8")
    (artifact_dir / "response.md").write_text(context.agent.response, encoding="utf-8")
    (artifact_dir / "workspace.diff").write_text(context.diff, encoding="utf-8")
    if context.agent.rollout:
        (artifact_dir / "codex-rollout.jsonl").write_text(
            context.agent.rollout, encoding="utf-8"
        )
    if context.agent.permission_denials:
        (artifact_dir / "permission-denials.json").write_text(
            json.dumps(context.agent.permission_denials, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if context.agent.rate_limit_events:
        (artifact_dir / "rate-limit-events.json").write_text(
            json.dumps(context.agent.rate_limit_events, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    payload = {
        "skill": context.skill,
        "case_id": context.case["id"],
        "harness": context.harness,
        "command": context.agent.command,
        "exit_code": context.agent.exit_code,
        "timed_out": context.agent.timed_out,
        "usage": context.agent.usage,
        "adapter_errors": context.agent.adapter_errors,
        "permission_denials": context.agent.permission_denials,
        "rate_limit_events": context.agent.rate_limit_events,
        "changed_paths": context.changed_paths,
        **(metadata or {}),
        **evaluation,
    }
    (artifact_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def project_paths(paths: list[str]) -> list[str]:
    return [
        path
        for path in paths
        if not path.startswith((".agents/skills/", ".codex/skills/", ".claude/skills/"))
    ]


def skill_trigger_evidence(context: RunContext) -> str | None:
    """Return adapter-normalized evidence that the target Skill was invoked."""

    skill = context.skill.lower()
    for event in context.agent.tool_trace:
        if not isinstance(event, dict):
            continue
        name = str(event.get("name", "")).lower()
        tool_input = event.get("input", {})
        if name != "skill" or not isinstance(tool_input, dict):
            continue
        value = tool_input.get("skill")
        if isinstance(value, str) and value.strip().lower().lstrip("$/") == skill:
            return f"Skill activation input.skill={value!r}"
    return None


def tool_calls(context: RunContext) -> list[tuple[str, dict[str, Any]]]:
    """Normalize the small subset of Claude and Codex trace events used by checks."""

    calls: list[tuple[str, dict[str, Any]]] = []
    for event in context.agent.tool_trace:
        if not isinstance(event, dict):
            continue
        if isinstance(event.get("name"), str):
            tool_input = event.get("input", {})
            calls.append((event["name"], tool_input if isinstance(tool_input, dict) else {}))
            continue
        item = event.get("item")
        if isinstance(item, dict) and isinstance(item.get("type"), str):
            calls.append((item["type"], item))
    return calls


def common_registry() -> dict[str, Check]:
    def skill_triggered(context: RunContext) -> CheckResult:
        evidence = skill_trigger_evidence(context)
        return CheckResult(evidence is not None, evidence or "trigger evidence not found")

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
        patterns = [
            r"(?:확인|승인|선택|결정).{0,40}(?:해\s*주세요|해주세요|해줘|부탁드립니다|받은\s*뒤|받기\s*전|필요합니다|할까요|하시겠습니까|\?)",
            r"(?:알려\s*주세요|말해\s*주세요|입력해\s*주세요)",
        ]
        matched = [pattern for pattern in patterns if re.search(pattern, response, re.DOTALL)]
        changed = project_paths(context.changed_paths)
        return CheckResult(
            bool(matched) and not changed,
            f"confirmation_patterns={len(matched)}, changed={changed}",
        )

    return {
        "skill_triggered": skill_triggered,
        "skill_not_triggered": skill_not_triggered,
        "no_project_files_changed": no_project_files_changed,
        "no_code_modified": no_code_modified,
        "no_sdd_modified": no_sdd_modified,
        "asks_for_confirmation": asks_for_confirmation,
    }
