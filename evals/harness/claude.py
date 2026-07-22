from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import AgentResult, run_process


ALLOWED_TOOLS = [
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
        "--allowedTools",
        *ALLOWED_TOOLS,
    ]
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    return command


def _parse(stdout: str) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    response = ""
    tool_trace: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            if isinstance(event.get("result"), str):
                response = event["result"]
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        for block in message.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and event.get("type") == "assistant":
                response = block.get("text", response)
            elif block.get("type") == "tool_use":
                tool_trace.append(
                    {"name": block.get("name"), "input": block.get("input", {})}
                )
    return response, tool_trace, usage


def run(prompt: str, workspace: Path, timeout: int, model: str | None = None) -> AgentResult:
    command = build_command(prompt, model)
    exit_code, stdout, stderr, timed_out = run_process(command, workspace, timeout)
    response, tool_trace, usage = _parse(stdout)
    return AgentResult(
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        response=response,
        tool_trace=tool_trace,
        usage=usage,
        timed_out=timed_out,
    )
