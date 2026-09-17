"""Single source of truth for a modeling run: stage, candidates, metrics, approvals.

Design rules (learned from a real end-to-end contest run):
  * run-state.json is the ONLY machine-readable authority for: current stage,
    question state, candidates, incumbent/challenger, objective values,
    feasibility, bounds/gap, evaluator (referee) versions, artifact paths,
    superseded/stale marks, rollback history and human approval state.
  * Markdown summaries are DERIVED products (`report`), never hand-edited;
    a report carries the state seq it was generated from, so staleness is
    detectable. Downstream documents must quote `metrics show`, not copies.
  * Approvals are semantically separated. A bare "continue" records
    CONTINUE_STAGE only; it never accepts a route, freezes results, approves
    a manuscript or authorizes submission.
  * Gates are structural (machine-checkable). Scientific quality stays a
    human/REVIEWER judgement; the gate only fails when the required artifact,
    record or approval is missing, so the machine never stalls real work.
  * Fail-closed: missing files, escaping paths, non-finite numbers, unsigned
    state when a secret is configured, all raise instead of passing.

State file: <project>/team_control/run-state.json
Integrity: optional HMAC via HUAWEI_CUP_STATE_SECRET; unsigned supervised mode works without a secret. run-state is the only approval/state authority.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from audit_core import inside, read, sha, route_report, validation_evidence_sha
from gate_output import emit

SCHEMA_VERSION = 4
STAGES = ["UNDERSTAND", "IDEATE", "SELECT", "FALSIFY", "BUILD",
          "VALIDATE", "INTERPRET", "WRITE", "DELIVER", "DONE"]
QUESTION_APPROVAL_GATES = ["ACCEPT_ROUTE", "FREEZE_RESULT"]
PAPER_APPROVAL_GATES = ["APPROVE_MANUSCRIPT", "AUTHORIZE_SUBMISSION"]
APPROVAL_GATES = QUESTION_APPROVAL_GATES + PAPER_APPROVAL_GATES
EVIDENCE_KINDS = ["baseline_comparison", "exact_comparison", "constraint_check", "sensitivity",
                  "robustness", "perturbation", "bound_gap", "error_residual", "ablation",
                  "independent_evaluator", "extreme_case", "theory_check", "mechanism_consistency"]
PRIMARY_VALIDATION_KINDS = ["baseline_comparison", "exact_comparison", "bound_gap",
                            "constraint_check", "error_residual", "sensitivity", "robustness",
                            "perturbation", "ablation", "mechanism_consistency",
                            "independent_evaluator", "extreme_case"]
CLAIM_MODES = ["computational", "theoretical", "mixed"]
OBJECTIVE_MODES = ["scalar", "vector", "lexicographic", "none"]
TRACE_ROLES = ["input", "decision_variable", "state_variable", "observed_variable", "parameter",
               "hard_constraint", "soft_constraint", "objective", "evaluation_rule",
               "implicit_condition", "assumption", "relation", "claim"]
READABILITY_MARKERS = ["为什么这样建", "模型是什么", "为什么这样求", "结果怎么样", "为什么可信", "结果说明什么"]
CORE_PRINCIPLE_MARKERS = ["建模贴题", "方法合适", "结果可信", "表达清楚"]
ROUTE_STATUSES = ["proposed", "kept", "pilot", "killed", "main", "challenger"]
CANDIDATE_STATUSES = ["active", "incumbent", "challenger", "superseded", "rejected"]


def state_secret() -> str:
    return os.environ.get("HUAWEI_CUP_STATE_SECRET", "")


def state_signature(data: dict, secret: str) -> str:
    payload = {k: v for k, v in data.items() if k != "state_signature"}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def state_path(project) -> Path:
    return Path(project) / "team_control" / "run-state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(project) -> dict:
    p = state_path(project)
    if not p.exists():
        raise ValueError("run-state.json missing; run: python scripts/run_state.py --project . init")
    data = read(p)
    secret = state_secret()
    signature = data.get("state_signature")
    if secret:
        if not isinstance(signature, str) or not _sig_ok(data, secret):
            raise ValueError("run-state signature missing or invalid")
    elif isinstance(signature, str):
        raise ValueError("signed run-state present but HUAWEI_CUP_STATE_SECRET not set; cannot verify integrity")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported run-state schema_version")
    return data


def _sig_ok(data: dict, secret: str) -> bool:
    import hmac
    return hmac.compare_digest(data["state_signature"], state_signature(data, secret))


def save(project, data: dict) -> None:
    data["updated_at"] = _now()
    secret = state_secret()
    if secret:
        data["integrity"] = "hmac-sha256"
        data["state_signature"] = state_signature(data, secret)
    else:
        data["integrity"] = "unsigned"
        data.pop("state_signature", None)
    p = state_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def event(data: dict, action: str, **detail) -> int:
    data["seq"] = int(data.get("seq", 0)) + 1
    data.setdefault("events", []).append(
        {"seq": data["seq"], "at": _now(), "action": action, "detail": detail})
    return data["seq"]


def _question(data: dict, qid: str) -> dict:
    if not re.fullmatch(r"Q[1-9][0-9]*", qid or ""):
        raise ValueError(f"invalid question id: {qid}")
    qs = data["questions"].get(qid)
    if qs is None:
        raise ValueError(f"question {qid} not registered; use: question add --id {qid}")
    return qs


def _finite_number(value: str, field: str) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number, got: {value!r}")
    if not math.isfinite(x):
        raise ValueError(f"{field} must be finite")
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number, not a boolean")
    return x


def _file_sha(project, rel: str) -> str:
    p = inside(project, rel)
    if not p.is_file():
        raise ValueError(f"file not found in project: {rel}")
    return sha(p)


def _candidate(qs: dict, cid: str) -> dict:
    c = qs.get("candidates", {}).get(cid)
    if c is None:
        raise ValueError(f"candidate {cid} not registered")
    return c


def _authority_rank(result: dict) -> int:
    # Final paper numbers prefer the official/reference evaluator on full scale.
    if result.get("evaluator") == "a" and result.get("scale") == "full": return 3
    if result.get("evaluator") == "a": return 2
    if result.get("scale") == "full": return 1
    return 0


def best_result(cand: dict, objective_mode: str = "scalar") -> dict | None:
    feasible = [r for r in cand.get("results", []) if r.get("feasible") is True]
    if not feasible:
        return None
    top = max(_authority_rank(r) for r in feasible)
    pool = [r for r in feasible if _authority_rank(r) == top]
    if objective_mode in ("vector", "lexicographic"):
        # Do not invent a scalar ranking for multi-metric/Pareto/lexicographic questions.
        # Candidate promotion is an explicit modeling decision; use the latest authoritative vector.
        return pool[-1]
    if objective_mode == "none":
        return None
    senses = {r.get("sense") for r in pool}
    if len(senses) != 1 or None in senses:
        raise ValueError("candidate mixes or omits scalar objective sense; keep one objective definition per candidate")
    sense = next(iter(senses))
    return min(pool, key=lambda r: r["objective"]) if sense == "min" else max(pool, key=lambda r: r["objective"])

def incumbent_metrics(qs: dict) -> dict:
    cid = qs.get("incumbent")
    if not cid:
        return {"incumbent": None, "objective": None, "metrics": {}, "sense": None, "feasible": False,
                "evidence": None, "evaluator": None, "scale": None, "authority": None, "params": {}}
    cand = qs["candidates"].get(cid, {})
    best = best_result(cand, qs.get("objective_mode", "scalar"))
    return {
        "incumbent": cid,
        "objective": (best or {}).get("objective"),
        "metrics": (best or {}).get("metrics", {}),
        "sense": (best or {}).get("sense"),
        "feasible": bool(best),
        "evidence": (best or {}).get("evidence"),
        "evaluator": (best or {}).get("evaluator"),
        "scale": (best or {}).get("scale"),
        "authority": ("referee-a/full" if best and best.get("evaluator") == "a" and best.get("scale") == "full" else "provisional" if best else None),
        "params": (best or {}).get("params", {}),
    }


def _manuscript_source_sha(project) -> str:
    from package_overleaf import source_tree_digest
    src=inside(project, "manuscript/latex")
    if not src.is_dir():
        raise ValueError("manuscript/latex missing")
    return source_tree_digest(src)


def _approval_snapshot(qs: dict) -> dict:
    # Materialize a detached JSON value. Approval snapshots must never share
    # mutable dict/list objects with live run-state.
    snapshot = {
        "claim_mode": qs.get("claim_mode", "computational"),
        "objective_mode": qs.get("objective_mode", "scalar"),
        "metrics": incumbent_metrics(qs),
        "validation_evidence": sorted([[e.get("kind"), e.get("file"), e.get("sha256")] for e in qs.get("validation_evidence", [])]),
        "conclusions": qs.get("conclusions", {}),
    }
    return json.loads(json.dumps(snapshot, ensure_ascii=False))


def _route_fingerprint(project, qid: str, qs: dict) -> str | None:
    routes = qs.get("routes", [])
    if not any(r.get("status") == "main" for r in routes):
        return None
    # Approval covers the route decision, not only the main-route ID. Changing a
    # competitor status/evidence can change why the main route was chosen.
    payload = {"routes": sorted((dict(r) for r in routes), key=lambda r: r.get("id", ""))}
    log = Path(project) / "team_control" / f"route-{qid}.json"
    payload["falsification_log_sha256"] = sha(log) if log.is_file() else None
    payload["falsification_evidence"] = []
    if log.is_file():
        try:
            rows = read(log).get("iterations") or []
            for row in rows:
                rel = row.get("evidence")
                ep = inside(project, rel)
                payload["falsification_evidence"].append({"path": rel, "sha256": sha(ep) if ep.is_file() else None})
        except Exception:
            payload["falsification_evidence"] = [{"invalid": True}]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _revalidate_final_report(project, payload: dict) -> tuple[bool, str]:
    """Re-run the final gate from the artifact paths stored in a report."""
    if payload.get("passed") is not True or payload.get("scope") != "final":
        return False, "final compliance report is not PASS/final"
    b = payload.get("bindings") or {}
    for key in ("paper", "source", "proof", "official_checklist", "source_registry", "overleaf_zip"):
        rec = b.get(key) or {}
        if not rec.get("path") or not rec.get("sha256"):
            return False, f"final compliance report missing binding: {key}"
        try:
            fp = inside(project, rec["path"])
            if not fp.is_file() or sha(fp) != rec["sha256"]:
                return False, f"final compliance binding changed: {key}"
        except Exception as e:
            return False, f"cannot verify final compliance binding {key}: {e}"
    if b.get("source_tree_sha256") != _manuscript_source_sha(project):
        return False, "final compliance report is stale: LaTeX source tree changed"
    try:
        from final_compliance_gate import report as final_report
        fresh = final_report(
            project, b["paper"]["path"], b["proof"]["path"], scope="final",
            provenance=(b.get("numeric_provenance") or {}).get("path", "manuscript/numeric-provenance.json"),
            theoretical_evidence=(b.get("theoretical_evidence") or {}).get("path", "manuscript/theoretical-evidence.json"),
            official_checklist=b["official_checklist"]["path"],
            overleaf_zip=b["overleaf_zip"]["path"],
            source_registry=b["source_registry"]["path"],
            tex=b["source"]["path"],
        )
    except Exception as e:
        return False, "cannot re-run final compliance: " + str(e)
    if fresh.get("passed") is not True:
        failed = [k for k, v in (fresh.get("checks") or {}).items() if v.get("passed") is not True]
        return False, "current artifacts no longer pass final compliance: " + ", ".join(failed[:5])
    if fresh.get("bindings") != b:
        return False, "final compliance report is stale: bound artifacts changed"
    return True, ""


def _invalidate_paper(data: dict) -> list[str]:
    paper = data.setdefault("paper", {
        "readability_review": None, "principles_review": None,
        "approvals": {g: None for g in PAPER_APPROVAL_GATES},
    })
    invalidated = []
    for key, label in (("readability_review", "READABILITY_REVIEW"),
                       ("principles_review", "FOUR_PRINCIPLES_REVIEW")):
        if paper.get(key) is not None:
            paper[key] = None
            invalidated.append(label)
    approvals = paper.setdefault("approvals", {g: None for g in PAPER_APPROVAL_GATES})
    for g in PAPER_APPROVAL_GATES:
        if approvals.get(g) is not None:
            approvals[g] = None
            invalidated.append(g)
    return invalidated


def _invalidate_downstream(data: dict, qs: dict, include_route: bool = False) -> list[str]:
    invalidated = []
    gates = QUESTION_APPROVAL_GATES if include_route else ("FREEZE_RESULT",)
    for g in gates:
        if qs.get("approvals", {}).get(g) is not None:
            qs["approvals"][g] = None
            invalidated.append(g)
    invalidated.extend(_invalidate_paper(data))
    return invalidated


def _paper(data: dict) -> dict:
    return data.setdefault("paper", {
        "readability_review": None, "principles_review": None,
        "approvals": {g: None for g in PAPER_APPROVAL_GATES},
    })


def _question_quality_basis(project, data: dict, qid: str, qs: dict) -> dict:
    """Return the current evidence basis used by the whole-paper four-principles review."""
    tr = qs.get("traceability")
    su = qs.get("suitability")
    freeze = qs.get("approvals", {}).get("FREEZE_RESULT")
    if not tr or tr.get("passed") is not True:
        raise ValueError(f"{qid}: current traceability missing")
    if not su:
        raise ValueError(f"{qid}: Method Suitability A-F missing")
    if freeze is None or freeze.get("snapshot") != _approval_snapshot(qs):
        raise ValueError(f"{qid}: FREEZE_RESULT missing or stale")
    if freeze.get("dependency_freezes", {}) != _dependency_freeze_basis(data, qid):
        raise ValueError(f"{qid}: FREEZE_RESULT stale because an upstream dependency changed")
    for label, rec in (("traceability", tr), ("suitability", su)):
        fp = Path(project) / rec.get("file", "")
        if not fp.is_file() or (rec.get("sha256") and sha(fp) != rec["sha256"]):
            raise ValueError(f"{qid}: {label} artifact missing or changed")
    claim_mode = qs.get("claim_mode", "computational")
    kinds = ({"theory_check"} if claim_mode == "theoretical" else
             set(PRIMARY_VALIDATION_KINDS) if claim_mode == "computational" else
             set(PRIMARY_VALIDATION_KINDS) | {"theory_check"})
    evidence = [e for e in qs.get("validation_evidence", []) if e.get("kind") in kinds]
    if not evidence:
        raise ValueError(f"{qid}: problem-matched validation evidence missing")
    if claim_mode == "mixed":
        if not any(e.get("kind") == "theory_check" for e in evidence):
            raise ValueError(f"{qid}: mixed claim is missing theory_check evidence")
        if not any(e.get("kind") in PRIMARY_VALIDATION_KINDS for e in evidence):
            raise ValueError(f"{qid}: mixed claim is missing computational validation evidence")
    for ev in evidence:
        current_sha = validation_evidence_sha(project, ev.get("file", ""))
        if current_sha != ev.get("sha256"):
            raise ValueError(f"{qid}: validation evidence missing or changed: {ev.get('file')}")
    return {
        "claim_mode": qs.get("claim_mode"),
        "objective_mode": qs.get("objective_mode"),
        "traceability_sha256": tr.get("sha256"),
        "suitability_sha256": su.get("sha256"),
        "validation_basis": sorted(
            [{"kind": e.get("kind"), "file": e.get("file"), "sha256": e.get("sha256")} for e in evidence],
            key=lambda x: (x.get("kind") or "", x.get("file") or ""),
        ),
        "freeze_snapshot": freeze.get("snapshot"),
    }


def ancestors(data: dict, qid: str) -> set:
    """Transitive closure of depends_on (all questions qid is built upon)."""
    seen: set = set()
    stack = list(data["questions"].get(qid, {}).get("depends_on", []))
    while stack:
        q = stack.pop()
        if q in seen or q not in data["questions"]:
            continue
        seen.add(q)
        stack.extend(data["questions"][q].get("depends_on", []))
    return seen


def _assert_dependency_dag(data: dict) -> None:
    """Reject circular question dependencies; a modeling dependency graph must be acyclic."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(qid: str, trail: list[str]) -> None:
        if qid in visiting:
            start = trail.index(qid) if qid in trail else 0
            cycle = trail[start:] + [qid]
            raise ValueError("question dependency cycle detected: " + " -> ".join(cycle))
        if qid in visited:
            return
        visiting.add(qid)
        trail.append(qid)
        for parent in data.get("questions", {}).get(qid, {}).get("depends_on", []):
            visit(parent, trail)
        trail.pop()
        visiting.remove(qid)
        visited.add(qid)

    for qid in data.get("questions", {}):
        visit(qid, [])



