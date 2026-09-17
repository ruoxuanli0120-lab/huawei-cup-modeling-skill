# LaTeX 论文生产

最终论文只有一个权威 LaTeX 项目：`manuscript/latex/`，入口是 `main.tex`；可使用 `\input`、`.bib`、图片等子文件，但它们必须留在同一源码树内。无官方 LaTeX 模板时可从 [中性 starter](../templates/main.tex) 开始；若当届官方提供模板/类文件，优先保留其明确要求的结构。

## 写作

围绕同一条论证链写：

`题目结构 → 建模理由 → 数学表达 → 求解/证明方法 → 验证证据 → 对原问题的结论`

内部工程术语（route、gate、rollback、registry、incumbent 等）不进入论文主体。摘要优先写清问题、模型、方法、最重要结果、验证与结论；页数、关键词、封面等格式要求只看当届官方明确规定。

## 当届官方格式

进入 WRITE 后自动查当届官方通知/模板，并维护 `manuscript/official-checklist.json`：

- `mandatory`（明确“必须/不得/限定”）未满足 → FAIL；
- `advisory`（建议/原则上/推荐）未满足 → warning；
- 官方未说明/表述不清 → 不创建额外限制；
- 当届材料暂不可核验 → `unverifiable` + search note，继续写作并提示后续确认。

详细规则见 [official checklist](../rules/official-clause-checklist.md)。历史年份只可帮助定位官方入口，不能自动继承成当届硬规则。

## 编译与视觉 QA

1. 运行 `python scripts/render_manuscript.py --project . --source manuscript/latex/main.tex --output-dir qa/final-render`，编译当前源并生成最新 PDF 与全量页图。
2. 检查标题层级、公式/CJK 字形、图表/图注、引用、明显溢出/空白和整体可读性。
3. 有实际视觉缺陷就修改同一 LaTeX 源码树后重编译；旧 proof 自动视为 stale。
4. 终稿全量页图检查完成后，将最新 render manifest 的视觉项设为 `pass`、`defects=[]`。

编译器从首轮辅助文件识别传统 BibTeX 或 biblatex/Biber，执行对应文献工具后再编译以解析引用；缺少所需工具会明确报错。PDF、页图与 manifest 使用项目内统一的正斜杠路径，便于 Windows 上继续运行最终校验与授权。

轻微 overfull/underfull 警告本身不作为交付失败；是否修复以页图是否影响可读性和官方明确规则为准。Missing character、未解析引用/文献等会破坏内容的编译问题必须修。

## Overleaf

运行 `python scripts/package_overleaf.py --project . --source-dir manuscript/latex --main main.tex --output manuscript/overleaf-project.zip`。脚本只归档源码，不改写 TeX；ZIP 中 `main.tex` 必须与权威源逐字节一致。LaTeX 项目须自包含在 `manuscript/latex/` 内，不用 `../` 或绝对路径引用外部项目文件。上传 Overleaf 后若继续修改，应重新编译、QA 和最终授权。

## 最终门

`final_compliance_gate --scope final` 只检查：

- 当前 PDF 与当前 `main.tex`/proof 绑定；
- run-state 中出现计算问则要求 numeric provenance，出现理论问则要求 theoretical evidence，两者都有则两类都要求；
- 来源核验；
- 当届官方明确 mandatory 格式条款；
- Overleaf ZIP 与当前完整 LaTeX 源目录逐文件一致。

通过后再 `AUTHORIZE_SUBMISSION`；授权绑定 final report 和当前源码，稿件改动后旧授权失效。
