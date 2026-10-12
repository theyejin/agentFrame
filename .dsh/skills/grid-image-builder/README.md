# 整图生成师（grid-image-builder）

<!--
文件用途：整图生成师 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-06 / R-L1-19 / §6.5 交接契约 / C-09 零付费门禁 / R-L2-14 适配器层。
对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `grid-image-builder` |
| 中文岗位名 | 整图生成师 |
| 归属 | 视觉线 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/grid-image-builder/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
把 24 条分镜一次性画进一张 6×4 的整图，保证 24 个格子与 24 条分镜一一对应；不做切分、不做参考图、不做视频。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| task_id | 整数 | 是 | 要出整图的任务号 | 编排者派单 |
| --cols/--rows | 整数 | 否 | 网格行列，默认 6×4 | 命令行（规格 Q-11） |
| --cell-w/--cell-h | 整数 | 否 | 单格尺寸，默认 320×320（单格至少 32） | 命令行 |
| --style-hint | 文本 | 否 | 风格提示；留空用默认基准 | 命令行/编排者 |
| --attempts | 整数 | 否 | 自检不过重试次数，默认 3 | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务必须已过关口①（有 `selected_plan`）。
2. 数据库分镜条数必须等于 `cols×rows`（默认 24）且形状通过体检。
3. 行列数与单格尺寸必须为正，单格每边 ≥ 32 像素。

## 4. 输出
- `workspace/topic-<选题号>/images/grid/grid-<时间戳>.png`。
- `artifacts`：一条（kind=image，meta.role=grid，含 cols/rows/cell/cells/width/height）。
- `step_runs`：一条 ok。
- stdout：整图路径与尺寸 + 下一步（切分）。

## 5. 完成判据（自检通过才交给下游）
- 整图真实存在且非空；
- 尺寸必须正好等于 `(cols×cell_w) × (rows×cell_h)`，差一个像素都不通过；
- 格数等于分镜条数；`model_version` 与 `prompt_version` 已登记。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 出图失败 | 按降级链继续，仍失败则记 failed | 链尾 | 任务置 blocked |
| 尺寸不符（模型自作主张改了比例） | 重试（`--attempts`） | 3 次 | `step_runs` 记 failed + `tasks.status='blocked'` |
| 分镜数量与格数不一致 | 进场就退回，不调用适配器 | — | 退出码 2，先修分镜 |

## 7. 依赖
- `.dsh/skills/_shared/`：`db.py`、`recording.py`、`adapter_runtime.py`、`prompt_templates.py`、`images.py`、`text_utils.py`
- `templates/prompts/image-grid.md`（提示词 `image-grid`）
- `templates/adapters/registry.json`（image 链）
- 上游：`storyboard-builder`（分镜）；下游：`image-splitter`（切分）。不直接调用它们（D-10）。

## 8. 不在本版范围
- 整图内单格重画；多风格整图对比；真实生图服务接入（本版走 `image.placeholder` 离线占位）。

## 9. 变更记录

| 版本 | 日期 | 变更 | 讨论节点 |
| --- | --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：WP-05 步骤 5 视觉线落地 | N009 |
