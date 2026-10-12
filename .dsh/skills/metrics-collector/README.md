# 指标采集员（metrics-collector）

<!--
文件用途：指标采集员 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：FLOW-9 数据采集 / R-8-14（三项口径、来源可追溯）/ Q-16（口径固定，不多不少）。
对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `metrics-collector` |
| 中文岗位名 | 指标采集员 |
| 归属 | 分发数据线 / 指标 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/metrics-collector/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
按任务采集三项指标（播放量 views、互动量 engagements、涨粉数 follower_gain），同一任务同一平台同一周期同一指标更新而不堆行，产出指标快照（JSON + Markdown）并把任务阶段推进到 `metrics`。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| `--task-id` | 整数 | 是 | 要采指标的任务号 | 编排者派单 |
| `--values` | 文本 | 二选一 | 人工录入，例 `"播放量=1200,互动量=88,涨粉=12"` | 人工 |
| `--fixture` | 文件 | 二选一 | 离线指标夹具 JSON（经 metrics 降级链采集） | 命令行/仓库夹具 |
| `--platform` | 文本 | 否 | 平台；缺省用任务的 target_platform | 命令行/任务表 |
| `--period-start / --period-end` | 日期 | 是 | 统计周期（复盘按周期取数） | 人工/命令行 |
| `--source` | 枚举 | 否 | manual / browser / api / export | 命令行 |
| `--allow-partial` | 开关 | 否 | 允许只采部分指标（默认三项必须齐全） | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务存在；周期起止必须都给（缺周期就没法按周期复盘）。
2. 指标口径只能是三项，中文别名会被归一（播放/播放量→views、互动/点赞评论→engagements、涨粉/新增粉丝→follower_gain）。
3. 数值必须非负、可解析为数字；默认三项必须齐全，缺项要显式 `--allow-partial`。

## 4. 输出
- `workspace/topic-<选题号>/metrics/metrics-<时间戳>.json`（记录 + 聚合）。
- `…/metrics-<时间戳>.md`（人读明细）。
- `metrics` 表：同期同键更新（不堆重复行）。
- `artifacts` 一条 table（meta.role=metrics）；`step_runs` 一条 ok（adapter_used 记实际来源链）。

## 5. 完成判据（自检通过才交给下游）
- 三项数值都落在 `metrics.metric_key` 允许集合内、非负、带周期。
- 同一 (task, platform, metric, period) 只有一行（重复采集是更新而不是插入）。
- 指标快照里的合计与库里 `SUM(value)` 一致。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 既没给 `--values` 也没给 `--fixture` | 退出 2，提示给其中一种 | — | — |
| 周期缺失或三项不全 | 退出 2，列出缺哪些 | — | — |
| 夹具里没有该平台的记录 | 退出 2，提示核对 `--platform` | 1 次 | 退回重给夹具 |

## 7. 依赖
`_shared/metrics.py`（口径归一、校验、落库、聚合、渲染）、`_shared/adapter_runtime.py`（metrics 降级链，`metrics.local-fixture`）、`_shared/recording.py`。

## 8. 不在本版范围
本版不做真正的浏览器抓指标（`metrics.browser-scrape` 未接）；不采三项以外的指标（Q-16）。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：播放量/互动量/涨粉数三项指标落库（WP-05 步骤 7） |
