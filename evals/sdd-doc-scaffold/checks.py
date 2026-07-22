from __future__ import annotations

from pathlib import Path

from evals.harness.core import CheckResult, RunContext, common_registry, project_paths, tool_trace_text


def proposes_task_grade(context: RunContext) -> CheckResult:
    markers = ["등급", "Trivial", "Small", "Medium", "Large", "Epic"]
    matched = [marker for marker in markers if marker in context.agent.response]
    return CheckResult(bool(matched), f"grade markers={matched}")


def proposes_required_documents(context: RunContext) -> CheckResult:
    markers = ["01-as-is-flow.md", "02-to-be-mapping.md", "change-plan", "backlog", "문서"]
    matched = [marker for marker in markers if marker in context.agent.response]
    return CheckResult(bool(matched), f"document markers={matched}")


def no_markdown_created(context: RunContext) -> CheckResult:
    paths = [p for p in project_paths(context.changed_paths) if Path(p).suffix.lower() == ".md"]
    return CheckResult(not paths, f"Markdown changes={paths}")


def does_not_advance_stage(context: RunContext) -> CheckResult:
    advanced = [
        p
        for p in project_paths(context.changed_paths)
        if any(token in p for token in ["02-to-be", "change-plans/", "backlog/"])
    ]
    response_markers = [marker for marker in ["Stage 1", "완료", "확인"] if marker in context.agent.response]
    return CheckResult(not advanced and bool(response_markers), f"advanced={advanced}, markers={response_markers}")


def no_repository_discovery(context: RunContext) -> CheckResult:
    trace = tool_trace_text(context)
    forbidden = ["git status", "git log", "git diff", "git branch", "rg ", "find ", "ls "]
    matched = [command for command in forbidden if command in trace]
    return CheckResult(not matched, f"discovery commands={matched}")


def existing_sdd_unchanged(context: RunContext) -> CheckResult:
    paths = [p for p in project_paths(context.changed_paths) if p.startswith("docs/payment-recovery-sdd/")]
    return CheckResult(not paths, f"existing SDD changes={paths}")


CHECK_REGISTRY = {
    **common_registry(),
    "proposes_task_grade": proposes_task_grade,
    "proposes_required_documents": proposes_required_documents,
    "no_markdown_created": no_markdown_created,
    "does_not_advance_stage": does_not_advance_stage,
    "no_repository_discovery": no_repository_discovery,
    "existing_sdd_unchanged": existing_sdd_unchanged,
}
