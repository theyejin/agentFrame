# 复盘报告员（review-reporter）

<!--
文件用途：复盘报告员 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：FLOW-9 数据复盘与优化 / R-8-15（复盘报告）/ R-8-16（给可执行建议、不给孩子打分）/ Q-19（只回写仓库内提示词版本建议）。
对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `review-reporter` |
| 中文岗位名 | 复盘报告员 |
| 归属 | 分发数据线 / 复盘 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/review-reporter/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
读当期指标聚合成表，再按播放在同一期内排出前后选题，渲染 `review-report` v1 提示词，经 llm 降级链产出复盘报告（Markdown + JSON）。建议只作为下一轮提示词版本改动的输入，不自动改提示词（Q-19）。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| `--task-id` | 整数 | 是 | 要复盘的任务号 | 编排者派单 |
| `--period-start` | 日期 | 否 | 复盘周期；缺省取该任务最近一期指标 | 命令行/库 |
| `--period-end` | 日期 | 否 | 周期结束（缺省同开始） | 命令行 |
| `--attempts` | 整数 | 否 | 最多尝试次数（默认 3） | 命令行 |
| `--allow-paid` | 开关 | 否 | 允许调用计费适配器（默认只走免费链） | 命令行 |
| `--out` | 目录 | 否 | 输出目录；缺省 `workspace/topic-<id>/review` | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务必须已有指标；没有就退回并提示先跑 metrics-collector。
2. 报告至少 200 字、必须含「建议」段、必须出现数字（否则判定不合格并重试）。
3. 渲染提示词变量必须与模板变量一致（`_shared/prompt_templates.py` 会校验）。

## 4. 输出
- `workspace/topic-<选题号>/review/report-<时间戳>.md`（人读复盘）。
- `…/report-<时间戳>.json`（聚合数据 + 全文 + 提示词/模型版本 + 建议用途说明）。
- `artifacts` 一条 report（meta.role=review）；`step_runs` 一条 ok。
- `tasks.stage` 推进到 `review`。

## 5. 完成判据（自检通过才交给下游）
- 报告含周期、发布条数、指标明细、复盘与建议四部分。
- 产物登记带 prompt_version（review-report vN）与 model_version。
- 建议是「下一轮怎么改」，不包含自动改提示词的动作。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 任务没有任何指标 | 退出 2，提示先跑 metrics-collector | — | — |
| 报告不合格（太短/没建议/没数字） | 带反馈重试 | 3 次 | 写一份失败说明、登记 failed、任务置 blocked、退出 1 |
| llm 链全不可用 | 退出 1 并把原因写进失败说明 | 3 次 | 转人工 |

## 7. 依赖
`_shared/metrics.py`（聚合与渲染）、`_shared/prompt_templates.py`（`templates/prompts/review-report.md`）、`_shared/adapter_runtime.py`（llm 链，离线走 llm.mock）、`_shared/recording.py`。

## 8. 不在本版范围
不自动修改提示词模板、不做选题决策、不发布、不给孩子或内容打分排名（R-8-16）。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：按指标出复盘与下一轮优化建议（WP-05 步骤 7） |
