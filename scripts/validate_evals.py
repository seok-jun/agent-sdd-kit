#!/usr/bin/env python3
"""Backward-compatible entry point. Prefer validate_eval_specs.py."""

from validate_eval_specs import main


if __name__ == "__main__":
    raise SystemExit(main())
