"""Final manuscript gate for the single authoritative LaTeX source."""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

from audit_core import inside, numeric_report, proof_report, read, same, sha, theoretical_report
from gate_output import emit
from package_overleaf import collect, source_tree_digest


def figure_table_coverage(tex):
    if not Path(tex).is_file():
        return {"passed": False, "errors": ["missing source"]}
    s = Path(tex).read_text(encoding="utf8")
    s = re.sub(r"(?m)(?<!\\)%.*$", "", s)
    if re.search(r"\\(?:input|include|includeonly)\b", s):
        return {"passed": True, "errors": [],
                "warnings": ["modular TeX detected: figure/table coverage is limited to main.tex; rendered PDF/source-tree binding remains authoritative"],
                "objects": []}
    refs = set(re.findall(r"\\(?:ref|autoref|Cref)\{([^}]+)\}", s))
    errors, objects = [], []
    for m in re.finditer(r"\\begin\{(figure\*?|table\*?|longtable|sidewaystable|sidewaysfigure)\}(.*?)\\end\{\1\}", s, re.S):
        kind, body = m[1], m[2]
        label = re.search(r"\\label\{([^}]+)\}", body)
        if not label or label[1] not in refs:
            errors.append("unreferenced " + kind)
        if "\\caption" not in body:
            errors.append("missing caption " + kind)
        objects.append(kind)
    return {"passed": not errors, "errors": errors, "objects": objects}


def tex_report(project, proof, tex=None):
    data = read(inside(project, proof))
    source = inside(project, data["source_path"])
    if source.suffix.lower() != ".tex":
        return {"passed": False, "errors": ["PDF requires bound TeX source"]}
    if tex is not None and inside(project, tex) != source:
        return {"passed": False, "errors": ["TeX source differs from proof source"]}
    return figure_table_coverage(source)


def overleaf_report(project, proof, zip_rel="manuscript/overleaf-project.zip", main_name="main.tex"):
    errors = []
    try:
        pr = read(inside(project, proof))
        source = inside(project, pr["source_path"])
        archive = inside(project, zip_rel)
        if source.suffix.lower() != ".tex":
            errors.append("proof source is not TeX")
        if not archive.is_file():
            errors.append("Overleaf ZIP missing")
        else:
            src_dir = source.parent
            current = {f.relative_to(src_dir).as_posix(): f.read_bytes() for f in collect(src_dir)}
            with zipfile.ZipFile(archive) as z:
                bad = z.testzip()
                names = z.namelist()
                if bad:
                    errors.append("corrupt Overleaf ZIP member: " + bad)
                if len(names) != len(set(names)):
                    errors.append("duplicate member name in Overleaf ZIP")
                if any(n.startswith("/") or ".." in Path(n).parts for n in names):
                    errors.append("unsafe path in Overleaf ZIP")
                if main_name not in names:
                    errors.append(main_name + " missing from Overleaf ZIP")
                elif z.read(main_name) != source.read_bytes():
                    errors.append("Overleaf main.tex differs from authoritative source")
                if set(names) != set(current):
                    errors.append("Overleaf ZIP member set differs from current LaTeX source tree")
                else:
                    for name, data in current.items():
                        if z.read(name) != data:
                            errors.append("Overleaf ZIP differs from current LaTeX source tree: " + name)
                            break
    except Exception as e:
        errors.append(type(e).__name__ + ": " + str(e))
    return {"passed": not errors, "errors": errors, "zip": zip_rel, "main": main_name}


def evidence_coverage(project, state, provenance="manuscript/numeric-provenance.json",
                      theoretical="manuscript/theoretical-evidence.json"):
    """Ensure evidence manifests cover each question's current primary claim."""
    errors, covered = [], {}
    questions = state.get("questions") or {}
    numeric_rows, theory_rows = [], []
    if any(q.get("claim_mode", "computational") in ("computational", "mixed") for q in questions.values()):
        try:
            numeric_rows = read(inside(project, provenance)).get("results") or []
        except Exception as e:
            errors.append("cannot read numeric provenance for coverage: " + str(e))
    if any(q.get("claim_mode") in ("theoretical", "mixed") for q in questions.values()):
        try:
            theory_rows = read(inside(project, theoretical)).get("claims") or []
        except Exception as e:
            errors.append("cannot read theoretical evidence for coverage: " + str(e))

    from run_state import incumbent_metrics, best_result
    for qid, qs in questions.items():
        claim_mode = qs.get("claim_mode", "computational")
        theory_summary = None
        if claim_mode in ("theoretical", "mixed"):
            hits = [r for r in theory_rows if r.get("question") == qid]
            if not hits:
                errors.append(f"{qid}: theoretical-evidence has no claim bound to this question")
            current_checks = {(e.get("file"), e.get("sha256")) for e in qs.get("validation_evidence", [])
                              if e.get("kind") == "theory_check"}
            bound_hits = [r for r in hits if (r.get("proof_file"), r.get("proof_sha256")) in current_checks]
            if hits and not bound_hits:
                errors.append(f"{qid}: theoretical-evidence is not bound to the current theory_check evidence")
            theory_summary = {"claims": len(hits), "current_bound_claims": len(bound_hits)}
            if claim_mode == "theoretical":
                covered[qid] = {"mode": "theoretical", **theory_summary}
                continue

        metrics = incumbent_metrics(qs)
        if metrics.get("authority") != "referee-a/full":
            errors.append(f"{qid}: current headline result is not full-scale Referee A")
            continue
        rows = [r for r in numeric_rows if r.get("question") == qid and str(r.get("tier", "A")).upper() == "A"]
        mode = qs.get("objective_mode", "scalar")
        current = best_result((qs.get("candidates") or {}).get(qs.get("incumbent"), {}), mode) or {}
        current_run_sha = current.get("evidence_sha256")
        needed = {"objective": metrics.get("objective")} if mode == "scalar" else dict(metrics.get("metrics") or {})
        missing = []
        for name, value in needed.items():
            found = False
            for row in rows:
                raw = row["raw_value"] if "raw_value" in row else row.get("value")
                same_run = bool(current_run_sha) and row.get("run_sha256") == current_run_sha
                if row.get("metric") == name and raw is not None and same(raw, value) and same_run:
                    found = True
                    break
            if not found:
                missing.append(name)
        if missing:
            errors.append(f"{qid}: Tier-A numeric provenance does not cover current headline metric(s): {', '.join(missing)}")
        covered[qid] = {"mode": ("mixed" if claim_mode == "mixed" else mode),
                         "objective_mode": mode, "metrics": sorted(needed),
                         **({"theory": theory_summary} if theory_summary is not None else {})}
    return {"passed": not errors, "errors": errors, "covered": covered}


