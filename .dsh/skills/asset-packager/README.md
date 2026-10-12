# 素材打包员（asset-packager）

<!--
文件用途：素材打包员 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-07 图文打包 / R-L1-19 一一对应 / §6.5 交接契约 / C-09。
对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `asset-packager` |
| 中文岗位名 | 素材打包员 |
| 归属 | 视频线 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/asset-packager/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
把选定文案、24 条分镜与 24 张独立图按镜号顺序打包成一个工程文件夹（图片 + 文案 + manifest.json），作为图生视频的唯一输入。不调用任何外部服务、不改图片内容、不做视频。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| task_id | 整数 | 是 | 要打包的任务号 | 编排者派单 |
| --out | 目录 | 否 | 输出目录；缺省 `workspace/topic-<id>/video/package/<时间戳>` | 命令行 |
| --shot-seconds | 小数 | 否 | 每镜默认时长（秒），默认 3.0，写进清单供下游参考 | 命令行 |
| --step-no | 整数 | 否 | 步骤序号；缺省自动取下一个 | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 关口① 必须已选定文案（`tasks.selected_plan` 有值且该套 `status=active`），否则退回。
2. 分镜必须正好 24 条（`storyboards` 表按 shot_no 升序），否则退回文案线。
3. 独立图必须是最近一代（`latest_shots`）且正好 24 张、文件都存在，否则退回视觉线。
4. 每张独立图必须非空（0 字节视为缺失）。

## 4. 输出
- `workspace/topic-<选题号>/video/package/<时间戳>/images/shot-01.png … shot-24.png`（按镜号复制）。
- `…/copy.md`：关口① 选定的那套文案正文。
- `…/manifest.json`：task/topic/platform/content_type/plan_no/focus/count/shot_seconds/total_seconds/generated_at + shots[{shot_no,image,source_image,scene_text,duration_s}]（路径一律写仓库相对路径，便于换机器后仍可解析）。
- `artifacts` 一条（kind=manifest、meta.role=package、model_version=local、prompt_version=none）；`step_runs` 一条 ok。
- 任务阶段保持 `video` 不变（打包不改阶段）。

## 5. 完成判据（自检通过才交给下游）
- 清单里的镜号是 1–24 连续、不重不漏，且条数等于分镜条数与图片张数。
- 清单里每一张图片路径都真实存在且非空。
- 总时长 = Σ 每镜时长，可被下游直接使用。
- 同秒重复执行不会覆盖上一代（目录自动加 -2/-3）。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 任务不存在 | 报错并退出 2 | — | — |
| 未过关口① / 分镜数不对 / 图片缺失或不齐 | 登记 step_runs(failed)，退出 2，提示先跑哪个上游 skill | — | 由编排者派人补齐上游 |
| 打包过程写盘失败 | 登记 step_runs(failed)，任务置 blocked，退出 1 | 3 次 | 转人工检查磁盘与权限 |

## 7. 依赖
`_shared/recording.py`（任务与产物、最近一代切图清单）、`_shared/db.py`；不依赖任何外部服务与密钥。

## 8. 不在本版范围
不做图片质检（那是 image-consistency-checker）、不改图、不做视频、不管发布。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：图文打包 + manifest 清单（WP-05 步骤 6） |
