"""Structural validator for the huawei-cup-modeling skill (no third-party deps).

Checks, in order:
  1. SKILL.md frontmatter has name + description.
  2. Every relative markdown link in SKILL.md / references / rules / templates
     resolves to a real file (runtime example paths are skipped, not failed).
  3. All bundled *.py compile (syntax) and all bundled *.json parse.
  4. The modeling-behavior case library passes its own structural validation.
  5. Cleanliness: report (warn, not fail) on __pycache__ / *.pyc / runtime dirs
     that must be excluded from a release package.

Exit 0 = PASS, 3 = FAIL. Warnings never fail the build; they are packaging cues.
Run AFTER regression tests and AFTER cleaning, BEFORE packaging.
"""
from __future__ import annotations

import argparse
import json
import py_compile
import re
import sys
from pathlib import Path

# Validation imports local modules; never create bytecode as a side effect.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Path prefixes that are runtime/project examples, not bundled skill files.
RUNTIME_PREFIXES = ("project/", "team_control/", "manuscript/", "qa/", "runs/",
                    "code/", "figures/", "support-materials/", "support/", "data/")
SKIP_SCHEMES = ("http://", "https://", "mailto:", "#")


def _is_external(target: str) -> bool:
    return target.startswith(SKIP_SCHEMES)


def _clean_target(target: str) -> str:
    """Strip anchor, surrounding whitespace, and an optional link title."""
    t = target.strip()
    if " " in t:  # [text](path "title")
        t = t.split(" ", 1)[0].strip()
    if "#" in t:
        t = t.split("#", 1)[0].strip()
    return t.strip("<>")


def check_frontmatter(errors):
    skill = ROOT / "SKILL.md"
    if not skill.is_file():
        errors.append("SKILL.md missing")
        return
    text = skill.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        errors.append("SKILL.md has no YAML frontmatter block")
        return
    fm = m.group(1)
    if not re.search(r"(?m)^name:\s*\S+", fm):
        errors.append("SKILL.md frontmatter missing 'name'")
    if not re.search(r"(?m)^description:\s*\S+", fm):
        errors.append("SKILL.md frontmatter missing 'description'")


def check_links(errors, notes):
    md_files = [ROOT / "SKILL.md"]
    for sub in ("references", "rules", "templates"):
        d = ROOT / sub
        if d.is_dir():
            md_files.extend(sorted(d.rglob("*.md")))
    for md in md_files:
        if not md.is_file():
            continue
        text = md.read_text(encoding="utf-8")
        for raw in MD_LINK.findall(text):
            if _is_external(raw.strip()):
                continue
            target = _clean_target(raw)
            if not target:
                continue
            if target.startswith(RUNTIME_PREFIXES):
                notes.append(f"{md.relative_to(ROOT)}: runtime example link skipped ({target})")
                continue
            resolved = (md.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"{md.relative_to(ROOT)}: broken link -> {target}")


def check_python(errors):
    for py in sorted((ROOT / "scripts").glob("*.py")):
        try:
            py_compile.compile(str(py), cfile=str(py.with_suffix(".tmpvalidate.pyc")),
                               doraise=True, quiet=1)
        except py_compile.PyCompileError as e:
            errors.append(f"{py.name}: syntax error: {e.msg.splitlines()[0] if e.msg else e}")
        finally:
            tmp = py.with_suffix(".tmpvalidate.pyc")
            if tmp.exists():
                tmp.unlink()


def check_json(errors):
    for js in sorted(ROOT.rglob("*.json")):
        if "__pycache__" in js.parts:
            continue
        try:
            json.loads(js.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as e:
            errors.append(f"{js.relative_to(ROOT)}: invalid JSON: {e}")


def check_behavior_cases(errors):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import modeling_behavior_evals as mbe
        data = mbe.load_cases()
        case_errors, n, auto = mbe.validate_cases(data)
        errors.extend(f"cases.json: {e}" for e in case_errors)
        ok, _ = mbe.self_test()
        if not ok:
            errors.append("cases.json: behavior-eval engine self-test failed")
    except Exception as e:  # noqa: BLE001
        errors.append(f"cases.json: {type(e).__name__}: {e}")
    finally:
        if str(ROOT / "scripts") in sys.path:
            sys.path.remove(str(ROOT / "scripts"))


def check_orphans(warnings):
    """Warn on bundled reference/rule/template files that no markdown links to.

    Orphaned knowledge cannot be progressively loaded at runtime, so it either
    rots or duplicates a canonical location. Warnings only: some templates are
    consumed by scripts/tests rather than by prose.
    """
    md_files = [ROOT / "SKILL.md"]
    for sub in ("references", "rules", "templates"):
        d = ROOT / sub
        if d.is_dir():
            md_files.extend(sorted(d.rglob("*.md")))
    linked = set()
    for md in md_files:
        if not md.is_file():
            continue
        for raw in MD_LINK.findall(md.read_text(encoding="utf-8")):
            if _is_external(raw.strip()):
                continue
            target = _clean_target(raw)
            if not target or target.startswith(RUNTIME_PREFIXES):
                continue
            linked.add((md.parent / target).resolve())
    script_consumed = set()
    for sub in ("references", "rules", "templates"):
        d = ROOT / sub
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file() and f.resolve() not in linked and f.resolve() not in script_consumed:
                warnings.append(f"orphan (no markdown links to it): {f.relative_to(ROOT)}")


def check_cleanliness(warnings):
    for pyc in ROOT.rglob("*.pyc"):
        warnings.append(f"stray bytecode: {pyc.relative_to(ROOT)} (exclude from package)")
    for pc in ROOT.rglob("__pycache__"):
        if pc.is_dir():
            warnings.append(f"stray __pycache__: {pc.relative_to(ROOT)} (exclude from package)")
    for rt in ("team_control", "qa"):
        d = ROOT / rt
        if d.is_dir() and any(d.iterdir()):
            warnings.append(f"runtime dir bundled: {rt}/ (must not ship in a release package)")


def main():
    ap = argparse.ArgumentParser(description="Validate skill structure, links, JSON, and cleanliness")
    ap.add_argument("--output", help="write the JSON report here")
    a = ap.parse_args()

    errors, warnings, notes = [], [], []
    check_frontmatter(errors)
    check_links(errors, notes)
    check_python(errors)
    check_json(errors)
    check_behavior_cases(errors)
    check_orphans(warnings)
    check_cleanliness(warnings)

    report = {"passed": not errors, "errors": errors, "warnings": warnings,
              "link_notes": notes[:20], "root": str(ROOT)}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if a.output:
        p = Path(a.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n", encoding="utf-8")
    print(f"{'PASS' if not errors else 'FAIL'} validate_skill")
    for e in errors[:20]:
        print("  ERROR " + e)
    for w in warnings[:10]:
        print("  warn  " + w)
    if not errors and not warnings:
        print("  clean: no broken links, all JSON/py valid, no stray artifacts")
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
