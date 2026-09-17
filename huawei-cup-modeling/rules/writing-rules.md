# 竞赛论文表达规则

> **写作分配原则**：建模过程要想得细，论文只写**最关键的部分**。论文只需**准确、清晰、完整**——避免教科书式算法介绍与模型罗列，不为写得详细而挤占建模和验证的推理资源。把模型/方法的**合适性**讲清即可；用 [评委六问](../templates/readability-review.md) 检查可读性，不堆算法细节。

## Abstract: five beats

Prefer a concise abstract that lets the judge understand the problem, model, method, result and validation quickly. Abstract length/position/keywords become hard format requirements only when the current official rules explicitly require them or the user explicitly asks for them; official recommendations are warnings only. Write in this order:

1. background and concrete problem;
2. model and assumptions;
3. method/algorithm;
4. key results：计算题给关键数字、单位与尺度；理论题给核心命题/构造与成立条件；
5. validation and the main contribution/insight; only claim innovation when it is genuine and evidenced.

Do not open with internal workflow labels such as “audit—model repair”; explain the problem and then mention the insight. Every numerical claim must resolve to its real run/source. Headline or consequential numbers need the current problem-matched validation recorded in run-state; numeric provenance only binds raw→display→manuscript and does not create a second validation policy.

## Argument Chain（论证链）

论文不是把模型和结果罗列出来，而是用一条**可追溯的论证链**说服评委。每个实质性主张都是一条链，链上任何一环缺失就显式标“待验证”，不得用措辞掩盖：

```text
原题要求 → 问题表示/数学本质 → 建模决策（选它的依据 + 淘汰其它路线的理由 + 复杂度正当性）
→ 模型/公式 → 求解或证明 → 真实结果/证明 → 题型匹配验证 → 结果解释 → 结论边界
```

硬规则：
- **无孤儿结论**：任何结论都必须能回溯到真实运行输出或绑定证明；追不到的，删掉或降级为“推测/待验证”。
- **建模决策要写成论证**，不是“我们用了 X 算法”：说明为什么当前**表示/模型**契合题目结构；只有当替代模型的比较有助于说服评委时，才简要说明主要替代为何不如当前方案。回扣“更好的表示 > 更高级的算法”。
- **关键定量结论绑定台账**：支撑结论、比较或决策的 headline/关键数字要能在 numeric provenance 台账里按 `manuscript_location` 找到对应的 raw→display→run 绑定；题面给定常数、编号、普通说明数字不强迫入台账（见 [../templates/numeric-provenance.json](../templates/numeric-provenance.json)）。理论型主张则绑定 theoretical-evidence 的 proof 定位。
- **主指标只从单一事实源取值**：incumbent 的 objective/feasibility/bounds/gap 一律引自 `run_state.py metrics show`（或它生成的派生报告），不手抄旧稿；WRITE 前与打包前跑 `metrics scan`，superseded 候选的旧数字残留即 FAIL。
- **措辞与证据强度匹配**：固定 portfolio 中挑出的参数只能写 “best in the fixed/tested portfolio”，不写 “optimal parameter”（除非绑定了最优性证明，见 run-state `param close --claim`）；启发式解写“较好的可行解/在测试组合中最优”，不写“理论最优/全局最优”；post-hoc 扩大过搜索边界的实验必须如实说明。
- **单一 LaTeX 事实源**：WRITE/DELIVER 只维护一个以 `main.tex` 为入口的 LaTeX 源码树；PDF 与 Overleaf ZIP 都来自这棵树，避免两个稿件版本漂移。
- **主线服从题意**：有真实依赖的小问按 Question Dependency Graph 保持符号、接口和逻辑连续；真正独立的小问允许使用不同模型，不为了“统一故事”强行套同一模型家族。
- **结论边界显式**：写清支持什么、不支持什么、适用范围；启发式不写全局最优，关联不写因果，有限实例不写定理，拟合不写泛化。
- 论证链是 WRITE 阶段的自查工具；最终应与评委六问和四原则审查结论一致。

