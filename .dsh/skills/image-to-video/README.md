# 图生视频师（image-to-video）

<!--
文件用途：图生视频师 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-07 图生视频 / §6.5 适配器层 / R-L2-17 失败按降级链重试 / Q-7 / C-09。
对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `image-to-video` |
| 中文岗位名 | 图生视频师 |
| 归属 | 视频线 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/image-to-video/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
读取图文包清单，按镜号顺序与每镜时长合成一支竖屏草稿视频（默认 720×1280、30fps），登记产物并挂起关口②。只出草稿，不做剪辑参数调整、不做发布准备。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| task_id | 整数 | 是 | 要出草稿视频的任务号 | 编排者派单 |
| --package | 目录 | 否 | 图文包目录；缺省取最近登记的 package 产物 | 命令行/留痕表 |
| --seconds-per-shot | 小数 | 否 | 每镜秒数，默认 3.0；会被清单里的逐镜时长覆盖 | 命令行 |
| --fps | 整数 | 否 | 帧率，默认 30（合法区间 1–120） | 命令行 |
| --size | 文本 | 否 | 输出分辨率，默认 720x1280 | 命令行 |
| --out | 文件 | 否 | 输出文件；缺省 `workspace/topic-<id>/video/draft/draft-<时间戳>.mp4` | 命令行 |
| --attempts | 整数 | 否 | 最多重试次数，默认 3 | 命令行 |
| --allow-paid | 开关 | 否 | 允许计费适配器；默认关闭（C-09 零付费） | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务存在，且图文包清单可读（`role=package` 产物，清单里 count 必须等于 24）。
2. 清单里每一张图片都必须存在且非空。
3. 分辨率必须是偶数且单边 ≥ 64；帧率必须在 1–120。
4. 每镜时长必须 > 0，个数必须与图片张数一致。

## 4. 输出
- `workspace/topic-<选题号>/video/draft/draft-<时间戳>.mp4`（竖屏草稿成片）。
- `artifacts` 一条（kind=video、meta.role=draft、带实际适配器与模型版本）。
- `step_runs` 一条 ok（adapter_used 记录真实用了哪个适配器，如 video.ffmpeg）。
- 打印下一步：挂起关口② 的命令。

## 5. 完成判据（自检通过才交给下游）
- 成片可被 ffprobe 读出，时长 > 0.5s、分辨率等于目标尺寸。
- 成片时长与「每镜时长之和」偏差 ≤ 15%。
- 实际用时长的适配器已写进 step_runs 与 artifacts（能回答「到底谁生成的」）。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 图文包缺失或图不全 | 登记 step_runs(failed)，退出 2，提示先跑 asset-packager | — | — |
| 视频链全部不可用（含未实现与需付费） | 登记 step_runs(failed)，任务置 blocked，退出 1，并给出降级链快照 | 3 次 | 转人工：由 video.manual 线下合成 |
| 渲染出的成片读不出/时长偏差过大 | 登记 step_runs(failed)，任务置 blocked，退出 1 | 3 次 | 转人工检查素材与 ffmpeg 环境 |

## 7. 依赖
`_shared/adapter_runtime.py`（降级链 video：remotion → ffmpeg → external-i2v → manual）、`_shared/video.py`、`_shared/recording.py`；ffmpeg 本地二进制。

## 8. 不在本版范围
不做剪辑参数调整（auto-editor 负责）、不导出最终成片与封面（video-exporter 负责）、不做发布准备。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：图文包 → 草稿视频（WP-05 步骤 6） |
