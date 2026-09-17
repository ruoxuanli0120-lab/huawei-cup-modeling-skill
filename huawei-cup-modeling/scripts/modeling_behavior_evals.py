"""Modeling Behavioral Evals harness.

Codifies the skill's modeling PRIORITIES as testable behavioral cases:
each case is a scenario that tempts a specific bad behavior, plus the
expected expert behavior, the forbidden behavior, and a weighted rubric.
These evaluate MODELING REASONING, not code gates.

Some cases are auto_scorable via coarse keyword/regex proxies (kinds:
present, absent, count_min, requires); the rest must be scored by a
human/model against the rubric. An auto_pass is a PROXY, never a
certificate of excellent modeling - the rubric always governs.

Modes:
  validate                        validate cases.json schema + case count (8-23)
  list                            list case id / stage / auto-scorability
  self-test                       run the check engine on embedded synthetic text
  score --case ID --response FILE run auto_checks (auto cases) or emit rubric sheet
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evals" / "modeling_behavior" / "cases.json"
REQUIRED_FIELDS = ("id", "stage", "scenario", "expected_behaviors", "forbidden_behaviors",
                   "rubric", "auto_scorable", "auto_checks")
CHECK_KINDS = ("present", "absent", "count_min", "requires")


def load_cases(path=None):
    return json.loads(Path(path or DEFAULT_CASES).read_text(encoding="utf-8-sig"))


def _search(patterns, text):
    """Return the subset of patterns (regex, case-insensitive) that match text.
    A pattern that is not valid regex falls back to a literal substring test."""
    hits = []
    for p in patterns or []:
        try:
            if re.search(p, text, re.IGNORECASE):
                hits.append(p)
        except re.error:
            if str(p).lower() in text.lower():
                hits.append(p)
    return hits


def run_auto_checks(case, text):
    """Run a case's auto_checks against text. Returns (all_passed, details)."""
    details = []
    for chk in case.get("auto_checks", []):
        kind = chk.get("kind")
        if kind == "present":
            hits = _search(chk.get("patterns"), text)
            details.append({"kind": kind, "passed": bool(hits), "matched": hits})
        elif kind == "absent":
            hits = _search(chk.get("patterns"), text)
            details.append({"kind": kind, "passed": not hits, "matched": hits})
        elif kind == "count_min":
            hits = _search(chk.get("patterns"), text)
            mn = int(chk.get("min", 1))
            details.append({"kind": kind, "passed": len(hits) >= mn,
                            "distinct_matched": len(hits), "min": mn, "matched": hits})
        elif kind == "requires":
            trigger = _search(chk.get("if"), text)
            if trigger:
                then = _search(chk.get("then"), text)
                details.append({"kind": kind, "passed": bool(then), "trigger": trigger, "then_matched": then})
            else:
                details.append({"kind": kind, "passed": True, "trigger": [],
                                "note": "trigger absent; requirement vacuously satisfied"})
        else:
            details.append({"kind": kind, "passed": False, "error": "unknown check kind"})
    return all(d["passed"] for d in details), details


def validate_cases(data):
    """Structural validation of the case library. Returns (errors, n_cases, n_auto)."""
    errors = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    cases = data.get("cases")
    if not isinstance(cases, list):
        return ["cases must be a list"], 0, 0
    n = len(cases)
    if not (8 <= n <= 23):
        errors.append(f"case count {n} outside required [8,23]")
    ids = set()
    auto = 0
    for i, c in enumerate(cases):
        cid = c.get("id", f"<index {i}>")
        if cid in ids:
            errors.append(f"duplicate case id: {cid}")
        ids.add(cid)
        for f in REQUIRED_FIELDS:
            if f not in c:
                errors.append(f"{cid}: missing field {f}")
        for lf in ("expected_behaviors", "forbidden_behaviors", "rubric"):
            v = c.get(lf)
            if not isinstance(v, list) or not v:
                errors.append(f"{cid}: {lf} must be a non-empty list")
        rub = c.get("rubric")
        if isinstance(rub, list) and rub:
            total = 0.0
            for x in rub:
                if not isinstance(x, dict):
                    errors.append(f"{cid}: rubric item must be an object")
                    continue
                for k in ("criterion", "weight"):
                    if k not in x:
                        errors.append(f"{cid}: rubric item missing {k}")
                total += float(x.get("weight", 0) or 0)
            if abs(total - 1.0) > 0.05:
                errors.append(f"{cid}: rubric weights sum {total:.2f} != 1.0")
        if not isinstance(c.get("auto_scorable"), bool):
            errors.append(f"{cid}: auto_scorable must be a boolean")
        ac = c.get("auto_checks", [])
        if not isinstance(ac, list):
            errors.append(f"{cid}: auto_checks must be a list")
            ac = []
        if c.get("auto_scorable") and not ac:
            errors.append(f"{cid}: auto_scorable=true but no auto_checks")
        if not c.get("auto_scorable") and ac:
            errors.append(f"{cid}: auto_scorable=false but has auto_checks")
        for chk in ac:
            if not isinstance(chk, dict) or chk.get("kind") not in CHECK_KINDS:
                errors.append(f"{cid}: unknown/invalid check kind {chk.get('kind') if isinstance(chk, dict) else chk}")
        if c.get("auto_scorable"):
            auto += 1
    return errors, n, auto


