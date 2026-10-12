# 成片导出师（video-exporter）

<!--
文件用途：成片导出师 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-08 导出成片 / R-7-03 产物登记模型版本 / §6.5 / Q-7 / C-09。
对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `video-exporter` |
| 中文岗位名 | 成片导出师 |
| 归属 | 视频线 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/video-exporter/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
校验剪辑版产物，复制为最终成片，用 ffmpeg 抽取封面帧，登记两条产物并把任务阶段推进到 `publish`。不做发布准备、不自动发布。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| task_id | 整数 | 是 | 要导出的任务号 | 编排者派单 |
| --edited | 文件 | 否 | 剪辑版路径；缺省取最近登记的 edited 产物 | 命令行/留痕表 |
| --cover-at | 小数 | 否 | 抽封面帧的时间点（秒），默认 1.0 | 命令行 |
| --out-dir | 目录 | 否 | 输出目录；缺省 `workspace/topic-<id>/video/final` | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务存在，且能找到剪辑版产物（`role=edited`）或显式 `--edited` 文件。
2. 剪辑版文件必须真实存在、非空。
3. 本机必须能找到 ffmpeg（找不到就提示降级到 `video.manual`）。

## 4. 输出
- `workspace/topic-<选题号>/video/final/final-<时间戳>.mp4`（最终成片）。
- `…/cover-<时间戳>.png`（封面帧）。
- `artifacts` 两条：kind=video（meta.role=final）、kind=image（meta.role=cover）。
- `step_runs` 一条 ok（adapter_used=video.ffmpeg）；`tasks.stage` 推进到 `publish`。

## 5. 完成判据（自检通过才交给下游）
- 成片可被 ffprobe 读出、时长 > 0.5s、分辨率与剪辑版一致。
- 封面帧文件非空、能被 Pillow/ffprobe 识别。
- 产物登记带模斯版本字段（final=ffmpeg-render-v1、cover=ffmpeg-cover-v1）。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 没有剪辑版产物 | 登记 step_runs(failed)，退出 2，提示先跑 auto-editor | — | — |
| 复制或抽帧失败 | 登记 step_runs(failed)，任务置 blocked，退出 1 | 3 次 | 转人工检查磁盘与 ffmpeg 环境 |

## 7. 依赖
`_shared/video.py`（ffprobe 校验与抽帧）、`_shared/recording.py`；ffmpeg 本地二进制。

## 8. 不在本版范围
不做剪辑调整、不做发布准备、不自动发布（C-08 红线：发布必须人工授权）。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：成片定稿 + 封面帧（WP-05 步骤 6） |
