from __future__ import annotations

from pathlib import Path

from evals.harness.core import CheckResult, RunContext, common_registry, project_paths, tool_trace_text


def inspects_diff(context: RunContext) -> CheckResult:
    trace = tool_trace_text(context)
    return CheckResult("git diff" in trace, "git diff found" if "git diff" in trace else "git diff not found")


def identifies_document_candidates(context: RunContext) -> CheckResult:
    markers = [marker for marker in ["business", "문서", "후보", "order-cancel"] if marker in context.agent.response]
    return CheckResult(len(markers) >= 2, f"document markers={markers}")


def grounds_in_supplied_diff(context: RunContext) -> CheckResult:
    markers = [
        marker
        for marker in ["부분 취소", "cancelPartially", "itemIds", "전체 취소"]
        if marker in context.agent.response
    ]
    return CheckResult(bool(markers), f"diff evidence markers={markers}")


def preserves_partial_update_default(context: RunContext) -> CheckResult:
    response = context.agent.response
    partial = "부분" in response
    confirmation = any(marker in response for marker in ["확인", "승인", "이유", "범위"])
    return CheckResult(partial and confirmation, f"partial={partial}, confirmation={confirmation}")


def reports_code_issue_only(context: RunContext) -> CheckResult:
    code_changes = [
        p
        for p in project_paths(context.changed_paths)
        if Path(p).suffix.lower() in {".java", ".kt", ".py", ".js", ".ts", ".sql"}
    ]
    markers = [marker for marker in ["보고", "수정하지", "별도", "범위"] if marker in context.agent.response]
    return CheckResult(not code_changes and bool(markers), f"code changes={code_changes}, markers={markers}")


def asks_for_comparison_base(context: RunContext) -> CheckResult:
    markers = [marker for marker in ["비교 기준", "base", "기준 브랜치", "HEAD", "확인"] if marker in context.agent.response]
    return CheckResult(len(markers) >= 2, f"base markers={markers}")


CHECK_REGISTRY = {
    **common_registry(),
    "inspects_diff": inspects_diff,
    "identifies_document_candidates": identifies_document_candidates,
    "grounds_in_supplied_diff": grounds_in_supplied_diff,
    "preserves_partial_update_default": preserves_partial_update_default,
    "reports_code_issue_only": reports_code_issue_only,
    "asks_for_comparison_base": asks_for_comparison_base,
}
