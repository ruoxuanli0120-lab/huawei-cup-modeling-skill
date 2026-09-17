# Changelog

## 2026-09-13 严重问题审计修复

- 数值 Tier A/B 强制声明显示值与舍入规则；拒绝非有限/布尔显示值和容差，修复微小非零值按 asis 显示为零仍通过的问题。
- 更新同 kind/同路径验证文件时替换当前绑定、保留事件历史，避免旧哈希永久阻塞；空证据和明确机器 FAIL 在登记及后续门检查中被拒绝。
- 题意追溯文件删除后不再放行；主路线更换后不能沿用旧路线 incumbent；禁止直接将 incumbent probe 标为 abort 而保留其主结果。
- 渲染 manifest 使用可移植项目路径，最终门和授权按解析后路径比较，兼容 Windows 分隔符。
- 补齐传统 BibTeX 与 biblatex/Biber 文献编译及后续引用解析，防止含 .bib 的正常论文卡在 undefined citation。
- 增加针对实际故障的回归测试；保留新版单一 LaTeX/Overleaf 流程与原有显式调用策略。

## Current simplification and consistency pass

- Keep four priorities: problem fit, method suitability, result credibility, clear explanation.
- Make `team_control/run-state.json` the only research and approval state.
- Separate computational scalar, vector, lexicographic, and theoretical questions without forcing scalarization or fake numeric evidence.
- Use full-scale Referee A results as computational headline values; diagnostic solver/small-scale values cannot replace them.
- Bind route approval, frozen results, manuscript approval, reviews, and submission authorization to the artifacts they actually approved.
- Infer final numeric/theoretical evidence needs directly from run-state; remove duplicate submission-profile state.
- Keep one authoritative LaTeX source and one Overleaf-editable source package; remove inactive Word/parity workflow.
- Apply only current-edition official mandatory format rules as hard gates; advisory rules warn and unspecified items are ignored.
- Reduce legacy tests and docs to the active workflow so removed mechanisms cannot silently return.
## Consistency cleanup
- Unified Referee B as risk-based optional validation rather than a universal hard gate.
- Bound final theoretical evidence to the current frozen `theory_check` artifact.
- Clarified that manuscript approval covers the complete Overleaf/LaTeX source tree, not only `main.tex`.
- Removed stale kill-evidence metadata when a route is no longer killed.
- Aligned numeric-writing guidance with risk-tiered provenance: consequential/headline quantitative claims are provenance-bound; ordinary labels/constants are not forced into a ledger.


## Final contradiction cleanup
- Keep Method Suitability inside BUILD and require it before VALIDATE, consistently across code and templates.
- Reject cyclic or late-mutated question dependencies.
- Accept problem-matched validation such as perturbation, independent evaluation, or extreme-case checks without forcing a universal second implementation.
- Require a claimed promoted backward projection to be reflected in the destination's current validated result.
- Preserve scientific freezes on paper-only rollback; reopening only DELIVER invalidates only submission authorization.
- Keep route, result, whole-paper review, manuscript approval, final compliance, and Overleaf source bindings freshness-checked.

## Final coherence pass
- Make Method Suitability a BUILD exit check bound to the accepted route.
- Freeze dependent questions against current upstream freezes so upstream changes cannot silently leave downstream paper results stale.
- Allow whole-paper review/approval to be repeated after a partial rollback even when other questions are already at DELIVER/DONE.
- Keep current-edition format checking in final compliance instead of duplicating it before DELIVER.
- Package the complete LaTeX source tree without guessing that user directories named build/out/qa are disposable.
