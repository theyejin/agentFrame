# 切图师（image-splitter）

<!--
文件用途：切图师 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-06 / R-L1-19 / §6.5 交接契约 / C-09 零付费门禁 / R-L2-14 适配器层。
对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `image-splitter` |
| 中文岗位名 | 切图师 |
| 归属 | 视觉线 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/image-splitter/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
把整图按行列等分成 24 张独立图片，命名连续，写清单 `latest.json`，把任务阶段推进到 `video`。不做体检判定、不做视频。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| task_id | 整数 | 是 | 要切图的任务号 | 编排者派单 |
| --grid | 路径 | 否 | 整图路径；缺省取最近登记的 grid 产物 | 命令行/留痕表 |
| --cols/--rows | 整数 | 否 | 行列，默认 6×4 | 命令行 |
| --out | 目录 | 否 | 输出目录；缺省 `workspace/topic-<id>/images/shots/<时间戳>` | 命令行 |
| --prefix/--start-no | 文本/整数 | 否 | 文件名前缀与起始编号，默认 shot / 1 | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务必须有 24 条形状合格的分镜（否则先退回文案线）。
2. 整图必须存在、可读，且宽高分别能被 cols、rows 整除（否则无法等分，直接退回）。
3. 没有整图产物时给出「先跑 grid-image-builder」的明确提示。

## 4. 输出
- `workspace/topic-<选题号>/images/shots/<时间戳>/shot-01.png … shot-24.png`。
- `…/latest.json` 清单：每张的编号、路径、宽高、字节数与对应分镜描述。
- `artifacts`：24 张各一条（meta.role=shot、shot_no）+ 清单一条（meta.role=shots-manifest）。
- `step_runs` 一条 ok；`tasks.stage` 推进到 `video`。

## 5. 完成判据（自检通过才交给下游）
- 张数正好等于 `cols×rows`（默认 24），命名连续从 `--start-no` 起；
- 每张非空、单边 ≥ 64 像素、同代尺寸一致；
- 清单文件已写出且条数与图片一致。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 切分适配器失败 | 按 split 链继续，仍失败记 failed | 链尾 | 任务置 blocked |
| 切出来的张数/尺寸不合规 | 记 failed（本版不自动重试，整图重出更划算） | — | `tasks.status='blocked'`，由编排者决定重出整图 |
| 整图尺寸不能整除 | 进场退回，不产生半张图 | — | 退出码 2，先重出整图 |

## 7. 依赖
- `.dsh/skills/_shared/`：`db.py`、`recording.py`、`adapter_runtime.py`、`images.py`、`text_utils.py`
- `templates/adapters/registry.json`（split 链：grid-slicer → manual）
- 上游 `grid-image-builder`；下游 `image-consistency-checker`、`asset-packager`。不直接调用它们（D-10）。

## 8. 不在本版范围
- 重叠区域裁切、去白边、超分；单张重切（本版重切即重切一代）；真实切分服务接入。

## 9. 变更记录

| 版本 | 日期 | 变更 | 讨论节点 |
| --- | --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：WP-05 步骤 5 视觉线落地 | N009 |
