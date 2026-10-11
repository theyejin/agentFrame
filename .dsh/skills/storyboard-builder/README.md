# 分镜拆解师（storyboard-builder）

<!--
文件用途：文案线收尾工序 —— 把关口① 选定的文案拆成 24 条分镜（6×4），交给视觉线出图。
对应需求：R-L1-06（分镜拆解）、R-L1-19（24 条且编号连续）、R-L1-18（未选定文案不得往下走）、R-7-03（记录模型与提示词版本）。
对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（storyboard-builder → storyboard.json → 视觉线）
维护提示：条数 24 与网格 6×4 是跨环节契约，改动要同步 db/schema.sql 的 storyboards.shot_no 上限、templates/prompts/storyboard-split.md 与 docs/skill-roster.md。
-->

| 项 | 值 |
| -- | -- |
| skill_id | `storyboard-builder` |
| 中文岗位名 | 分镜拆解师 |
| 归属 | 文案线 |
| 版本 | `0.1.0` |
| 入口文件 | `run.py` |
| 执行者 | 由编排者派单调用（关口① 通过后） |

## 1. 职责

输入「已选定的文案 + 每条时长 + 风格提示」→ 输出 24 条分镜（画面描述 / 镜头提示 / 时长），写库与产物，并把任务交给视觉线。它是文案与画面之间的翻译器：分镜要能直接拿去出参考图与整图。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| ---- | ---- | ---- | ---- | ---- |
| `task_id` | int | 是 | 任务编号，必须已有 `selected_plan` | 编排者派单 |
| `--shot-seconds` | float | 否 | 每条分镜时长（秒），默认 3（24 条 = 72 秒） | 调用方 |
| `--style-hint` | str | 否 | 画面风格提示 | 调用方 / 平台模板 |
| `--out` | path | 否 | 产出目录，缺省 `workspace/topic-<选题号>/storyboard` | 调用方 |
| `--attempts` | int | 否 | 不合格重试次数，默认 3 | 调用方 |

## 3. 输入校验（进场前，不通过直接退回）

- [ ] 任务 `stage` ∈ {copy, visual}
- [ ] `tasks.selected_plan` 已定（否则提示先去关口① 选文案）
- [ ] 选定的那套 `copy_variants` 存在且 `status = 'active'`、`body` 非空

退回时返回：`{"ok": false, "reason": "<缺什么>"}`，步骤记 `failed`、任务置 `blocked`（退出码 2）。

## 4. 输出

| 字段 | 类型 | 说明 | 落库位置 |
| ---- | ---- | ---- | -------- |
| 24 条分镜 | rows | `shot_no` 01–24、`scene_text`、`camera_note`、`duration_s` | `storyboards`（按任务整体替换） |
| 本次生成记录 | file | 含 24 条、网格、时长、模型与提示词版本 | `storyboard-<时间戳>.json` |
| 人读版 | file | `NN \| 画面描述 \| 镜头提示` 逐行 | `storyboard.md` |
| 交接 | field | 任务 `stage` 置为 `visual` | `tasks.stage` |

## 5. 完成判据（自检通过才交给下游）

- [ ] 正好 24 条，编号 1–24 连续
- [ ] 每条画面描述非空、前 20 字不重复
- [ ] 总时长 = 24 × 每条时长
- [ ] 产物登记带 `model_version` 与 `prompt_version`

自检失败返回：`{"ok": false, "failed": [...], "retry": <已试次数>}`。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| -------- | ---- | ---- | ------ |
| 模型/服务不可用 | 由 llm-adapter 降级链换下一个（最终转人工兜底） | 每条链一次 | 本次生成失败 |
| 生成不合格（条数/编号/重复/时长） | 重新生成 | `--attempts`，默认 3 | 步骤记 `failed` + 任务 `blocked`，由编排者决定重试或转人工 |
| 未过关口① | 直接拒绝，不调用模型 | — | 提示先去关口① 选定文案 |

## 7. 依赖

- 统一接口：`llm-adapter`
- 提示词：`prompt-registry`（`storyboard-split` v2）
- 留痕：`_shared/recording.py`
- 复检工具：`storyboard-validator`（人工或流程外复检同一份文件）
- 样例：`templates/mock/storyboard-split.v2.txt`

## 8. 不在本版范围

- 不做分镜配乐/旁白文案
- 不做参考图提示词（视觉线 `reference-image-builder` 负责）
- 不做分镜级时长的人工微调界面（视频线关口② 负责整体参数）

## 9. 变更记录

| 日期 | 变更 | 来源 |
| ---- | ---- | ---- |
| 2026-10-12 | 首版：24 条固定契约 + 前置关口① 卡口，提示词升到 v2 | N008 |
