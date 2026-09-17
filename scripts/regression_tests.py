#!/usr/bin/env python3
"""Focused regression tests for the active Huawei Cup workflow.

The suite intentionally tests invariants that protect paper quality. Removed Word,
question-gate and autonomy stacks are not kept alive by legacy tests.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_state as rs
from audit_core import sha, theoretical_report
from final_compliance_gate import evidence_coverage, overleaf_report
from official_clause_gate import report as official_report
from source_gate import report as source_report
from package_overleaf import build as build_overleaf, source_tree_digest


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SkillRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, content, *, binary=False) -> Path:
        p = self.p / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            p.write_bytes(content)
        elif isinstance(content, (dict, list)):
            p.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            p.write_text(str(content), encoding="utf-8")
        return p

    def call(self, *args, expect=0, env=None):
        out = "team_control/test-report.json"
        argv = ["--project", str(self.p), *args, "--output", out]
        buf = io.StringIO()
        ctx = patch.dict(os.environ, env or {}, clear=False) if env is not None else contextlib.nullcontext()
        with ctx, contextlib.redirect_stdout(buf):
            code = rs.main(argv)
        self.assertEqual(code, expect, msg=f"args={args}\nstdout={buf.getvalue()}\nreport={(self.p/out).read_text() if (self.p/out).exists() else ''}")
        return json.loads((self.p / out).read_text(encoding="utf-8"))

    def init(self, profile="fast", questions="Q1", depends=""):
        args=["init", "--profile", profile, "--questions", questions]
        if depends: args += ["--depends", depends]
        return self.call(*args)

    def trace(self, q="Q1", theoretical=False):
        role = "claim" if theoretical else "objective"
        doc = {"question": q, "elements": [{
            "id": "E1", "role": role, "problem_element": "题目要求", "model_expression": "P" if theoretical else "min C(x)",
            "math_object": "proposition" if theoretical else "objective function", "core": True, "analysis_role": "captures the requested claim"
        }]}
        self.write(f"team_control/traceability-{q}.json", doc)
        return self.call("trace", "check", "--question", q, "--file", f"team_control/traceability-{q}.json")

    def route_log(self, q="Q1"):
        # Three different review lenses may legitimately use the same real pilot/proof file.
        f=self.write(f"runs/route-{q}-evidence.txt", "shared real pilot/proof evidence")
        rows=[]
        for i,lens in enumerate(("architect","skeptic","reviewer")):
            rows.append({"question":q,"lens":lens,"evidence":str(f.relative_to(self.p)),
                         "finding":f"finding {i}","change":f"change {i}","risk":f"risk {i}"})
        self.write(f"team_control/route-{q}.json", {"iterations":rows})

    def suitability(self, q="Q1"):
        text="\n".join(f"{c}. {c}项说明：当前模型或证明策略与题目结构相匹配，并说明替代、条件、正确性与验证依据。" for c in "ABCDEF")
        self.write(f"qa/suitability-{q}.md", text + "\n" + "具体依据。"*30)
        return self.call("suitability","record","--question",q,"--file",f"qa/suitability-{q}.md")

    def prepare_route(self, q="Q1", theoretical=False):
        self.trace(q,theoretical)
        self.call("stage","advance","--question",q)  # IDEATE
        self.call("route","add","--question",q,"--id","R1","--name","structural route","--structure-tag","structure-A")
        self.call("stage","advance","--question",q)  # SELECT (route count only warning)
        self.call("route","status","--question",q,"--id","R1","--status","main")
        self.call("stage","advance","--question",q)  # FALSIFY
        self.route_log(q)
        self.call("approve","--question",q,"--gate","ACCEPT_ROUTE","--rationale","user selected the falsified main route")

    def enter_build(self, q="Q1", theoretical=False):
        self.prepare_route(q, theoretical)
        self.call("stage", "advance", "--question", q)  # BUILD
        self.suitability(q)

    def make_review_files(self, fail_readability=False, fail_principles=False):
        self.write("manuscript/latex/main.tex", "\\documentclass{article}\n\\begin{document}Current paper\\end{document}\n")
        r=[]
        for m in rs.READABILITY_MARKERS:
            r += [f"## {m}", "这里给出与当前论文位置和证据对应的具体审阅说明，足够让评委快速理解论证链。"]
        r += ["判定：" + ("FAIL" if fail_readability else "PASS"), "补充说明：" + "清楚。"*40]
        self.write("qa/readability.md", "\n".join(r))
        p=[]
        for m in rs.CORE_PRINCIPLE_MARKERS:
            p += [f"## {m}", "本项引用当前题目、模型、证据与论文位置进行核对。", "判定：" + ("FAIL" if fail_principles and m==rs.CORE_PRINCIPLE_MARKERS[0] else "PASS")]
        p += ["总结：" + "证据充分且表达直接。"*40]
        self.write("qa/principles.md", "\n".join(p))

    # ---------- result authority / problem modes ----------
    def test_best_result_prefers_full_referee_a(self):
        cand={"results":[
            {"objective":1.0,"sense":"min","feasible":True,"scale":"small","evaluator":"solver"},
            {"objective":100.0,"sense":"min","feasible":True,"scale":"full","evaluator":"a"},
        ]}
        self.assertEqual(rs.best_result(cand,"scalar")["objective"],100.0)

    def test_best_result_rejects_mixed_scalar_sense_at_top_authority(self):
        cand={"results":[
            {"objective":1.0,"sense":"min","feasible":True,"scale":"full","evaluator":"a"},
            {"objective":2.0,"sense":"max","feasible":True,"scale":"full","evaluator":"a"},
        ]}
        with self.assertRaises(ValueError): rs.best_result(cand,"scalar")

    def test_vector_uses_latest_authoritative_vector_without_scalarizing(self):
        cand={"results":[
            {"metrics":{"cost":10,"risk":0.2},"feasible":True,"scale":"full","evaluator":"a"},
            {"metrics":{"cost":11,"risk":0.1},"feasible":True,"scale":"full","evaluator":"a"},
        ]}
        self.assertEqual(rs.best_result(cand,"vector")["metrics"],{"cost":11,"risk":0.1})

    def test_theoretical_mode_requires_explanation_and_forces_none(self):
        self.init()
        self.call("question","configure","--id","Q1","--claim-mode","theoretical",expect=2)
        self.call("question","configure","--id","Q1","--claim-mode","theoretical","--mode-note","proof is the requested deliverable")
        self.assertEqual(rs.load(self.p)["questions"]["Q1"]["objective_mode"],"none")

    def test_vector_mode_requires_semantics_note(self):
        self.init()
        self.call("question","configure","--id","Q1","--claim-mode","computational","--objective-mode","vector",expect=2)
        self.call("question","configure","--id","Q1","--claim-mode","computational","--objective-mode","vector","--mode-note","Pareto cost-risk trade-off")

    def test_theoretical_numeric_result_is_rejected(self):
        self.init(); self.call("question","configure","--id","Q1","--claim-mode","theoretical","--mode-note","proof")
        self.write("runs/x.json", {"x":1})
        # Candidate can exist as a modeling scratch artifact; numeric result still cannot be recorded.
        self.call("candidate","register","--question","Q1","--id","C1")
        self.call("result","record","--question","Q1","--candidate","C1","--objective","1","--sense","min","--feasible","true","--evidence","runs/x.json",expect=2)

    # ---------- problem fit / route logic ----------
    def test_traceability_rejects_orphan_model_element(self):
        self.init()
        self.write("team_control/traceability-Q1.json", {"question":"Q1","elements":[{"id":"E1","role":"objective","problem_element":"","model_expression":"min x","math_object":"objective"}]})
        self.call("trace","check","--question","Q1","--file","team_control/traceability-Q1.json",expect=3)

    def test_duplicate_structure_routes_rejected(self):
        self.init(); self.trace()
        self.call("route","add","--question","Q1","--id","R1","--name","one","--structure-tag","flow")
        self.call("route","add","--question","Q1","--id","R2","--name","same structure new solver","--structure-tag","flow",expect=2)

    def test_route_count_is_target_not_hard_gate(self):
        self.init(); self.trace(); self.call("stage","advance","--question","Q1")
        self.call("route","add","--question","Q1","--id","R1","--name","one defensible route","--structure-tag","unique")
        rep=self.call("stage","advance","--question","Q1")
        self.assertTrue(any("exploration target" in w for w in rep.get("warnings",[])))

    def test_accept_route_binds_falsification_fingerprint(self):
        self.init(); self.prepare_route()
        q=rs.load(self.p)["questions"]["Q1"]
        old=q["approvals"]["ACCEPT_ROUTE"]["route_fingerprint"]
        self.write("runs/route-Q1-evidence.txt","changed evidence")
        rep=self.call("gate","check","--question","Q1","--to","BUILD",expect=3)
        self.assertTrue(any("stale" in x for x in rep.get("missing",[])))
        self.assertEqual(old, q["approvals"]["ACCEPT_ROUTE"]["route_fingerprint"])

    def test_route_resurrection_clears_old_kill_evidence(self):
        self.init(); self.trace(); self.call("stage","advance","--question","Q1")
        self.call("route","add","--question","Q1","--id","R1","--name","route","--structure-tag","flow")
        self.write("runs/kill.txt","reason")
        self.call("route","status","--question","Q1","--id","R1","--status","killed","--evidence","runs/kill.txt")
        self.call("route","status","--question","Q1","--id","R1","--status","proposed")
        r=rs.load(self.p)["questions"]["Q1"]["routes"][0]
        self.assertIsNone(r.get("kill_evidence"));self.assertNotIn("kill_evidence_sha256",r)

    def test_dependency_graph_cannot_change_after_modeling_starts(self):
        self.init(questions="Q1,Q2")
        self.trace("Q1")
        self.call("stage","advance","--question","Q1")
        self.call("question","add","--id","Q1","--depends-on","Q2",expect=2)
        self.assertEqual(rs.load(self.p)["questions"]["Q1"]["depends_on"],[])

    def test_dependency_cycle_is_rejected(self):
        self.init(questions="Q1,Q2")
        self.call("question","add","--id","Q1","--depends-on","Q2")
        self.call("question","add","--id","Q2","--depends-on","Q1",expect=2)

    # ---------- stage branches ----------
    def test_theoretical_path_reaches_interpret_without_numeric_incumbent(self):
        self.init(); self.call("question","configure","--id","Q1","--claim-mode","theoretical","--mode-note","prove construction")
        self.enter_build(theoretical=True)
        self.call("stage","advance","--question","Q1") # VALIDATE
        self.write("runs/proof-review.md","proof checked at boundary cases")
        self.call("evidence","record","--question","Q1","--kind","theory_check","--file","runs/proof-review.md","--summary","proof steps and boundary cases checked")
        self.call("stage","advance","--question","Q1") # INTERPRET
        q=rs.load(self.p)["questions"]["Q1"]
        self.assertIsNone(q["incumbent"])
        self.assertIsNone(q["referees"]["a"])

    def test_computational_interpret_requires_full_referee_a(self):
        self.init(); self.enter_build()
        self.write("code/a.py","# ref a\n"); self.call("referee","register","--question","Q1","--role","a","--path","code/a.py")
        self.call("candidate","register","--question","Q1","--id","C1","--route","R1")
        self.write("runs/small.json", {"obj":1})
        self.call("result","record","--question","Q1","--candidate","C1","--objective","1","--sense","min","--feasible","true","--scale","small","--evidence","runs/small.json","--evaluator","a")
        self.call("candidate","promote","--question","Q1","--id","C1","--reason","pilot leader")
        self.call("stage","advance","--question","Q1") # VALIDATE
        self.write("code/b.py","# independent b\n"); self.call("referee","register","--question","Q1","--role","b","--path","code/b.py","--independence","independent","--independence-note","independent implementation")
        self.write("runs/base.json", {"passed":True}); self.call("evidence","record","--question","Q1","--kind","baseline_comparison","--file","runs/base.json","--summary","baseline checked")
        rep=self.call("stage","advance","--question","Q1",expect=3)
        self.assertTrue(any("full-scale Referee A" in x for x in rep.get("missing",[])))

    def test_computational_interpret_does_not_require_referee_b(self):
        self.init(); self.enter_build()
        self.write("code/a.py","# ref a\n"); self.call("referee","register","--question","Q1","--role","a","--path","code/a.py")
        self.call("candidate","register","--question","Q1","--id","C1","--route","R1")
        self.write("runs/full.json", {"obj":2})
        self.call("result","record","--question","Q1","--candidate","C1","--objective","2","--sense","min","--feasible","true","--scale","full","--evidence","runs/full.json","--evaluator","a")
        self.call("candidate","promote","--question","Q1","--id","C1","--reason","validated route candidate")
        self.call("stage","advance","--question","Q1") # VALIDATE
        self.write("runs/sens.json", {"passed":True}); self.call("evidence","record","--question","Q1","--kind","sensitivity","--file","runs/sens.json","--summary","result is stable under the tested perturbation")
        self.call("stage","advance","--question","Q1") # INTERPRET, no Referee B

    def test_mixed_mode_requires_numeric_and_theory_evidence(self):
        self.init(); self.call("question","configure","--id","Q1","--claim-mode","mixed","--objective-mode","scalar","--mode-note","numeric optimum plus proof of structural property")
        self.enter_build()
        self.write("code/a.py","# ref a\n"); self.call("referee","register","--question","Q1","--role","a","--path","code/a.py")
        self.call("candidate","register","--question","Q1","--id","C1","--route","R1")
        self.write("runs/full.json", {"obj":2})
        self.call("result","record","--question","Q1","--candidate","C1","--objective","2","--sense","min","--feasible","true","--scale","full","--evidence","runs/full.json","--evaluator","a")
        self.call("candidate","promote","--question","Q1","--id","C1","--reason","validated route candidate")
        self.call("stage","advance","--question","Q1")
        self.write("runs/sens.json", {"passed":True}); self.call("evidence","record","--question","Q1","--kind","sensitivity","--file","runs/sens.json","--summary","numeric claim checked")
        rep=self.call("stage","advance","--question","Q1",expect=3)
        self.assertTrue(any("theory_check" in x for x in rep.get("missing",[])))
        self.write("runs/proof.md","proof reviewed")
        self.call("evidence","record","--question","Q1","--kind","theory_check","--file","runs/proof.md","--summary","theoretical claim checked")
        self.call("stage","advance","--question","Q1")

    def test_mixed_final_coverage_requires_both_manifests(self):
        run=self.write("runs/mixed.json", {"objective":5})
        proof=self.write("runs/proof.md", "checked proof")
        state={"questions":{"Q1":{"claim_mode":"mixed","objective_mode":"scalar","incumbent":"C1",
            "candidates":{"C1":{"results":[{"objective":5.0,"metrics":{},"sense":"min","feasible":True,"scale":"full","evaluator":"a","evidence":"runs/mixed.json","evidence_sha256":digest(run)}]}},
            "validation_evidence":[{"kind":"theory_check","file":"runs/proof.md","sha256":digest(proof)}]}}}
        self.write("manuscript/numeric-provenance.json", {"results":[{"question":"Q1","tier":"A","metric":"objective","raw_value":5.0,"run_sha256":digest(run)}]})
        self.write("manuscript/theoretical-evidence.json", {"claims":[{"question":"Q1","proof_file":"runs/proof.md","proof_sha256":digest(proof)}]})
        self.assertTrue(evidence_coverage(self.p,state)["passed"])
        self.write("manuscript/theoretical-evidence.json", {"claims":[]})
        self.assertFalse(evidence_coverage(self.p,state)["passed"])

    def test_route_change_after_accept_immediately_invalidates_route_approval(self):
        self.init(); self.prepare_route()
        self.call("route","add","--question","Q1","--id","R2","--name","new structural alternative","--structure-tag","structure-B")
        self.assertIsNone(rs.load(self.p)["questions"]["Q1"]["approvals"]["ACCEPT_ROUTE"])

    def test_vector_result_requires_stable_metric_definition(self):
        self.init(); self.call("question","configure","--id","Q1","--claim-mode","computational","--objective-mode","vector","--mode-note","Pareto")
        self.call("candidate","register","--question","Q1","--id","C1")
        self.write("runs/v1.json", {"ok":1}); self.write("runs/v2.json", {"ok":2})
        self.call("result","record","--question","Q1","--candidate","C1","--metric","cost=1","--metric","risk=2","--feasible","true","--evidence","runs/v1.json")
        self.call("result","record","--question","Q1","--candidate","C1","--metric","risk=2","--metric","cost=1","--feasible","true","--evidence","runs/v2.json",expect=2)

    # ---------- reviews / approval binding ----------
    def _minimal_write_state(self, theoretical=False):
        self.init()
        if theoretical:
            self.call("question","configure","--id","Q1","--claim-mode","theoretical","--mode-note","proof")
        data=rs.load(self.p);q=data["questions"]["Q1"];q["stage"]="WRITE"
        self.write("team_control/traceability-Q1.json", {"x":1});q["traceability"]={"file":"team_control/traceability-Q1.json","sha256":sha(self.p/"team_control/traceability-Q1.json"),"passed":True}
        self.write("qa/suitability-Q1.md", "A. x\nB. x\nC. x\nD. x\nE. x\nF. x\n"+"reason "*60);q["suitability"]={"file":"qa/suitability-Q1.md","sha256":sha(self.p/"qa/suitability-Q1.md")}
        self.write("runs/ev.json", {"passed":True});kind="theory_check" if theoretical else "constraint_check";q["validation_evidence"]=[{"kind":kind,"file":"runs/ev.json","sha256":sha(self.p/"runs/ev.json")}]
        q["approvals"]["FREEZE_RESULT"]={"snapshot":rs._approval_snapshot(q),"at":"test"}
        q["conclusions"]["supported"]=[{"statement":"supported"}]
        # Refresh snapshot after conclusion insertion.
        q["approvals"]["FREEZE_RESULT"]["snapshot"]=rs._approval_snapshot(q)
        rs.save(self.p,data)
        self.make_review_files()

    def test_readability_explicit_fail_blocks(self):
        self._minimal_write_state(); self.make_review_files(fail_readability=True)
        self.call("readability","record","--file","qa/readability.md",expect=2)

    def test_four_principles_fail_blocks(self):
        self._minimal_write_state(); self.call("readability","record","--file","qa/readability.md")
        self.make_review_files(fail_principles=True)
        self.call("principles","record","--file","qa/principles.md",expect=2)

    def test_four_principles_rejects_trailing_fail_after_four_passes(self):
        self._minimal_write_state(); self.call("readability","record","--file","qa/readability.md")
        self.make_review_files()
        with (self.p/"qa/principles.md").open("a",encoding="utf-8") as f:
            f.write("\n补充复核：判定：FAIL\n")
        self.call("principles","record","--file","qa/principles.md",expect=2)

    def test_paper_only_rollback_keeps_scientific_freeze(self):
        self._minimal_write_state()
        data=rs.load(self.p); data["questions"]["Q1"]["stage"]="DELIVER"; rs.save(self.p,data)
        self.call("stage","back","--question","Q1","--to","WRITE","--reason","revise manuscript layout")
        self.assertIsNotNone(rs.load(self.p)["questions"]["Q1"]["approvals"]["FREEZE_RESULT"])

    def test_manuscript_approval_binds_entire_source_tree(self):
        self._minimal_write_state(); self.write("manuscript/latex/section.tex","A")
        # Recreate reviews after adding section so their source-tree binding is current.
        self.make_review_files(); self.call("readability","record","--file","qa/readability.md")
        self.call("principles","record","--file","qa/principles.md")
        self.call("approve","--gate","APPROVE_MANUSCRIPT","--rationale","user approved this complete LaTeX source")
        self.write("manuscript/latex/section.tex","B")
        self.write("manuscript/official-checklist.json", {"verification_status":"unverifiable","search_attempted":True,"search_note":"checked current official channels","official_sources":[],"items":[]})
        rep=self.call("gate","check","--question","Q1","--to","DELIVER",expect=3)
        self.assertTrue(any("source tree changed" in x for x in rep.get("missing",[])))

    def test_principles_review_binds_validation_evidence(self):
        self._minimal_write_state(); self.call("readability","record","--file","qa/readability.md")
        self.call("principles","record","--file","qa/principles.md")
        self.write("runs/ev.json", {"passed":False})
        self.write("manuscript/official-checklist.json", {"verification_status":"unverifiable","search_attempted":True,"search_note":"checked","official_sources":[],"items":[]})
        rep=self.call("gate","check","--question","Q1","--to","DELIVER",expect=3)
        self.assertTrue(any("validation" in x or "evidence" in x for x in rep.get("missing",[])))

    def test_freeze_snapshot_survives_json_roundtrip(self):
        self._minimal_write_state()
        q=rs.load(self.p)["questions"]["Q1"]
        self.assertEqual(q["approvals"]["FREEZE_RESULT"]["snapshot"], rs._approval_snapshot(q))

    def test_whole_paper_review_and_approval_are_not_repeated_per_question(self):
        self.init(questions="Q1,Q2")
        data=rs.load(self.p)
        for qid in ("Q1","Q2"):
            q=data["questions"][qid]; q["stage"]="WRITE"
            self.write(f"team_control/traceability-{qid}.json", {"x":qid})
            q["traceability"]={"file":f"team_control/traceability-{qid}.json","sha256":sha(self.p/f"team_control/traceability-{qid}.json"),"passed":True}
            self.write(f"qa/suitability-{qid}.md", "A. x\nB. x\nC. x\nD. x\nE. x\nF. x\n"+"reason "*60)
            q["suitability"]={"file":f"qa/suitability-{qid}.md","sha256":sha(self.p/f"qa/suitability-{qid}.md")}
            self.write(f"runs/ev-{qid}.json", {"passed":True})
            q["validation_evidence"]=[{"kind":"sensitivity","file":f"runs/ev-{qid}.json","sha256":sha(self.p/f"runs/ev-{qid}.json")}]
            q["conclusions"]["supported"]=[{"statement":"supported"}]
            q["approvals"]["FREEZE_RESULT"]={"snapshot":rs._approval_snapshot(q),"at":"test"}
        rs.save(self.p,data)
        self.make_review_files()
        self.call("readability","record","--file","qa/readability.md")
        self.call("principles","record","--file","qa/principles.md")
        self.call("approve","--gate","APPROVE_MANUSCRIPT","--rationale","user approved the whole paper once")
        loaded=rs.load(self.p)
        self.assertIsNotNone(loaded["paper"]["approvals"]["APPROVE_MANUSCRIPT"])
        self.assertNotIn("APPROVE_MANUSCRIPT", loaded["questions"]["Q1"]["approvals"])
        self.assertNotIn("APPROVE_MANUSCRIPT", loaded["questions"]["Q2"]["approvals"])

    def test_non_scalar_project_back_uses_evidence_and_note_without_fake_objective(self):
        self.init(questions="Q1,Q2", depends="Q2:Q1")
        self.call("question","configure","--id","Q1","--claim-mode","computational","--objective-mode","vector","--mode-note","Pareto cost/risk")
        self.write("runs/project-back.md","qualitative/vector implication checked")
        rep=self.call("project-back","record","--from","Q2","--to","Q1","--evidence","runs/project-back.md","--note","improves risk without a scalar comparison")
        self.assertEqual(rep["comparison_mode"],"qualitative_or_vector")
        rec=rs.load(self.p)["questions"]["Q2"]["project_back"][-1]
        self.assertIsNone(rec["objective"])

    def test_empty_source_registry_is_valid_when_nothing_is_borrowed(self):
        paper=self.write("paper.pdf", b"paper", binary=True)
        self.write("registry.json", {"paper":"paper.pdf","paper_sha256":digest(paper),"sources":[],"claims":[]})
        self.assertTrue(source_report(self.p,"paper.pdf","registry.json")["passed"])

    def test_sensitivity_is_valid_problem_matched_evidence(self):
        self.assertIn("sensitivity", rs.PRIMARY_VALIDATION_KINDS)
        self.assertIn("robustness", rs.PRIMARY_VALIDATION_KINDS)
        self.assertIn("ablation", rs.PRIMARY_VALIDATION_KINDS)
        self.assertIn("mechanism_consistency", rs.PRIMARY_VALIDATION_KINDS)

    # ---------- evidence completeness ----------
    def test_numeric_headline_coverage_is_question_metric_and_run_bound(self):
        run=self.write("runs/final.json", {"objective":5.0}); run_sha=digest(run)
        state={"questions":{"Q1":{"claim_mode":"computational","objective_mode":"scalar","incumbent":"C1","candidates":{"C1":{"results":[{"objective":5.0,"sense":"min","feasible":True,"scale":"full","evaluator":"a","evidence":"runs/final.json","evidence_sha256":run_sha}]}}}}}
        self.write("manuscript/numeric-provenance.json", {"schema_version":3,"results":[{"question":"Q1","metric":"objective","tier":"A","raw_value":5.0,"run_sha256":run_sha}]})
        self.assertTrue(evidence_coverage(self.p,state)["passed"])
        self.write("manuscript/numeric-provenance.json", {"schema_version":3,"results":[{"question":"Q2","metric":"objective","tier":"A","raw_value":5.0,"run_sha256":run_sha}]})
        self.assertFalse(evidence_coverage(self.p,state)["passed"])
        self.write("manuscript/numeric-provenance.json", {"schema_version":3,"results":[{"question":"Q1","metric":"objective","tier":"A","raw_value":5.0,"run_sha256":"different-run"}]})
        self.assertFalse(evidence_coverage(self.p,state)["passed"])

    def test_vector_headline_coverage_requires_each_metric(self):
        run=self.write("runs/vector-final.json", {"cost":5.0,"risk":0.1}); run_sha=digest(run)
        state={"questions":{"Q1":{"claim_mode":"computational","objective_mode":"vector","incumbent":"C1","candidates":{"C1":{"results":[{"metrics":{"cost":5.0,"risk":0.1},"feasible":True,"scale":"full","evaluator":"a","evidence":"runs/vector-final.json","evidence_sha256":run_sha}]}}}}}
        self.write("manuscript/numeric-provenance.json", {"schema_version":3,"results":[{"question":"Q1","metric":"cost","tier":"A","raw_value":5.0,"run_sha256":run_sha}]})
        rep=evidence_coverage(self.p,state)
        self.assertFalse(rep["passed"]);self.assertIn("risk",rep["errors"][0])

    def test_theoretical_coverage_requires_each_theory_question(self):
        state={"questions":{"Q1":{"claim_mode":"theoretical"},"Q2":{"claim_mode":"theoretical"}}}
        self.write("manuscript/theoretical-evidence.json", {"claims":[{"question":"Q1"}]})
        rep=evidence_coverage(self.p,state)
        self.assertFalse(rep["passed"]);self.assertTrue(any("Q2" in e for e in rep["errors"]))

    def test_theoretical_report_requires_question_id(self):
        proof=self.write("proof.md","proof")
        self.write("manuscript/theoretical-evidence.json", {"claims":[{"statement":"T","kind":"theorem","location":"Sec 2","proof_file":"proof.md","proof_sha256":digest(proof)}]})
        self.assertFalse(theoretical_report(self.p)["passed"])

    def test_theoretical_final_evidence_must_match_current_theory_check(self):
        current=self.write("runs/current-proof.md","current proof and review")
        old=self.write("runs/old-proof.md","old proof")
        state={"questions":{"Q1":{"claim_mode":"theoretical","validation_evidence":[
            {"kind":"theory_check","file":"runs/current-proof.md","sha256":digest(current)}
        ]}}}
        self.write("manuscript/theoretical-evidence.json", {"claims":[
            {"question":"Q1","proof_file":"runs/old-proof.md","proof_sha256":digest(old)}
        ]})
        rep=evidence_coverage(self.p,state)
        self.assertFalse(rep["passed"]);self.assertTrue(any("current theory_check" in e for e in rep["errors"]))
        self.write("manuscript/theoretical-evidence.json", {"claims":[
            {"question":"Q1","proof_file":"runs/current-proof.md","proof_sha256":digest(current)}
        ]})
        self.assertTrue(evidence_coverage(self.p,state)["passed"])

    # ---------- official-format policy ----------
    def test_official_unverifiable_warns_but_does_not_block(self):
        self.write("paper.pdf",b"x",binary=True)
        self.write("check.json", {"verification_status":"unverifiable","search_attempted":True,"search_note":"current official material not yet available","official_sources":[],"items":[]})
        rep=official_report(self.p,"paper.pdf","check.json")
        self.assertTrue(rep["passed"]);self.assertTrue(rep["warnings"])

    def test_official_advisory_never_blocks(self):
        self.write("paper.pdf",b"x",binary=True)
        self.write("check.json", {"verification_status":"verified","search_attempted":True,"extraction_reviewed":True,"official_sources":[{"source":"https://official.example/notice","locator":"format"}],"items":[{"id":"A","strength":"advisory","rule":"recommended","source_locator":"p1","status":"warn","note":"not applied"}]})
        self.assertTrue(official_report(self.p,"paper.pdf","check.json")["passed"])

    def test_official_mandatory_failure_blocks(self):
        self.write("paper.pdf",b"x",binary=True)
        self.write("check.json", {"verification_status":"verified","search_attempted":True,"extraction_reviewed":True,"official_sources":[{"source":"https://official.example/notice","locator":"format"}],"items":[{"id":"M","strength":"mandatory","rule":"must","source_locator":"p1","status":"pending","note":"not done"}]})
        self.assertFalse(official_report(self.p,"paper.pdf","check.json")["passed"])

    # ---------- Overleaf / source integrity ----------
    def test_overleaf_package_keeps_main_byte_identical(self):
        main=self.write("manuscript/latex/main.tex","\\documentclass{article}\n")
        self.write("manuscript/latex/section.tex","hello")
        rep=build_overleaf(self.p,"manuscript/latex","main.tex","manuscript/overleaf-project.zip")
        self.assertTrue(rep["passed"])
        with zipfile.ZipFile(self.p/"manuscript/overleaf-project.zip") as z:
            self.assertEqual(z.read("main.tex"),main.read_bytes())

    def test_overleaf_output_cannot_live_inside_source_tree(self):
        self.write("manuscript/latex/main.tex","main")
        with self.assertRaises(ValueError):
            build_overleaf(self.p,"manuscript/latex","main.tex","manuscript/latex/overleaf-project.zip")

    def test_overleaf_package_rejects_parent_directory_dependencies(self):
        self.write("shared.tex","outside")
        self.write("manuscript/latex/main.tex","\\input{../../shared.tex}\n")
        with self.assertRaises(ValueError):
            build_overleaf(self.p,"manuscript/latex","main.tex","manuscript/overleaf-project.zip")

    def test_overleaf_package_rejects_external_graphicspath(self):
        self.write("manuscript/latex/main.tex","\\documentclass{article}\n\\graphicspath{{../figures/}}\n")
        with self.assertRaises(ValueError):
            build_overleaf(self.p,"manuscript/latex","main.tex","manuscript/overleaf-project.zip")

    def test_overleaf_package_ignores_os_metadata(self):
        self.write("manuscript/latex/main.tex","main")
        self.write("manuscript/latex/.DS_Store",b"junk",binary=True)
        rep=build_overleaf(self.p,"manuscript/latex","main.tex","manuscript/overleaf-project.zip")
        self.assertNotIn(".DS_Store",rep["members"])

    def test_source_tree_digest_changes_when_included_file_changes(self):
        self.write("manuscript/latex/main.tex","main");sec=self.write("manuscript/latex/section.tex","A")
        a=source_tree_digest(self.p/"manuscript/latex");sec.write_text("B")
        self.assertNotEqual(a,source_tree_digest(self.p/"manuscript/latex"))

    def test_overleaf_report_rejects_stale_auxiliary_source(self):
        self.write("manuscript/latex/main.tex","main");self.write("manuscript/latex/section.tex","A")
        build_overleaf(self.p,"manuscript/latex","main.tex","manuscript/overleaf-project.zip")
        self.write("proof.json", {"source_path":"manuscript/latex/main.tex"})
        self.assertTrue(overleaf_report(self.p,"proof.json")["passed"])
        self.write("manuscript/latex/section.tex","B")
        self.assertFalse(overleaf_report(self.p,"proof.json")["passed"])

    def test_overleaf_report_rejects_duplicate_member_names(self):
        main=self.write("manuscript/latex/main.tex","main")
        archive=self.p/"manuscript/overleaf-project.zip";archive.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("main.tex",main.read_bytes());z.writestr("main.tex",main.read_bytes())
        self.write("proof.json", {"source_path":"manuscript/latex/main.tex"})
        rep=overleaf_report(self.p,"proof.json")
        self.assertFalse(rep["passed"]);self.assertTrue(any("duplicate member" in e for e in rep["errors"]))

    def test_final_report_revalidation_rejects_any_bound_artifact_change(self):
        main=self.write("manuscript/latex/main.tex","main")
        paths={
            "paper":self.write("qa/final.pdf",b"pdf",binary=True),
            "proof":self.write("qa/proof.json",{}),
            "official_checklist":self.write("manuscript/official-checklist.json",{}),
            "source_registry":self.write("manuscript/source-registry.json",{}),
            "overleaf_zip":self.write("manuscript/overleaf-project.zip",b"zip",binary=True),
        }
        bindings={k:{"path":str(v.relative_to(self.p)),"sha256":digest(v)} for k,v in paths.items()}
        bindings["source"]={"path":"manuscript/latex/main.tex","sha256":digest(main)}
        bindings["source_tree_sha256"]=source_tree_digest(self.p/"manuscript/latex")
        payload={"passed":True,"scope":"final","bindings":bindings}
        fresh={"passed":True,"scope":"final","checks":{},"bindings":bindings}
        with patch("final_compliance_gate.report", return_value=fresh):
            self.assertEqual(rs._revalidate_final_report(self.p,payload),(True,""))
        paths["overleaf_zip"].write_bytes(b"changed")
        ok,reason=rs._revalidate_final_report(self.p,payload)
        self.assertFalse(ok);self.assertIn("changed",reason)

    def test_renderer_matches_overleaf_relative_path_semantics_and_disables_shell_escape(self):
        text=(SCRIPTS/"render_manuscript.py").read_text(encoding="utf-8")
        self.assertIn('source.name], source.parent)', text)
        self.assertIn('"-no-shell-escape"', text)

    def test_renderer_keeps_qa_outside_authoritative_source_tree(self):
        text=(SCRIPTS/"render_manuscript.py").read_text(encoding="utf-8")
        self.assertIn("output.is_relative_to(source.parent)", text)

    def test_project_back_promoted_must_be_reflected_in_destination_result(self):
        self.init(questions="Q1,Q2", depends="Q2:Q1")
        data=rs.load(self.p); q=data["questions"]["Q1"]
        q["candidates"]["C1"]={"id":"C1","route":None,"kind":None,"complexity":"low","status":"incumbent","results":[
            {"objective":10.0,"metrics":{},"sense":"min","feasible":True,"scale":"full","evaluator":"a","evidence":"runs/q1-old.json","evidence_sha256":"x","params":{}}
        ],"probes":[]}
        q["incumbent"]="C1"; rs.save(self.p,data)
        self.write("runs/back.json", {"candidate_objective":5})
        self.call("project-back","record","--from","Q2","--to","Q1","--objective","5","--sense","min","--evidence","runs/back.json")
        self.call("project-back","done","--from","Q2","--to","Q1","--outcome","promoted",expect=2)
        data=rs.load(self.p); data["questions"]["Q1"]["candidates"]["C1"]["results"].append(
            {"objective":4.0,"metrics":{},"sense":"min","feasible":True,"scale":"full","evaluator":"a","evidence":"runs/q1-new.json","evidence_sha256":"y","params":{}})
        rs.save(self.p,data)
        self.call("project-back","done","--from","Q2","--to","Q1","--outcome","promoted")

    def test_project_back_has_one_record_and_requires_explicit_outcome(self):
        self.init(questions="Q1,Q2")
        data=rs.load(self.p); data["questions"]["Q2"]["depends_on"]=["Q1"]; rs.save(self.p,data)
        self.write("runs/pb.json", {"candidate":"projection"})
        self.call("project-back","record","--from","Q2","--to","Q1","--objective","5","--evidence","runs/pb.json")
        data=rs.load(self.p)
        self.assertEqual(len(data["questions"]["Q2"]["project_back"]),1)
        self.assertNotIn("project_back_in",data["questions"]["Q1"])
        self.assertIsNone(data["questions"]["Q2"]["project_back"][0]["outcome"])
        self.call("project-back","done","--from","Q2","--to","Q1","--outcome","promoted")
        self.assertEqual(rs.load(self.p)["questions"]["Q2"]["project_back"][0]["outcome"],"promoted")

    # ---------- integrity / maintenance ----------
    def test_hmac_tamper_is_rejected_when_secret_configured(self):
        with patch.dict(os.environ,{"HUAWEI_CUP_STATE_SECRET":"secret"},clear=False):
            self.init()
            p=self.p/"team_control/run-state.json";d=json.loads(p.read_text());d["profile"]="full";p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):rs.load(self.p)

    def test_active_docs_do_not_reference_removed_stacks(self):
        forbidden=("submission-profile","question-gate","question_gate","autonomy.json","parity_gate","paper.docx","objective-mode multiobjective")
        files=[ROOT/"SKILL.md",*sorted((ROOT/"references").glob("*.md")),*sorted((ROOT/"rules").glob("*.md"))]
        text="\n".join(p.read_text(encoding="utf-8") for p in files if p.name!="CHANGELOG.md")
        for token in forbidden:self.assertNotIn(token,text)

    def test_removed_legacy_scripts_stay_removed(self):
        for name in ("question_gate.py","sign_autonomy.py","parity_gate.py","word_author.py","docx_audit.py","create_word_template.py","format_profile.py","restyle_word.py"):
            self.assertFalse((SCRIPTS/name).exists(),name)

    def test_only_one_authoritative_paper_template_path(self):
        self.assertTrue((ROOT/"templates/main.tex").is_file())
        self.assertFalse((ROOT/"templates/paper_q1.tex").exists())


    def test_done_question_rejects_scientific_mutation_until_rollback(self):
        self.init()
        data = rs.load(self.p); data["questions"]["Q1"]["stage"] = "DONE"; rs.save(self.p, data)
        self.write("evidence.txt", "checked")
        self.call("evidence", "record", "--question", "Q1", "--kind", "constraint_check",
                  "--file", "evidence.txt", "--summary", "x", expect=2)

    def test_question_topology_cannot_expand_after_writing_started(self):
        self.init()
        data = rs.load(self.p); data["questions"]["Q1"]["stage"] = "WRITE"; rs.save(self.p, data)
        self.call("question", "add", "--id", "Q2", "--depends-on", "Q1", expect=2)

    def test_suitability_is_build_exit_not_build_entry(self):
        self.init(); self.call("question","configure","--id","Q1","--claim-mode","theoretical","--mode-note","proof")
        self.prepare_route(theoretical=True)
        self.call("suitability","record","--question","Q1","--file","missing.md",expect=2)
        self.call("stage", "advance", "--question", "Q1")  # BUILD must not require A-F yet
        self.call("stage", "advance", "--question", "Q1", expect=3)  # VALIDATE does require it
        self.suitability()
        self.call("stage", "advance", "--question", "Q1")  # VALIDATE

    def test_suitability_binds_current_accepted_route(self):
        self.init(); self.prepare_route(); self.call("stage", "advance", "--question", "Q1")
        self.suitability()
        old = rs.load(self.p)["questions"]["Q1"]["suitability"]["route_fingerprint"]
        self.write("runs/route-Q1-evidence.txt", "new real evidence")
        self.assertNotEqual(old, rs._route_fingerprint(self.p, "Q1", rs.load(self.p)["questions"]["Q1"]))
        rep = self.call("gate", "check", "--question", "Q1", "--to", "VALIDATE", expect=3)
        self.assertTrue(any("Suitability is stale" in x for x in rep.get("missing", [])))

    def test_tier_a_provenance_does_not_duplicate_scientific_validation_gate(self):
        run = self.write("runs/value.json", {"value": 3.14159})
        self.write("manuscript/numeric-provenance.json", {
            "schema_version": 3,
            "results": [{
                "artifact": "headline", "tier": "A", "run_file": "runs/value.json",
                "run_sha256": digest(run), "field": "value", "raw_value": 3.14159,
                "display_value": 3.142, "rounding_rule": "round(3)",
                "manuscript_location": "Sec. 4", "question": "Q1", "metric": "objective"
            }]
        })
        from audit_core import numeric_report
        self.assertTrue(numeric_report(self.p, "manuscript/numeric-provenance.json")["passed"])

    def test_whole_paper_review_allows_other_questions_already_done_after_rollback(self):
        self.init(questions="Q1,Q2")
        data=rs.load(self.p); data["questions"]["Q1"]["stage"]="WRITE"; data["questions"]["Q2"]["stage"]="DONE"; rs.save(self.p,data)
        self.make_review_files()
        self.call("readability","record","--file","qa/readability.md")

    def test_dependency_freeze_basis_detects_upstream_change(self):
        self.init(questions="Q1,Q2", depends="Q2:Q1")
        data=rs.load(self.p)
        q1=data["questions"]["Q1"]; q2=data["questions"]["Q2"]
        q1["conclusions"]["supported"]=[{"statement":"old"}]
        q1["approvals"]["FREEZE_RESULT"]={"snapshot":rs._approval_snapshot(q1),"dependency_freezes":{}}
        q2["conclusions"]["supported"]=[{"statement":"downstream"}]
        q2["approvals"]["FREEZE_RESULT"]={"snapshot":rs._approval_snapshot(q2),"dependency_freezes":rs._dependency_freeze_basis(data,"Q2")}
        old=dict(q2["approvals"]["FREEZE_RESULT"]["dependency_freezes"])
        q1["conclusions"]["supported"].append({"statement":"changed"})
        self.assertNotEqual(old.get("Q1"), rs._freeze_token(q1))
        with self.assertRaises(ValueError):
            rs._dependency_freeze_basis(data,"Q2")

    def test_overleaf_keeps_legitimate_out_directory(self):
        self.write("manuscript/latex/main.tex", "\\documentclass{article}\n\\begin{document}x\\end{document}\n")
        self.write("manuscript/latex/out/data.csv", "x,y\n1,2\n")
        rep=build_overleaf(self.p,"manuscript/latex","main.tex","manuscript/overleaf-project.zip")
        self.assertIn("out/data.csv", rep["members"])


    # Reproductions from the 2026-09-13 audit: observable failures, not wording pins.
    def _audit_numeric_ledger(self, **changes):
        from audit_core import numeric_report
        run = self.write("runs/value.json", {"value": 1e-14})
        row = {"artifact": "error", "tier": "A", "run_file": "runs/value.json",
               "run_sha256": digest(run), "field": "value", "raw_value": 1e-14,
               "display_value": 1e-14, "rounding_rule": "asis", "manuscript_location": "Sec. 4"}
        row.update(changes)
        for key in [k for k, v in row.items() if v is None]:
            del row[key]
        self.write("ledger.json", {"schema_version": 3, "results": [row]})
        return numeric_report(self.p, "ledger.json")

    def test_audit_numeric_display_binding_required(self):
        for key in ("display_value", "rounding_rule"):
            with self.subTest(key=key):
                self.assertFalse(self._audit_numeric_ledger(**{key: None})["passed"])

    def test_audit_tiny_nonzero_cannot_be_displayed_as_exact_zero(self):
        self.assertFalse(self._audit_numeric_ledger(display_value=0)["passed"])
        self.assertTrue(self._audit_numeric_ledger(display_value=0, rounding_rule="round(3)")["passed"])

    def test_audit_nonfinite_or_boolean_display_tolerance_rejected(self):
        for changes in ({"display_value": True}, {"display_value": "Infinity"},
                        {"display_value": 999, "tolerance": "Infinity"}, {"tolerance": True}):
            with self.subTest(changes=changes):
                self.assertFalse(self._audit_numeric_ledger(**changes)["passed"])

    def _audit_theory_validate(self):
        self.init()
        self.call("question", "configure", "--id", "Q1", "--claim-mode", "theoretical", "--mode-note", "prove claim")
        self.enter_build(theoretical=True)
        self.call("stage", "advance", "--question", "Q1")

    def test_audit_refreshed_evidence_can_advance(self):
        self._audit_theory_validate()
        for revision in (1, 2):
            self.write("runs/check.json", {"passed": True, "revision": revision})
            self.call("evidence", "record", "--question", "Q1", "--kind", "theory_check",
                      "--file", "runs/check.json", "--summary", "review current proof")
        self.call("stage", "advance", "--question", "Q1")
        self.assertEqual(len(rs.load(self.p)["questions"]["Q1"]["validation_evidence"]), 1)

    def test_audit_failed_or_empty_validation_cannot_be_registered(self):
        self._audit_theory_validate()
        for payload in ({"passed": False, "errors": ["counterexample"]}, ""):
            self.write("runs/check.json", payload)
            self.call("evidence", "record", "--question", "Q1", "--kind", "theory_check",
                      "--file", "runs/check.json", "--summary", "review current proof", expect=2)

    def test_audit_existing_failed_validation_blocks_advancement(self):
        self._audit_theory_validate()
        f = self.write("runs/check.json", {"passed": False})
        data = rs.load(self.p)
        data["questions"]["Q1"]["validation_evidence"] = [
            {"kind": "theory_check", "file": "runs/check.json", "sha256": sha(f)}]
        rs.save(self.p, data)
        self.call("stage", "advance", "--question", "Q1", expect=3)

    def test_audit_missing_traceability_blocks_advancement(self):
        self.init(); self.trace()
        (self.p / "team_control/traceability-Q1.json").unlink()
        self.call("stage", "advance", "--question", "Q1", expect=3)

    def test_audit_abort_cannot_leave_rejected_incumbent_active(self):
        self.test_computational_interpret_does_not_require_referee_b()
        self.call("probe", "record", "--question", "Q1", "--candidate", "C1",
                  "--scale-desc", "small", "--runtime-s", "1", "--decision", "abort",
                  "--rationale", "candidate no longer usable", expect=2)
        self.assertEqual(rs.load(self.p)["questions"]["Q1"]["candidates"]["C1"]["status"], "incumbent")

    def test_audit_new_route_cannot_reuse_old_route_incumbent(self):
        self.test_computational_interpret_does_not_require_referee_b()
        self.call("stage", "back", "--question", "Q1", "--to", "FALSIFY", "--reason", "replace model")
        self.call("route", "add", "--question", "Q1", "--id", "R2", "--name", "new model", "--structure-tag", "structure-B")
        self.call("route", "status", "--question", "Q1", "--id", "R1", "--status", "kept")
        self.call("route", "status", "--question", "Q1", "--id", "R2", "--status", "main")
        self.call("approve", "--question", "Q1", "--gate", "ACCEPT_ROUTE", "--rationale", "user accepts new model")
        self.call("stage", "advance", "--question", "Q1")
        self.suitability()
        self.call("stage", "advance", "--question", "Q1", expect=3)

    def test_audit_render_manifest_has_portable_paths(self):
        from render_manuscript import proof_draft
        main = self.write("manuscript/latex/main.tex", "source")
        pdf = self.write("qa/render/main.pdf", b"pdf", binary=True)
        page = self.write("qa/render/page-1.png", b"png", binary=True)
        manifest = proof_draft(self.p, main, pdf, [page], 150)
        self.assertEqual(manifest["source_path"], "manuscript/latex/main.tex")
        self.assertEqual(manifest["rendered_path"], "qa/render/main.pdf")
        self.assertEqual(manifest["page_images"], ["qa/render/page-1.png"])

    def test_audit_bibtex_render_end_to_end(self):
        import subprocess
        from render_manuscript import locate
        if not all(locate(tool) for tool in ("xelatex", "pdftoppm", "bibtex")):
            self.skipTest("XeLaTeX, Poppler and BibTeX are required for bibliography integration")
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("pypdf is required to inspect the rendered bibliography")
        self.write("manuscript/latex/main.tex", r"""\documentclass{article}
\begin{document}
An auditable reference is given in \cite{knuth1984}.
\bibliographystyle{plain}
\bibliography{refs}
\end{document}
""")
        self.write("manuscript/latex/refs.bib", "@book{knuth1984,author={Donald Knuth},title={The TeXbook},publisher={Addison-Wesley},year={1984}}")
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "render_manuscript.py"),
            "--project", str(self.p), "--source", "manuscript/latex/main.tex", "--output-dir", "qa/render"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(self.p / "qa/render/main.pdf").pages)
        self.assertIn("TeXbook", pdf_text)
        self.assertIn("1984", pdf_text)
        self.assertNotIn("[?]", pdf_text)
        manifest = json.loads((self.p / "qa/render/render-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["bibliography_backend"], "bibtex")
        self.assertEqual(manifest["source_tree_sha256"], source_tree_digest(self.p / "manuscript/latex"))


if __name__ == "__main__":
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SkillRegression)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
