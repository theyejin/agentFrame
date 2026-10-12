# 人工关口器（hitl-gate）

<!--
文件用途：三类形态、五个关口点（选定文案 / 风格确认 / 单张返工 / 剪辑干预 / 发布授权）的开启、决议与留痕，让流水线只在真人拍板处等待。
对应需求：§8.3 三类 HITL 形态、R-8-03（记录操作人）、C-08（未授权不发布）、C-01（发布前人工确认）。
对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（关口① 选定文案）、.archify/FLOW-VIDEO-20261012/video-line.html（关口②）、.archify/FLOW-PUBLISH-20261012/publish-line.html（关口③）
维护提示：关口枚举（gate1_select_copy / gate_visual_style / gate_visual_fix / gate2_edit_video / gate3_publish_auth）改动要同步 db/schema.sql 的 hitl_events.gate（含迁移 db/migrations/0002_add_visual_gates.sql）、docs/skill-roster.md 与本文件。
-->

| 项 | 值 |
| -- | -- |
| skill_id | `hitl-gate` |
| 中文岗位名 | 人工关口器 |
| 归属 | 基础设施（支撑件） |
| 版本 | `0.1.0` |
| 入口文件 | `run.py` |
| 执行者 | 各环节结束时调用 `open`；运营人员处理时调用 `resolve` |

## 1. 职责

输入「哪个任务、哪个关口、谁做的决定」→ 把任务状态在 `running` 与 `waiting_human` 之间正确切换，并把决定内容（当时的待确认快照 + 调整差异）写进 `hitl_events`。三类关口的形态不同：**选择**（关口① 三选一）、**调整**（关口② 改参数）、**授权**（关口③ 允许用已登录会话发出去）。

它不产生任何内容，也不替人做决定；它只保证「流水线不会在没人拍板时自己往下走」，以及「事后能查出是谁拍的板」。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| ---- | ---- | ---- | ---- | ---- |
| `--task-id` | int | 是 | 任务编号 | 编排者 |
| `--gate` | enum | 是 | `gate1_select_copy` / `gate_visual_style` / `gate_visual_fix` / `gate2_edit_video` / `gate3_publish_auth` | 规格 §8.3 |
| `--action` | enum | 决议时是 | `confirm` / `reject` / `adjust` | 运营人员 |
| `--actor` | str | 决议时是 | 谁做的决定（R-8-03） | 运营人员 |
| `--plan-no` | int | 关口① confirm 时是 | 选定第几套（1/2/3） | 运营人员 |
| `--snapshot-json` `--diff-json` | JSON | 否 | 当时的内容快照、调整前后差异 | 调用方 |

## 3. 输入校验（进场前，不通过直接退回）

- [ ] `--gate` 必须是三个枚举之一
- [ ] `--action` 必须是 `confirm` / `reject` / `adjust` 之一
- [ ] `--actor` 不能为空（要能回答「谁点的」）
- [ ] 决议前任务状态必须是 `waiting_human`（即必须先 `open`）
- [ ] 关口① `confirm` 必须给 `--plan-no`，且该套文案存在且 `status = 'active'`
- [ ] `gate_visual_fix` 的 confirm/adjust 必须用 `--diff-json` 给出 `shot_nos`（哪几张要重做），否则拒绝（返工范围不可追溯）

退回时返回：`{"ok": false, "reason": "<不合法原因>"}`（退出码 2）。

## 4. 输出

| 字段 | 类型 | 说明 | 落库位置 |
| ---- | ---- | ---- | -------- |
| 事件 id | int | 本次决议的行号 | `hitl_events` |
| 任务状态 | str | 决议后回到 `running` | `tasks.status` |
| 选定方案 | int | 仅关口① confirm | `tasks.selected_plan` + `selected_at` |

## 5. 完成判据（自检通过才交给下游）

- [ ] `hitl_events` 里能找到该事件，且 `actor` 非空
- [ ] 关口① 确认后 `tasks.selected_plan` 等于所给 `plan_no`
- [ ] 决议后任务状态是 `running`（流水线可以继续）

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| -------- | ---- | ---- | ------ |
| 任务不在 `waiting_human` 就决议 | 拒绝并提示先 `open` | — | 由编排者补开关口 |
| 关口① 给了一个不存在/已失效的套号 | 拒绝，要求重新选择 | — | 重新生成文案后再选 |
| 同一关口被重复决议 | 允许：每次都是新事件，历史保留 | — | 人工核对 `list` 输出 |

## 7. 依赖

- 共享库：`_shared/hitl.py`（关口逻辑）、`_shared/recording.py`（任务状态写入）

## 8. 不在本版范围

- 不做通知推送（邮件/IM）
- 不做超时自动通过：**真人必须显式点击**，不会被「等太久」自动放行
- 不做权限校验（首版靠 `actor` 字段留痕，Q-17）

## 9. 变更记录

| 日期 | 变更 | 来源 |
| ---- | ---- | ---- |
| 2026-10-12 | 首版：三类关口 open/resolve/list/status | N008 |
| 2026-10-12 | v0.2.0：关口枚举扩为五个（新增 gate_visual_style、gate_visual_fix） | N009 |
