---
name: huawei-cup-modeling
description: "华为杯数学建模专家系统。用于完整赛题求解、建模路线选择、求解验证与高水平 LaTeX 论文交付：先从题目对象/关系/约束/目标建立贴题模型，再选择适合模型的方法，主动证伪并用可追溯证据验证结果，最后形成清楚有说服力的论文。格式只在 WRITE/DELIVER 自动核对当届官方明确要求：mandatory 才阻断，advisory 只提醒，未说明项不加限制。"
---

# 华为杯数学建模专家系统

## 四个最高原则

所有流程只服务四件事，发生冲突时按此判断是否保留机制：

1. **建模贴题**：模型必须对应题目的对象、关系、约束、目标与信息结构；禁止先选算法再套题。
2. **方法合适**：方法由数学模型决定；优先最简单可靠且能有效解决模型的方法，复杂方法必须有明确必要性。
3. **结果可信**：结论必须有题型匹配的证据——误差、基线/精确解/下界对比、约束检查、敏感性/稳健性、独立复核或理论证明；程序跑通不等于模型正确。
4. **表达清楚**：评委应能快速回答“为什么这样建、模型是什么、为什么这样求、结果怎么样、为什么可信、结果说明什么”。

不承诺奖项；目标是提高模型合理性、证据质量和论文说服力，而不是堆流程或格式。

## 入口

- **咨询/局部改写**：直接回答或局部修改，不启动整套状态机。
- **完整求解**：先运行 `scripts/run_state.py --project . init --profile full|fast --questions Q1,...`，然后逐问按 9 个工作阶段执行，完成后进入 `DONE` 终态。
- **维护本 Skill**：修改后运行 `scripts/regression_tests.py`、`scripts/validate_skill.py`，最后用 `scripts/package_skill.py` 打包。

`team_control/run-state.json` 是唯一机器可读研究状态。不要另建第二套审批状态。主指标从 `metrics show` 读取；候选、证据或论文改变后，相关审批必须失效并重新确认。

## 问题模式

在 UNDERSTAND 阶段、创建路线/候选前用 `question configure` 明确每问：

- `claim_mode=computational`：需要真实计算结果；`objective_mode=scalar|vector|lexicographic`。
- `claim_mode=theoretical`：不强迫代码、数值 objective、incumbent 或 Referee A/B；用证明、反例、边界和 `theory_check` 证据验证。
- `claim_mode=mixed`：同一小问同时有数值结论与必须证明的理论结论；只比 computational 多要求当前 `theory_check`，不另建一套流程。
- 多目标不自动压成单指标。`vector` 保存 Pareto/指标向量，`lexicographic` 表示题意给出明确优先级；两者都要用 `--mode-note` 写清指标语义或选择规则。

## 9 阶段

| 阶段 | 做什么 | 关键出口 |
|---|---|---|
| **UNDERSTAND** | 读懂对象、关系、变量、约束、目标、信息结构、小问依赖，形成模型雏形 | [Problem Insight](references/problem-intelligence.md) + [traceability](templates/traceability.json) 通过 |
| **IDEATE** | 构思结构不同的建模路线；目标 FULL 4–6、FAST 2，但若更多路线只是凑数，不强制增加 | 至少 1 条可辩护路线；结构等价路线合并 |
| **SELECT** | 比较路线，确定 1 主线 + 至多 1 挑战者 | 主线明确，淘汰有理由/证据 |
| **FALSIFY** | ARCHITECT / SKEPTIC / REVIEWER 三个认知 Pass，主动找反例、遗漏条件和更简单替代 | `route-Qn.json` 三 Pass 有不同发现/修改依据；用户 `ACCEPT_ROUTE` 绑定当前路线+证据 |
| **BUILD** | 方法由模型决定；做 Method Suitability A–F；计算题建 baseline、Referee A、候选与必要 probe；理论题建立证明/构造框架 | 计算题有可行候选；理论题有可审查证明框架；复杂方法有必要性 |
| **VALIDATE** | 按题型验证模型与方法 | 计算题：full-scale Referee A headline + 题型匹配的硬证据，必要时再用 Referee B 独立复核；理论题：至少 1 个 `theory_check` |
| **INTERPRET** | 把结果翻译回题目语言并限定结论边界 | `interpret record`；用户 `FREEZE_RESULT` 绑定当前结果、证据和结论 |
| **WRITE** | 只写最有说服力的论证链；不把内部状态机写进论文 | `main.tex`；评委六问和四原则终审全部 PASS；用户 `APPROVE_MANUSCRIPT` 绑定当前 LaTeX 源码树 |
| **DELIVER** | 编译 PDF、逐页 QA、查当届官方明确格式要求、打包 Overleaf | final compliance PASS；用户 `AUTHORIZE_SUBMISSION` 绑定当前 final report；再进 DONE |

