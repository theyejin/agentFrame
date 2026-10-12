# 文案线 Agent（`copy-agent`）

<!--
文件用途：文案线环节 Agent 的定义：管什么、不管什么、派单范围与交接契约（R-L1-18）。
对应需求：R-L1-05（Agent 定义）、R-L1-06（边界）、R-L1-18（交接契约）、R-L1-19（校验失败退回）、FLOW-1~FLOW-3。
对应流程图：.archify/FLOW-COPY-20261012/copy-line.html
维护提示：改职责或派单范围先改 agents/orchestrator/config.yml，再同步本文件；两侧不一致时以 config.yml 为准。
-->

| 项目 | 内容 |
| --- | --- |
| agent_id | `copy-agent` |
| 中文名 | 文案线 Agent |
| 所属环节 | 文案线（`entry_stage: copy` → `exit_stage: visual`） |
| 可派单 Skill | `copy-writer`、`storyboard-builder`、`storyboard-validator`、`hitl-gate`、`artifact-recorder` |
| 涉及关口 | 关口① 选定文案（`gate1_select_copy`，**必须真人拍板**） |
| 定义位置 | 本文件 + `agents/orchestrator/config.yml` |
| 版本 | v0.1.0 |

## 1. 管什么

把一条已建好的任务做成「选定的文案 + 24 条分镜」：先用 `copy-writer` 出 3 套不同侧重点的候选文案，挂在关口① 等运营人员三选一；选定后用 `storyboard-builder` 拆成 24 条分镜，用 `storyboard-validator` 体检，全通过才把任务交给视觉线。

| 序 | Skill | 子命令 | 干什么 |
| --- | --- | --- | --- |
| 1 | `copy-writer` | `generate` | 生成 3 套候选文案（plan_no 1–3，各含开头钩子 / 情绪强度 / 行动号召侧重） |
| 2 | `hitl-gate` | `open` / `resolve` / `status` | 挂起关口①、记录真人选择（`selected_plan`） |
| 3 | `storyboard-builder` | `build` | 把选定文案拆成 24 条分镜（画面描述 / 镜头提示 / 时长） |
| 4 | `storyboard-validator` | （无子命令） | 分镜体检：条数 24、编号连续、描述非空不重复、总时长在区间 |
| 5 | `artifact-recorder` | `step-run` / `artifact` | 步骤与产物留痕 |

## 2. 不管什么

- 不管选题（话题由运营人员或分发数据线的热点采集给出）。
- 不管出图、切图、视频、发布、指标（分别是视觉线、视频线、分发数据线的活）。
- 不代答关口①：只能 `hitl-gate open` 挂待办，`resolve` 必须带真人 actor（C-10）。
- 不跳过体检：`storyboard-validator` 不通过的稿子不得进视觉线（R-L1-19）。

## 3. 派单契约（R-L1-18）

**起手命令**：`python3 .dsh/skills/copy-writer/run.py generate --task-id <N> --json`

### 3.1 输入校验（进场前，不通过退回编排者）

1. 话题已建（`topics` 有一行）且 `tasks.stage == copy`；
2. 平台 `enum_in` `platform_templates.platform`；内容类型 `enum_in` [情绪冲突, 干货教程, 热点观点, 其他]；
3. 字数区间 `in_range`：`100 <= word_min <= word_max <= 2000`。

### 3.2 产出物清单

| 产物 | kind | role | 说明 |
| --- | --- | --- | --- |
| 候选文案 ×3 | `copy` | — | 每套 `non_empty`，字数落在任务区间内 |
| 关口① 决议 | —（`hitl_events`） | — | `gate=gate1_select_copy`，`selected_plan in 1..3` |
| 分镜 ×24 | `storyboard` | — | `ids_continuous 1..24`，每条含画面描述与时长 |

### 3.3 完成判据（逐条机器可判定，自检通过才交给视觉线）

- `count(kind=copy) == 3`；
- `selected_plan in_range 1..3`；
- `count(kind=storyboard) == 24` 且 `ids_continuous(1..24)`；
- `tasks.stage == visual`。

## 4. 失败与退回

| 情况 | 动作 |
| --- | --- |
| 字数不在区间 | `copy-writer` 按 README 失败处理重试（最多 `--attempts` 次），超限标「需人工」退回编排者 |
| 未选定文案就想拆分镜 | `storyboard-builder` 直接退回（`selected_plan` 为空或不在 1..3） |
| 分镜体检不过 | `storyboard-validator` 输出问题清单，退回 `storyboard-builder` 重拆；同一批最多 3 次 |
| 需要付费模型 | 就地停下（C-09），向运营人员报告，不得静默转付费渠道 |

## 5. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | WP-07 首版：文案线 Agent 定义与交接契约（N012） |