## 评委六问（WRITE 出口闸）

论文不是研究日志，也不是代码说明书。WRITE 完成的判据是：一位**只读摘要、模型建立、求解方法、结果、验证**五部分的独立 reviewer，能快速回答下面六问（记录模板 [../templates/readability-review.md](../templates/readability-review.md)，登记 `run_state.py readability record`；任一问答不上 → WRITE 不 PASS）：

1. **为什么这样建？**——题目中的什么对象/关系/约束结构促使这样的数学抽象（不是“建立了XX模型”，而是“因为题目具有…结构，所以这样定义变量/约束/目标”）；
2. **模型是什么？**——变量、约束、目标集中、自包含、符号有定义；
3. **为什么这样求？**——模型真正难在哪，方法利用了模型的哪个结构；不是算法名词堆砌或代码流程说明；
4. **结果怎么样？**——突出真正回答题目的关键结果：计算题给核心指标、baseline、约束、误差/gap/敏感性；理论题给核心命题、构造、条件与边界；不是大量无重点数字或空泛结论；
5. **为什么可信？**——验证证据紧挨核心结果：“与谁比、提高多少、误差多少、约束是否满足、对参数变化是否稳定”；不是“实验表明方法有效”；
6. **结果说明什么？**——数字翻译回题目语言：这个值意味着什么、为什么出现、对实际问题有什么启示；不停在“目标函数值为 75102”。

内部工程（状态机、rollback 次数、candidate registry、AI 工作流程）**不进论文主体**。终审用 [评委六问](../templates/readability-review.md) + [四原则终稿审计](../templates/core-principles-review.md) 即可，不再维护重复 checklist。

## 四原则终稿闭环（不增加论文篇幅，只增加终审质量）

在 WRITE 末尾、进入 DELIVER 前，用 [../templates/core-principles-review.md](../templates/core-principles-review.md) 做一次短审计并 `principles record`。目的不是再写一套研究日志，而是检查前面四类高价值工作是否真正进入了终稿：

- **建模贴题**：原题对象/关系/约束/目标能追到当前模型元素，论文能定位“为什么这样建”；
- **方法合适**：Method Suitability A–F 仍对应当前方法，论文能定位“为什么这样求”，不是算法名词堆砌；
- **结果可信**：核心结论旁边有当前、未被篡改的题型匹配验证证据，数值来自当前 incumbent/provenance，结论不过界；
- **表达清楚**：独立 reviewer 的六问能够从终稿快速回答，关键结果有单位/尺度/对比并翻译回题目语言。

`principles record` 只做结构和文件 freshness 检查，不自动宣称科学质量 PASS；四项内容是否真正有说服力仍由 reviewer 判断。

## Judge-preview material

For a multi-question paper include a compact table mapping `question requirement → answer/model → key result → evidence location`. Add a flow diagram only if dependencies benefit from it. These aid retrieval, not a guaranteed review time or substitute for derivation.

## Layered mathematical writing

When the conclusion depends on a theorem or proposition, provide its statement, assumptions, proof idea and consequence in the body; ordinary statistical, predictive or simulation results do not need artificial theorem packaging. Move long algebra, exhaustive cases and full code to the appendix/support package while preserving a reader-checkable logical bridge. Translate formal results into the problem's actual domain meaning when that adds understanding.

## Figure/table readability

图表服务于论证：编号清楚、正文能找到、变量/单位/图例完整、关键结论可读、外部图有来源。图注位置、表格线型、字号、颜色等只有当届官方明确 mandatory 或用户明确要求时才作为格式门；官方建议只提醒，未说明项只要求整篇一致、清楚、不遮挡。

## Formula, theorem and reference rules

重要公式应便于正文引用，符号定义完整；定理性结论给出假设与证明依据。参考文献格式仅在当届官方明确 mandatory 或用户明确要求时设硬门；官方建议只提醒。未明确具体样式时，只要求来源真实、正文引用与文献条目可对应、整篇一致。
