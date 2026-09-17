# 当届官方格式清单（轻量）

只记录**当届官方通知/官方模板**中与论文格式/提交形式有关的内容；不跨年份继承。进入 WRITE 后自动检索官方来源。

核心原则：

> **明确硬性要求才阻断；建议只提醒；没说或说不清的不管。**

从 [official-checklist 模板](../templates/official-checklist.json) 复制后填写。

```json
{
  "edition": "2026",
  "verification_status": "verified",
  "search_attempted": true,
  "search_note": "checked current official contest notice and template",
  "official_sources": [
    {"source": "https://official.example/current-notice", "locator": "submission section"}
  ],
  "items": [
    {
      "id": "R01",
      "strength": "mandatory",
      "rule": "官方明确硬性要求的准确转述",
      "source_locator": "第3条",
      "status": "pass",
      "note": "main.tex 中已落实"
    },
    {
      "id": "R02",
      "strength": "advisory",
      "rule": "官方建议性表述",
      "source_locator": "说明第2点",
      "status": "warn",
      "note": "仅提醒，不阻断"
    }
  ]
}
```

规则：

- `mandatory`：只有官方明确强制语气或模板明确标为不可更改时使用；状态必须 `pass` 或有真实条件依据的 `not_applicable`，否则 FAIL。
- `advisory`：建议/原则上/推荐/可选等；可记 `pass`、`warn`、`not_applicable`，永远只产生提示，不阻断。
- 官方未说明或表述含糊的格式项**不要加入 items**，更不能靠历史模板、优秀论文或审美推断补成规则。
- 对模板的视觉样式（例如“看起来像某字号/页边距”）不要反推为 mandatory，除非官方文字或模板说明明确要求。
- `verification_status=verified` 时应记录至少一个当届官方来源，并确认实际读过。
- 当届材料暂时找不到时使用 `verification_status=unverifiable`，`search_attempted=true` 并写 `search_note`；此时格式状态只是“待确认”，不阻断 LaTeX/Overleaf 交付，也不得声称已官方核验。
- `evidence` 可选；若提供机器检查证据，脚本会检查文件是否仍有效，并拒绝用手工 `pass` 覆盖机器 FAIL。

`scripts/official_clause_gate.py` 只做这套轻量检查，不承担未被官方明确要求的排版规范。
