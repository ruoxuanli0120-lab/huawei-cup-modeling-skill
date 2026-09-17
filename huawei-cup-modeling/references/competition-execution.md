# 比赛执行中的质量与效率

## 前置高风险检查

开工先按 9 阶段工作流走 UNDERSTAND → IDEATE → SELECT → FALSIFY（见 SKILL.md）：先完成 [Problem Insight Map](../templates/problem-audit.md)（方法见 [problem-intelligence.md](problem-intelligence.md)），再用 [model-ideation.md](model-ideation.md) 构思并竞争路线，然后才进入本文件的执行纪律。开工先核实题面、数据完整性和评价口径，并用小样本试通数值工具链。排版/状态配置可并行准备，不阻断题意理解和初步研究。先建可复现基线，再尝试复杂路线；每处复杂度都要修复一个已观测到的基线失效模式。

每问维护要求到证据的对应表：原题小问/要求、实现位置、验收指标、实际结果、未解决项。各问约束独立登记，不把上一问约束自动带入下一问。零解审计是模型检查，不是用投机解替代工程任务。

## 适配问题类型

给每个小问标主/辅助类型，基线、核心 Gate 和失败修法的唯一题型出处是 [model-type-playbooks.md](model-type-playbooks.md)，经验按其链接加载。统计推断不同于预测，聚类不同于分类，连续空间不同于路径，因果不同于关联；不要用旧的总表覆盖这些分支。

不强求每问套同一结构。灵敏度只分析会改变结论的参数；不适用时说明，不能制造无意义图表。

## 候选竞争与结论闭环

路线的生成与淘汰统一走 [model-ideation.md](model-ideation.md)：先按 Problem Insight Map 的表示备选构思 **4–6 条结构不同**的路线（换库/换超参/换求解器不算新路线，RF/XGBoost/LightGBM 属同一条），用简洁的题目契合/可验证性/信息可行性/成本风险/区分证据比较收敛到 **1 主线 + ≤1 挑战者**。评分表只在确有帮助时使用，不用固定权重制造假精确。明显不适合的候选带证据淘汰（**禁止沉没成本保留**），不必完整实现；若只有一种合理构造，说明唯一性依据，不硬凑模型。调参算法不等于新的建模路线；每处复杂度必须修复一个具体的、已观测到的基线失效模式。

小问结果表用已有记录串联：原题要求、模型公式位置、实现函数/配置、运行输出字段、验证证据、正文/图表位置、结论边界。任何一环缺失就标待验证；上游输入/代码变化后重算受影响下游，摘要必须来自最终选中模型。直接计算与独立复核若共用相同预处理/指标实现，另以解析边界或不同实现核验该共同部分。

统计/预测/分类的预处理、特征筛选、调参与最终评估隔离；官方指标先准确实现，再加解释性辅助指标，不能用更好看的指标替换题目指标。两候选必须在同一划分、信息截止时刻和预算下比较。

## 有效迭代与停止条件

默认做 ARCHITECT/SKEPTIC/REVIEWER 三个认知视角（见 [route-iteration.md](route-iteration.md)）；可以共享同一真实 pilot/推导证据，但 finding/change 必须不同，不为流程制造文件。先回答主问并得到可靠基线，再按预期收益决定追加实验。记录计算预算与停止理由；算法耗时不佳时交付已验证基线及不足，不伪装未完成搜索为最优。

**继续搜索的准入条件**（机器强制：同一问已有 ≥3 个结果后，`result record` 必须带 `--continue-reason`）。每批新实验至少满足其一，否则停止：

1. incumbent 有实际改善（不是噪声级抖动）；
2. lower bound / optimality gap 明显改善；
3. 新实验能够区分两个结构性假设（判别性实验）；
4. 正在验证一个关键 failure mode。

禁止“因为还能计算，所以继续扫”。扫描类搜索必须先声明候选空间大小；ready-set 全扫描、anchor 全组合这类接近二次/组合增长的枚举，必须先做复杂度 probe（见下）。

## 复杂度 probe（全规模前的低成本守卫）

