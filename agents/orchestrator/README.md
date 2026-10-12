# 编排者（`orchestrator`）

<!--
文件用途：编排者（唯一顶层 Agent）的定义：管什么、不管什么、向下派单契约、向上回报契约与状态机。
对应需求：R-L1-05（Agent 定义）、R-L1-06（职责边界）、§5.2.1（编排者/Agent/Skill 三层边界）、R-L1-18（交接契约）。
对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
维护提示：改职责或派单范围先改同目录 config.yml（机器可读单一事实源），再同步本文件与各 Agent 的 README.md。
-->

| 项目 | 内容 |
| --- | --- |
| agent_id | `orchestrator` |
| 中文名 | 编排者（唯一） |
| 归属 | 顶层（不属任何一条线） |
| 工具 Skill | `task-decomposer`（派单）、`summary-writer`（汇总回报） |
| 配置来源 | `agents/orchestrator/config.yml` |
| 并发上限 | `max_parallel: 1`（同一任务同一时刻只有一个环节在跑） |
| 版本 | v0.1.0 |

## 1. 管什么

- 接收运营人员输入（话题标题 / 关键词 / 平台 / 内容类型 / 字数区间），把它变成一条任务。
- 判定流程走向：按 `tasks.stage` 决定下一步该找哪个环节 Agent（见 config.yml 的 `stage_routing`）。
- 向下派单：用 `task-decomposer` 生成派单书（派给谁、按什么命令起手、进场校验什么、做完什么算完）。
- 向上回报：用 `summary-writer` 把「当前环节 / 已完成步骤 / 待办关口 / 关键产物 / 下一步找谁」汇总成一段话给运营人员。
- 维护任务状态：`tasks.status`（pending / running / waiting_human / blocked / done / failed / cancelled）与 `tasks.stage`（copy / visual / video / publish / metrics / review / closed）。

## 2. 不管什么

- **不直接写文件**：所有文件由 Skill 产出（§5.2.1）。
- **不直接调用外部 API**：模型、图像、视频、浏览器、文档、指标一律经适配器与对应 Skill。
- **不做具体内容加工**：不写文案、不拆分镜、不出图、不剪片、不写复盘结论。
- **不代答人工关口**：五个关口（见 config.yml `human_gates`）只能由真人拍板，编排者只负责把待办挂起来（C-10）。
- **不跨环节并行**：同一任务同一时刻只有一个环节在跑（`max_parallel: 1`），避免两条线同时改同一份素材。

## 3. 派单契约（对下，R-L1-18）

派单书由 `task-decomposer` 生成，五项必须齐全（缺一不得开工）：

| 项 | 内容 |
| --- | --- |
| 找谁 | `agent_id` + `line`（由 `tasks.stage` 经 `stage_routing` 决定） |
| 起手命令 | 该环节第一个 Skill 的完整命令行（可直接复制执行） |
| 进场校验 | 取自 config.yml `handoff.input_check`（逐条机器可判定，不通过退回，退回对象是编排者） |
| 产出物清单 | 取自 config.yml `handoff.outputs` |
| 完成判据 | 取自 config.yml `handoff.done`（词汇表：`count` / `ids_continuous` / `unique` / `in_range` / `all_resolution_equal` / `file_exists` / `non_empty` / `enum_in` / `no_auto_publish`） |

派单书落盘 `workspace/topic-<id>/plan/dispatch-<时间戳>.{json,md}`，并登记为 `kind=manifest`、`meta.role=dispatch` 的产物。

## 4. 回报契约（对上）

`summary-writer` 输出的回报必须含五项，缺一项即视为不合格：当前环节（`stage`）、已完成步骤数、待办关口（`waiting_human` 且未决议）、关键产物（按 kind 计数）、下一步找谁。回报只读库与产物清单，不改任何表、不调模型。

## 5. 环节路由（stage → 谁）

| `tasks.stage` | 找谁 |
| --- | --- |
| `copy` | `copy-agent`（文案线） |
| `visual` | `visual-agent`（视觉线） |
| `video` | `video-agent`（视频线） |
| `publish` / `metrics` / `review` | `publish-agent`（分发数据线） |
| `closed` | 编排者（归档，不再派单） |

## 6. 失败与退回

| 情况 | 编排者动作 |
| --- | --- |
| 环节进场校验不通过 | 不进入执行，退回编排者；由编排者决定补料还是改任务 |
| 环节自检不通过、重试超限 | Skill 按自己 README 的失败处理标记「需人工」，任务置 `blocked`，编排者转述给运营人员 |
| 停在人工关口 | 任务置 `waiting_human`；编排者只转述待办，不代答 |
| 需要付费或需要真实账号 | 就地停下（C-09 零付费门禁），向运营人员提出，不得静默降级到付费渠道 |

## 7. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | WP-07 首版：编排者定义与派单/回报契约（N012） |
