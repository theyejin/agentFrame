# 汇总回报员（summary-writer）

<!--
文件用途：汇总回报员 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-05（编排者汇总对外汇报）/ §5.2.1（编排者不写文件，回报由 Skill 落盘）/ R-L1-18（回报五项齐备）。
对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
维护提示：回报只汇总已留痕的事实；缺数据写缺口，不得推算或编造数字（C-09 / Q-19）。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `summary-writer` |
| 中文岗位名 | 汇总回报员 |
| 归属 | 支撑件 / 编排者工具 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/summary-writer/run.py` |
| 执行者 | 编排者（或人用命令行） |

## 1. 职责
把一条任务的留痕汇总成一段给运营人员看的回报：当前环节、已完成步骤数、待办关口、关键产物、下一步找谁，另附指标、复盘与派单书位置。只读库、不改任何状态、不调模型。

## 2. 输入

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--task-id` | 是 | 要汇总的任务号 |
| `--period-start` `--period-end` | 否 | 指标周期（缺省取最近一期） |
| `--min-chars` | 否 | 回报最短字数，默认 120 |
| `--out-dir` | 否 | 输出目录（缺省 `workspace/topic-<选题号>/reports`） |
| `--step-no` | 否 | 步骤号（缺省自动递增） |
| `--db` | 否 | 数据库路径（缺省 .env 的 DB_PATH） |
| `--json` | 否 | JSON 输出（写在子命令前后都行） |

## 3. 输入校验（进场前，不通过直接退回）
- `file_exists`：任务存在（`task_bundle` 抛「任务不存在」即退回）；
- `enum_in`：`--min-chars >= 1`（负数或 0 视为非法）；
- 回报自检（生成后立刻判，属完成判据的一部分）：五项标签齐、字数 ≥ `--min-chars`、至少含一个数字。

## 4. 输出
- `workspace/topic-<选题号>/reports/summary-<时间戳>.md`：给人看的回报（五项 + 数据与复盘 + 派单书）；
- `workspace/topic-<选题号>/reports/summary-<时间戳>.json`：结构化结果（`stage` / `steps_ok` / `waiting_human` / `artifacts_by_kind` / `metrics` / `agent_id` / `next_command`）；
- `step_runs` 一行（`skill_id=summary-writer`）+ `artifacts` 一行（`kind=report`、`meta.role=summary`、`prompt_version=none`）；
- **不改** `tasks` / `topics` / `metrics` / `publish_records` 等任何业务表（留痕两表除外）。

## 5. 完成判据（自检通过才算完成）
- 回报含五项标签：`当前环节`、`已完成步骤`、`待办关口`、`关键产物`、`下一步找谁`；
- 字数 ≥ `--min-chars`（默认 120）且含至少一个数字；
- `file_exists(summary .md)` 且 `file_exists(summary .json)`；
- 任务状态与环节在汇总前后完全一致（只读，不得顺手推进）。

## 6. 失败处理

| 情况 | 处理 |
| --- | --- |
| 任务不存在 | 退出码 2；不写任何文件 |
| 回报太短 / 缺标签 / 没数字 | 退出码 2，逐条列出问题；不落盘（避免留下不合格回报） |
| 指标缺失 | 不报错：照实写「本期还没有指标」，并提示先跑 `metrics-collector collect` |
| 复盘报告缺失 | 不报错：写「还没有复盘报告」 |
| 任务挂在关口 | 写「有 1 个关口待人工决议」，并提示用 `hitl-gate status` 查是谁在等；**不代答** |

## 7. 依赖
- `_shared/db.py`、`_shared/recording.py`、`_shared/hitl.py`、`_shared/metrics.py`；
- 只读 `tasks` / `topics` / `step_runs` / `artifacts` / `hitl_events` / `metrics`；
- 不需要网络、不需要模型（离线可用，零费用）。

## 8. 不在本版范围
- 不做多任务/多选题的跨任务汇总（逐任务回报）；
- 不做图文化看板（那是步骤 8 的控制台）；
- 不把回报自动同步到飞书（需要的话另跑 `feishu-sync`，本版不隐式调用其他 Skill）。

## 9. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | WP-07 首版：`summarize` 子命令与回报五项判据（N012） |
