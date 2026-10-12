---
name: review-reporter
description: "复盘报告员：按当期指标生成数据复盘与下一轮优化建议，只建议不改提示词。Use when 指标已采集需要出复盘、需要给下一轮内容提优化建议、或想按周期对比选题表现时。"
---

# 复盘报告员（review-reporter）

- 归属：分发数据线 / 复盘
- 输入：任务号（+ 可选复盘周期）
- 输出：`review/report-<时间戳>.{md,json}` + report 产物 + 阶段推进到 review
- 副作用：写产物与步骤流水，任务阶段 metrics→review

## 用法
```bash
python3 .dsh/skills/review-reporter/run.py --help
```

## 契约（摘要）
- 输入校验：任务必须已有指标；提示词变量必须与模板一致。
- 完成判据：报告含四部分、≥200 字、带数字与建议；产物带提示词与模型版本。
- 失败处理：无指标退出 2；报告不合格重试 3 次后写失败说明并置 blocked、退出 1。

完整九段说明见 `.dsh/skills/review-reporter/README.md`。
条目来源：`.dsh/skills/review-reporter/run.py`、`docs/skill-roster.md`。
