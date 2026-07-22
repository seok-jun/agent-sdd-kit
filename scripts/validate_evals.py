#!/usr/bin/env python3
"""Backward-compatible entry point. Prefer validate_eval_specs.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_eval_specs import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
