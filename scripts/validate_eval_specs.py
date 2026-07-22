#!/usr/bin/env python3
"""Validate executable Skill eval specifications, fixtures, and check registries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.harness.core import load_check_registry  # noqa: E402

VALID_CATEGORIES = {"trigger", "non-trigger", "procedure"}


class ValidationError(Exception):
    pass


def require_string(value: Any, field: str, source: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{source}: '{field}' must be a non-empty string")
    return value


def validate_spec(source: Path) -> tuple[int, int]:
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{source}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"{source}: root must be an object")

    skill = require_string(payload.get("skill"), "skill", source)
    if source.parent.name != skill:
        raise ValidationError(f"{source}: skill must match parent directory '{source.parent.name}'")
    if not isinstance(payload.get("version"), int) or payload["version"] < 1:
        raise ValidationError(f"{source}: version must be a positive integer")

    defaults = payload.get("defaults")
    if not isinstance(defaults, dict):
        raise ValidationError(f"{source}: defaults must be an object")
    default_fixture = require_string(defaults.get("fixture"), "defaults.fixture", source)
    trials = defaults.get("trials")
    if not isinstance(trials, int) or not 3 <= trials <= 5:
        raise ValidationError(f"{source}: defaults.trials must be between 3 and 5")

    checks_path = source.parent / "checks.py"
    if not checks_path.is_file():
        raise ValidationError(f"{source}: missing {checks_path.name}")
    try:
        registry = load_check_registry(checks_path)
    except Exception as exc:
        raise ValidationError(f"{checks_path}: cannot load CHECK_REGISTRY: {exc}") from exc

    cases = payload.get("cases")
    if not isinstance(cases, list) or not 10 <= len(cases) <= 20:
        raise ValidationError(f"{source}: cases must contain 10 to 20 prompts")

    seen_ids: set[str] = set()
    categories: set[str] = set()
    fixtures: set[str] = {default_fixture}
    for case in cases:
        if not isinstance(case, dict):
            raise ValidationError(f"{source}: every case must be an object")
        case_id = require_string(case.get("id"), "id", source)
        if case_id in seen_ids:
            raise ValidationError(f"{source}: duplicate case id '{case_id}'")
        seen_ids.add(case_id)
        category = require_string(case.get("category"), "category", source)
        if category not in VALID_CATEGORIES:
            raise ValidationError(f"{source}: case '{case_id}' has invalid category '{category}'")
        categories.add(category)
        require_string(case.get("prompt"), "prompt", source)
        should_trigger = case.get("should_trigger")
        if not isinstance(should_trigger, bool):
            raise ValidationError(f"{source}: case '{case_id}' should_trigger must be boolean")
        if category == "non-trigger" and should_trigger:
            raise ValidationError(f"{source}: non-trigger case '{case_id}' cannot trigger")
        if category != "non-trigger" and not should_trigger:
            raise ValidationError(f"{source}: {category} case '{case_id}' must trigger")

        checks = case.get("expected_checks")
        if not isinstance(checks, list) or not checks:
            raise ValidationError(f"{source}: case '{case_id}' expected_checks must be non-empty")
        unknown = [check for check in checks if check not in registry]
        if unknown:
            raise ValidationError(f"{source}: case '{case_id}' has unknown checks: {unknown}")
        trigger_check = "skill_triggered" if should_trigger else "skill_not_triggered"
        if trigger_check not in checks:
            raise ValidationError(f"{source}: case '{case_id}' must include '{trigger_check}'")

        fixture = require_string(case.get("fixture", default_fixture), "fixture", source)
        if Path(fixture).name != fixture:
            raise ValidationError(f"{source}: case '{case_id}' fixture must be a simple name")
        fixtures.add(fixture)

    missing_categories = VALID_CATEGORIES - categories
    if missing_categories:
        raise ValidationError(f"{source}: missing categories {sorted(missing_categories)}")
    for fixture in fixtures:
        base = source.parent / "fixtures" / fixture / "base"
        if not base.is_dir():
            raise ValidationError(f"{source}: fixture '{fixture}' is missing base/")
    return len(cases), len(registry)


def main() -> int:
    sources = sorted((ROOT / "evals").glob("*/prompts.json"))
    if not sources:
        print("ERROR: no eval prompt sets found", file=sys.stderr)
        return 1
    try:
        counts = [validate_spec(source) for source in sources]
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"Validated {sum(cases for cases, _ in counts)} cases across {len(sources)} skills "
        f"with {sum(checks for _, checks in counts)} registered check entries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
