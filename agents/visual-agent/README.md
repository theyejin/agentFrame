# 视觉线 Agent（`visual-agent`）

<!--
文件用途：视觉线环节 Agent 的定义：管什么、不管什么、派单范围与交接契约（R-L1-18）。
对应需求：R-L1-05（Agent 定义）、R-L1-06（边界）、R-L1-18（交接契约）、R-L1-19（校验失败退回）、FLOW-4~FLOW-6、Q-11（先整图后切图）。
对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html
维护提示：改职责或派单范围先改 agents/orchestrator/config.yml，再同步本文件；两侧不一致时以 config.yml 为准。
-->

| 项目 | 内容 |
| --- | --- |
| agent_id | `visual-agent` |
| 中文名 | 视觉线 Agent |
| 所属环节 | 视觉线（`entry_stage: visual` → `exit_stage: video`） |
| 可派单 Skill | `reference-image-builder`、`grid-image-builder`、`image-splitter`、`image-consistency-checker`、`hitl-gate`、`artifact-recorder` |
| 涉及关口 | 人的风格确认（`gate_visual_style`）、人工修图 / 单张返工（`gate_visual_fix`）——均**必须真人拍板** |
| 定义位置 | 本文件 + `agents/orchestrator/config.yml` |
| 版本 | v0.1.0 |

## 1. 管什么

把选定的文案变成 24 张可用独立图：先出 1–3 张风格参考图并等人在 `gate_visual_style` 确认风格；确认后按 6×4 画一张整图（Q-11：先整图后切图），再等分切成 `shot-01`…`shot-24`；切完用 `image-consistency-checker` 体检，全通过才交给视频线。中途人工可在 `gate_visual_fix` 要求单张返工。

| 序 | Skill | 子命令 | 干什么 |
| --- | --- | --- | --- |
| 1 | `reference-image-builder` | `build` | 依据选定文案出 1–3 张风格参考图（`--count`、`--style-hint`） |
| 2 | `hitl-gate` | `open` / `resolve` / `status` | 挂起风格确认关口，记录真人决议（含风格关键词） |
| 3 | `grid-image-builder` | `build` | 按 6×4 画整图（尺寸必须正好 `cols×cell_w` × `rows×cell_h`） |
| 4 | `image-splitter` | `split` | 整图等分成 `shot-01`…`shot-24` 并登记留痕 |
| 5 | `image-consistency-checker` | `check` | 数量 24、编号连续、非空、尺寸一致，并与分镜对齐 |
| 6 | `artifact-recorder` | `step-run` / `artifact` | 步骤与产物留痕 |

## 2. 不管什么

- 不管文案与分镜（文案线的活），不改文案内容；
- 不管视频合成与发布（视频线、分发数据线的活）；
- 不代答两个视觉关口：Agent 只挂待办，风格确认与返工决定必须真人给（C-10）；
- 不用「切完自己抽检一下」代替 `image-consistency-checker` 的机器判据。

## 3. 派单契约（R-L1-18）

**起手命令**：`python3 .dsh/skills/reference-image-builder/run.py build --task-id <N> --json`

### 3.1 输入校验（进场前，不通过退回编排者）

1. `tasks.stage == visual` 且 `selected_plan in 1..3`（文案已选定，R-L1-19）；
2. 分镜 `non_empty`、`count == 24` 且 `ids_continuous 1..24`；
3. 图片规格可满足：`cell_w`、`cell_h` 为正偶数（切图与整图都用它）。

### 3.2 产出物清单

| 产物 | kind | role | 说明 |
| --- | --- | --- | --- |
| 参考图 1–3 张 | `image` | `reference` | 风格基准，经 `gate_visual_style` 确认 |
| 整图 1 张 | `image` | `grid` | 6×4，尺寸正好等于 `cols×cell_w` × `rows×cell_h` |
| 独立图 24 张 | `image` | `shot` | `shot-01`…`shot-24` |
| 图片体检结论 | `report` | `image-check` | 问题清单 + 提示 |

### 3.3 完成判据（逐条机器可判定，自检通过才交给视频线）

- `count(role=shot) == 24` 且 `ids_continuous(1..24)`；
- `all_resolution_equal(role=shot)`；
- 每张 `file_exists` 且 `non_empty`；
- `tasks.stage == video`。

## 4. 失败与退回

| 情况 | 动作 |
| --- | --- |
| 风格未确认就要出整图 | `grid-image-builder` 直接退回，等 `gate_visual_style` 决议 |
| 整图尺寸不对 | 退回 `grid-image-builder` 重画（判据：整图宽高 == `cols×cell_w` / `rows×cell_h`） |
| 体检不过（缺图 / 编号断 / 尺寸不一） | 按问题清单决定重切或返工该张；单张返工走 `gate_visual_fix` 留痕 |
| 需要付费图像模型 | 就地停下（C-09），向运营人员报告；不得静默降级到付费渠道 |

## 5. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | WP-07 首版：视觉线 Agent 定义与交接契约（N012） |