def report(project, paper, format_proof, *, scope="final",
           provenance="manuscript/numeric-provenance.json",
           theoretical_evidence="manuscript/theoretical-evidence.json",
           official_checklist="manuscript/official-checklist.json",
           overleaf_zip="manuscript/overleaf-project.zip", overleaf_main="main.tex",
           source_registry="manuscript/source-registry.json", tex=None):
    checks, bindings = {}, {}
    try:
        from run_state import load as load_run_state
        state = load_run_state(project)
        questions = state.get("questions") or {}
        if not questions:
            raise ValueError("run-state has no registered questions; cannot infer evidence mode")
        modes = {q.get("claim_mode", "computational") for q in questions.values()}
        if not modes <= {"computational", "theoretical", "mixed"}:
            raise ValueError("run-state contains unsupported claim_mode")

        paper_path = inside(project, paper)
        checks["proof"] = proof_report(project, paper, format_proof, final=scope == "final")
        checks["evidence_mode"] = {"passed": True, "modes": sorted(modes), "source": "team_control/run-state.json"}
        if modes & {"computational", "mixed"}:
            checks["numbers"] = numeric_report(project, provenance)
        if modes & {"theoretical", "mixed"}:
            checks["theoretical_evidence"] = theoretical_report(project, theoretical_evidence)
        checks["evidence_coverage"] = evidence_coverage(project, state, provenance, theoretical_evidence)

        if paper_path.suffix.lower() != ".pdf":
            checks["paper_type"] = {"passed": False, "errors": ["final manuscript QA expects a compiled PDF"]}
        else:
            checks["figure_table_coverage"] = tex_report(project, format_proof, tex)
        if scope == "final":
            from official_clause_gate import report as clause_report
            from source_gate import report as source_report
            checks["official_format"] = clause_report(project, paper, official_checklist)
            checks["sources"] = source_report(project, paper, source_registry)
            checks["overleaf"] = overleaf_report(project, format_proof, overleaf_zip, overleaf_main)

        bindings["paper"] = {"path": paper, "sha256": sha(paper_path)}
        pr = read(inside(project, format_proof))
        src = pr.get("source_path")
        if src:
            source = inside(project, src)
            bindings["source"] = {"path": src, "sha256": sha(source)}
            bindings["source_tree_sha256"] = source_tree_digest(source.parent)
        candidates = [("proof", format_proof), ("official_checklist", official_checklist),
                      ("source_registry", source_registry), ("overleaf_zip", overleaf_zip)]
        if modes & {"computational", "mixed"}:
            candidates.append(("numeric_provenance", provenance))
        if modes & {"theoretical", "mixed"}:
            candidates.append(("theoretical_evidence", theoretical_evidence))
        for key, rel in candidates:
            fp = inside(project, rel)
            if fp.is_file():
                bindings[key] = {"path": rel, "sha256": sha(fp)}
    except Exception as e:
        checks["input_error"] = {"passed": False, "error": type(e).__name__ + ": " + str(e)}

    return {"passed": bool(checks) and all(v.get("passed") is True for v in checks.values()),
            "scope": scope, "checks": checks, "bindings": bindings}


def main():
    p = argparse.ArgumentParser()
    for key in ("project", "paper", "format-proof"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--scope", choices=["review", "final"], default="final")
    p.add_argument("--provenance", default="manuscript/numeric-provenance.json")
    p.add_argument("--theoretical-evidence", default="manuscript/theoretical-evidence.json")
    p.add_argument("--official-checklist", default="manuscript/official-checklist.json")
    p.add_argument("--overleaf-zip", default="manuscript/overleaf-project.zip")
    p.add_argument("--overleaf-main", default="main.tex")
    p.add_argument("--source-registry", default="manuscript/source-registry.json")
    p.add_argument("--tex")
    p.add_argument("--output", default="team_control/final-compliance-report.json")
    a = p.parse_args()
    rep = report(a.project, a.paper, a.format_proof, scope=a.scope,
                 provenance=a.provenance, theoretical_evidence=a.theoretical_evidence,
                 official_checklist=a.official_checklist, overleaf_zip=a.overleaf_zip,
                 overleaf_main=a.overleaf_main, source_registry=a.source_registry, tex=a.tex)
    out = inside(a.project, a.output)
    emit(rep, out, label="final compliance", failure_file=inside(a.project, a.paper))
    return 0 if rep["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
