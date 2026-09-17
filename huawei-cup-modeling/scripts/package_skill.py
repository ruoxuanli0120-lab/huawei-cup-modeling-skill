"""Package the skill into a clean, distributable zip (no third-party deps).

Bundles: SKILL.md, CHANGELOG.md, agents/, evals/, references/, rules/,
         scripts/*.py, templates/.
Excludes: __pycache__/, *.pyc / *.pyo, transient validator artifacts
          (*.tmpvalidate.pyc), runtime dirs (qa/, archive/, team_control/,
          dist/, build/), VCS/OS noise (.git, .DS_Store, Thumbs.db), and the
          output archive itself.

The archive carries a single top-level folder named after the skill directory
so it can be unzipped straight into a skills root and remain valid.

Usage:
  python package_skill.py                      # -> ../<skill>.zip
  python package_skill.py --output dist/x.zip  # explicit path
  python package_skill.py --verify             # rebuild then re-open & assert clean
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = ROOT.name  # single top-level folder inside the zip

EXCLUDE_DIRS = {"__pycache__", ".git", ".hg", ".svn", ".venv", "venv",
                "node_modules", ".pytest_cache", ".mypy_cache", ".idea", ".vscode",
                "qa", "archive", "team_control", "dist", "build"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".tmp", ".bak", ".swp", ".log"}
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def _excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    if path.name in EXCLUDE_NAMES:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if path.name.endswith(".tmpvalidate.pyc"):
        return True
    return False


def collect():
    """Return the sorted list of files to bundle (absolute paths)."""
    out = []
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file():
            continue
        if _excluded(f):
            continue
        out.append(f)
    return out


def build(output: Path) -> dict:
    files = collect()
    out_res = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            if f.resolve() == out_res:  # never include the archive itself
                continue
            arc = f"{TOP}/{f.relative_to(ROOT).as_posix()}"
            z.write(f, arc)
            manifest.append(arc)
    # sanity: nothing excluded slipped in
    bad = [m for m in manifest
           if any(part in EXCLUDE_DIRS for part in m.split("/"))
           or Path(m).suffix.lower() in EXCLUDE_SUFFIXES]
    return {"output": str(output), "files": len(manifest),
            "bytes": output.stat().st_size, "manifest": manifest, "leaks": bad}


def verify(output: Path) -> int:
    with zipfile.ZipFile(output) as z:
        names = z.namelist()
        bad = z.testzip()
    problems = []
    if bad is not None:
        problems.append(f"corrupt member: {bad}")
    leaks = [n for n in names
             if any(part in EXCLUDE_DIRS for part in n.split("/"))
             or Path(n).suffix.lower() in EXCLUDE_SUFFIXES
             or Path(n).name in EXCLUDE_NAMES]
    problems.extend(f"leaked excluded path: {n}" for n in leaks)
    required = {f"{TOP}/SKILL.md"}
    for r in required:
        if r not in names:
            problems.append(f"missing required member: {r}")
    if not any(n.startswith(f"{TOP}/scripts/") and n.endswith(".py") for n in names):
        problems.append("no scripts bundled")
    return problems, names


def main():
    ap = argparse.ArgumentParser(description="Clean-packager for the huawei-cup-modeling skill")
    ap.add_argument("--output", default=str(ROOT.parent / f"{ROOT.name}.zip"),
                    help="destination zip (default: ../<skill>.zip)")
    ap.add_argument("--verify", action="store_true",
                    help="after building, re-open the archive and assert it is clean")
    a = ap.parse_args()

    out = Path(a.output)
    report = build(out)
    print(f"BUILT {out} ({report['files']} files, {report['bytes']} bytes, top-level '{TOP}/')")
    if report["leaks"]:
        for l in report["leaks"]:
            print("  LEAK " + l)
        return 3

    if a.verify:
        problems, names = verify(out)
        if problems:
            print("VERIFY FAIL")
            for p in problems:
                print("  " + p)
            return 3
        print(f"VERIFY PASS ({len(names)} members, no excluded paths, SKILL.md present)")
        for n in sorted(names):
            print("  " + n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
