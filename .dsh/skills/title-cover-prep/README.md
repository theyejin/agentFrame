# 发布准备师（title-cover-prep）

<!--
文件用途：发布准备师 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-8-01 平台预设模板 / R-L1-09 发布前信息准备 / Q-18 / C-01 红线 / C-09。
对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html 与 .archify/FLOW-PUBLISH-20261012/publish-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `title-cover-prep` |
| 中文岗位名 | 发布准备师 |
| 归属 | 分发数据线 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/title-cover-prep/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
读平台预设模板，渲染 `publish-prep` 提示词并调用文本模型，产出标题候选、标签与封面文案，做红线自检后写成 JSON + Markdown。只准备信息，不登录、不填写表单、不发布。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| task_id | 整数 | 是 | 要准备发布信息的任务号 | 编排者派单 |
| --platform | 文本 | 否 | 平台名；缺省取任务 `target_platform`（抖音/小红书/B站/视频号） | 命令行/任务 |
| --out | 目录 | 否 | 输出目录；缺省 `workspace/topic-<id>/publish/prep` | 命令行 |
| --attempts | 整数 | 否 | 最多重试次数，默认 3 | 命令行 |
| --allow-paid | 开关 | 否 | 允许计费适配器；默认关闭（C-09 零付费） | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务存在，且有成片产物（`role=final`）——发布信息必须对应一支真成片。
2. 平台必须在 `platform_templates` 里有预设模板，否则列出已配置平台并退回。
3. 必须能取到关口① 选定的那套文案（标题与摘录），否则退回文案线。
4. 提示词 `publish-prep` 的变量必须齐（缺变量直接退回）。

## 4. 输出
- `workspace/topic-<选题号>/publish/prep/prep-<时间戳>.json`：平台、标题写法、字数区间、标签数、封面比例、三条标题、标签、封面文案、提示词版本、适配器与模型版本、对应成片路径。
- `…/prep-<时间戳>.md`：给人在关口③ 核对的可读版。
- `artifacts` 一条（kind=manifest、meta.role=publish-prep，带 prompt_version）。
- `step_runs` 一条 ok；`tasks.stage` 保持/推进到 `publish`。

## 5. 完成判据（自检通过才交给下游）
- 标题正好 3 条，且每条 ≤ 30 字、不含绝对化用语（C-01）。
- 标签数量等于该平台模板的 `tag_count`。
- 封面文案非空且 ≤ 12 字。
- 产物里记录了 prompt_version 与实际适配器（可回答「这条标题是哪版提示词生成的」）。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 没有成片 / 平台无模板 / 取不到选定文案 | 登记 step_runs(failed)，退出 2 并指出先跑哪个上游 skill | — | — |
| 模型调用失败或连续自检不过 | 登记 step_runs(failed)，任务置 blocked，退出 1 | 3 次 | 转人工改提示词或手工写发布信息 |
| 命中绝对化用语红线 | 登记 step_runs(failed) 并说明命中了哪个词，退出 1 | 3 次 | 转人工改写标题 |

## 7. 依赖
`_shared/prompt_templates.py`（publish-prep v1）、`_shared/adapter_runtime.py`（llm 链：mock → deepseek(计费) → manual）、`_shared/text_utils.py`（解析与红线检查）、`_shared/recording.py`；平台模板表 `platform_templates`。

## 8. 不在本版范围
不登录平台、不填写表单、不点击发布（C-08：自动流程只填不发）、不采集数据。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：平台模板 → 标题/标签/封面（WP-05 步骤 6） |