def _all_questions_at_least(data: dict, stage: str) -> bool:
    questions = data.get("questions") or {}
    return bool(questions) and all(STAGES.index(q.get("stage", "UNDERSTAND")) >= STAGES.index(stage)
                                   for q in questions.values())


def _freeze_token(qs: dict) -> str | None:
    freeze = (qs.get("approvals") or {}).get("FREEZE_RESULT")
    if not freeze or freeze.get("snapshot") != _approval_snapshot(qs):
        return None
    raw = json.dumps(freeze.get("snapshot"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _dependency_freeze_basis(data: dict, qid: str) -> dict[str, str]:
    """Current scientific freeze tokens for every upstream dependency.

    A declared dependency means the downstream result is built on the upstream
    question.  If an upstream freeze disappears or changes, the downstream
    freeze must be revisited before writing/submission.
    """
    basis = {}
    for dep in sorted(ancestors(data, qid)):
        token = _freeze_token(_question(data, dep))
        if token is None:
            raise ValueError(f"{qid}: upstream dependency {dep} has no current FREEZE_RESULT")
        basis[dep] = token
    return basis

def number_forms(x) -> list[str]:
    """Display forms a metric may take in prose, for stale-number scanning."""
    if x is None:
        return []
    forms = {repr(float(x)), f"{float(x):.6g}", f"{float(x):.4g}", str(x)}
    if float(x) == int(float(x)):
        forms.add(str(int(float(x))))
    return sorted(f for f in forms if f and f not in {"nan", "inf", "-inf"})


# ---------------------------------------------------------------- commands

def cmd_init(project, a) -> dict:
    p = state_path(project)
    if p.exists() and not a.force:
        raise ValueError("run-state.json already exists (use --force to reinitialize; this is logged)")
    data = {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "created_at": _now(),
        "profile": a.profile,
        "competition": {"name": a.competition or "", "edition": a.edition or ""},
        "seq": 0,
        "events": [],
        "questions": {},
        "paper": {"readability_review": None, "principles_review": None,
                  "approvals": {g: None for g in PAPER_APPROVAL_GATES}},
        "derived_reports": [],
    }
    event(data, "init", profile=a.profile, run_id=data["run_id"],
          note="forced reinit of existing state" if p.exists() else None)
    for qid in [q for q in (a.questions or "").split(",") if q.strip()]:
        _add_question(data, qid.strip())
    for dep in [d for d in (a.depends or "").split(",") if d.strip()]:
        child, _, parent = dep.partition(":")
        _add_question(data, child.strip())
        _add_question(data, parent.strip())
        deps = data["questions"][child.strip()].setdefault("depends_on", [])
        if parent.strip() not in deps:
            deps.append(parent.strip())
        event(data, "question_depends", question=child.strip(), depends_on=parent.strip())
    _assert_dependency_dag(data)
    save(project, data)
    return {"passed": True, "command": "init", "state_path": str(p), "profile": a.profile}


def _add_question(data: dict, qid: str) -> None:
    if not re.fullmatch(r"Q[1-9][0-9]*", qid):
        raise ValueError(f"invalid question id: {qid}")
    if qid in data["questions"]:
        return
    data["questions"][qid] = {
        "depends_on": [], "stage": "UNDERSTAND", "stage_history": [{"stage": "UNDERSTAND", "at": _now()}],
        "claim_mode": "computational", "objective_mode": "scalar", "mode_note": "",
        "traceability": None, "routes": [], "candidates": {}, "incumbent": None, "challenger": None,
        "bounds": {"lower": None, "upper": None, "gap": None, "source": None, "not_applicable_reason": None},
        "referees": {"a": None, "b": None},
        "validation_evidence": [], "conclusions": {"supported": [], "empirical": [], "unproven": []},
        "suitability": None,
        "parameter_sweeps": [], "budget_notes": [], "project_back": [],
        "approvals": {g: None for g in QUESTION_APPROVAL_GATES},
        "rollbacks": [],
    }
    event(data, "question_registered", question=qid)


def cmd_question_add(project, data, a) -> dict:
    existing = data.get("questions", {})
    existed = a.id in existing
    parents = [d.strip() for d in (a.depends_on or "").split(",") if d.strip()]
    introduces_question = (not existed) or any(parent not in existing for parent in parents)
    if introduces_question and any(STAGES.index(q.get("stage", "UNDERSTAND")) >= STAGES.index("WRITE") for q in existing.values()):
        raise ValueError("cannot add a new question/dependency after manuscript writing has started; stage back before changing paper topology")
    _add_question(data, a.id)
    qs = data["questions"][a.id]
    new_parents = [parent for parent in parents if parent not in qs["depends_on"]]
    if existed and new_parents and (qs.get("stage") != "UNDERSTAND" or qs.get("routes") or qs.get("candidates")):
        raise ValueError("change question dependencies only during UNDERSTAND before routes or candidates are created")
    changed = not existed
    for parent in parents:
        _add_question(data, parent)
        if parent not in qs["depends_on"]:
            qs["depends_on"].append(parent)
            changed = True
    if changed:
        _assert_dependency_dag(data)
        qs["traceability"] = None
        _invalidate_paper(data)
    event(data, "question_add", question=a.id)
    save(project, data)
    return {"passed": True, "command": "question add", "question": a.id}


def cmd_question_configure(project, data, a) -> dict:
    qs = _question(data, a.id)
    if qs.get("stage") != "UNDERSTAND" or qs.get("routes") or qs.get("candidates"):
        raise ValueError("configure claim/objective mode during UNDERSTAND before routes or candidates are created")
    claim = a.claim_mode or qs.get("claim_mode", "computational")
    objective = a.objective_mode or qs.get("objective_mode", "scalar")
    if claim not in CLAIM_MODES:
        raise ValueError("claim-mode must be computational|theoretical|mixed")
    if objective not in OBJECTIVE_MODES:
        raise ValueError("objective-mode must be scalar|vector|lexicographic|none")
    note = (a.mode_note or "").strip()
    if claim == "theoretical":
        objective = "none"
        if not note:
            raise ValueError("theoretical mode requires --mode-note explaining why proof/derivation is the primary claim")
    elif objective == "none":
        raise ValueError("computational/mixed questions need scalar, vector, or lexicographic evaluation")
    elif claim == "mixed" and not note:
        raise ValueError("mixed mode requires --mode-note stating both the computational and proof obligations")
    elif objective in ("vector", "lexicographic") and not note:
        raise ValueError("vector/lexicographic mode requires --mode-note stating metric semantics or priority/Pareto policy")
    qs["claim_mode"] = claim
    qs["objective_mode"] = objective
    qs["mode_note"] = note
    qs["traceability"] = None
    event(data, "question_configure", question=a.id, claim_mode=claim, objective_mode=objective, mode_note=note)
    save(project, data)
    return {"passed": True, "command": "question configure", "question": a.id,
            "claim_mode": claim, "objective_mode": objective, "mode_note": note}

def _stage_index(qs: dict) -> int:
    return STAGES.index(qs["stage"])


def _ensure_not_done(qs: dict, action: str) -> None:
    if qs.get("stage") == "DONE":
        raise ValueError(f"{action} cannot modify a DONE question; use 'stage back' first")


def _scalar_computational(qs: dict) -> bool:
    return qs.get("claim_mode", "computational") in ("computational", "mixed") and qs.get("objective_mode", "scalar") == "scalar"


def gate_check(project, data: dict, qid: str, to_stage: str) -> dict:
    """Structural entry requirements for `to_stage`. Returns a report dict."""
    qs = _question(data, qid)
    fast = data.get("profile") == "fast"
    missing: list[str] = []
    gate_warnings_pre: list[str] = []

    def need(cond: bool, msg: str):
        if not cond:
            missing.append(msg)

    idx = STAGES.index(to_stage)
    if idx <= _stage_index(qs):
        return {"passed": False, "errors": [
            {"kind": f"{qid} already at {qs['stage']}; use 'stage back' to roll back", "where": to_stage}]}

    if idx >= STAGES.index("IDEATE"):
        tr = qs.get("traceability")
        need(tr and tr.get("passed") is True,
             "Problem-to-Model traceability not checked (trace check --question %s --file team_control/traceability-%s.json)" % (qid, qid))
        if tr:
            tp = inside(project, tr.get("file", ""))
            need(tp.is_file() and bool(tr.get("sha256")) and sha(tp) == tr["sha256"],
                 "traceability file changed after check; re-run trace check")
    route_target = 2 if fast else 4
    route_warning = None
    if idx >= STAGES.index("SELECT"):
        routes = qs.get("routes", [])
        need(len(routes) >= 1, "need at least one defensible modeling route")
        tags=[r.get("structure_tag") for r in routes if r.get("structure_tag")]
        need(len(tags)==len(set(tags)), "duplicate structure_tag detected; merge structurally equivalent routes")
        if len(routes) < route_target:
            route_warning=f"only {len(routes)} route(s) registered vs exploration target {route_target}; acceptable only when additional routes would be artificial"
    if idx >= STAGES.index("FALSIFY"):
        need(any(r.get("status") == "main" for r in qs.get("routes", [])),
             "no route marked main (route status --status main)")
        for r in qs.get("routes", []):
            if r.get("status") != "killed":
                continue
            need(bool(r.get("kill_evidence")), f"killed route {r.get('id')} without evidence")
            if r.get("kill_evidence"):
                ep = Path(project) / r["kill_evidence"]
                need(ep.is_file(), f"killed route {r.get('id')} evidence file missing")
                if ep.is_file() and r.get("kill_evidence_sha256"):
                    need(sha(ep) == r["kill_evidence_sha256"],
                         f"killed route {r.get('id')} evidence changed; re-record route status")
    if idx >= STAGES.index("BUILD"):
        route_approval = qs["approvals"].get("ACCEPT_ROUTE")
        need(route_approval is not None,
             "ACCEPT_ROUTE approval missing; a bare 'continue' is NOT route acceptance")
        current_main = next((r.get("id") for r in qs.get("routes", []) if r.get("status") == "main"), None)
        if route_approval is not None:
            need(route_approval.get("main_route_at_approval") == current_main,
                 "ACCEPT_ROUTE is stale: approved main route differs from the current main route")
            need(route_approval.get("route_fingerprint") == _route_fingerprint(project, qid, qs),
                 "ACCEPT_ROUTE is stale: route definition or falsification evidence changed after approval")
        rl = Path(project) / "team_control" / f"route-{qid}.json"
        if rl.is_file():
            rr = route_report(project, f"team_control/route-{qid}.json", qid)
            need(rr["passed"], f"route-{qid}.json falsification log invalid: {rr['errors'][:2]}")
        else:
            need(False, f"team_control/route-{qid}.json (3 cognitive passes) missing")
    if idx >= STAGES.index("VALIDATE"):
        suitability = qs.get("suitability")
        need(suitability is not None,
             "Method Suitability A-F is the BUILD exit check (suitability record --file ...)")
        if suitability is not None:
            sp = Path(project) / suitability.get("file", "")
            need(sp.is_file(), "Method Suitability file missing; re-record suitability")
            if sp.is_file() and suitability.get("sha256"):
                need(sha(sp) == suitability["sha256"],
                     "Method Suitability file changed after record; re-run suitability record")
            need(suitability.get("route_fingerprint") == _route_fingerprint(project, qid, qs),
                 "Method Suitability is stale: approved route/falsification evidence changed; re-record A-F")
    if idx >= STAGES.index("VALIDATE") and qs.get("claim_mode") in ("computational", "mixed"):
        need(qs.get("referees", {}).get("a") is not None,
             "Referee A (reference evaluator) not registered (referee register --role a)")
        need(qs.get("incumbent") is not None, "no incumbent promoted (candidate promote)")
        if qs.get("incumbent"):
            incumbent = qs["candidates"][qs["incumbent"]]
            need(incumbent.get("status") == "incumbent", "incumbent candidate is no longer active; promote a valid candidate")
            need(incumbent.get("route") == current_main,
                 "incumbent belongs to a different modeling route; evaluate and promote a candidate for the accepted main route")
            best = best_result(qs["candidates"][qs["incumbent"]], qs.get("objective_mode", "scalar"))
            need(best is not None, "incumbent has no feasible result on record")
            for r in qs["candidates"][qs["incumbent"]].get("results", []):
                if r.get("scale") == "full":
                    need(any(p.get("decision") == "continue" for p in qs["candidates"][qs["incumbent"]].get("probes", []))
                         or qs["candidates"][qs["incumbent"]].get("complexity") != "high",
                         "full-scale result without a recorded continue-probe")
    if idx >= STAGES.index("INTERPRET"):
        evidence_records = qs.get("validation_evidence", [])
        kinds = {e.get("kind") for e in evidence_records}
        claim_mode = qs.get("claim_mode", "computational")
        if claim_mode in ("theoretical", "mixed"):
            need("theory_check" in kinds, f"{claim_mode} question needs at least one bound theory_check/proof review evidence")
        if claim_mode in ("computational", "mixed"):
            ref_b = qs.get("referees", {}).get("b")
            if ref_b:
                need(bool(ref_b.get("independence_note")), "Referee B independence note is required when Referee B is used")
                need(ref_b.get("independence") in ("independent", "shares_code"),
                     "Referee B independence must be declared honestly")
                if ref_b.get("independence") == "shares_code":
                    gate_warnings_pre.append("Referee B shares code with the main implementation; treat it as supporting rather than independent evidence")
            need(bool(kinds & set(PRIMARY_VALIDATION_KINDS)),
                 "need at least one problem-matched validation evidence record")
            if not fast and len(kinds & set(PRIMARY_VALIDATION_KINDS)) == 1:
                gate_warnings_pre.append("only one validation evidence kind recorded; add a second only if the claim risk warrants it")
            ref_a = qs.get("referees", {}).get("a")
            if ref_a:
                ap = Path(project) / ref_a.get("path", "")
                need(ap.is_file() and ref_a.get("sha256") == sha(ap), "Referee A file changed or disappeared; re-register and re-evaluate")
            if ref_b:
                bp = Path(project) / ref_b.get("path", "")
                need(bp.is_file() and ref_b.get("sha256") == sha(bp), "Referee B file changed or disappeared; re-register validation")
            m=incumbent_metrics(qs)
            need(m.get("authority")=="referee-a/full", "final interpretation requires a full-scale Referee A result; provisional solver/small-scale values cannot be headline numbers")
            if m.get("evidence"):
                best = best_result(qs["candidates"][qs["incumbent"]], qs.get("objective_mode", "scalar"))
                ep = Path(project) / best.get("evidence", "")
                need(ep.is_file() and best.get("evidence_sha256") == sha(ep), "authoritative result evidence changed or disappeared; re-run/re-record the result")
                need(ref_a is not None and best.get("evaluator_sha256") == ref_a.get("sha256"),
                     "authoritative result was not produced by the currently registered Referee A; re-evaluate and re-record it")
        for ev in evidence_records:
            try:
                current_sha = validation_evidence_sha(project, ev.get("file", ""))
                need(current_sha == ev.get("sha256"), f"validation evidence changed after record: {ev.get('file')}; re-run evidence record")
            except (ValueError, OSError) as e:
                need(False, str(e))
    if idx >= STAGES.index("WRITE"):
        freeze = qs["approvals"].get("FREEZE_RESULT")
        need(freeze is not None,
             "FREEZE_RESULT approval missing; numbers must be frozen before writing")
        if freeze is not None:
            need(freeze.get("snapshot") == _approval_snapshot(qs),
                 "FREEZE_RESULT is stale: current results/evidence/conclusions changed after approval")
            try:
                need(freeze.get("dependency_freezes", {}) == _dependency_freeze_basis(data, qid),
                     "FREEZE_RESULT is stale: an upstream dependent question changed after this result was frozen")
            except Exception as e:
                need(False, "FREEZE_RESULT dependency basis is stale: " + str(e))
        concl = qs.get("conclusions", {})
        need(any(concl.get(k) for k in ("supported", "empirical", "unproven")),
             "INTERPRET conclusions not recorded (interpret record)")
        for dep_q, dep in data["questions"].items():
            if dep_q != qid and qid in ancestors(data, dep_q) and _stage_index(dep) >= STAGES.index("VALIDATE"):
                pbs = _project_back_records(data, dep_q, qid)
                need(any(pb.get("record") and pb.get("outcome") in ("no_improvement", "promoted", "rejected") for pb in pbs),
                     f"backward projection from {dep_q} to {qid} not resolved (project-back record + done)")
    if idx >= STAGES.index("DELIVER"):
        paper = _paper(data)
        manuscript_approval = paper.get("approvals", {}).get("APPROVE_MANUSCRIPT")
        need(manuscript_approval is not None,
             "APPROVE_MANUSCRIPT missing; approve the whole paper once after every question reaches WRITE")
        rr = paper.get("readability_review")
        pr = paper.get("principles_review")
        need(rr is not None, "whole-paper readability review not recorded")
        need(pr is not None, "whole-paper four-principles review not recorded")
        try:
            mp = inside(project, "manuscript/latex/main.tex")
            source_sha = _manuscript_source_sha(project) if mp.is_file() else None
            if manuscript_approval is not None:
                need(mp.is_file() and manuscript_approval.get("manuscript_sha256") == sha(mp)
                     and manuscript_approval.get("source_tree_sha256") == source_sha,
                     "APPROVE_MANUSCRIPT is stale: LaTeX source tree changed after approval")
            if rr is not None:
                rp = Path(project) / rr.get("file", "")
                need(rp.is_file() and rr.get("sha256") == (sha(rp) if rp.is_file() else None),
                     "readability review file missing or changed")
                need(mp.is_file() and rr.get("manuscript_sha256") == sha(mp)
                     and rr.get("source_tree_sha256") == source_sha,
                     "readability review is stale: LaTeX source tree changed")
            if pr is not None:
                pp = Path(project) / pr.get("file", "")
                need(pp.is_file() and pr.get("sha256") == (sha(pp) if pp.is_file() else None),
                     "four-principles review file missing or changed")
                need(mp.is_file() and pr.get("manuscript_sha256") == sha(mp)
                     and pr.get("source_tree_sha256") == source_sha,
                     "four-principles review is stale: LaTeX source tree changed")
                current_basis = {k: _question_quality_basis(project, data, k, v) for k, v in sorted(data["questions"].items())}
                basis = pr.get("basis") or {}
                need(basis.get("readability_sha256") == (rr or {}).get("sha256"),
                     "four-principles review is stale: readability review changed")
                need(basis.get("questions") == current_basis,
                     "four-principles review is stale: question evidence/results changed")
            if manuscript_approval is not None:
                need(manuscript_approval.get("readability_sha256") == (rr or {}).get("sha256"),
                     "APPROVE_MANUSCRIPT is stale: readability review changed")
                need(manuscript_approval.get("principles_sha256") == (pr or {}).get("sha256"),
                     "APPROVE_MANUSCRIPT is stale: four-principles review changed")
        except Exception as e:
            need(False, "cannot verify whole-paper review/approval freshness: " + str(e))
    if idx >= STAGES.index("DONE"):
        paper = _paper(data)
        auth = paper.get("approvals", {}).get("AUTHORIZE_SUBMISSION")
        need(auth is not None,
             "AUTHORIZE_SUBMISSION missing; authorize the whole final package once after every question reaches DELIVER")
        if auth is not None:
            rp = Path(project) / auth.get("final_report_path", "")
            need(rp.is_file(), "authorized final compliance report missing")
            if rp.is_file():
                need(sha(rp) == auth.get("final_report_sha256"),
                     "final compliance report changed after submission authorization")
                try:
                    fr = read(rp)
                    ok, reason = _revalidate_final_report(project, fr)
                    need(ok, reason or "final compliance revalidation failed")
                except Exception as e:
                    need(False, "cannot revalidate final compliance report: " + str(e))

    stale = [r for r in data.get("derived_reports", []) if r.get("state_seq", -1) < data.get("seq", 0)]
    gate_warnings = [f"derived report stale: {r.get('path')} (regenerate with 'report')" for r in stale]
    gate_warnings.extend(gate_warnings_pre)
    if locals().get("route_warning"): gate_warnings.append(route_warning)
    report = {"passed": not missing, "command": "gate check", "question": qid, "to_stage": to_stage,
              "profile": data.get("profile"), "missing": missing,
              "warnings": gate_warnings}
    report["errors"] = [{"kind": m, "where": f"{qid}->{to_stage}"} for m in missing]
    return report


def _project_back_records(data: dict, from_q: str, to_q: str) -> list:
    return [pb for pb in data["questions"].get(from_q, {}).get("project_back", []) if pb.get("to") == to_q]


def cmd_gate(project, data, a) -> dict:
    to = a.to or STAGES[min(_stage_index(_question(data, a.question)) + 1, len(STAGES) - 1)]
    if to not in STAGES:
        raise ValueError(f"unknown stage: {to}")
    return gate_check(project, data, a.question, to)


def cmd_stage_show(project, data, a) -> dict:
    if a.question:
        qs = _question(data, a.question)
        out = {"question": a.question, "stage": qs["stage"], "metrics": incumbent_metrics(qs)}
    else:
        out = {"questions": {q: {"stage": v["stage"], **incumbent_metrics(v)} for q, v in data["questions"].items()}}
    return {"passed": True, "command": "stage show", **out}


def cmd_stage_advance(project, data, a) -> dict:
    qs = _question(data, a.question)
    current_idx = _stage_index(qs)
    if current_idx >= len(STAGES) - 1:
        raise ValueError("question is already DONE")
    expected = STAGES[current_idx + 1]
    to = a.to or expected
    if to != expected:
        raise ValueError(f"stage advance is one step at a time; next stage is {expected}")
    report = gate_check(project, data, a.question, to)
    if not report["passed"]:
        return report
    old = qs["stage"]
    qs["stage"] = to
    qs["stage_history"].append({"stage": to, "at": _now(), "from": old})
    event(data, "stage_advance", question=a.question, **{"from": old, "to": to})
    save(project, data)
    report["passed"] = True
    report["command"] = "stage advance"
    report["stage"] = to
    return report


def cmd_stage_back(project, data, a) -> dict:
    qs = _question(data, a.question)
    if a.to not in STAGES or STAGES.index(a.to) >= _stage_index(qs):
        raise ValueError("'stage back' needs an earlier valid stage")
    if not a.reason or not a.reason.strip():
        raise ValueError("--reason is required for a rollback")
    old = qs["stage"]
    qs["stage"] = a.to
    qs["stage_history"].append({"stage": a.to, "at": _now(), "from": old, "rollback": True})
    qs.setdefault("rollbacks", []).append({"from": old, "to": a.to, "reason": a.reason, "at": _now()})
    if a.to == "DELIVER":
        # Re-open only the final packaging step. Keep manuscript reviews/approval if the source is unchanged;
        # final gates will invalidate them automatically if artifacts actually changed.
        paper = _paper(data)
        invalidated = []
        if paper.get("approvals", {}).get("AUTHORIZE_SUBMISSION") is not None:
            paper["approvals"]["AUTHORIZE_SUBMISSION"] = None
            invalidated.append("AUTHORIZE_SUBMISSION")
    elif a.to == "WRITE":
        # Re-open paper content: scientific freezes remain valid, paper-level review/approval does not.
        invalidated = _invalidate_paper(data)
    else:
        invalidated = _invalidate_downstream(data, qs, include_route=STAGES.index(a.to) < STAGES.index("BUILD"))
    if STAGES.index(a.to) < STAGES.index("BUILD"):
        qs["suitability"] = None
    event(data, "stage_rollback", question=a.question, **{"from": old, "to": a.to, "reason": a.reason},
          approvals_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "stage back", "question": a.question, "stage": a.to,
            "approvals_invalidated": invalidated,
            "note": "downstream decisions cleared; revalidate before re-advancing"}

def cmd_trace_check(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "trace check")
    rel = a.file
    doc = read(inside(project, rel))
    errors: list[str] = []
    elements = doc.get("elements")
    if doc.get("question") and doc["question"] != a.question:
        errors.append("traceability file belongs to a different question")
    if not isinstance(elements, list) or not elements:
        errors.append("elements must be a non-empty list")
        elements = []
    ids = set()
    roles_seen = set()
    for el in elements:
        if not isinstance(el, dict):
            errors.append("element must be an object")
            continue
        eid = el.get("id")
        if not eid or eid in ids:
            errors.append(f"element id missing or duplicate: {eid}")
        ids.add(eid)
        role = el.get("role")
        if role not in TRACE_ROLES:
            errors.append(f"{eid}: role must be one of {TRACE_ROLES}")
        roles_seen.add(role)
        problem_element = (el.get("problem_element") or "").strip()
        model_expression = (el.get("model_expression") or "").strip()
        math_object = (el.get("math_object") or "").strip()
        # The core anti-drift rule: every model element must answer
        # "which part of the problem does this correspond to?"
        if not problem_element:
            errors.append(f"{eid}: model element without problem_element (orphan; untraceable to the problem statement)")
        if role in ("decision_variable", "state_variable", "hard_constraint", "objective", "evaluation_rule", "relation", "claim") \
                and not model_expression:
            errors.append(f"{eid}: role {role} without model_expression")
        if not math_object:
            errors.append(f"{eid}: math_object missing (what mathematical object represents it)")
        if el.get("core") is True and not (el.get("analysis_role") or el.get("solver_role")):
            errors.append(f"{eid}: core element without analysis_role (what it does in the model/proof/solution)")
    if qs.get("claim_mode", "computational") in ("computational", "mixed"):
        if not ({"objective", "evaluation_rule"} & roles_seen):
            errors.append("computational question has no objective/evaluation target in traceability")
    report = {"passed": not errors, "command": "trace check", "question": a.question,
              "file": rel, "errors": [{"kind": e, "where": rel} for e in errors]}
    if not errors:
        new_sha = sha(inside(project, rel))
        old_sha = (qs.get("traceability") or {}).get("sha256")
        invalidated = _invalidate_downstream(data, qs, include_route=True) if old_sha and old_sha != new_sha else []
        qs["traceability"] = {"file": rel, "sha256": new_sha,
                              "elements": len(elements), "passed": True, "checked_at": _now()}
        event(data, "traceability_checked", question=a.question, file=rel, elements=len(elements),
              approvals_invalidated=invalidated)
        save(project, data)
    return report


def cmd_route_add(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "route add")
    if not (a.name or "").strip() or not (a.structure_tag or "").strip():
        raise ValueError("route add requires --name and --structure-tag "
                         "(the tag is the mathematical structure, not the solver brand)")
    if any(r["id"] == a.id for r in qs["routes"]):
        raise ValueError(f"route {a.id} already exists")
    if any(r.get("structure_tag") == a.structure_tag for r in qs["routes"]):
        raise ValueError("duplicate structure_tag: merge structurally equivalent routes instead of padding the route count")
    qs["routes"].append({"id": a.id, "name": a.name, "structure_tag": a.structure_tag,
                         "status": "proposed", "kill_evidence": None, "at": _now()})
    invalidated = _invalidate_downstream(data, qs, include_route=True) if qs.get("approvals", {}).get("ACCEPT_ROUTE") else []
    event(data, "route_add", question=a.question, route=a.id, structure_tag=a.structure_tag,
          approvals_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "route add", "route": a.id, "approvals_invalidated": invalidated}


def cmd_route_status(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "route status")
    old_main = next((r.get("id") for r in qs.get("routes", []) if r.get("status") == "main"), None)
    old_fp = _route_fingerprint(project, a.question, qs) if qs.get("approvals", {}).get("ACCEPT_ROUTE") else None
    route = next((r for r in qs["routes"] if r["id"] == a.id), None)
    if route is None:
        raise ValueError(f"route {a.id} not found")
    if a.status not in ROUTE_STATUSES:
        raise ValueError(f"status must be one of {ROUTE_STATUSES}")
    if a.status == "killed" and not a.evidence:
        raise ValueError("killing a route requires --evidence (no sunk-cost retention, but no silent kills either)")
    kill_sha = None
    if a.status == "killed":
        ep = inside(project, a.evidence)
        if not ep.is_file():
            raise ValueError("route kill evidence file does not exist inside the project")
        kill_sha = sha(ep)
    if a.status == "main":
        for r in qs["routes"]:
            if r["status"] == "main" and r["id"] != a.id:
                raise ValueError(f"route {r['id']} is already main; demote it first")
    if a.status == "challenger":
        others = [r for r in qs["routes"] if r["status"] == "challenger" and r["id"] != a.id]
        if others:
            raise ValueError("at most one challenger route")
    route["status"] = a.status
    if a.status == "killed":
        route["kill_evidence"] = a.evidence
        route["kill_evidence_sha256"] = kill_sha
    else:
        # Kill evidence describes only the killed state; do not let stale metadata
        # silently contaminate a resurrected/main/challenger route fingerprint.
        route["kill_evidence"] = None
        route.pop("kill_evidence_sha256", None)
    new_main = next((r.get("id") for r in qs.get("routes", []) if r.get("status") == "main"), None)
    new_fp = _route_fingerprint(project, a.question, qs) if qs.get("approvals", {}).get("ACCEPT_ROUTE") else None
    invalidated = []
    if old_fp is not None and old_fp != new_fp:
        invalidated = _invalidate_downstream(data, qs, include_route=True)
    event(data, "route_status", question=a.question, route=a.id, status=a.status,
          previous_main=old_main, current_main=new_main, approvals_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "route status", "route": a.id, "status": a.status}


def cmd_candidate_register(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "candidate register")
    if a.id in qs.get("candidates", {}):
        raise ValueError(f"candidate {a.id} already registered")
    if a.route and not any(r["id"] == a.route for r in qs["routes"]):
        raise ValueError(f"route {a.route} not registered")
    qs.setdefault("candidates", {})[a.id] = {
        "id": a.id, "route": a.route, "kind": a.kind, "complexity": a.complexity,
        "status": "active", "results": [], "probes": [], "created_at": _now(),
        "superseded_by": None, "origin": a.origin, "reject_reason": None,
    }
    event(data, "candidate_register", question=a.question, candidate=a.id, kind=a.kind, complexity=a.complexity)
    save(project, data)
    return {"passed": True, "command": "candidate register", "candidate": a.id}


def cmd_probe_record(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "probe record")
    cand = _candidate(qs, a.candidate)
    if a.decision not in ("continue", "abort"):
        raise ValueError("decision must be continue|abort")
    if a.decision == "abort" and qs.get("incumbent") == a.candidate:
        raise ValueError("cannot abort the incumbent; promote another candidate first")
    if a.decision == "continue" and a.extrapolated_full_s is not None and a.abort_threshold_s is not None \
            and float(a.extrapolated_full_s) > float(a.abort_threshold_s) and not a.override_rationale:
        raise ValueError("extrapolated full cost exceeds abort threshold; choose abort or give --override-rationale")
    probe = {"scale_desc": a.scale_desc, "runtime_s": _finite_number(a.runtime_s, "runtime-s"),
             "memory_mb": _finite_number(a.memory_mb, "memory-mb") if a.memory_mb is not None else None,
             "extrapolated_full_s": _finite_number(a.extrapolated_full_s, "extrapolated-full-s")
             if a.extrapolated_full_s is not None else None,
             "abort_threshold_s": _finite_number(a.abort_threshold_s, "abort-threshold-s")
             if a.abort_threshold_s is not None else None,
             "decision": a.decision, "rationale": a.rationale, "override_rationale": a.override_rationale,
             "at": _now()}
    cand.setdefault("probes", []).append(probe)
    if a.decision == "abort":
        cand["status"] = "rejected"
        cand["reject_reason"] = f"complexity probe aborted: {a.rationale}"
    event(data, "probe_record", question=a.question, candidate=a.candidate, decision=a.decision,
          scale=a.scale_desc, extrapolated_full_s=a.extrapolated_full_s)
    save(project, data)
    return {"passed": True, "command": "probe record", "candidate": a.candidate, "decision": a.decision,
            "note": "aborted candidate marked rejected; do not run it at full scale" if a.decision == "abort" else None}


def cmd_result_record(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "result record")
    if qs.get("claim_mode") == "theoretical":
        raise ValueError("theoretical question: record proof/theory evidence instead of forcing a numeric result")
    cand = _candidate(qs, a.candidate)
    if cand["status"] in ("superseded", "rejected"):
        raise ValueError(f"candidate {a.candidate} is {cand['status']}; register a new candidate instead")
    mode = qs.get("objective_mode", "scalar")
    objective = None
    sense = None
    metrics = {}
    if mode == "scalar":
        if a.objective is None or a.sense is None:
            raise ValueError("scalar result requires --objective and --sense")
        objective = _finite_number(a.objective, "objective")
        if a.sense not in ("min", "max"):
            raise ValueError("sense must be min|max")
        senses = {r.get("sense") for r in cand.get("results", []) if r.get("sense")}
        if senses and a.sense not in senses:
            raise ValueError("candidate objective sense changed; register a new candidate/objective definition")
        sense = a.sense
    else:
        for kv in a.metric or []:
            k, sep, v = kv.partition("=")
            if not sep or not k.strip():
                raise ValueError("--metric expects name=value")
            metrics[k.strip()] = _finite_number(v, f"metric {k.strip()}")
        if len(metrics) < 2:
            raise ValueError(f"{mode} result requires at least two --metric name=value entries")
        old_metric_sets = {tuple(r.get("metrics", {}).keys()) for r in cand.get("results", []) if r.get("metrics")}
        if old_metric_sets and tuple(metrics.keys()) not in old_metric_sets:
            raise ValueError("candidate metric vector/order changed; register a new candidate or keep one objective definition")
    evidence_sha = _file_sha(project, a.evidence)
    evaluator_sha = None
    if a.evaluator in ("a", "b"):
        evaluator_rec = (qs.get("referees") or {}).get(a.evaluator)
        if not evaluator_rec:
            raise ValueError(f"evaluator {a.evaluator} is not registered; register the referee before recording its result")
        evaluator_sha = evaluator_rec.get("sha256")
    continue_reason = (a.continue_reason or "").strip() or None
    if a.scale == "full" and cand.get("complexity") == "high" and not any(p.get("decision") == "continue" for p in cand.get("probes", [])):
        raise ValueError("complexity guard: high-complexity candidate needs a continue-probe before a full-scale result")
    params = {}
    for kv in a.param or []:
        k, sep, v = kv.partition("=")
        if not k or not sep:
            raise ValueError(f"--param expects k=v, got {kv}")
        params[k] = v
    result = {"objective": objective, "metrics": metrics, "sense": sense, "feasible": _parse_bool(a.feasible),
              "scale": a.scale, "evidence": a.evidence, "evidence_sha256": evidence_sha,
              "evaluator": a.evaluator, "evaluator_sha256": evaluator_sha,
              "params": params, "continue_reason": continue_reason, "at": _now()}
    cand.setdefault("results", []).append(result)
    invalidated = _invalidate_downstream(data, qs) if qs.get("incumbent") == a.candidate else []
    if continue_reason:
        qs.setdefault("budget_notes", []).append({"reason": continue_reason, "candidate": a.candidate,
                                                  "objective": objective, "metrics": metrics, "at": _now()})
    event(data, "result_record", question=a.question, candidate=a.candidate, objective=objective,
          metrics=metrics, feasible=result["feasible"], scale=a.scale, downstream_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "result record", "candidate": a.candidate, "objective": objective,
            "metrics": metrics, "feasible": result["feasible"], "downstream_invalidated": invalidated}

def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if str(value).lower() in ("true", "1", "yes"):
        return True
    if str(value).lower() in ("false", "0", "no"):
        return False
    raise ValueError(f"expected a boolean, got {value!r}")


def cmd_candidate_promote(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "candidate promote")
    if _stage_index(qs) < STAGES.index("BUILD"):
        raise ValueError("candidate promotion belongs to BUILD or later; accept and falsify the main route first")
    cand = _candidate(qs, a.id)
    if cand["status"] == "rejected":
        raise ValueError("cannot promote a rejected candidate")
    if qs.get("claim_mode") == "theoretical":
        raise ValueError("theoretical question has no numeric incumbent; use evidence + conclusions instead")
    if best_result(cand, qs.get("objective_mode", "scalar")) is None:
        raise ValueError("candidate has no feasible authoritative result on record; nothing to promote")
    main_route = next((r.get("id") for r in qs.get("routes", []) if r.get("status") == "main"), None)
    approval = qs.get("approvals", {}).get("ACCEPT_ROUTE")
    if cand.get("route") != main_route:
        raise ValueError("candidate belongs to a route that is not the current main route")
    if not approval or approval.get("main_route_at_approval") != main_route \
            or approval.get("route_fingerprint") != _route_fingerprint(project, a.question, qs):
        raise ValueError("current main route is not covered by a fresh ACCEPT_ROUTE approval")
    old = qs.get("incumbent")
    if old and old != a.id:
        old_c = qs["candidates"].get(old)
        if old_c:
            old_c["status"] = "superseded"
            old_c["superseded_by"] = a.id
    cand["status"] = "incumbent"
    qs["incumbent"] = a.id
    if qs.get("challenger") == a.id:
        qs["challenger"] = None
    invalidated = _invalidate_downstream(data, qs)
    event(data, "candidate_promote", question=a.question, candidate=a.id, superseded=old,
          approvals_invalidated=invalidated, reason=a.reason)
    save(project, data)
    return {"passed": True, "command": "candidate promote", "incumbent": a.id, "superseded": old,
            "approvals_invalidated": invalidated,
            "note": "downstream documents must regenerate from metrics show/report; superseded numbers are stale"}

def cmd_candidate_set_challenger(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "candidate set challenger")
    cand = _candidate(qs, a.id)
    if cand["status"] in ("superseded", "rejected"):
        raise ValueError(f"candidate {a.id} is {cand['status']}")
    if qs.get("incumbent") == a.id:
        raise ValueError("the incumbent cannot be its own challenger")
    if qs.get("challenger") and qs["challenger"] != a.id:
        prev = qs["candidates"].get(qs["challenger"])
        if prev and prev["status"] == "challenger":
            prev["status"] = "active"
    cand["status"] = "challenger"
    qs["challenger"] = a.id
    event(data, "candidate_challenger", question=a.question, candidate=a.id)
    save(project, data)
    return {"passed": True, "command": "candidate set-challenger", "challenger": qs["challenger"]}


def cmd_candidate_reject(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "candidate reject")
    if not (a.reason or "").strip():
        raise ValueError("rejecting a candidate requires --reason")
    cand = _candidate(qs, a.id)
    if qs.get("incumbent") == a.id:
        raise ValueError("cannot reject the incumbent; promote another candidate first")
    cand["status"] = "rejected"
    cand["reject_reason"] = a.reason
    event(data, "candidate_reject", question=a.question, candidate=a.id, reason=a.reason)
    save(project, data)
    return {"passed": True, "command": "candidate reject", "candidate": a.id}


def cmd_referee_register(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "referee register")
    if qs.get("claim_mode") == "theoretical":
        raise ValueError("theoretical questions use theory_check/proof evidence; Referee A/B are for computational evaluation")
    file_sha = _file_sha(project, a.path)
    rec = {"path": a.path, "sha256": file_sha, "registered_at": _now(), "note": a.note}
    if a.role == "b":
        if a.independence not in ("independent", "shares_code"):
            raise ValueError("Referee B must declare independence honestly: --independence independent|shares_code")
        if not a.independence_note or not a.independence_note.strip():
            raise ValueError("--independence-note is required for Referee B")
        rec.update({"independence": a.independence, "independence_note": a.independence_note})
        ref_a = qs["referees"].get("a")
        if ref_a and ref_a.get("sha256") == file_sha:
            raise ValueError("Referee B is byte-identical to Referee A; that is not validation, that is a copy")
    else:
        rec["role_note"] = ("Referee A parses official input, checks legality and computes the objective; "
                            "it must not contain solver search logic")
    qs.setdefault("referees", {})[a.role] = rec
    invalidated = _invalidate_downstream(data, qs)
    event(data, "referee_register", question=a.question, role=a.role, path=a.path,
          independence=rec.get("independence"), downstream_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "referee register", "role": a.role, "path": a.path,
            "warning": ("independence declared insufficient (shares_code); VALIDATE conclusions must say so"
                        if rec.get("independence") == "shares_code" else None)}


def cmd_evidence_record(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "evidence record")
    if a.kind not in EVIDENCE_KINDS:
        raise ValueError(f"kind must be one of {EVIDENCE_KINDS}")
    file_sha = validation_evidence_sha(project, a.file)
    old_records = qs.get("validation_evidence", [])
    replaced = [e for e in old_records if e.get("kind") == a.kind
                and inside(project, e.get("file", "")) == inside(project, a.file)]
    qs["validation_evidence"] = [e for e in old_records if e not in replaced]
    qs["validation_evidence"].append(
        {"kind": a.kind, "file": a.file, "sha256": file_sha, "summary": a.summary, "at": _now()})
    invalidated = _invalidate_downstream(data, qs)
    event(data, "evidence_record", question=a.question, kind=a.kind, file=a.file,
          sha256=file_sha, replaced_evidence=replaced, downstream_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "evidence record", "kind": a.kind, "downstream_invalidated": invalidated}


def cmd_interpret_record(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "interpret record")
    concl = qs.setdefault("conclusions", {"supported": [], "empirical": [], "unproven": []})
    added = False
    for bucket, value in (("supported", a.supported), ("empirical", a.empirical), ("unproven", a.unproven)):
        if value:
            concl.setdefault(bucket, []).append({"statement": value, "at": _now()})
            added = True
    if not added:
        raise ValueError("record at least one of --supported/--empirical/--unproven")
    invalidated = _invalidate_downstream(data, qs)
    event(data, "interpret_record", question=a.question,
          supported=bool(a.supported), empirical=bool(a.empirical), unproven=bool(a.unproven),
          downstream_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "interpret record"}


def cmd_readability_record(project, data, a) -> dict:
    if not _all_questions_at_least(data, "WRITE"):
        raise ValueError("whole-paper readability review requires every question to have reached WRITE")
    main = inside(project, "manuscript/latex/main.tex")
    if not main.is_file():
        raise ValueError("manuscript/latex/main.tex missing; readability review must inspect the current manuscript")
    p = inside(project, a.file)
    if not p.is_file():
        raise ValueError(f"review file not found: {a.file}")
    text = p.read_text(encoding="utf-8-sig")
    missing = [m for m in READABILITY_MARKERS if m not in text]
    if missing:
        raise ValueError("readability review must answer all six judge questions; missing sections: " + ", ".join(missing))
    if len(text.strip()) < 240:
        raise ValueError("readability review is too thin to be a real six-question review")
    verdicts = re.findall(r"判定\s*[:：]\s*(PASS|FAIL)(?!\s*/)", text, re.I)
    if not verdicts or verdicts[-1].upper() != "PASS" or any(v.upper() == "FAIL" for v in verdicts):
        raise ValueError("readability review must end in an explicit PASS; any FAIL blocks delivery")
    paper = _paper(data)
    invalidated = []
    if paper.get("principles_review") is not None:
        paper["principles_review"] = None; invalidated.append("FOUR_PRINCIPLES_REVIEW")
    for g in PAPER_APPROVAL_GATES:
        if paper["approvals"].get(g) is not None:
            paper["approvals"][g] = None; invalidated.append(g)
    paper["readability_review"] = {
        "file": a.file, "sha256": sha(p), "recorded_at": _now(),
        "manuscript_sha256": sha(main), "source_tree_sha256": _manuscript_source_sha(project),
        "six_questions": READABILITY_MARKERS,
    }
    event(data, "readability_record", file=a.file, approvals_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "readability record", "file": a.file,
            "approvals_invalidated": invalidated,
            "note": "whole-paper review bound to the current LaTeX source tree"}


def cmd_principles_record(project, data, a) -> dict:
    if not _all_questions_at_least(data, "WRITE"):
        raise ValueError("whole-paper four-principles review requires every question to have reached WRITE")
    main = inside(project, "manuscript/latex/main.tex")
    if not main.is_file():
        raise ValueError("manuscript/latex/main.tex missing")
    main_sha = sha(main)
    source_sha = _manuscript_source_sha(project)
    paper = _paper(data)
    rr = paper.get("readability_review")
    if not rr:
        raise ValueError("four-principles review requires the whole-paper readability review first")
    rfp = Path(project) / rr.get("file", "")
    if not rfp.is_file() or sha(rfp) != rr.get("sha256") or rr.get("manuscript_sha256") != main_sha or rr.get("source_tree_sha256") != source_sha:
        raise ValueError("readability review is stale or not bound to the current LaTeX source tree")
    basis = {qid: _question_quality_basis(project, data, qid, qs) for qid, qs in sorted(data["questions"].items())}
    fp = inside(project, a.file)
    if not fp.is_file():
        raise ValueError(f"four-principles review file not found: {a.file}")
    text = fp.read_text(encoding="utf-8-sig")
    missing = [m for m in CORE_PRINCIPLE_MARKERS if m not in text]
    if missing:
        raise ValueError("four-principles review must cover all four principles; missing sections: " + ", ".join(missing))
    if len(text.strip()) < 360:
        raise ValueError("four-principles review is too thin; cite concrete evidence and manuscript locations")
    verdicts = re.findall(r"判定\s*[:：]\s*(PASS|FAIL)(?!\s*/)", text, re.I)
    if len(verdicts) < 4 or any(v.upper() == "FAIL" for v in verdicts) or sum(v.upper() == "PASS" for v in verdicts) < 4:
        raise ValueError("all four core principles must be explicitly PASS and no explicit FAIL may remain before delivery")
    invalidated = []
    for g in PAPER_APPROVAL_GATES:
        if paper["approvals"].get(g) is not None:
            paper["approvals"][g] = None; invalidated.append(g)
    paper["principles_review"] = {
        "file": a.file, "sha256": sha(fp), "recorded_at": _now(),
        "manuscript_sha256": main_sha, "source_tree_sha256": source_sha,
        "markers": CORE_PRINCIPLE_MARKERS,
        "basis": {"readability_sha256": rr.get("sha256"), "questions": basis},
    }
    event(data, "principles_record", file=a.file, approvals_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "principles record", "file": a.file,
            "approvals_invalidated": invalidated,
            "note": "one whole-paper four-principles review covers every current question and the current source tree"}


def cmd_suitability_record(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "suitability record")
    if qs.get("stage") != "BUILD":
        raise ValueError("Method Suitability A-F is a BUILD-stage decision; advance to BUILD or roll back to BUILD before recording it")
    p = inside(project, a.file)
    if not p.is_file():
        raise ValueError(f"suitability file not found: {a.file}")
    text = p.read_text(encoding="utf-8-sig")
    labels = set(re.findall(r"(?m)^\s*([A-F])[\.、:：]", text))
    required = set("ABCDEF")
    if labels != required:
        missing = sorted(required - labels)
        raise ValueError("Method Suitability record must answer all A-F items; missing: "
                         + (",".join(missing) or "none") + "; found: "
                         + (",".join(sorted(labels)) or "none"))
    if len(text.strip()) < 200:
        raise ValueError("Method Suitability record is too thin to justify the chosen method/proof strategy")
    approval = qs.get("approvals", {}).get("ACCEPT_ROUTE")
    current_fp = _route_fingerprint(project, a.question, qs)
    if not approval or approval.get("route_fingerprint") != current_fp:
        raise ValueError("record Method Suitability after a fresh ACCEPT_ROUTE so A-F is bound to the chosen route")
    new_sha = sha(p)
    old = qs.get("suitability") or {}
    changed = bool(old) and (old.get("sha256") != new_sha or old.get("route_fingerprint") != current_fp)
    invalidated = _invalidate_downstream(data, qs) if changed else []
    qs["suitability"] = {"file": a.file, "sha256": new_sha, "route_fingerprint": current_fp, "recorded_at": _now()}
    event(data, "suitability_record", question=a.question, file=a.file, downstream_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "suitability record", "file": a.file,
            "downstream_invalidated": invalidated}

def cmd_bounds(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "bounds")
    if a.action == "set" and not _scalar_computational(qs):
        raise ValueError("numeric lower/upper bounds are only defined for scalar computational questions; use bounds na with a reason otherwise")
    if a.action == "na":
        if not a.reason:
            raise ValueError("--reason required when bounds are not applicable")
        qs["bounds"] = {"lower": None, "upper": None, "gap": None, "source": a.source,
                        "not_applicable_reason": a.reason}
    else:
        lower = _finite_number(a.lower, "lower") if a.lower is not None else None
        upper = _finite_number(a.upper, "upper") if a.upper is not None else None
        gap = None
        m = incumbent_metrics(qs)
        if lower is not None and upper is not None and m.get("objective") is not None:
            span = abs(upper - lower)
            gap = abs(m["objective"] - (lower if m.get("sense") == "min" else upper)) / span if span else 0.0
        qs["bounds"] = {"lower": lower, "upper": upper, "gap": gap, "source": a.source,
                        "not_applicable_reason": None}
    invalidated = _invalidate_downstream(data, qs)
    event(data, "bounds_set", question=a.question, downstream_invalidated=invalidated, **qs["bounds"])
    save(project, data)
    return {"passed": True, "command": "bounds", **qs["bounds"]}


def cmd_param_sweep(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "param sweep")
    if not _scalar_computational(qs):
        raise ValueError("parameter portfolio scoring requires a scalar computational objective; use direct evidence/analysis for other modes")
    cand = _candidate(qs, a.candidate)
    values = []
    for v in a.values.split(","):
        values.append(_finite_number(v.strip(), "sweep value"))
    if len(set(values)) != len(values):
        raise ValueError("sweep values contain duplicates")
    sid = f"S{len(qs.get('parameter_sweeps', [])) + 1}"
    qs.setdefault("parameter_sweeps", []).append({
        "id": sid, "candidate": cand["id"], "param": a.param, "values": values,
        "budget": a.budget, "status": "open", "records": [], "best_value": None,
        "claim": None, "optimality_evidence": None, "post_hoc_expansions": [], "closed_at": None})
    event(data, "param_sweep_open", question=a.question, sweep=sid, param=a.param, n_values=len(values))
    save(project, data)
    return {"passed": True, "command": "param sweep", "sweep": sid,
            "note": "fixed portfolio declared up front; results may only claim 'best in tested portfolio' "
                    "unless closed with optimality evidence"}


def cmd_param_record(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "param record")
    if not _scalar_computational(qs):
        raise ValueError("parameter portfolio scoring requires a scalar computational objective")
    sweep = next((s for s in qs.get("parameter_sweeps", []) if s["id"] == a.sweep), None)
    if sweep is None:
        raise ValueError(f"sweep {a.sweep} not found")
    if sweep["status"] == "closed":
        raise ValueError("sweep is closed; open a new sweep instead of appending to a closed portfolio")
    value = _finite_number(a.value, "value")
    expansion = None
    if value not in sweep["values"]:
        if not a.expand_rationale:
            raise ValueError(f"value {value} is outside the declared portfolio {sweep['values']}; "
                             "post-hoc expansion requires --expand-rationale and is recorded as such")
        expansion = {"value": value, "rationale": a.expand_rationale, "at": _now()}
        sweep["post_hoc_expansions"].append(expansion)
        sweep["values"].append(value)
    objective = _finite_number(a.objective, "objective")
    sweep["records"].append({"value": value, "objective": objective,
                             "feasible": _parse_bool(a.feasible) if a.feasible is not None else True,
                             "at": _now()})
    event(data, "param_record", question=a.question, sweep=a.sweep, value=value, objective=objective,
          post_hoc_expansion=bool(expansion))
    save(project, data)
    return {"passed": True, "command": "param record", "sweep": a.sweep, "value": value,
            "warning": "post-hoc portfolio expansion recorded; wording must remain 'best in tested portfolio'"
            if expansion else None}


def cmd_param_close(project, data, a) -> dict:
    qs = _question(data, a.question)
    _ensure_not_done(qs, "param close")
    if not _scalar_computational(qs):
        raise ValueError("parameter portfolio scoring requires a scalar computational objective")
    sweep = next((s for s in qs.get("parameter_sweeps", []) if s["id"] == a.sweep), None)
    if sweep is None:
        raise ValueError(f"sweep {a.sweep} not found")
    if sweep["status"] == "closed":
        raise ValueError("sweep already closed")
    best = _finite_number(a.best, "best")
    if not any(r["value"] == best for r in sweep["records"]):
        raise ValueError("best value was never evaluated in this sweep; record it first")
    feasible_records = [r for r in sweep["records"] if r.get("feasible") is not False]
    if feasible_records:
        true_best = (min if a.sense == "min" else max)(feasible_records, key=lambda r: r["objective"])
        if true_best["value"] != best:
            raise ValueError(f"claimed best {best} contradicts recorded results (actual best {true_best['value']})")
    if a.claim == "optimal":
        if not a.optimality_evidence:
            raise ValueError("claim=optimal requires --optimality-evidence (a proof/derivation file); "
                             "selecting the best of a fixed portfolio is 'portfolio_best', not 'optimal'")
        _file_sha(project, a.optimality_evidence)
    if len(sweep["records"]) < len(set(sweep["values"])):
        # Not fatal (some values may have been pruned for cause) but must be visible.
        note = "warning: not every declared portfolio value has a record; document why in the report"
    else:
        note = None
    sweep.update({"status": "closed", "best_value": best, "claim": a.claim,
                  "optimality_evidence": a.optimality_evidence, "closed_at": _now()})
    event(data, "param_close", question=a.question, sweep=a.sweep, best=best, claim=a.claim)
    save(project, data)
    return {"passed": True, "command": "param close", "sweep": a.sweep, "claim": a.claim,
            "allowed_wording": ("optimal (evidence-bound)" if a.claim == "optimal"
                                else "best in the fixed/tested portfolio ONLY"),
            "note": note}


def cmd_project_back_record(project, data, a) -> dict:
    src = _question(data, a.from_question)
    dst = _question(data, a.to_question)
    _ensure_not_done(src, "project-back record")
    _ensure_not_done(dst, "project-back record")
    if a.to_question not in ancestors(data, a.from_question):
        raise ValueError(f"{a.to_question} is not an (indirect) dependency of {a.from_question}; backward projection only follows the dependency graph")
    evidence_sha = _file_sha(project, a.evidence)
    m = incumbent_metrics(dst)
    scalar_dst = _scalar_computational(dst)
    if scalar_dst and a.objective is None:
        raise ValueError("scalar destination requires --objective for backward projection")
    objective = _finite_number(a.objective, "objective") if scalar_dst else None
    if not scalar_dst and not (a.note or "").strip():
        raise ValueError("non-scalar/theoretical projection requires --note explaining the qualitative/vector implication")
    better = None
    if scalar_dst and m.get("objective") is not None:
        sense = a.sense or m.get("sense") or "min"
        better = objective < m["objective"] if sense == "min" else objective > m["objective"]
    rec = {"from": a.from_question, "to": a.to_question, "record": True, "objective": objective,
           "sense": a.sense or m.get("sense"), "evidence": a.evidence, "evidence_sha256": evidence_sha,
           "comparison_mode": "scalar" if scalar_dst else "qualitative_or_vector",
           "beats_dst_incumbent": better, "dst_incumbent": m.get("incumbent"),
           "dst_incumbent_objective": m.get("objective"),
           "outcome": None, "at": _now(), "note": a.note}
    src.setdefault("project_back", []).append(rec)
    invalidated = _invalidate_downstream(data, dst)
    event(data, "project_back_record", **{"from": a.from_question, "to": a.to_question},
          objective=objective, comparison_mode=rec["comparison_mode"], beats_dst_incumbent=better,
          downstream_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "project-back record", "beats_dst_incumbent": better,
            "comparison_mode": rec["comparison_mode"],
            "action_required": (f"projected solution beats {a.to_question} incumbent ({objective} vs {m.get('objective')}); register/revalidate/promote or reject with reasons"
                                if better else None)}

def cmd_project_back_done(project, data, a) -> dict:
    src = _question(data, a.from_question)
    _ensure_not_done(src, "project-back done")
    if a.outcome not in ("no_improvement", "promoted", "rejected"):
        raise ValueError("outcome must be no_improvement|promoted|rejected")
    if a.outcome == "rejected" and not (a.note or "").strip():
        raise ValueError("rejecting a better projected solution requires --note with reasons")
    recs = [r for r in src.get("project_back", []) if r.get("to") == a.to_question and r.get("record")]
    if not recs:
        raise ValueError(f"no project-back record from {a.from_question} to {a.to_question}")
    if any(r.get("beats_dst_incumbent") for r in recs) and a.outcome == "no_improvement":
        raise ValueError("a recorded projection beats the incumbent; outcome cannot be no_improvement")
    dst = _question(data, a.to_question)
    if a.outcome == "promoted":
        scalar_improvements = [r for r in recs if r.get("comparison_mode") == "scalar" and r.get("beats_dst_incumbent") is True]
        if scalar_improvements:
            now = incumbent_metrics(dst)
            if now.get("authority") != "referee-a/full" or now.get("objective") is None:
                raise ValueError("promoted backward projection must be reflected in a current full-scale Referee A incumbent result")
            for r in scalar_improvements:
                old_obj = r.get("dst_incumbent_objective")
                sense = r.get("sense") or now.get("sense") or "min"
                improved = old_obj is None or (now["objective"] < old_obj if sense == "min" else now["objective"] > old_obj)
                if not improved:
                    raise ValueError("promoted backward projection is not reflected by an improved destination incumbent; revalidate/promote it or mark rejected")
    for r in recs:
        r["outcome"] = a.outcome
        r["outcome_note"] = a.note
        r["outcome_at"] = _now()
    dst = _question(data, a.to_question)
    _ensure_not_done(dst, "project-back done")
    invalidated = _invalidate_downstream(data, dst)
    event(data, "project_back_done", **{"from": a.from_question, "to": a.to_question}, outcome=a.outcome,
          downstream_invalidated=invalidated)
    save(project, data)
    return {"passed": True, "command": "project-back done", "outcome": a.outcome,
            "downstream_invalidated": invalidated}


def cmd_approve(project, data, a) -> dict:
    if a.gate not in APPROVAL_GATES:
        raise ValueError(f"gate must be one of {APPROVAL_GATES}")
    if not (a.rationale or "").strip():
        raise ValueError("--rationale with the user's actual decision is required")

    if a.gate in QUESTION_APPROVAL_GATES:
        if not a.question:
            raise ValueError(f"{a.gate} requires --question")
        qs = _question(data, a.question)
        required_stage = {"ACCEPT_ROUTE": "FALSIFY", "FREEZE_RESULT": "INTERPRET"}[a.gate]
        if qs.get("stage") != required_stage:
            raise ValueError(f"{a.gate} belongs to stage {required_stage}; current stage is {qs.get('stage')}")
        if a.gate == "FREEZE_RESULT" and qs["approvals"].get("ACCEPT_ROUTE") is None:
            raise ValueError("FREEZE_RESULT requires ACCEPT_ROUTE first")
        rec = {"rationale": a.rationale, "at": _now(), "evidence": a.evidence}
        if a.gate == "ACCEPT_ROUTE":
            main = next((r.get("id") for r in qs.get("routes", []) if r.get("status") == "main"), None)
            if not main:
                raise ValueError("no route marked main; nothing to accept")
            rel = f"team_control/route-{a.question}.json"
            route_log = Path(project) / rel
            if not route_log.is_file():
                raise ValueError("route falsification log missing; complete ARCHITECT/SKEPTIC/REVIEWER review first")
            rr = route_report(project, rel, a.question)
            if not rr.get("passed"):
                raise ValueError("route falsification log is not valid; do not approve the route yet")
            rec.update(main_route_at_approval=main, route_fingerprint=_route_fingerprint(project, a.question, qs))
        else:
            if qs.get("claim_mode") in ("computational", "mixed"):
                if not qs.get("incumbent"):
                    raise ValueError("no incumbent; nothing to freeze")
                m = incumbent_metrics(qs)
                if m.get("authority") != "referee-a/full":
                    raise ValueError("freeze requires a full-scale Referee A result; provisional values are not paper headline numbers")
                if not any(e.get("kind") in PRIMARY_VALIDATION_KINDS for e in qs.get("validation_evidence", [])):
                    raise ValueError("FREEZE_RESULT requires problem-matched validation evidence")
                if qs.get("claim_mode") == "mixed" and not any(e.get("kind") == "theory_check" for e in qs.get("validation_evidence", [])):
                    raise ValueError("mixed FREEZE_RESULT also requires theory_check evidence")
            elif not any(e.get("kind") == "theory_check" for e in qs.get("validation_evidence", [])):
                raise ValueError("theoretical FREEZE_RESULT requires theory_check evidence")
            if not any(qs.get("conclusions", {}).get(k) for k in ("supported", "empirical", "unproven")):
                raise ValueError("record INTERPRET conclusions before FREEZE_RESULT")
            rec["snapshot"] = _approval_snapshot(qs)
            rec["dependency_freezes"] = _dependency_freeze_basis(data, a.question)
        qs["approvals"][a.gate] = rec
        _invalidate_paper(data)
        event(data, "approve", question=a.question, gate=a.gate)
        save(project, data)
        return {"passed": True, "command": "approve", "gate": a.gate, "question": a.question}

    if a.question:
        raise ValueError(f"{a.gate} is a whole-paper approval; omit --question")
    paper = _paper(data)
    rec = {"rationale": a.rationale, "at": _now(), "evidence": a.evidence}
    if a.gate == "APPROVE_MANUSCRIPT":
        if not _all_questions_at_least(data, "WRITE"):
            raise ValueError("APPROVE_MANUSCRIPT requires every question to have reached WRITE")
        # This also checks every per-question freeze/evidence basis.
        current_basis = {qid: _question_quality_basis(project, data, qid, qs) for qid, qs in sorted(data["questions"].items())}
        main = inside(project, "manuscript/latex/main.tex")
        if not main.is_file():
            raise ValueError("manuscript/latex/main.tex missing; nothing to approve")
        main_sha = sha(main); source_sha = _manuscript_source_sha(project)
        rr = paper.get("readability_review"); pr = paper.get("principles_review")
        if not rr or not pr:
            raise ValueError("APPROVE_MANUSCRIPT requires current whole-paper readability and four-principles reviews")
        for label, record in (("readability", rr), ("four-principles", pr)):
            fp = Path(project) / record.get("file", "")
            if not fp.is_file() or sha(fp) != record.get("sha256") or record.get("manuscript_sha256") != main_sha or record.get("source_tree_sha256") != source_sha:
                raise ValueError(label + " review is stale or not bound to the current LaTeX source tree")
        if (pr.get("basis") or {}).get("readability_sha256") != rr.get("sha256") or (pr.get("basis") or {}).get("questions") != current_basis:
            raise ValueError("four-principles review is stale relative to current question evidence")
        rec.update(manuscript_path="manuscript/latex/main.tex", manuscript_sha256=main_sha,
                   source_tree_sha256=source_sha, readability_sha256=rr.get("sha256"),
                   principles_sha256=pr.get("sha256"))
    else:
        if not _all_questions_at_least(data, "DELIVER"):
            raise ValueError("AUTHORIZE_SUBMISSION requires every question to have reached DELIVER")
        ma = paper.get("approvals", {}).get("APPROVE_MANUSCRIPT") or {}
        main = inside(project, "manuscript/latex/main.tex")
        if not main.is_file() or ma.get("manuscript_sha256") != sha(main) or ma.get("source_tree_sha256") != _manuscript_source_sha(project):
            raise ValueError("current LaTeX source tree is not the manuscript version the user approved")
        report = inside(project, "team_control/final-compliance-report.json")
        if not report.is_file():
            raise ValueError("final compliance report missing; run final_compliance_gate --scope final first")
        payload = read(report)
        ok, reason = _revalidate_final_report(project, payload)
        if not ok:
            raise ValueError(reason or "final compliance revalidation failed")
        source = (payload.get("bindings") or {}).get("source") or {}
        if inside(project, source.get("path", "")) != main or source.get("sha256") != sha(main):
            raise ValueError("final compliance report is not bound to the current authoritative LaTeX source tree")
        rec.update(final_report_path="team_control/final-compliance-report.json",
                   final_report_sha256=sha(report), final_bindings=payload.get("bindings", {}))
    paper["approvals"][a.gate] = rec
    event(data, "approve", gate=a.gate)
    save(project, data)
    return {"passed": True, "command": "approve", "gate": a.gate, "scope": "paper"}


def cmd_continue(project, data, a) -> dict:
    if a.question:
        _question(data, a.question)  # validate id; CONTINUE_STAGE never changes stage or approvals
    event(data, "continue_stage", question=a.question, note=a.note)
    save(project, data)
    return {"passed": True, "command": "continue", "recorded": "CONTINUE_STAGE",
            "approvals_unchanged": True,
            "note": "'continue' only advances work in the current stage. It is NOT ACCEPT_ROUTE, "
                    "FREEZE_RESULT, APPROVE_MANUSCRIPT or AUTHORIZE_SUBMISSION; those need "
                    "'approve --gate ... --rationale ...' with the user's actual decision."}


def cmd_metrics_show(project, data, a) -> dict:
    qs = _question(data, a.question)
    m = incumbent_metrics(qs)
    stale = []
    for cid, c in qs.get("candidates", {}).items():
        if c.get("status") in ("superseded", "rejected"):
            for r in c.get("results", []):
                values=[r.get("objective")] if r.get("objective") is not None else list((r.get("metrics") or {}).values())
                stale.append({"candidate": cid, "status": c["status"], "objective": r.get("objective"), "metrics": r.get("metrics",{}),
                              "forms": sorted({f for v in values for f in number_forms(v)})})
    out = {"passed": True, "command": "metrics show", "question": a.question,
           "authoritative": m, "bounds": qs.get("bounds"),
           "referees": {k: (v or {}).get("path") for k, v in (qs.get("referees") or {}).items()},
           "stale_values_never_quote": stale,
           "note": "this is the single authoritative source for the headline metric; "
                   "manuscript numbers must bind to it via numeric-provenance, reports via 'report'"}
    return out


def cmd_metrics_scan(project, data, a) -> dict:
    qs = _question(data, a.question)
    p = inside(project, a.file)
    if not p.is_file():
        raise ValueError(f"file not found: {a.file}")
    text = p.read_text(encoding="utf-8-sig")
    stale_hits = []
    for cid, c in qs.get("candidates", {}).items():
        if c.get("status") not in ("superseded", "rejected"):
            continue
        for r in c.get("results", []):
            values=[r.get("objective")] if r.get("objective") is not None else list((r.get("metrics") or {}).values())
            for form in sorted({f for v in values for f in number_forms(v)}):
                if len(form) >= 3 and form in text:
                    stale_hits.append({"candidate": cid, "objective": r.get("objective"), "metrics": r.get("metrics",{}), "form": form})
                    break
    m = incumbent_metrics(qs)
    incumbent_forms = number_forms(m.get("objective"))
    incumbent_present = any(f in text for f in incumbent_forms) if m.get("objective") is not None else None
    report = {"passed": not stale_hits, "command": "metrics scan", "file": a.file,
              "stale_hits": stale_hits, "incumbent_value_present": incumbent_present,
              "errors": [{"kind": f"stale superseded value {h['form']} (candidate {h['candidate']}) still in document",
                          "where": a.file} for h in stale_hits]}
    return report


def build_summary(data: dict, project) -> dict:
    questions = {}
    for qid, qs in data["questions"].items():
        m = incumbent_metrics(qs)
        questions[qid] = {
            "stage": qs["stage"],
            "depends_on": qs.get("depends_on", []),
            "metrics": m,
            "bounds": qs.get("bounds"),
            "challenger": qs.get("challenger"),
            "candidates": {cid: {"status": c.get("status"), "kind": c.get("kind"),
                                 "n_results": len(c.get("results", [])),
                                 "best_objective": (best_result(c, qs.get("objective_mode", "scalar")) or {}).get("objective")}
                           for cid, c in qs.get("candidates", {}).items()},
            "referees": {k: ({"path": v.get("path"), "independence": v.get("independence")} if v else None)
                         for k, v in (qs.get("referees") or {}).items()},
            "validation_evidence_kinds": sorted({e.get("kind") for e in qs.get("validation_evidence", [])}),
            "conclusions": {k: len(v) for k, v in (qs.get("conclusions") or {}).items()},
            "parameter_sweeps": [{"id": s["id"], "param": s["param"], "status": s["status"],
                                  "claim": s.get("claim"), "best_value": s.get("best_value"),
                                  "post_hoc_expansions": len(s.get("post_hoc_expansions", []))}
                                 for s in qs.get("parameter_sweeps", [])],
            "project_back": qs.get("project_back", []),
            "approvals": {g: (v["at"] if v else None) for g, v in qs["approvals"].items()},
            "rollbacks": qs.get("rollbacks", []),
            "traceability": qs.get("traceability"),
        }
    paper = _paper(data)
    paper_summary = {
        "readability_review": bool(paper.get("readability_review")),
        "principles_review": bool(paper.get("principles_review")),
        "approvals": {g: ((paper.get("approvals") or {}).get(g) or {}).get("at") for g in PAPER_APPROVAL_GATES},
    }
    return {"run_id": data["run_id"], "profile": data.get("profile"), "state_seq": data.get("seq"),
            "generated_at": _now(), "competition": data.get("competition"), "questions": questions,
            "paper": paper_summary, "recent_events": data.get("events", [])[-12:]}


def render_markdown(summary: dict) -> str:
    lines = ["<!-- DERIVED REPORT: generated by scripts/run_state.py report. DO NOT hand-edit. -->",
             f"# Run State Summary — {summary['run_id']} (profile: {summary['profile']})",
             f"state_seq: {summary['state_seq']} · generated_at: {summary['generated_at']}", ""]
    paper = summary.get("paper") or {}
    pappr = paper.get("approvals") or {}
    lines += ["## Whole-paper state",
              f"- readability review={'yes' if paper.get('readability_review') else 'no'} · four-principles review={'yes' if paper.get('principles_review') else 'no'}",
              "- approvals: " + ", ".join(f"{g}={'YES' if pappr.get(g) else 'no'}" for g in PAPER_APPROVAL_GATES), ""]
    for qid in sorted(summary["questions"]):
        q = summary["questions"][qid]
        m = q["metrics"]
        lines.append(f"## {qid} — stage {q['stage']}" + (f" (depends on {', '.join(q['depends_on'])})" if q["depends_on"] else ""))
        if m.get("incumbent"):
            if m.get("metrics"):
                lines.append(f"- incumbent: **{m['incumbent']}** metrics={m['metrics']} feasible={m['feasible']} evidence=`{m.get('evidence')}` evaluator={m.get('evaluator') or 'n/a'} authority={m.get('authority')}")
            else:
                lines.append(f"- incumbent: **{m['incumbent']}** objective={m['objective']} ({m.get('sense')}) feasible={m['feasible']} evidence=`{m.get('evidence')}` evaluator={m.get('evaluator') or 'n/a'} authority={m.get('authority')}")
        else:
            lines.append("- incumbent: none")
        b = q.get("bounds") or {}
        if any(b.get(k) is not None for k in ("lower", "upper", "gap")):
            lines.append(f"- bounds: lower={b.get('lower')} upper={b.get('upper')} gap={b.get('gap')} source={b.get('source')}")
        elif b.get("not_applicable_reason"):
            lines.append(f"- bounds: N/A ({b['not_applicable_reason']})")
        for cid, c in sorted(q["candidates"].items()):
            mark = {"incumbent": "", "challenger": " [challenger]", "superseded": " [SUPERSEDED — stale, do not quote]",
                    "rejected": " [rejected]", "active": ""}.get(c["status"], "")
            lines.append(f"- candidate {cid}: {c['status']}{mark} kind={c['kind']} results={c['n_results']} best={c['best_objective']}")
        refs = q.get("referees") or {}
        for role in ("a", "b"):
            r = refs.get(role)
            if r:
                lines.append(f"- referee {role.upper()}: `{r['path']}`" +
                             (f" independence={r.get('independence')}" if r.get("independence") else ""))
        if q.get("validation_evidence_kinds"):
            lines.append(f"- validation evidence: {', '.join(q['validation_evidence_kinds'])}")
        for s in q.get("parameter_sweeps", []):
            lines.append(f"- sweep {s['id']} ({s['param']}): {s['status']} claim={s['claim']} best={s['best_value']} "
                         f"post_hoc_expansions={s['post_hoc_expansions']}")
        for pb in q.get("project_back", []):
            lines.append(f"- backward projection {pb.get('from')}→{pb.get('to')}: objective={pb.get('objective')} "
                         f"beats_incumbent={pb.get('beats_dst_incumbent')} outcome={pb.get('outcome')}")
        appr = q.get("approvals") or {}
        lines.append("- approvals: " + ", ".join(f"{g}={'YES' if appr.get(g) else 'no'}" for g in QUESTION_APPROVAL_GATES))
        concl = q.get("conclusions") or {}
        lines.append(f"- conclusions: supported={concl.get('supported', 0)} empirical={concl.get('empirical', 0)} "
                     f"unproven={concl.get('unproven', 0)}")
        for rb in q.get("rollbacks", []):
            lines.append(f"- rollback: {rb.get('from')}→{rb.get('to')} ({rb.get('reason')})")
        lines.append("")
    lines.append("## Recent events")
    for e in summary.get("recent_events", []):
        lines.append(f"- #{e['seq']} {e['action']} {json.dumps({k: v for k, v in e.get('detail', {}).items() if v is not None}, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def cmd_report(project, data, a) -> dict:
    # Log the event FIRST so the derived product carries the seq it was built from.
    seq = event(data, "report_generated", path=a.output)
    summary = build_summary(data, project)
    md_path = inside(project, a.output)
    json_path = md_path.with_suffix(".json")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reports = data.setdefault("derived_reports", [])
    reports[:] = [r for r in reports if r.get("path") != a.output]
    reports.append({"path": a.output, "json_path": str(json_path.relative_to(Path(project).resolve()))
                    if json_path.is_relative_to(Path(project).resolve()) else str(json_path),
                    "state_seq": seq, "at": _now()})
    save(project, data)
    return {"passed": True, "command": "report", "markdown": str(md_path), "json": str(json_path),
            "state_seq": seq,
            "note": "derived product: regenerate after every promote/rollback; never hand-edit metrics into documents"}


def cmd_status(project, data, a) -> dict:
    out = {"passed": True, "command": "status", "run_id": data["run_id"], "profile": data.get("profile"),
           "seq": data.get("seq"),
           "questions": {q: {"stage": v["stage"], "claim_mode": v.get("claim_mode"), "objective_mode": v.get("objective_mode"), **{k: m[k] for k in ("incumbent", "objective", "metrics", "feasible")}}
                         for q, v in data["questions"].items()
                         for m in [incumbent_metrics(v)]}}
    return out


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--project", type=Path, required=True)
    s = p.add_subparsers(dest="command", required=True)

    x = s.add_parser("init")
    x.add_argument("--profile", choices=["full", "fast"], default="full")
    x.add_argument("--competition"); x.add_argument("--edition")
    x.add_argument("--questions", help="comma separated, e.g. Q1,Q2,Q3")
    x.add_argument("--depends", help="comma separated child:parent pairs, e.g. Q2:Q1,Q3:Q2")
    x.add_argument("--force", action="store_true")

    x = s.add_parser("question"); x.add_argument("action", choices=["add","configure"])
    x.add_argument("--id", required=True); x.add_argument("--depends-on")
    x.add_argument("--claim-mode", choices=CLAIM_MODES); x.add_argument("--objective-mode", choices=OBJECTIVE_MODES)
    x.add_argument("--mode-note")

    x = s.add_parser("stage"); x.add_argument("action", choices=["show", "advance", "back"])
    x.add_argument("--question"); x.add_argument("--to"); x.add_argument("--reason")

    x = s.add_parser("gate"); x.add_argument("action", choices=["check"], nargs="?", default="check")
    x.add_argument("--question", required=True); x.add_argument("--to")

    x = s.add_parser("trace"); x.add_argument("action", choices=["check"])
    x.add_argument("--question", required=True); x.add_argument("--file", required=True)

    x = s.add_parser("route"); x.add_argument("action", choices=["add", "status"])
    x.add_argument("--question", required=True); x.add_argument("--id", required=True)
    x.add_argument("--name"); x.add_argument("--structure-tag"); x.add_argument("--status"); x.add_argument("--evidence")

    x = s.add_parser("candidate"); x.add_argument("action", choices=["register", "promote", "reject", "set-challenger"])
    x.add_argument("--question", required=True); x.add_argument("--id", required=True)
    x.add_argument("--route"); x.add_argument("--kind", default="baseline",
                   choices=["baseline", "structural", "heuristic", "exact", "projection", "other"])
    x.add_argument("--complexity", default="low", choices=["low", "medium", "high"])
    x.add_argument("--origin", help="e.g. projection-from-Q3")
    x.add_argument("--reason")

    x = s.add_parser("probe"); x.add_argument("action", choices=["record"])
    x.add_argument("--question", required=True); x.add_argument("--candidate", required=True)
    x.add_argument("--scale-desc", required=True); x.add_argument("--runtime-s", required=True)
    x.add_argument("--memory-mb"); x.add_argument("--extrapolated-full-s"); x.add_argument("--abort-threshold-s")
    x.add_argument("--decision", required=True); x.add_argument("--rationale", required=True)
    x.add_argument("--override-rationale")

    x = s.add_parser("result"); x.add_argument("action", choices=["record"])
    x.add_argument("--question", required=True); x.add_argument("--candidate", required=True)
    x.add_argument("--objective"); x.add_argument("--sense")
    x.add_argument("--metric", action="append")
    x.add_argument("--feasible", required=True); x.add_argument("--scale", choices=["small", "full"], default="small")
    x.add_argument("--evidence", required=True); x.add_argument("--evaluator", choices=["a", "b", "solver"])
    x.add_argument("--param", action="append"); x.add_argument("--continue-reason")

    x = s.add_parser("referee"); x.add_argument("action", choices=["register"])
    x.add_argument("--question", required=True); x.add_argument("--role", required=True, choices=["a", "b"])
    x.add_argument("--path", required=True); x.add_argument("--note")
    x.add_argument("--independence", choices=["independent", "shares_code"])
    x.add_argument("--independence-note")

    x = s.add_parser("evidence"); x.add_argument("action", choices=["record"])
    x.add_argument("--question", required=True); x.add_argument("--kind", required=True)
    x.add_argument("--file", required=True); x.add_argument("--summary", required=True)

    x = s.add_parser("interpret"); x.add_argument("action", choices=["record"])
    x.add_argument("--question", required=True)
    x.add_argument("--supported"); x.add_argument("--empirical"); x.add_argument("--unproven")

    x = s.add_parser("readability"); x.add_argument("action", choices=["record"])
    x.add_argument("--file", required=True)

    x = s.add_parser("principles"); x.add_argument("action", choices=["record"])
    x.add_argument("--file", required=True)

    x = s.add_parser("suitability"); x.add_argument("action", choices=["record"])
    x.add_argument("--question", required=True); x.add_argument("--file", required=True)

    x = s.add_parser("bounds"); x.add_argument("action", choices=["set", "na"])
    x.add_argument("--question", required=True); x.add_argument("--lower"); x.add_argument("--upper")
    x.add_argument("--source"); x.add_argument("--reason")

    x = s.add_parser("param"); x.add_argument("action", choices=["sweep", "record", "close"])
    x.add_argument("--question", required=True); x.add_argument("--candidate"); x.add_argument("--sweep")
    x.add_argument("--param"); x.add_argument("--values"); x.add_argument("--budget")
    x.add_argument("--value"); x.add_argument("--objective"); x.add_argument("--feasible")
    x.add_argument("--expand-rationale"); x.add_argument("--best"); x.add_argument("--sense", default="min")
    x.add_argument("--claim", choices=["portfolio_best", "optimal"]); x.add_argument("--optimality-evidence")

    x = s.add_parser("project-back"); x.add_argument("action", choices=["record", "done"])
    x.add_argument("--from", dest="from_question", required=True); x.add_argument("--to", dest="to_question", required=True)
    x.add_argument("--objective"); x.add_argument("--sense"); x.add_argument("--evidence"); x.add_argument("--note")
    x.add_argument("--outcome")


    x = s.add_parser("approve")
    x.add_argument("--question"); x.add_argument("--gate", required=True)
    x.add_argument("--rationale", required=True); x.add_argument("--evidence")

    x = s.add_parser("continue"); x.add_argument("--question"); x.add_argument("--note")

    x = s.add_parser("metrics"); x.add_argument("action", choices=["show", "scan"])
    x.add_argument("--question", required=True); x.add_argument("--file")

    x = s.add_parser("report"); x.add_argument("--output", default="team_control/reports/state-summary.md")
    x = s.add_parser("status")

    for sub in s.choices.values():
        if not any(act.dest == "output" for act in sub._actions):
            sub.add_argument("--output", default="team_control/run-state-report.json")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    a = parser.parse_args(argv)
    project = a.project
    try:
        if a.command == "init":
            report = cmd_init(project, a)
            emit(report, inside(project, a.output), label="run state")
            return 0
        data = load(project)
        handlers = {
            ("question", "add"): cmd_question_add,
            ("question", "configure"): cmd_question_configure,
            ("stage", "show"): cmd_stage_show,
            ("stage", "advance"): cmd_stage_advance,
            ("stage", "back"): cmd_stage_back,
            ("gate", "check"): cmd_gate,
            ("trace", "check"): cmd_trace_check,
            ("route", "add"): cmd_route_add,
            ("route", "status"): cmd_route_status,
            ("candidate", "register"): cmd_candidate_register,
            ("candidate", "promote"): cmd_candidate_promote,
            ("candidate", "reject"): cmd_candidate_reject,
            ("candidate", "set-challenger"): cmd_candidate_set_challenger,
            ("probe", "record"): cmd_probe_record,
            ("result", "record"): cmd_result_record,
            ("referee", "register"): cmd_referee_register,
            ("evidence", "record"): cmd_evidence_record,
            ("interpret", "record"): cmd_interpret_record,
            ("readability", "record"): cmd_readability_record,
            ("principles", "record"): cmd_principles_record,
            ("suitability", "record"): cmd_suitability_record,
            ("bounds", "set"): cmd_bounds, ("bounds", "na"): cmd_bounds,
            ("param", "sweep"): cmd_param_sweep,
            ("param", "record"): cmd_param_record,
            ("param", "close"): cmd_param_close,
            ("project-back", "record"): cmd_project_back_record,
            ("project-back", "done"): cmd_project_back_done,
            ("approve", None): cmd_approve,
            ("continue", None): cmd_continue,
            ("metrics", "show"): cmd_metrics_show,
            ("metrics", "scan"): cmd_metrics_scan,
            ("report", None): cmd_report,
            ("status", None): cmd_status,
        }
        key = (a.command, getattr(a, "action", None))
        handler = handlers.get(key) or handlers.get((a.command, None))
        if handler is None:
            raise ValueError(f"unknown command: {a.command} {getattr(a, 'action', '')}")
        report = handler(project, data, a)
        # 'report' writes its derived markdown to --output; its own emit goes to the
        # standard JSON report path so the derived product is never overwritten.
        out = "team_control/run-state-report.json" if a.command == "report" \
            else getattr(a, "output", "team_control/run-state-report.json")
        emit(report, inside(project, out), label=f"run state {a.command}")
        return 0 if report.get("passed") else 3
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as e:
        report = {"passed": False, "errors": [{"kind": str(e), "where": f"run state {a.command}"}]}
        emit(report, inside(project, getattr(a, "output", "team_control/run-state-report.json")),
             label=f"run state {a.command}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
