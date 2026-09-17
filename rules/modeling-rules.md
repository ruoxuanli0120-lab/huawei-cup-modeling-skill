# 第二梯队：建模质量规则

## Step 0 — 题面审计

Complete the audit before route comparison. 本 Step 0 是 Problem Insight Map（[../templates/problem-audit.md](../templates/problem-audit.md)）的填写纪律，方法出处见 [../references/problem-intelligence.md](../references/problem-intelligence.md)。硬规则：按 **问题结构 → 数学抽象 → 数学模型 → 求解方法**（等价展开：结构 → 抽象 → 机理 → 路线 → 算法）推理，禁止 algorithm-first（看到预测就默认 XGBoost、看到优化就默认遗传算法、看到评价就默认 AHP/TOPSIS/熵权、看到图就默认最短路，都是违规）。**数学模型必须从问题本身建立**：先写清研究对象、真实关系、变量四分类（状态/决策/观测/参数）、约束、结构（时间/空间/网络/阶段/随机/反馈/守恒）与真正难点，得到目标 + 约束 + 变量域的模型雏形；求解方法再由模型属性决定。**禁止罗列大量模型制造复杂度**——每个候选都要指向本题的一个具体结构或难点，否则不进入锦标赛。先写出数学本质与结构；若存在实质不同且合理的表示，至少比较一个替代表示。若没有，不为凑数制造伪路线。

1. Record the requested output, observations/variables, applicable constraints, metric, units and evidence standard; operation counts only when relevant.
2. Test the type-specific shortcut: zero/empty decisions for optimization, majority-class or leakage shortcuts for prediction/classification, arbitrary weights for evaluation, unidentifiable parameters for mechanisms, and boundary/counterexamples for theory.
3. Check whether the metric and assumptions support the practical question. Do not turn explanation, estimation or existence into an optimization task merely to fill a template.
4. List missing constraints and hidden assumptions. For each, state `official / inferred / added engineering assumption`.
5. Identify ambiguous conventions and run a small discriminating example under each plausible convention.
6. Record the literal answer, a repaired engineering model if needed, and the effect of the repair separately.

## 模型与方法合适性——第一等检查

评分首先问“**模型是否适合问题**”“**求解方法是否适合模型**”。进入正式求解前，下列必须能回答（完整方法见 [../references/model-ideation.md](../references/model-ideation.md)）：

- **模型合适性**：模型是否从问题结构（对象/关系/约束/机理项）建立，而非从算法或模板倒推？有没有**更简单、更自然**的模型能解释同样关系？有没有遗漏重要关系、约束或守恒量？
- **方法合适性**：过 [Method Suitability A–F](../templates/method-suitability.md)。六项按题型解释：计算题检查模型结构→方法表示→合法性→验证；理论题检查命题结构→证明策略→条件/反例→独立 proof review。**任一项无法合理回答，不锁定该方法。**
- **禁止口号选法**：“GA 全局搜索能力强”“PSO 收敛快”“LSTM 能处理长期依赖”“XGBoost 精度高”，都没有回答**它为何适合这个数学模型**；必须点名主要替代方法并说明差在哪。
- **方法内部设计对应本题**：编码/算子/约束处理/修复/初始化必须映射到本题变量与结构；无法自然对应即说明方法不适配（详见 model-ideation.md“方法内部设计必须真正对应本题”）。
- **创新服务于合适性**：优先表示/状态变量/机理项/分解/耦合/针对 baseline failure 的改进；算法换新版本只是次级创新，且每个创新点要答“它解决了原模型的什么具体问题”。
- **验证的是模型与方法，不是程序能跑**：**程序运行成功 ≠ 模型正确；指标更高 ≠ 模型一定更合适**。验证须覆盖假设合理、关键参数稳定、扰动稳健、无泄漏、能泛化、解可行、与精确解/下界/基线比较、边界极端条件、结论真的回答题目。

## The optimality hook (conditional)

Only optimization, operations research, discrete construction, or explicitly optimality-seeking questions trigger this card before the word “optimal” is allowed. For prediction, statistics, machine learning, mechanistic, simulation and evaluation questions, replace it with the relevant playbook Gate (generalization, calibration, convergence, ranking stability, etc.):

```text
Construction: ...
Claimed objective: ...
Structural lemma or invariant: ...
Lower bound: ...
Does the construction attain it? ...
Boundary cases: ...
If not attained, gap and limitation: ...
Numerical falsification test: ...
```

For matrix factorization, for example, a support-growth lemma may prove a factor-count lower bound, but it does not automatically prove minimum nonzero count. State exactly what is proved.

## Complete model card

For each question, preserve:

- assumptions and why each is acceptable;
- symbols, dimensions and units;
- candidate routes and baseline;
- **why the chosen solving method fits THIS mathematical model, and why the main alternatives are less suitable** (the two必答 sentences — model-ideation.md);
- **Method Suitability Test A–F**：使用统一模板，按计算/理论题型解释，不人为制造不适用的数值步骤；
- objective order/Pareto policy only for multiple objectives;
- model/algorithm, estimation or proof, and applicable cost/precision convention;
- independent validation and tolerance;
- sensitivity, failure conditions and scope;
- engineering translation and possible extension.

If one item is not applicable, write why. A compact model is better than a decorative section that does not support a decision.

## Multi-objective choice

Use a decision card:

```text
Objectives: ...
Priority policy: lexicographic / weighted / Pareto / other
Reason tied to the question: ...
Baseline and trade-off evidence: ...
Sensitivity to weights/order: ...
Change condition: ...
```
