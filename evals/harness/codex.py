from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .core import AgentResult, run_process


DEFAULT_MODEL = "gpt-5.4"


def build_command(prompt: str, model: str | None = None) -> list[str]:
    # The prompt is intentionally sent through UTF-8 stdin in run(). Passing
    # Korean text through an npm .cmd shim can corrupt argv on Windows/CP949.
    command = [
        "codex",
        "exec",
        "--json",
        "--sandbox",
        "workspace-write",
        "--ignore-user-config",
        "--ignore-rules",
    ]
    command.extend(["--model", model or DEFAULT_MODEL])
    return command


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for child in value.values() for text in _strings(child)]
    if isinstance(value, list):
        return [text for child in value for text in _strings(child)]
    return []


def _rollout_path(thread_id: str, sessions_root: Path | None = None) -> Path:
    if sessions_root is None:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        sessions_root = codex_home / "sessions"
    try:
        candidates = list(sessions_root.rglob(f"*{thread_id}*.jsonl"))
    except OSError as exc:
        raise RuntimeError(f"Cannot search Codex rollouts in {sessions_root}: {exc}") from exc
    if not candidates:
        raise FileNotFoundError(
            f"Codex rollout not found for thread_id={thread_id} under {sessions_root}"
        )
    if len(candidates) > 1:
        candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    return candidates[0]


def _skill_events_from_rollout(rollout: str, target_skill: str) -> list[dict[str, Any]]:
    """Read only injected user-role <skill> blocks, never installed-skill lists."""

    events: list[dict[str, Any]] = []
    block_pattern = re.compile(r"<skill\b[^>]*>(.*?)</skill>", re.IGNORECASE | re.DOTALL)
    name_pattern = re.compile(r"<name>\s*([^<]+?)\s*</name>", re.IGNORECASE)
    for line in rollout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        candidates = [event]
        for key in ("payload", "item"):
            if isinstance(event.get(key), dict):
                candidates.append(event[key])
        for candidate in candidates:
            if str(candidate.get("role", "")).lower() != "user":
                continue
            for text in _strings(candidate.get("content")):
                for block in block_pattern.findall(text):
                    match = name_pattern.search(block)
                    if match and match.group(1).strip().lower() == target_skill.lower():
                        events.append(
                            {
                                "name": "Skill",
                                "input": {"skill": match.group(1).strip()},
                                "source": "codex-rollout-user-record",
                            }
                        )
    return events


def _parse(
    stdout: str,
    skill: str,
    sessions_root: Path | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any], str, list[str]]:
    response_parts: list[str] = []
    tool_trace: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    thread_id: str | None = None
    adapter_errors: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = event["thread_id"]
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "agent_message" and isinstance(item.get("text"), str):
            response_parts.append(item["text"])
        if item_type not in {"agent_message", "reasoning"}:
            tool_trace.append({"event": event.get("type"), "item": item})

    rollout = ""
    if thread_id is None:
        adapter_errors.append("Codex thread.started event did not contain thread_id")
    else:
        try:
            rollout = _rollout_path(thread_id, sessions_root).read_text(encoding="utf-8")
            tool_trace.extend(_skill_events_from_rollout(rollout, skill))
        except (OSError, RuntimeError) as exc:
            adapter_errors.append(str(exc))
    return "\n\n".join(response_parts), tool_trace, usage, rollout, adapter_errors


def run(
    prompt: str,
    workspace: Path,
    timeout: int,
    model: str | None = None,
    skill: str | None = None,
) -> AgentResult:
    if not skill:
        raise ValueError("Codex adapter requires the target skill name")
    command = build_command(prompt, model)
    exit_code, stdout, stderr, timed_out = run_process(
        command, workspace, timeout, input_text=prompt
    )
    response, tool_trace, usage, rollout, adapter_errors = _parse(stdout, skill)
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
        rollout=rollout,
    )
