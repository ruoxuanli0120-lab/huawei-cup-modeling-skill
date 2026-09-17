# 推导、实现与视觉审计

Use the definition-to-code and problem-matched validation sections for computational questions. Sections 2 and 4 apply only when the question actually concerns optimality, construction or complexity; they do not replace statistical inference, generalization or mechanistic validation in the type playbook.

## 1. Anchor every definition to the official source

Before deriving or coding, copy the exact problem definition into a rule/notation record: objective, normalization, roots or squares, optimized variables, permitted constants/operations, and counting conventions. A previous draft may reveal a useful route but is not proof that its formula matches the official statement.

When an ambiguity changes a result, state it explicitly, choose the official interpretation, and run a sensitivity check under the plausible alternate convention if it is feasible. Do not silently replace an official metric with a visually similar one.

## 2. Close the theory–construction loop

When a claim specifically asserts an optimum or minimum, seek this chain (an empirical speed/accuracy advantage alone does not require an optimality proof):

1. a precise structural lemma;
2. a lower bound or impossibility result derived from it;
3. a construction or algorithm attaining the bound, if one exists;
4. a statement of the gap if the bound is not attained.

Check boundary cases independently. A proof must use the same operation-counting convention and variables as the numerical result.

## 3. Independent numerical audit

Choose validation that matches the claim. When a simple direct/reference calculation exists, compare it with the proposed method using the exact relevant metric and stated tolerance. Otherwise use suitable evidence such as constraint checks, exact/small cases, baseline or bound comparisons, sensitivity/perturbation, robustness, extreme cases, or an independent evaluator. Do not build a second implementation merely to satisfy a template.

### Referee A / Referee B（solver 与裁判分离）

对存在明确评价口径的计算题，在 BUILD 早期、正式 full-scale 评价前建立 **Referee A**：解析输入、检查合法性并按题目口径计算指标；它不参与求解，也不读取 solver 的内部搜索状态。候选尽量由同一个 A 评价，保证比较公平。

若题型和值得投入的风险需要独立复算，可在 VALIDATE 增加 **Referee B**；它是增强证据而不是所有计算题的固定门。使用时尽量独立实现，重算最终核心指标，以降低 solver 与 evaluator 的同源错误。纪律：

- B 与 A **字节相同**直接拒绝（那不是验证，是复制）；
- 若 A 与 B 共享大量核心代码（同一解析器、同一指标函数），必须如实登记 `shares_code` 与共享范围（`run_state.py referee register --role b --independence shares_code --independence-note ...`），论文与验证报告的“独立复核”措辞随之降级；
- **validator 不得自己撰写 numeric-provenance 台账**：台账由求解侧记录、由复核侧核对，方向不能反；
- “不同文件/不同哈希”不等于科学独立：优先要求**不同算法族**（如显式构造 vs `np.fft`、逐条约束检查 vs 对偶界），并把独立性判断写进验证报告，交 REVIEWER/人审。

Before declaring results paper-ready, reconcile the **official definition → displayed formula → implementation → table/figure label** chain. In particular, distinguish a norm from its square, a sum from a mean, and a normalized objective from an unnormalized residual. Record the code expression or test result that establishes the displayed quantity; a prose claim that the code “computes RMSE” is insufficient.

For products, transforms, or staged algorithms, test order, orientation, indexing, permutations, and shared-operation accounting separately. Maintain a short audit table with `test`, `expected invariant`, `observed value`, `status`, and `diagnosis/fix` when a test fails. Independently substitute matrix-product row/column expansions used in a proof; a reversed factor or index is a proof defect even if the intended result is true. Never edit a failed result out of the project history; the paper need only retain the final, reader-relevant verification and any limitation.

## 4. Complexity and counting audit

Define exactly what one operation means before publishing a complexity count. For example, distinguish matrix nonzero entries from reused arithmetic products, and count free/sign/unit operations only if the official convention says so. Recompute a closed-form total from the per-stage/item counts and compare it against enumeration on small and medium inputs.

If a reasonable alternative convention multiplies or shifts the count but does not alter the qualitative conclusion, report that sensitivity briefly in the question manuscript.

## 5. Publication-quality evidence

Create figures only when they add a reader decision: e.g., scale comparison, component distribution, residual trend, or structural flow. Give each figure a source/result link, readable Chinese fonts, captions, units, and discussion in the text. Prefer vector diagrams generated in LaTeX when they represent model structure; otherwise keep plotting scripts and source data traceable.

For the formal authoring loop, renderer selection, page-image inspection, revision records and delivery proof, read [paper-production.md](paper-production.md). A compiler success is not publication approval.
