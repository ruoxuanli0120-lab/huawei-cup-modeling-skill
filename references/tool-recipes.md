# 常用命令

路径相对用户项目。竞赛运行只维护一个 LaTeX 稿源：`manuscript/latex/main.tex`。

## 开工与状态

```bash
python scripts/run_state.py --project . init --profile full --questions Q1,Q2 --depends Q2:Q1
python scripts/run_state.py --project . question configure --id Q1 --claim-mode computational --objective-mode scalar
python scripts/run_state.py --project . trace check --question Q1 --file team_control/traceability-Q1.json
python scripts/run_state.py --project . stage advance --question Q1
python scripts/run_state.py --project . metrics show --question Q1
python scripts/run_state.py --project . report
```

完整子命令用 `python scripts/run_state.py --help` 查看。

## 多指标 / 理论题

```bash
python scripts/run_state.py --project . question configure --id Q2 --claim-mode computational --objective-mode vector --mode-note "cost/risk Pareto trade-off"
python scripts/run_state.py --project . result record --question Q2 --candidate C2 --metric cost=10 --metric risk=0.08 --feasible true --scale full --evidence runs/c2.json --evaluator a

python scripts/run_state.py --project . question configure --id Q3 --claim-mode theoretical --mode-note "prove existence and characterize equality cases"
# 同一小问若既有数值结论又有必须证明的理论结论，用 mixed；只多要求 theory_check
python scripts/run_state.py --project . question configure --id Q4 --claim-mode mixed --objective-mode scalar --mode-note "numeric result + proof obligation"
python scripts/run_state.py --project . evidence record --question Q3 --kind theory_check --file runs/q3-proof-review.md --summary "boundary cases and proof steps checked"
```

理论题不注册 numeric result/incumbent/Referee A/B。Method Suitability A–F 在进入 BUILD 后记录，并作为进入 VALIDATE 的出口检查。

## 计算题权威结果

```bash
python scripts/run_state.py --project . referee register --question Q1 --role a --path code/referee_a.py
python scripts/run_state.py --project . result record --question Q1 --candidate C1 --objective 12.3 --sense min --feasible true --scale full --evidence runs/c1.json --evaluator a
python scripts/run_state.py --project . candidate promote --question Q1 --id C1 --reason "best validated candidate on the approved route"
python scripts/run_state.py --project . evidence record --question Q1 --kind baseline_comparison --file runs/baseline_check.json --summary "beats baseline under the same evaluator"
# 可选：高风险结论需要独立复核时再注册 Referee B
python scripts/run_state.py --project . referee register --question Q1 --role b --path code/referee_b.py --independence independent --independence-note "independent implementation"
```

## 全篇写作审查与批准

所有小问到 WRITE 后，全篇各做一次审查和批准，不逐问重复同一份论文：

```bash
python scripts/run_state.py --project . readability record --file qa/readability.md
python scripts/run_state.py --project . principles record --file qa/core-principles.md
python scripts/run_state.py --project . approve --gate APPROVE_MANUSCRIPT --rationale "user approved the current whole manuscript"
```

所有小问到 DELIVER、final compliance PASS 后，只做一次提交授权：

```bash
python scripts/run_state.py --project . approve --gate AUTHORIZE_SUBMISSION --rationale "user authorized the current final package"
```

## 论文、PDF 与 Overleaf

```bash
python scripts/environment_probe.py --output qa/environment.json --require-xelatex
python scripts/render_manuscript.py --project . --source manuscript/latex/main.tex --output-dir qa/final-render
python scripts/package_overleaf.py --project . --source-dir manuscript/latex --main main.tex --output manuscript/overleaf-project.zip
python scripts/final_compliance_gate.py --project . --paper qa/final-render/main.pdf --format-proof qa/final-render/render-manifest.json --tex manuscript/latex/main.tex --scope final
```

`render_manuscript.py` 生成 proof 草稿；检查全部最新页图后，把 manifest 的视觉项逐项改为 `pass` 并清空 `defects`，再跑 final gate。编译成功不等于视觉终审通过。

WRITE/DELIVER 自动检索当届官方格式：mandatory 才阻断，advisory 只 warning，未说明项不设规则；当届材料无法核验时标记待确认，不假装已核验。

## 维护 Skill

```bash
python scripts/regression_tests.py
python scripts/modeling_behavior_evals.py validate
python scripts/modeling_behavior_evals.py self-test
python scripts/validate_skill.py
python scripts/package_skill.py --output /mnt/data/skill.zip --verify
```
