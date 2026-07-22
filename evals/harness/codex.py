from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import AgentResult, run_process


def build_command(prompt: str, model: str | None = None) -> list[str]:
    command = ["codex", "exec", "--json", "--full-auto"]
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
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "agent_message" and isinstance(item.get("text"), str):
            response = item["text"]
        if item_type not in {"agent_message", "reasoning"}:
            tool_trace.append({"event": event.get("type"), "item": item})
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
