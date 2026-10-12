---
name: summary-writer
description: "汇总回报员：把一条任务的留痕（环节 / 步骤 / 关口 / 产物 / 指标 / 复盘 / 派单书）汇总成一段给运营人员看的回报，只读库、不改状态、不调模型。Use when 需要向运营人员汇报某条任务进展、需要看现在卡在哪个关口、或想把一整条链路的留痕收成一段话时。"
---

# 汇总回报员（summary-writer）

- 归属：支撑件 / 编排者工具
- 入口：`.dsh/skills/summary-writer/run.py`
- 详细字段与判据以同目录 `README.md` 为准

```bash
# 汇总一条任务的进展
python3 .dsh/skills/summary-writer/run.py --db db/app.db summarize --task-id 1

# 只看结构化结果（不改任何表）
python3 .dsh/skills/summary-writer/run.py --db db/app.db summarize --task-id 1 --json
```

- 回报固定含五项：当前环节 / 已完成步骤数 / 待办关口 / 关键产物 / 下一步找谁。
- 产物落 `workspace/topic-<选题号>/reports/summary-<时间戳>.{md,json}`，登记 `kind=report`、`meta.role=summary`。
- 只汇总已留痕的事实：缺数据写缺口，不推算、不编数字、不代答关口。
