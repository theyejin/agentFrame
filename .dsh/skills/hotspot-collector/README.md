# 热点采集员（hotspot-collector）

<!--
文件用途：热点采集员 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：FLOW-6 热点采集 / R-7-01（按关键词采集）/ R-7-02（四类归类）/ Q-13（需登录的来源先人工授权）。
对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `hotspot-collector` |
| 中文岗位名 | 热点采集员 |
| 归属 | 分发数据线 / 采集 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/hotspot-collector/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
按关键词采集一批热点，归到四类里（情绪冲突 / 干货教程 / 热点观点 / 其他），把条目与批次写进 hotspot_batches / hotspot_items，产出热点清单（JSON + Markdown）。只读公开来源，不做发布、不碰账号。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| `--keyword` | 文本 | 二选一 | 采集关键词 | 命令行/编排者派单 |
| `--keywords` | 文本 | 二选一 | 多个关键词（逗号分隔） | 命令行 |
| `--limit` | 整数 | 否 | 最多保留条数（默认 20） | 命令行 |
| `--fixture` | 文件 | 否 | 离线夹具 JSON；给了就走夹具，不联网 | 命令行/仓库夹具 |
| `--batch-key` | 文本 | 否 | 指定批次号（缺省按时间戳生成） | 命令行 |
| `--period-start / --period-end` | 日期 | 否 | 这批热点对应的统计周期 | 命令行 |
| `--attempts` | 整数 | 否 | 最多尝试次数（默认 3） | 命令行 |
| `--allow-paid` | 开关 | 否 | 允许调用计费适配器（默认只走免费链） | 命令行 |
| `--out` | 目录 | 否 | 输出目录；缺省 `workspace/hotspots/<批次号>` | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 必须给 `--keyword` 或 `--keywords`，关键词不能是空白。
2. 批次号不能与已有批次重复（`hotspot_batches.batch_key` 唯一）。
3. 给了 `--fixture` 时文件必须存在且能被 JSON 解析。

## 4. 输出
- `workspace/hotspots/<批次号>/hotspots.json`（条目原文 + 分类 + 热度）。
- `workspace/hotspots/<批次号>/hotspots.md`（人读清单）。
- `hotspot_batches` 一条 + `hotspot_items` N 条（条目级留痕）。
- 不写 `step_runs` / `artifacts`：这两张表的 task_id 是 NOT NULL，而热点批次是话题级的。

## 5. 完成判据（自检通过才交给下游）
- 条目数 ≥ 1，每条标题非空、分类落在四类里。
- 批次记录带 `adapter_used` 与 `collected_at`（来源可追溯）。
- 清单文件里的条数与库中 `hotspot_items` 条数一致。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 适配器链全不可用（浏览器未接且没给夹具） | 退出 2，提示给 `--fixture` 或先在适配器登记表接上浏览器适配器 | 1 次 | 不重试，直接退回 |
| 条目自检不过（标题空 / 分类非法） | 带反馈重试最多 3 次 | 3 次 | 登记失败并回报编排者 |

## 7. 依赖
`_shared/hotspots.py`（解析、归类、落库、渲染）、`_shared/adapter_runtime.py`（browser 采集 + llm 归类）、`_shared/prompt_templates.py`、`_shared/db.py`。

## 8. 不在本版范围
不抓需要登录的来源（Q-13 要求先人工授权）、不做选题决策、不自动建任务。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：关键词采热点 + 归类 + 批次留痕（WP-05 步骤 7） |
