# 文案写手（copy-writer）

<!--
文件用途：文案线第一道工序 —— 一条选题生成 3 套不同侧重点的候选文案（hook / emotion / cta），产出后停在关口① 等人选择。
对应需求：R-L1-05（文案生成）、F-01（对话框 Prompt）、F-02（字数范围）、F-03（类型）、R-L1-19（3 套且侧重互不重复）、R-7-03（记录模型与提示词版本）、R-L1-18（校验失败必退回）。
对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（copy-writer → 3 套候选文案 → 关口①）
维护提示：侧重枚举改动要同步 db/schema.sql 的 copy_variants.focus、templates/prompts/copy-generate.md 与 docs/skill-roster.md；样例文案在 templates/mock/copy-generate.v2.txt。
-->

| 项 | 值 |
| -- | -- |
| skill_id | `copy-writer` |
| 中文岗位名 | 文案写手 |
| 归属 | 文案线 |
| 版本 | `0.1.0` |
| 入口文件 | `run.py` |
| 执行者 | 由编排者派单调用（一条任务一次） |

## 1. 职责

输入一条选题与要求（对话框 Prompt、字数区间、类型、目标平台）→ 生成 3 套**侧重点不同**的候选文案 → 自检（套数、套号、侧重、字数）→ 写库与产物 → 把任务停在关口①。它只负责「给出可比较的三种写法」，不做最终选择。

三套侧重固定为：`hook`（开头钩子）、`emotion`（情绪强度）、`cta`（行动号召）。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| ---- | ---- | ---- | ---- | ---- |
| `task_id` | int | 是 | 任务编号（库里带 `prompt` / `word_min` / `word_max` / `content_type` / `target_platform`） | 编排者派单 |
| `--out` | path | 否 | 产出目录，缺省 `workspace/topic-<选题号>/copy` | 调用方 |
| `--attempts` | int | 否 | 不合格重试次数，默认 3 | 调用方 |
| `--allow-paid` | flag | 否 | 显式批准计费模型（C-09，默认不批） | 运营人员 |
| 选题标题与简述 | str | 是 | `topics.title` 必填；`topics.summary` 与 `tasks.prompt` 至少要有一个 | 运营人员 |

## 3. 输入校验（进场前，不通过直接退回）

- [ ] 任务存在且 `tasks.stage = 'copy'`
- [ ] `topics.title` 非空
- [ ] `content_type` ∈ {情绪冲突, 干货教程, 热点观点, 其他}
- [ ] `0 < word_min ≤ word_max`
- [ ] `tasks.prompt` 与 `topics.summary` 至少有一个非空（对话框 Prompt 是 F-01 的主输入）

退回时返回：`{"ok": false, "reason": "<缺什么>"}`，同时把步骤记为 `failed`、任务置 `blocked`（退出码 2）。

## 4. 输出

| 字段 | 类型 | 说明 | 落库位置 |
| ---- | ---- | ---- | -------- |
| 3 套文案 | rows | `plan_no` 1/2/3、`focus`、`focus_note`、`title`、`body`、`word_count` | `copy_variants`（`UNIQUE(task_id, plan_no)`，重生成覆盖同套号） |
| 本次生成记录 | file | 含 3 套正文、模型与提示词版本、生成时间 | `variants-<时间戳>.json` |
| 人读版 | file | 三套并排看清侧重点 | `variants.md` |
| 步骤与产物留痕 | rows | 用了哪个适配器、产出文件与哈希 | `step_runs` / `artifacts` |

## 5. 完成判据（自检通过才交给下游）

- [ ] 正好 3 套，套号为 1/2/3
- [ ] 三套侧重正好是 `hook` / `emotion` / `cta`，互不重复
- [ ] 每套正文非空且字数（去空白字符数，含标点）落在 `word_min`–`word_max` 内
- [ ] `artifacts` 里每份产物都带 `model_version` 与 `prompt_version`

自检失败返回：`{"ok": false, "failed": [...], "retry": <已试次数>}`。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| -------- | ---- | ---- | ------ |
| 模型/服务不可用 | 由 llm-adapter 按降级链换下一个（最终转人工兜底） | 每条链一次 | 本次生成失败 |
| 生成不合格（套数/侧重/字数） | 重新生成 | `--attempts`，默认 3 | 步骤记 `failed` + 任务置 `blocked`，写明原因，由编排者决定重试或转人工 |
| 输入校验不通过 | 立刻退回，不调用模型 | — | 任务 `blocked`，等人修输入 |

## 7. 依赖

- 统一接口：`llm-adapter`（业务代码不出现具体服务名，R-L2-14）
- 提示词：`prompt-registry`（`copy-generate` v2，记录 `prompt_version`）
- 留痕：`_shared/recording.py`（`step_runs` / `artifacts` / 任务状态）
- 样例：`templates/mock/copy-generate.v2.txt`（离线假模型用）

## 8. 不在本版范围

- 不做多模型投票或打分排序
- 不做平台化改写（同一套文案改成小红书/抖音两版）
- 不做敏感词与合规自检（发布红线由 `publish-guard` 与关口③ 兜底）

## 9. 变更记录

| 日期 | 变更 | 来源 |
| ---- | ---- | ---- |
| 2026-10-12 | 首版：3 套侧重固定为 hook/emotion/cta，提示词升到 v2 | N008 |
