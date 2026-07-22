from __future__ import annotations

import re
from pathlib import Path

from evals.harness.core import (
    CheckResult,
    RunContext,
    common_registry,
    is_skill_path,
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
    shell_discovery = re.compile(
        r"(?:^|[;&|()]\s*|\b)(?:git\s+(?:status|log|diff|branch)|rg|find|ls|grep|sed|cat|head|tail)(?:\s|$)",
        re.IGNORECASE,
    )
    for name, tool_input in tool_calls(context):
        lowered = name.lower()
        values = [value for value in tool_input.values() if isinstance(value, str)]
        if lowered in {"glob", "grep"} and not values:
            matched.append(name)
        elif lowered in {"glob", "grep"} and any(not is_skill_path(value) for value in values):
            matched.append(f"{name}({values})")
        elif lowered == "read" and any(not is_skill_path(value) for value in values):
            matched.append(f"Read({values})")
        elif lowered in {"bash", "command_execution"}:
            commands = [
                tool_input.get("command", ""),
                tool_input.get("cmd", ""),
            ]
            for command in commands:
                if isinstance(command, str) and shell_discovery.search(command):
                    matched.append(command)
    return CheckResult(not matched, f"discovery events={matched}")


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
