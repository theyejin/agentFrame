---
name: table-builder
description: "表格汇总员：把一批热点条目按分类汇总成表格（Markdown + CSV），给出每类条数、热度与代表条目。Use when 热点已采集需要出汇总表、需要按分类看热点分布、或要把表交给文档同步时。"
---

# 表格汇总员（table-builder）

- 归属：分发数据线 / 汇总
- 输入：批次号或 `--latest`（+ 可选关键词/分类过滤）
- 输出：`hotspot-table-<时间戳>.{md,csv}` + 回填 `hotspot_batches.table_path`
- 副作用：只回填批次表的 table_path

## 用法
```bash
python3 .dsh/skills/table-builder/run.py --help
```

## 契约（摘要）
- 输入校验：批次必须存在且非空；`--category` 限四类。
- 完成判据：表格含固定表头与合计行，Markdown 与 CSV 行数一致。
- 失败处理：批次缺失/空退出 2；写盘失败退出 1。

完整九段说明见 `.dsh/skills/table-builder/README.md`。
条目来源：`.dsh/skills/table-builder/run.py`、`docs/skill-roster.md`。
