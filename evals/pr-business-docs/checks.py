from __future__ import annotations

import re
from pathlib import Path

from evals.harness.core import CheckResult, RunContext, common_registry, project_paths, tool_calls


def inspects_diff(context: RunContext) -> CheckResult:
    commands = [
        value
        for name, tool_input in tool_calls(context)
        if name.lower() in {"bash", "command_execution"}
        for key in ("command", "cmd")
        if isinstance((value := tool_input.get(key)), str)
    ]
    matched = [command for command in commands if re.search(r"\bgit\s+diff(?:\s|$)", command)]
    return CheckResult(bool(matched), f"git diff commands={matched}")


def identifies_document_candidates(context: RunContext) -> CheckResult:
    response = context.agent.response.lower()
    path_candidate = bool(re.search(r"(?:docs/)?business/.+\.md|order-cancel\.md", response))
    reason = any(marker in response for marker in ["부분 취소", "cancelpartially", "변경", "영향"])
    return CheckResult(path_candidate and reason, f"path_candidate={path_candidate}, reason={reason}")


def grounds_in_supplied_diff(context: RunContext) -> CheckResult:
    markers = [
        marker
        for marker in ["부분 취소", "cancelPartially", "itemIds", "전체 취소"]
        if marker in context.agent.response
    ]
    semantic = any(marker in markers for marker in ["부분 취소", "전체 취소"])
    code = any(marker in markers for marker in ["cancelPartially", "itemIds"])
    return CheckResult(semantic and code, f"diff evidence markers={markers}")


def preserves_partial_update_default(context: RunContext) -> CheckResult:
    response = context.agent.response
    partial = bool(re.search(r"(?:변경된|관련된|필요한).{0,25}부분|부분.{0,20}(?:갱신|수정)", response, re.DOTALL))
    rejects_rewrite = bool(
        re.search(r"전체.{0,25}(?:재작성|새로\s*쓰).{0,35}(?:하지|대신|확인|승인)", response, re.DOTALL)
    )
    return CheckResult(partial and rejects_rewrite, f"partial_update={partial}, rejects_rewrite={rejects_rewrite}")


def reports_code_issue_only(context: RunContext) -> CheckResult:
    code_changes = [
        p
        for p in project_paths(context.changed_paths)
        if Path(p).suffix.lower() in {".java", ".kt", ".py", ".js", ".ts", ".sql"}
    ]
    report_only = bool(
        re.search(r"(?:코드|문제).{0,50}(?:보고|알리).{0,50}(?:수정하지|별도|범위 밖)", context.agent.response, re.DOTALL)
        or re.search(r"(?:수정하지|고치지).{0,50}(?:보고|알리)", context.agent.response, re.DOTALL)
    )
    return CheckResult(not code_changes and report_only, f"code changes={code_changes}, report_only={report_only}")


def asks_for_comparison_base(context: RunContext) -> CheckResult:
    response = context.agent.response
    base = bool(re.search(r"비교\s*기준|base|기준\s*브랜치|HEAD", response, re.IGNORECASE))
    request = bool(re.search(r"(?:알려\s*주세요|지정해\s*주세요|확인.{0,20}(?:필요|후|뒤)|어느.{0,20}(?:인가요|할까요)|\?)", response))
    return CheckResult(base and request, f"base={base}, explicit_request={request}")


CHECK_REGISTRY = {
    **common_registry(),
    "inspects_diff": inspects_diff,
    "identifies_document_candidates": identifies_document_candidates,
    "grounds_in_supplied_diff": grounds_in_supplied_diff,
    "preserves_partial_update_default": preserves_partial_update_default,
    "reports_code_issue_only": reports_code_issue_only,
    "asks_for_comparison_base": asks_for_comparison_base,
}
