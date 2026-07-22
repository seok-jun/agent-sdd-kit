from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import AgentResult, run_process


ALLOWED_TOOLS = [
    "Skill",
    "Read",
    "Glob",
    "Grep",
    "Edit",
    "Write",
    "Bash(git status *)",
    "Bash(git diff *)",
    "Bash(git branch *)",
    "Bash(git merge-base *)",
    "Bash(rg *)",
]


def build_command(prompt: str, model: str | None = None) -> list[str]:
    command = [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--permission-mode",
        "dontAsk",
        "--setting-sources",
        "project",
        "--strict-mcp-config",
        "--tools",
        "Skill,Read,Glob,Grep,Edit,Write,Bash",
        "--allowedTools",
        ",".join(ALLOWED_TOOLS),
    ]
    if model:
        command.extend(["--model", model])
    command.extend(["--", prompt])
    return command


def _parse(
    stdout: str,
) -> tuple[
    str,
    list[dict[str, Any]],
    dict[str, Any],
    list[Any],
    list[dict[str, Any]],
    list[str],
]:
    response_parts: list[str] = []
    result_response = ""
    tool_trace: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    permission_denials: list[Any] = []
    rate_limit_events: list[dict[str, Any]] = []
    adapter_errors: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "rate_limit_event":
            rate_limit_events.append(event)
            info = event.get("rate_limit_info")
            status = info.get("status") if isinstance(info, dict) else event.get("status")
            if status != "allowed":
                adapter_errors.append(f"Claude rate limit status is {status!r}")
        if event.get("type") == "result":
            if isinstance(event.get("result"), str):
                result_response = event["result"]
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            denials = event.get("permission_denials")
            if isinstance(denials, list):
                permission_denials.extend(denials)
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        for block in message.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and event.get("type") == "assistant":
                text = block.get("text")
                if isinstance(text, str) and text:
                    response_parts.append(text)
            elif block.get("type") == "tool_use":
                tool_trace.append(
                    {"name": block.get("name"), "input": block.get("input", {})}
                )
    response = "\n\n".join(response_parts) if response_parts else result_response
    return (
        response,
        tool_trace,
        usage,
        permission_denials,
        rate_limit_events,
        adapter_errors,
    )


def run(
    prompt: str,
    workspace: Path,
    timeout: int,
    model: str | None = None,
    skill: str | None = None,
) -> AgentResult:
    command = build_command(prompt, model)
    exit_code, stdout, stderr, timed_out = run_process(command, workspace, timeout)
    (
        response,
        tool_trace,
        usage,
        permission_denials,
        rate_limit_events,
        adapter_errors,
    ) = _parse(stdout)
    return AgentResult(
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        response=response,
        tool_trace=tool_trace,
        usage=usage,
        timed_out=timed_out,
        adapter_errors=adapter_errors,
        permission_denials=permission_denials,
        rate_limit_events=rate_limit_events,
    )
