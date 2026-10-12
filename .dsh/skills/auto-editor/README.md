# 自动剪辑师（auto-editor）

<!--
文件用途：自动剪辑师 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-08 自动剪辑可人工干预 / §8.3 关口② 调整态 / R-L2-17 / Q-7 / C-09。
对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `auto-editor` |
| 中文岗位名 | 自动剪辑师 |
| 归属 | 视频线 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/auto-editor/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
读关口② 的决议（或命令行参数），按镜头顺序、每镜时长与素材替换渲染一版剪辑成片，并把生效参数写成 JSON 留痕。不做导出成片、不做发布准备。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| task_id | 整数 | 是 | 要剪辑的任务号 | 编排者派单 |
| --from-hitl | 开关 | 否 | 读该任务最近一次已决议的关口② 事件（confirm=原样 / adjust=按 diff_json） | 命令行 |
| --order | 文本 | 否 | 镜头顺序，如 `1,2,3…24`；必须 1–24 不重不漏 | 命令行/关口② |
| --durations | 文本 | 否 | 个别镜头时长覆盖，如 `1:3,5:2.5` | 命令行/关口② |
| --replace | 文本 | 否 | 单张素材替换，如 `7=workspace/…/shot-07.png` | 命令行/关口② |
| --draft | 文件 | 否 | 草稿视频路径；缺省取最近登记的 draft 产物 | 命令行/留痕表 |
| --fps/--size | 整数/文本 | 否 | 帧率 30、分辨率 720x1280 | 命令行 |
| --out | 文件 | 否 | 输出文件；缺省 `workspace/topic-<id>/video/edited/edited-<时间戳>.mp4` | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务存在，且最近一代独立图正好 24 张（先跑 image-splitter）。
2. `--order` 必须是 1–24 的一个排列（不重不漏）。
3. `--durations` 的镜号必须在 1–24、秒数必须 > 0。
4. `--replace` 给的替换图必须真实存在；`--from-hitl` 时任务必须有已决议的关口② 记录。

## 4. 输出
- `workspace/topic-<选题号>/video/edited/edited-<时间戳>.mp4`（剪辑版成片）。
- `…/edit-params-<时间戳>.json`：生效的顺序、逐镜时长、替换明细、参数来源（hitl/cli）、所用草稿。
- `artifacts` 两条：kind=video（meta.role=edited）与 kind=manifest（meta.role=edit-params）。
- `step_runs` 一条 ok。任务阶段保持 `video`。

## 5. 完成判据（自检通过才交给下游）
- 顺序确实是 1–24 的排列、每镜时长都 > 0、替换素材都已生效。
- 成片可读、分辨率等于目标尺寸、时长与参数计划偏差 ≤ 15%。
- 参数留痕能回答「谁改了哪几镜、改成什么」，且来源标注为 hitl 或 cli。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 关口② 没有已决议记录却给了 `--from-hitl` | 登记 step_runs(failed)，退出 2 并提示先 open/resolve 关口② | — | — |
| 顺序不合法 / 替换图缺失 | 登记 step_runs(failed)，退出 2 | — | — |
| 渲染失败或自检不过 | 登记 step_runs(failed)，任务置 blocked，退出 1 | 3 次 | 转人工用 video.manual 线下剪辑 |

## 7. 依赖
`_shared/adapter_runtime.py`（video 链）、`_shared/video.py`、`_shared/hitl.py`、`_shared/recording.py`；ffmpeg 本地二进制。

## 8. 不在本版范围
不做导出最终成片与封面（video-exporter）、不生成标题标签封面文案（title-cover-prep）、不发布。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：关口② 参数化剪辑（WP-05 步骤 6） |
