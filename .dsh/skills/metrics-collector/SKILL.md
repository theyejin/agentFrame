---
name: metrics-collector
description: "指标采集员：采集播放量/互动量/涨粉数三项指标并按周期落库，来源可追溯。Use when 发布后需要采一期数据、需要人工补录指标、或要查看某个任务的指标明细时。"
---

# 指标采集员（metrics-collector）

- 归属：分发数据线 / 指标
- 输入：任务号 + 周期 +（人工数值 或 指标夹具）
- 输出：`metrics/metrics-<时间戳>.{json,md}` + `metrics` 表更新 + table 产物
- 副作用：写 metrics 表与产物，任务阶段 publish→metrics

## 用法
```bash
python3 .dsh/skills/metrics-collector/run.py --help
```

## 契约（摘要）
- 输入校验：必须给 `--values` 或 `--fixture`；周期起止必填；三项口径必须齐全（除非 `--allow-partial`）。
- 完成判据：同键不重复堆行，快照合计与库中 SUM 一致，任务推进到 metrics。
- 失败处理：缺入口/缺周期/缺口径退出 2；夹具无记录退出 2。

完整九段说明见 `.dsh/skills/metrics-collector/README.md`。
条目来源：`.dsh/skills/metrics-collector/run.py`、`docs/skill-roster.md`。
