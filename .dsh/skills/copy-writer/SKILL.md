---
name: copy-writer
description: "文案写手：把一条选题（对话框 Prompt + 字数范围 + 类型 + 平台）写成 3 套不同侧重点的候选文案 —— 开头钩子 / 情绪强度 / 行动号召，供运营人员在关口① 三选一。Use when 需要为某个任务生成候选文案、需要重生成某套文案、或想演练文案线的降级链与字数门禁时。"
---

# copy-writer（文案写手）

**是什么**：文案线第一道工序。输入「选题 + 要求」，输出**3 套侧重点互不重复的候选文案**（R-L1-19），写进 `copy_variants` 并落一份带时间戳的产物，然后停在**关口①**等运营人员选一套。

**什么时候用**：
- 新任务进入文案线（`tasks.stage = copy`）；
- 运营人员对三套都不满意，要求带反馈重生成（再跑一次即可，同套号覆盖、历史留痕在产物里）；
- 想确认「字数区间没写错、类型是四种之一」（输入校验会直接挡住）。

**入口**：

```bash
python3 .dsh/skills/copy-writer/run.py generate --task-id 1
python3 .dsh/skills/copy-writer/run.py generate --task-id 1 --out workspace/topic-1/copy --attempts 3 --json
```

**产出**：`copy_variants` 三行（`focus` = hook / emotion / cta）、`variants-<时间戳>.json`、`variants.md`、`step_runs` 与 `artifacts` 留痕。

**详细说明与九段契约**见同目录 `README.md`；本文件只回答「是什么、什么时候用、入口在哪」。
