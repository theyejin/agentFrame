---
name: hotspot-collector
description: "热点采集员：按关键词从公开来源采集热点条目并归类（情绪冲突/干货教程/热点观点/其他），产出热点清单与批次留痕。Use when 需要按关键词搜热点找选题、需要重采一批热点、或想演练浏览器与文本的降级链时。"
---

# 热点采集员（hotspot-collector）

- 归属：分发数据线 / 采集
- 输入：关键词（+ 可选离线夹具、周期、条数上限）
- 输出：`workspace/hotspots/<批次号>/hotspots.{json,md}` + `hotspot_batches`/`hotspot_items` 留痕
- 副作用：只写热点两张表与清单文件，不改任务、不动账号

## 用法
```bash
python3 .dsh/skills/hotspot-collector/run.py --help
```

## 契约（摘要）
- 输入校验：必须给 `--keyword`/`--keywords`；批次号唯一；给了 `--fixture` 就要存在。
- 完成判据：条目数 ≥ 1、标题非空、分类合法，且清单条数与库中条数一致。
- 失败处理：链不可用退出 2；自检不过重试 3 次，仍不过登记失败。

完整九段说明见 `.dsh/skills/hotspot-collector/README.md`。
条目来源：`.dsh/skills/hotspot-collector/run.py`、`docs/skill-roster.md`。
