"""Small, consistent CLI presentation layer for evidence gates.

Validators continue to return their complete structured reports.  This module
only controls what is printed to a terminal: one conclusion line followed by
at most a short list of ``file: kind`` failures.  The complete report is
always written by the caller to ``--output``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _failure_items(value: Any, prefix: str = "") -> list[str]:
    """Extract stable short failure labels without dumping nested JSON."""
    found: list[str] = []
    if isinstance(value, dict):
        if "kind" in value:
            where = prefix or value.get("where") or "gate"
            found.append(f"{where}: {value.get('kind')}")
            return found
        for key, item in value.items():
            if key in {"errors", "error", "failures", "input_error", "checks", "results"}:
                found.extend(_failure_items(item, prefix))
            elif isinstance(item, dict) and item.get("passed") is False:
                label = item.get("file") or prefix or item.get("artifact") or "gate"
                nested = item.get("errors") or item.get("error") or item.get("results") or item.get("checks") or "failed"
                found.extend(_failure_items(nested, str(label)))
            elif key == "passed" and item is False:
                found.append(f"{prefix or 'gate'}: failed")
    elif isinstance(value, list):
        for item in value:
            found.extend(_failure_items(item, prefix))
    elif value is not None:
        text = str(value).replace("\r", " ").replace("\n", " ").strip()
        if text:
            found.append(f"{prefix or 'gate'}: {text}")
    else:
        found.append(f"{prefix or 'gate'}: failed")
    return found


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit(report: dict[str, Any], output: str | Path, *, label: str = "gate", failure_file: str | Path | None = None) -> None:
    """Write the full report and print only the prescribed short protocol."""
    out = Path(output)
    write_report(report, out)
    passed = report.get("passed") is True
    print(f"{'PASS' if passed else 'FAIL'} {label}")
    if not passed:
        seen: set[str] = set()
        for item in _failure_items(report, str(failure_file or out)):
            if item not in seen:
                print(item)
                seen.add(item)
            if len(seen) >= 8:
                break
