# 科研证据协议

Use this protocol when a question depends on literature, an external method claim, a domain fact, or a comparison with prior work. Its goal is a reproducible evidence chain, not a long bibliography.

## Research loop

1. **Question and scope.** Write the exact claim or decision the research must support, domain, date range, language, and inclusion/exclusion criteria. Do not search generically for “papers about the topic”.
2. **Focused search.** Record the useful query/date and why a selected source supports this decision. A contest task does not need a systematic-review log, result counts, or all rejected hits unless the question itself requires a review.
3. **Evidence table.** For each selected source record DOI or stable publisher URL, publication type/year, what was actually read (metadata/abstract/full text), the precise claim it can support, limitations, and manuscript location. Do not cite a paper for a detail that was not read.
4. **Triangulate consequential claims.** Use an official source, original paper, or two independent credible sources for claims that affect model choice, constraints, evaluation criteria, or a numerical constant. For a theorem or formal algorithm statement, use the original or authoritative source.
5. **Claim-bound writing.** Every literature-backed sentence must be narrower than or equal to what its source supports. Distinguish established facts, the team's inference, and proposed modeling assumptions.
6. **Final verification.** Check every in-text reference resolves to one verified entry; remove decorative citations and unsupported “state-of-the-art” language.

## Application to mathematical modeling

进入 WRITE 后若当届官方明确规定 AI 辅助写作、引用、模型/公式来源或参考文献要求，按 mandatory/advisory 强度登记；mandatory 执行，advisory 提醒。用户另有明确要求时也执行。无论格式如何，学术真实性仍要求：实际阅读所引用来源、记录原文定位与正文引用位置，改写既有公式说明变形过程，自建公式提供推导和假设，不把 AI 生成答案本身当作学术来源。

Literature is normally used to justify a mechanism, select a baseline, explain a constraint, or identify a real-world interpretation. It must not replace problem-specific derivation, independently reproduced computation, or validation. Prefer a short, high-quality source set over a survey-like reference list.

For a candidate model, write a one-paragraph decision card: `candidate → problem fit → source-supported premise → baseline/alternative → discriminating experiment → failure condition`. This card belongs in the Qn evidence package before the user approves the route.

## External research assistants

External research tools or ordinary web search may accelerate search and reading（可选插件的路由与边界见 [plugin-routing.md](plugin-routing.md)）. Their summaries, generated citations, code, and conclusions are leads only. Register only sources and results that can be independently opened, checked, and reproduced in the local question package.
