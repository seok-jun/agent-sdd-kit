#!/usr/bin/env python3
"""Validate data-driven Skill eval files using only the Python standard library."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evals"
VALID_CATEGORIES = {"trigger", "non-trigger", "procedure"}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_non_empty_string(value: Any, field: str, source: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{source}: '{field}' must be a non-empty string")
    return value


def validate_case(case: Any, source: Path, seen_ids: set[str]) -> None:
    if not isinstance(case, dict):
        fail(f"{source}: every case must be an object")

    case_id = require_non_empty_string(case.get("id"), "id", source)
    if case_id in seen_ids:
        fail(f"{source}: duplicate case id '{case_id}'")
    seen_ids.add(case_id)

    category = require_non_empty_string(case.get("category"), "category", source)
    if category not in VALID_CATEGORIES:
        fail(f"{source}: case '{case_id}' has invalid category '{category}'")

    require_non_empty_string(case.get("query"), "query", source)

    expected = case.get("expected")
    if not isinstance(expected, dict):
        fail(f"{source}: case '{case_id}' expected must be an object")
    if not isinstance(expected.get("should_trigger"), bool):
        fail(f"{source}: case '{case_id}' should_trigger must be boolean")

    behaviors = expected.get("behaviors")
    if not isinstance(behaviors, list) or not behaviors:
        fail(f"{source}: case '{case_id}' behaviors must be a non-empty array")
    for behavior in behaviors:
        require_non_empty_string(behavior, "behavior", source)

    if category == "non-trigger" and expected["should_trigger"]:
        fail(f"{source}: non-trigger case '{case_id}' cannot expect a trigger")
    if category in {"trigger", "procedure"} and not expected["should_trigger"]:
        fail(f"{source}: {category} case '{case_id}' must expect a trigger")


def validate_file(source: Path) -> int:
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{source}: cannot read valid JSON: {exc}")

    if not isinstance(payload, dict):
        fail(f"{source}: root must be an object")
    require_non_empty_string(payload.get("skill"), "skill", source)
    if not isinstance(payload.get("version"), int) or payload["version"] < 1:
        fail(f"{source}: version must be a positive integer")

    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) < 3:
        fail(f"{source}: at least three eval cases are required")

    seen_ids: set[str] = set()
    for case in cases:
        validate_case(case, source, seen_ids)

    categories = {case["category"] for case in cases}
    missing = VALID_CATEGORIES - categories
    if missing:
        fail(f"{source}: missing categories: {', '.join(sorted(missing))}")

    return len(cases)


def main() -> None:
    files = sorted(EVAL_DIR.glob("*.json"))
    if not files:
        fail(f"no eval files found in {EVAL_DIR}")

    total = sum(validate_file(source) for source in files)
    print(f"Validated {total} cases across {len(files)} eval files.")


if __name__ == "__main__":
    main()
