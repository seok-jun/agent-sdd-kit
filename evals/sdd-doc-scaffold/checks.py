from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from evals.harness.core import (
    CheckResult,
    RunContext,
    common_registry,
    project_paths,
    tool_calls,
)


def proposes_task_grade(context: RunContext) -> CheckResult:
    markers = ["Trivial", "Small", "Medium", "Large", "Epic"]
    matched = [marker for marker in markers if marker in context.agent.response]
    return CheckResult(bool(matched), f"grade markers={matched}")


def proposes_required_documents(context: RunContext) -> CheckResult:
    markers = ["01-as-is-flow.md", "02-to-be-mapping.md", "change-plan", "backlog"]
    matched = [marker for marker in markers if marker in context.agent.response]
    return CheckResult(len(matched) >= 2, f"document markers={matched}")


def no_markdown_created(context: RunContext) -> CheckResult:
    paths = [p for p in project_paths(context.changed_paths) if Path(p).suffix.lower() == ".md"]
    return CheckResult(not paths, f"Markdown changes={paths}")


def does_not_advance_stage(context: RunContext) -> CheckResult:
    advanced = [
        p
        for p in project_paths(context.changed_paths)
        if any(token in p for token in ["02-to-be", "change-plans/", "backlog/"])
    ]
    response = context.agent.response
    gate = bool(
        re.search(r"Stage\s*1.{0,80}(?:확인|승인).{0,80}(?:전|먼저)", response, re.DOTALL | re.IGNORECASE)
        and re.search(r"(?:진행|생성|작성).{0,30}(?:하지|보류|멈)", response, re.DOTALL)
    )
    return CheckResult(not advanced and gate, f"advanced={advanced}, explicit_gate={gate}")


def no_repository_discovery(context: RunContext) -> CheckResult:
    matched: list[str] = []
    for name, tool_input in tool_calls(context):
        lowered = name.lower()
        if context.harness == "claude" and lowered in {"read", "glob", "grep", "bash"}:
            matched.append(name)
        elif context.harness == "codex" and lowered in {
            "command_execution",
            "file_read",
            "directory_listing",
            "search_files",
        }:
            matched.append(name)
    return CheckResult(not matched, f"discovery events={matched}")


def existing_sdd_unchanged(context: RunContext) -> CheckResult:
    paths = [p for p in project_paths(context.changed_paths) if p.startswith("docs/payment-recovery-sdd/")]
    return CheckResult(not paths, f"existing SDD changes={paths}")


def _expected_stage_files(context: RunContext) -> list[str]:
    paths = context.case.get("expected_stage_files", [])
    return [path for path in paths if isinstance(path, str)]


def _relation_block(text: str) -> list[str]:
    lines = text.splitlines()
    first_content = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_content is None or not lines[first_content].lstrip().startswith("# "):
        return []

    block: list[str] = []
    for line in lines[first_content + 1 :]:
        stripped = line.strip()
        if not stripped and not block:
            continue
        if stripped.startswith("|"):
            block.append(stripped)
            continue
        if block:
            break
        return []
    return block


def stage1_files_created(context: RunContext) -> CheckResult:
    paths = _expected_stage_files(context)
    missing = [path for path in paths if not (context.workspace / path).is_file()]
    return CheckResult(bool(paths) and not missing, f"expected={paths}, missing={missing}")


def relation_block_present(context: RunContext) -> CheckResult:
    invalid: list[str] = []
    for path in _expected_stage_files(context):
        target = context.workspace / path
        if not target.is_file():
            invalid.append(f"{path}: missing")
            continue
        block = _relation_block(target.read_text(encoding="utf-8"))
        joined = "\n".join(block)
        required_rows = ["문서 종류", "선행 문서", "후속 문서", "관련 코드"]
        if len(block) < 3 or not all(row in joined for row in required_rows):
            invalid.append(f"{path}: relation table missing required rows")
    return CheckResult(not invalid and bool(_expected_stage_files(context)), f"invalid={invalid}")


def relative_links_resolve(context: RunContext) -> CheckResult:
    unresolved: list[str] = []
    link_count = 0
    workspace = context.workspace.resolve()
    for path in _expected_stage_files(context):
        target = context.workspace / path
        if not target.is_file():
            unresolved.append(f"{path}: missing")
            continue
        block = "\n".join(_relation_block(target.read_text(encoding="utf-8")))
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", block)
        if not links:
            unresolved.append(f"{path}: no relation link")
            continue
        for raw_link in links:
            parsed = urlparse(raw_link.strip().strip("<>"))
            if parsed.scheme or not parsed.path:
                unresolved.append(f"{path}: non-relative link {raw_link}")
                continue
            resolved = (target.parent / unquote(parsed.path)).resolve()
            link_count += 1
            try:
                resolved.relative_to(workspace)
            except ValueError:
                unresolved.append(f"{path}: link escapes workspace {raw_link}")
                continue
            if not resolved.is_file():
                unresolved.append(f"{path}: unresolved {raw_link}")
    return CheckResult(link_count > 0 and not unresolved, f"links={link_count}, unresolved={unresolved}")


def no_undeclared_files(context: RunContext) -> CheckResult:
    declared = set(_expected_stage_files(context))
    changed = set(project_paths(context.changed_paths))
    undeclared = sorted(changed - declared)
    missing = sorted(path for path in declared if not (context.workspace / path).is_file())
    return CheckResult(
        bool(declared) and not undeclared and not missing,
        f"declared={sorted(declared)}, undeclared={undeclared}, missing={missing}",
    )


CHECK_REGISTRY = {
    **common_registry(),
    "proposes_task_grade": proposes_task_grade,
    "proposes_required_documents": proposes_required_documents,
    "no_markdown_created": no_markdown_created,
    "does_not_advance_stage": does_not_advance_stage,
    "no_repository_discovery": no_repository_discovery,
    "existing_sdd_unchanged": existing_sdd_unchanged,
    "stage1_files_created": stage1_files_created,
    "relation_block_present": relation_block_present,
    "relative_links_resolve": relative_links_resolve,
    "no_undeclared_files": no_undeclared_files,
}