机器强制：`complexity=high` 的候选在全规模运行前必须 `run_state.py probe record`——小规模实测（runtime/memory）→ 按增长阶外推全规模成本 → 与 abort 阈值比较：

- 外推超阈值 → `--decision abort`（候选自动 rejected，尽早死，不等正式运行超时）；
- 确要继续 → `--decision continue` + rationale；外推超阈值仍 continue 必须 `--override-rationale` 留档。

probe 同时回答：最大实例规模、候选增长曲线、是否有结构性剪枝可把增长降阶。验证代码本身也要过复杂度审查：为清晰写的 O(N³) 暴力核对只用于小规模，生产验证用向量化/结构化实现（真实教训：数千 anchor 组合与 ready-set 全扫描都曾在正式运行中爆炸）。

## 历史资产分级加载（防 solution anchoring，不重复造基础设施）

- **Infrastructure assets（允许早用）**：官方输入 parser、schema、I/O helper、legality checker、evaluator/Referee A、test fixture、渲染与打包工具链。
- **Solution assets（晚加载）**：历史 solver、启发式与参数、历史最终结果、solution-specific features、往届论文的建模路线。必须在本项目独立完成 UNDERSTAND（traceability 通过）与 IDEATE/SELECT（自有路线已注册并竞争）之后，才允许进入比较；进入时作为**挑战者**登记，与主线同预算、同 Referee 评价。
- 优秀论文调用时机（Phase A/B/C）是本规则在文献资产上的特例，见 [excellent-paper-learning.md](excellent-paper-learning.md)。

## 状态与数字纪律（单一事实源）

研究状态与主指标只以 `team_control/run-state.json` 为准（[run-state.md](run-state.md)）：候选注册/晋升/淘汰、rollback、冻结与审批、派生报告全部走脚本。阶段总结、验证报告、指标表由 `report`/`metrics show` 生成或引用，**不人工抄写主指标**；WRITE 前与打包前跑 `metrics scan` 清除 superseded 候选的旧数字残留。产物文件同样反对“多代并存”：新版稿/新版页图产生后，旧版要么删除、要么在文档中显式标注 superseded 及替代者路径；gate 输出用固定路径覆盖写，不用 `-final/-final2/-final3` 后缀繁殖（真实运行中曾出现 7 份字节相同的“最终”审查文件与两份 `passed:false` 却宣称成功的 manifest）。

源文件、数值、图表与稿件绑定版本。相同输入/代码/配置可重用有效计算，发生相关变更就重算受影响结果；不以“效率”为由重用过期证明。**只为刷新哈希绑定而整体重跑一次计算是浪费**：优先重算哈希、复用逐字节相同的输出（用内容哈希确认），把重跑留给真正受变更影响的结果。目检统一为首轮全量 → 修复轮只看改动页+抽检2页 → 终稿全量。

## 来源与合并前检查

若论文实际借用了外部模型/公式/事实，或有一个关键自建推导需要单独绑定证据，就在 `manuscript/source-registry.json` 登记；没有这类内容时允许保持空 `sources/claims`，不为了过门制造台账。借用内容记录原文定位、稿件位置和已阅读核验状态；关键自建推导记录推导文件与位置。终审 `source_gate` 只验证实际登记的内容与当前 PDF 是否一致，不要求把每个编号公式都重复登记。

可从 [空台账模板](../templates/source-registry.json) 开始。来源台账顶层含 `paper / paper_sha256 / sources / claims`；字段细节以 `scripts/source_gate.py` 和模板为准。

终稿合并后重新检查全文符号、跨问结论依赖、数值、摘要、引用与图表是否自洽；页码、匿名、封面、字体等格式项只执行当届官方明确 mandatory 或用户明确要求，其他不自行加门。不能把各小问 PASS 相加就称全文 PASS。

## 自动化的明确边界

本地可编辑台账与哈希用于防疏忽，不防恶意造假；哈希一致不证明来源可靠、图像对应该PDF或数学成立。最终必须实际读来源和逐页核对。不得宣称“红线100%杜绝”或“完全无误”；脚本只能覆盖它实际检查的内容。
