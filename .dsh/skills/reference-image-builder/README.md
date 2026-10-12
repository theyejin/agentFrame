# 参考图生成师（reference-image-builder）

<!--
文件用途：参考图生成师 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-06 / R-L1-19 / §6.5 交接契约 / C-09 零付费门禁 / R-L2-14 适配器层。
对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `reference-image-builder` |
| 中文岗位名 | 参考图生成师 |
| 归属 | 视觉线 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/reference-image-builder/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
拿关口① 选定的那套文案，生成 1–3 张风格参考图，作为后面 24 张图的一致性基准。只负责参考图：不做整图、不切图、不碰视频与发布。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| task_id | 整数 | 是 | 要出参考图的任务号 | 编排者派单 |
| --count | 整数 1–3 | 否 | 参考图张数，默认 2 | 命令行 |
| --style-hint | 文本 | 否 | 风格提示；留空用默认基准（真实感、生活化、竖屏 9:16） | 命令行/编排者 |
| --cell-w/--cell-h | 整数 | 否 | 单张尺寸，默认 720×1280（竖屏） | 命令行 |
| --attempts | 整数 | 否 | 自检不过重试次数，默认 3 | 命令行 |
| --allow-paid | 开关 | 否 | 允许计费适配器（C-09 默认禁止） | 管理者显式批准 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务必须已过关口①（`tasks.selected_plan` 非空），否则直接退回并通过 `hitl-gate open --gate gate1_select_copy` 提示。
2. 选定那套文案必须真实存在且 `status='active'`（`recording.selected_copy`）。
3. 必须已有 24 条分镜且形状通过 `text_utils.check_storyboard_shape`（编号 1–24 连续、描述非空）。
4. `--count` 必须在 1–3。

## 4. 输出
- `workspace/topic-<选题号>/images/reference/reference-<时间戳>-NN.png`（同秒重跑不覆盖，自动加 -2/-3）。
- `artifacts`：每张一条（kind=image，meta.role=reference，带 model_version 与 prompt_version）。
- `step_runs`：一条 ok。
- stdout：产物清单 + 下一步命令（开风格确认关口）。

## 5. 完成判据（自检通过才交给下游）
- 参考图张数等于 `--count`；
- 每张真实非空、单边 ≥ 128 像素、竖屏（高 > 宽）；
- `model_version` 与 `prompt_version` 已登记（R-7-03）。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 链上所有适配器都失败/无密钥 | 按降级链继续；仍失败则由 `step_runs` 记 failed | 链尾 | 任务置 blocked，编排者决定重试或转人工 |
| 自检不过（张数/尺寸/方向） | 重试（`--attempts`） | 3 次 | `step_runs` 记 failed + `tasks.status='blocked'` |
| 输入校验不过（没选定文案/分镜不全） | 不调用任何适配器，直接退回 | — | 退出码 2，等上游补齐 |

## 7. 依赖
- `.dsh/skills/_shared/`：`db.py`、`recording.py`、`adapter_runtime.py`、`prompt_templates.py`、`images.py`
- `templates/prompts/image-reference.md`（提示词 `image-reference`）
- `templates/adapters/registry.json`（image 链：flow → doubao → comfyui → placeholder → manual）
- 不调用其他 skill（D-10）。

## 8. 不在本版范围
- 参考图的人工修图与风格矩阵；真实生图服务接入（本版走离线占位图 `image.placeholder`）；参考图版本对比页。

## 9. 变更记录

| 版本 | 日期 | 变更 | 讨论节点 |
| --- | --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：WP-05 步骤 5 视觉线落地 | N009 |
