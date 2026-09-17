# run-state：唯一研究状态

`team_control/run-state.json` 是唯一机器可读研究/审批状态，记录阶段、题目模式、路线、候选、权威结果、验证证据、结论和四个用户批准。

## 题目模式

```bash
python scripts/run_state.py --project . question configure --id Q1 --claim-mode computational --objective-mode scalar
python scripts/run_state.py --project . question configure --id Q2 --claim-mode computational --objective-mode vector --mode-note "cost/risk form a Pareto trade-off; no fixed weights in the problem"
python scripts/run_state.py --project . question configure --id Q3 --claim-mode computational --objective-mode lexicographic --mode-note "feasibility first, then cost, then variance"
python scripts/run_state.py --project . question configure --id Q4 --claim-mode theoretical --mode-note "primary deliverable is a proof/construction"
python scripts/run_state.py --project . question configure --id Q5 --claim-mode mixed --objective-mode scalar --mode-note "report a numerical optimum and prove the stated structural property"
```

- `scalar`：单一标量目标；同一 candidate 内保持同一目标定义和 `min|max`。
- `vector`：保存多指标向量；状态机不自动标量化，显式 promote 表示已经按题意/Pareto 逻辑选择。
- `lexicographic`：保存多指标向量；`mode_note` 写明优先级，显式 promote 表示按该顺序选择。
- `theoretical`：自动使用 `objective_mode=none`，不注册 numeric result/incumbent/Referee A/B。

题目模式与小问依赖图只在 UNDERSTAND、路线/候选尚未创建时确定；依赖图必须无环，避免中途改任务定义。

## 阶段与批准

阶段固定：

`UNDERSTAND → IDEATE → SELECT → FALSIFY → BUILD → VALIDATE → INTERPRET → WRITE → DELIVER → DONE`

`stage advance` 一次只前进一级。四个批准只允许在对应阶段记录：

| 阶段 | 批准 | 绑定内容 |
|---|---|---|
| FALSIFY | `ACCEPT_ROUTE` | 当前 main route + 三视角证伪记录/证据指纹 |
| INTERPRET | `FREEZE_RESULT` | 当前题目模式、权威结果/理论证据、验证证据、结论 |
| WRITE | `APPROVE_MANUSCRIPT`（全篇一次） | 当前完整 LaTeX 源目录 + 全篇 readability/four-principles 审查 hash |
| DELIVER | `AUTHORIZE_SUBMISSION`（全篇一次） | 当前 PASS 的 final-compliance report 与其源码 binding |

用户说“继续”只记录 `CONTINUE_STAGE`，不等于批准。

## 路线

FULL 以 4–6 条结构不同路线为探索目标，FAST 以 2 条为目标；机器只硬要求至少 1 条可辩护路线并拒绝重复 `structure_tag`。若更多路线只是同一模型换算法，不应凑数。

`ACCEPT_ROUTE` 前必须有有效的 `team_control/route-Qn.json` 三视角证伪记录；三个视角可共享同一真实证据文件。主路线、路线定义或证伪证据变化后旧批准失效。

## 权威结果与验证

计算题可记录 small/full、solver/Referee A 等结果，但论文 headline 固定优先使用 `evaluator=a + scale=full`。其他结果只能作 provisional/诊断。

- `scalar`：在最高权威层内按 `min|max` 比较。
- `vector/lexicographic`：不发明 scalar score；使用当前显式 promote 的 candidate 的最新权威向量。
- `theoretical`：没有 numeric incumbent；冻结证明证据与结论。

计算题进入 INTERPRET 前需要：full-scale Referee A headline + 至少一种题型匹配验证证据。FULL 若只有一种证据会提示是否需要补第二种，但不硬卡；Referee B 仅在独立复算确有价值时使用，不作为所有题的通用硬门。理论题至少需要一个 hash-bound `theory_check`；mixed 小问同时满足计算题证据和 `theory_check`。终稿 theoretical-evidence 至少一条相关主张必须绑定当前 proof/theory evidence，避免论文引用另一份未冻结证明。

证据文件、Referee 实现、incumbent、结论或题目 traceability 改变后，相关 downstream 审批/审查失效。若题目声明依赖上游小问，`FREEZE_RESULT` 还会记录上游冻结指纹；上游结果变化后，下游旧冻结不能直接进入写作/提交。

同一验证文件更新后，重新执行相同 `kind + file` 的 `evidence record` 会替换当前绑定，旧记录留在事件历史中；同文件用于多个 kind 时须分别重新核验和登记。空文件或 JSON 明确标为 `passed: false` 的报告不能作为已通过验证。更换主路线后，必须评价并晋升属于新路线的候选；旧路线的 incumbent 不满足 BUILD 出口。

## 多问 backward projection

依赖图上的下游问题进入 VALIDATE 后，上游问题在 WRITE 前要检查反向影响：

- 上游为 scalar computational：可自动比较投影 objective。
- 上游为 vector/lexicographic/theoretical：提供证据文件 + 简短 note，按题意判断影响，不制造无意义标量。

## WRITE / DELIVER / DONE

- BUILD 内完成并记录绑定当前已接受路线的 Method Suitability A–F；进入 VALIDATE 前检查。
- WRITE 前必须有当前 `FREEZE_RESULT`；依赖题还必须与当前上游冻结一致。
- 所有小问都至少到 WRITE 后，只做一份全篇 readability review 和一份全篇 four-principles review；两者必须显式 PASS，并绑定完整 LaTeX 源目录，稿件一改即 stale。这样某一小问回滚重写时，不会因为其他小问已到 DELIVER/DONE 而卡死全篇复审。
- `APPROVE_MANUSCRIPT` 全篇只批准一次，绑定当前稿件和两份审查。
- 所有小问都至少到 DELIVER 后，`AUTHORIZE_SUBMISSION` 全篇只授权一次，只能绑定当前 PASS/final 的 final-compliance report，且该报告必须绑定当前完整 LaTeX 源码树。
- DONE 会重新验证授权报告与当前源码，不能只靠一个历史“已批准”状态过关。

## 完整性

可选设置 `HUAWEI_CUP_STATE_SECRET` 对 run-state 做 HMAC。未设置时为 unsigned supervised；设置后签名缺失或篡改会 fail-closed。