阶段只能一步一步前进，不能跨阶段跳过审批或证据。

## 路线与方法纪律

- 先 `问题结构 → 数学抽象 → 数学模型 → 求解方法`，禁止 algorithm-first。
- 路线数量是探索目标，不是论文质量指标；**不为凑 4 条制造同模型不同算法的假路线**。
- Method Suitability 用 [A–F 模板](templates/method-suitability.md)；计算、理论两类都要回答，但按题型解释，不强迫理论题谈数值求解器。
- 同一 candidate 的 scalar objective 必须保持同一 `sense`；改变目标定义就注册新 candidate。
- 论文 headline 数值只允许来自**当前 incumbent 的 full-scale Referee A 结果**。small-scale/solver/internal 值只能作诊断，不得抢占最终主结果。
- `vector` / `lexicographic` 不由 `best_result()` 发明标量权重；论文必须说明题目给出的优先级、字典序或 Pareto 选择依据。

## 验证与证据

- 计算性结论：用 [numeric provenance](templates/numeric-provenance.json) 绑定真实运行、显示值和稿件位置；关键结论做独立复核。
- 理论性结论：用 [theoretical evidence](templates/theoretical-evidence.json) 绑定证明/推导/反例文件；有限实验不能冒充定理。
- 一篇论文若同时含计算问和理论问，final gate 直接从 run-state 自动要求两类证据；不要维护第二份“论文类型”配置。
- 证据、incumbent、结论、路线或 LaTeX 源码树改动后，旧的 downstream approval/review 不再有效。
- [四原则终稿审计](templates/core-principles-review.md) 与 [评委六问](templates/readability-review.md) 必须显式 PASS；任何 FAIL 都阻断交付。

## 论文与格式

正式稿只有一个权威 LaTeX 项目：`manuscript/latex/`，入口固定为 `main.tex`；章节、图片、`.bib` 等子文件都属于同一源码树。

- 论文结构围绕“题目结构 → 建模理由 → 数学表达 → 求解方法 → 验证证据 → 题目结论”，不要写 route tournament、rollback、registry、gate 等内部工程术语。
- WRITE/DELIVER 自动查**当届**官方通知/模板；只把明确“必须/不得/限定”的要求设为 hard gate；“建议/原则上/推荐”仅 warning；官方未说明或含糊的字号、页边距、封面、匿名、摘要页数、参考文献样式等不自行新增限制。
- 当届官方材料暂不可核验时，记录“格式待确认”，继续成稿，不伪称已核验。
- 用 `render_manuscript.py` 编译并生成全部页图；终稿必须检查最新 PDF 的全量页图。
- 用 `package_overleaf.py` 原样打包同一 `manuscript/latex/` 源码树；ZIP 中所有归档文件都必须与当前源码树一致，`main.tex` 逐字节不改写，可直接上传 Overleaf 后继续编辑。

详细论文流程见 [paper-production](references/paper-production.md)，当届格式规则见 [official checklist](rules/official-clause-checklist.md)。

## 用户审批

默认 supervised。用户说“继续”只表示继续当前阶段，不自动等于以下批准：

`ACCEPT_ROUTE → FREEZE_RESULT → APPROVE_MANUSCRIPT → AUTHORIZE_SUBMISSION`

四个批准分别绑定当前路线证据、结果/验证快照、LaTeX 源码树、final-compliance report。可选 `HUAWEI_CUP_STATE_SECRET` 只用于 run-state HMAC 完整性；不设密钥仍可正常 supervised 使用。

## 渐进加载

- UNDERSTAND–FALSIFY：读 [问题智能](references/problem-intelligence.md)、[构思](references/model-ideation.md)、[路线证伪](references/route-iteration.md)、[建模规则](rules/modeling-rules.md)，不提前加载排版工程。
- BUILD–INTERPRET：再读 [题型 playbook](references/model-type-playbooks.md)、[科研证据协议](references/research-evidence-protocol.md)、[推导与实现审计](references/proof-and-implementation-audit.md)、数值/理论证据模板。
- WRITE–DELIVER：最后才读 [paper-production](references/paper-production.md)、[writing rules](rules/writing-rules.md)、[官方格式](rules/official-clause-checklist.md) 和终稿审查模板。

工具命令见 [tool-recipes](references/tool-recipes.md)，状态语义见 [run-state](references/run-state.md)。