def self_test():
    """Exercise the auto_check engine on synthetic text; every kind, both outcomes."""
    trials = [
        ("present-pass", {"kind": "present", "patterns": ["结构|structure"]}, "先分析结构再建模", True),
        ("present-fail", {"kind": "present", "patterns": ["结构|structure"]}, "直接上模型", False),
        ("absent-pass", {"kind": "absent", "patterns": ["SOTA"]}, "没有触发词", True),
        ("absent-fail", {"kind": "absent", "patterns": ["SOTA"]}, "因为它是 SOTA", False),
        ("count_min-pass", {"kind": "count_min", "min": 2, "patterns": ["AHP", "TOPSIS", "熵权"]}, "用 AHP 和 TOPSIS", True),
        ("count_min-fail", {"kind": "count_min", "min": 2, "patterns": ["AHP", "TOPSIS", "熵权"]}, "只用 AHP", False),
        ("requires-triggered-pass", {"kind": "requires", "if": ["全局最优"], "then": ["证明|下界"]}, "全局最优需下界证明", True),
        ("requires-triggered-fail", {"kind": "requires", "if": ["全局最优"], "then": ["证明|下界"]}, "这是全局最优", False),
        ("requires-vacuous-pass", {"kind": "requires", "if": ["全局最优"], "then": ["证明"]}, "没有谈最优性", True),
    ]
    results = []
    for name, chk, text, expected in trials:
        ok, _ = run_auto_checks({"auto_checks": [chk]}, text)
        results.append({"name": name, "passed": ok == expected, "got": ok, "expected": expected})
    return all(r["passed"] for r in results), results


def score_case(case_id, response_path, data):
    case = next((c for c in data.get("cases", []) if c.get("id") == case_id), None)
    if case is None:
        return {"passed": False, "error": f"no such case: {case_id}"}
    text = Path(response_path).read_text(encoding="utf-8")
    if case.get("auto_scorable"):
        ok, details = run_auto_checks(case, text)
        return {"case": case_id, "mode": "auto", "auto_passed": ok, "auto_checks": details,
                "rubric": case.get("rubric"),
                "note": "auto_pass is a coarse keyword proxy, NOT a certificate of excellent "
                        "modeling; the rubric still governs the real score."}
    return {"case": case_id, "mode": "manual", "rubric": case.get("rubric"),
            "expected_behaviors": case.get("expected_behaviors"),
            "forbidden_behaviors": case.get("forbidden_behaviors"),
            "instruction": "Score the response against the rubric (weights sum to 1). "
                           "For each criterion record excellent/poor evidence and a weighted score."}


def _write(report, output):
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n", encoding="utf-8")
    return text


def main():
    p = argparse.ArgumentParser(description="Modeling behavioral evals harness")
    p.add_argument("--cases", default=str(DEFAULT_CASES), help="path to cases.json")
    p.add_argument("--output", help="write the JSON report here")
    s = p.add_subparsers(dest="command", required=True)
    s.add_parser("validate")
    s.add_parser("list")
    s.add_parser("self-test")
    sc = s.add_parser("score")
    sc.add_argument("--case", required=True)
    sc.add_argument("--response", required=True)
    a = p.parse_args()

    if a.command == "self-test":
        ok, results = self_test()
        report = {"passed": ok, "command": "self-test", "trials": results}
        _write(report, a.output)
        print(f"{'PASS' if ok else 'FAIL'} modeling-behavior self-test ({sum(r['passed'] for r in results)}/{len(results)})")
        return 0 if ok else 3

    data = load_cases(a.cases)

    if a.command == "validate":
        errors, n, auto = validate_cases(data)
        report = {"passed": not errors, "command": "validate", "cases": n,
                  "auto_scorable": auto, "manual": n - auto, "errors": errors}
        _write(report, a.output)
        print(f"{'PASS' if not errors else 'FAIL'} modeling-behavior cases ({n} cases, {auto} auto / {n - auto} manual)")
        for e in errors[:12]:
            print("  " + e)
        return 0 if not errors else 3

    if a.command == "list":
        rows = [{"id": c.get("id"), "stage": c.get("stage"), "priority_tested": c.get("priority_tested"),
                 "auto_scorable": c.get("auto_scorable")} for c in data.get("cases", [])]
        report = {"passed": True, "command": "list", "cases": rows}
        _write(report, a.output)
        for r in rows:
            print(f"  {r['id']:<28} {r['stage']:<11} {'auto' if r['auto_scorable'] else 'manual'}")
        return 0

    # score
    report = score_case(a.case, a.response, data)
    _write(report, a.output)
    if report.get("mode") == "auto":
        ok = report.get("auto_passed")
        print(f"{'PASS' if ok else 'FAIL'} auto-check {a.case}")
        for d in report.get("auto_checks", []):
            print(f"  [{'ok' if d.get('passed') else 'XX'}] {d.get('kind')}: {d.get('matched', d.get('trigger', ''))}")
        print("  note: " + report["note"])
        return 0 if ok else 3
    print(f"MANUAL rubric emitted for {a.case}; score against rubric (auto_scoring not applicable).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
