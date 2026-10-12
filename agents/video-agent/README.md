# 视频线 Agent（`video-agent`）

<!--
文件用途：视频线环节 Agent 的定义：管什么、不管什么、派单范围与交接契约（R-L1-18）。
对应需求：R-L1-05（Agent 定义）、R-L1-06（边界）、R-L1-18（交接契约）、R-L1-19（校验失败退回）、FLOW-7~FLOW-10。
对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html
维护提示：改职责或派单范围先改 agents/orchestrator/config.yml，再同步本文件；两侧不一致时以 config.yml 为准。
-->

| 项目 | 内容 |
| --- | --- |
| agent_id | `video-agent` |
| 中文名 | 视频线 Agent |
| 所属环节 | 视频线（`entry_stage: video` → `exit_stage: publish`） |
| 可派单 Skill | `asset-packager`、`image-to-video`、`auto-editor`、`video-exporter`、`title-cover-prep`、`hitl-gate`、`artifact-recorder` |
| 涉及关口 | 关口② 剪辑干预（`gate2_edit_video`，**必须真人拍板**） |
| 定义位置 | 本文件 + `agents/orchestrator/config.yml` |
| 版本 | v0.1.0 |

## 1. 管什么

把 24 张独立图做成「成片 + 封面 + 发布准备」：先打包成视频线工程（24 图与 24 分镜一一对应），合成草稿视频，挂关口② 由真人给剪辑参数（镜头顺序 / 每镜时长 / 单张替换），按参数渲染剪辑版并留痕，导出成片与封面帧，最后按平台模板准备三条标题候选、标签与封面文案。

| 序 | Skill | 子命令 | 干什么 |
| --- | --- | --- | --- |
| 1 | `asset-packager` | `pack` | 打包图文工程（`--shot-seconds` 定每镜时长） |
| 2 | `image-to-video` | `build` | 合成草稿视频（Remotion 首选、`video.ffmpeg` 兜底） |
| 3 | `hitl-gate` | `open` / `resolve` / `status` | 挂起关口②，记录真人的 `order` / `durations` / `replacements` |
| 4 | `auto-editor` | `edit` | 按参数渲染剪辑版 + 写 `edit-params` 参数留痕 |
| 5 | `video-exporter` | `export` | 定稿成片（`role=final`）+ 抽帧封面（`role=cover`），推进到 `publish` |
| 6 | `title-cover-prep` | `prepare` | 按平台模板出三条标题候选、标签与封面文案（`role=publish-prep`） |
| 7 | `artifact-recorder` | `step-run` / `artifact` | 步骤与产物留痕 |

## 2. 不管什么

- 不管出图与切图（视觉线的活）；
- 不管发布与指标（分发数据线的活）——本环节只做到「发布准备」为止；
- 不代答关口②：剪辑参数必须真人给；Agent 不得自行「顺手调整」顺序或时长；
- 不依赖付费合成服务：Remotion 不可用时降级到本地 `video.ffmpeg`（D-13），付费图生视频服务不得静默启用。

## 3. 派单契约（R-L1-18）

**起手命令**：`python3 .dsh/skills/asset-packager/run.py pack --task-id <N> --json`

### 3.1 输入校验（进场前，不通过退回编排者）

1. `tasks.stage == video`；
2. 24 张独立图齐备：`count(role=shot) == 24`、`ids_continuous 1..24`、`all_resolution_equal`、每张 `non_empty`；
3. 分镜 24 条与图片一一对应（`storyboard` 与本批 `shot` 数量一致）。

### 3.2 产出物清单

| 产物 | kind | role | 说明 |
| --- | --- | --- | --- |
| 图文包 | `manifest` | `package` | 含 24 图 + `copy.md` + `manifest.json` |
| 草稿视频 | `video` | `draft` | 时长与计划偏差 ≤15% |
| 关口② 决议 | —（`hitl_events`） | — | `gate=gate2_edit_video` |
| 剪辑版 | `video` | `edited` | 按真人参数渲染 |
| 剪辑参数留痕 | `manifest` | `edit-params` | `order` / `durations` / `replacements` 原样记录 |
| 成片 | `video` | `final` | `model_version=ffmpeg-render-v1` |
| 封面 | `image` | `cover` | ffmpeg 抽帧，与成片成对出现 |
| 发布准备 | `manifest` | `publish-prep` | 标题候选 ×3、标签、封面文案 |

### 3.3 完成判据（逐条机器可判定，自检通过才交给分发数据线）

- `file_exists(role=final)` 且 `file_exists(role=cover)`（成片与封面成对，缺一不可）；
- 成片时长 `in_range 0.5..1800` 秒；
- `file_exists(role=publish-prep)`；
- `tasks.stage == publish`。

## 4. 失败与退回

| 情况 | 动作 |
| --- | --- |
| 图片缺张 / 编号断号 | 退回视觉线补齐（R-L1-19），不得用重复图凑数 |
| 草稿时长偏差 >15% | `image-to-video` 按 README 重试；仍不过标「需人工」退回编排者 |
| 关口② 被退回（reject） | 任务留在 `video`，按真人意见重出草稿或改参数 |
| 导出后缺封面 | 判定失败：成片与封面必须成对留痕，不得只交成片 |
| 需要付费合成 | 就地停下（C-09），向运营人员报告 |

## 5. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | WP-07 首版：视频线 Agent 定义与交接契约（N012） |
