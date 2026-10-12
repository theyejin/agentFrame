# 派单员（task-decomposer）

<!--
文件用途：派单员 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：R-L1-05（Agent 定义）/ R-L1-18（交接契约由运行时校验）/ §5.2.1（编排者不写文件，派单书由 Skill 落盘）/ §16.2 统一执行流程。
对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
维护提示：改派单规则先改 agents/orchestrator/config.yml（单一事实源），再改本文件与 run.py；入口 skill 固定写在本 skill 的 run.py。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `task-decomposer` |
| 中文岗位名 | 派单员 |
| 归属 | 支撑件 / 编排者工具 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/task-decomposer/run.py` |
| 执行者 | 编排者（或人用命令行） |

## 1. 职责
把运营输入变成一条可执行的任务，并按 `agents/orchestrator/config.yml` 的交接契约生成派单书：派给哪个环节 Agent、起手命令是什么、进场校验哪几条、做完什么算完。另有两个只读子命令：`plan`（按任务当前环节给下一步）与 `agents`（核对五个 Agent 与其可派单 Skill）。

## 2. 输入

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--title` | 新建选题时必填 | 选题标题 |
| `--topic-id` | 二选一 | 复用已有话题（给了就不新建） |
| `--platform` | 是 | 目标平台，必须在 `platform_templates` 内 |
| `--content-type` | 否 | 四类之一（情绪冲突 / 干货教程 / 热点观点 / 其他），默认 情绪冲突 |
| `--source` | 否 | `manual` / `hotspot`，默认 manual |
| `--keywords` `--summary` `--created-by` | 否 | 话题字段 |
| `--prompt` | 否 | 对话框里的原始输入（透传给文案线） |
| `--word-min` `--word-max` | 否 | 缺省取平台模板的字数区间 |
| `--priority` | 否 | 1（最高）/ 2 / 3，默认 2 |
| `--operator` `--stage` `--step-no` `--out-dir` | 否 | 接单人 / 入口环节（默认 copy）/ 步骤号 / 派单书目录 |
| `--task-id` | `plan` 必填 | 要查的任务号 |
| `--db` | 否 | 数据库路径（缺省 .env 的 DB_PATH） |
| `--json` | 否 | JSON 输出（写在子命令前后都行） |

## 3. 输入校验（进场前，不通过直接退回）
- `enum_in`：`--platform` ∈ `platform_templates.platform`，否则列出已配置平台并退出码 2；
- `enum_in`：`--content-type` ∈ 四类内容类型；
- `in_range`：`100 <= word_min <= word_max <= 2000`；
- `non_empty`：新建选题时 `--title` 非空；`--topic-id` 必须存在；
- 派单前自检：`config.yml` 五个 Agent 齐、每个 Agent 的 `handoff` 三段（`input_check` / `outputs` / `done`）齐、声明的每个 Skill 目录 `file_exists`；任一条不满足即退回（R-L1-18）。

## 4. 输出
- `workspace/topic-<选题号>/plan/dispatch-<时间戳>.json`：派单书（机器读），含 `agent_id` / `entry_command` / `contract` 三段 / `gates` / `skills`；
- `workspace/topic-<选题号>/plan/dispatch-<时间戳>.md`：派单书（人读，同样是三段契约）；
- `topics` 一行（新建时）+ `tasks` 一行（`stage=copy`、`status=pending`）；
- `step_runs` 一行（`skill_id=task-decomposer`）+ `artifacts` 一行（`kind=manifest`、`meta.role=dispatch`、`prompt_version=none`）。

## 5. 完成判据（自检通过才交给下游）
- `file_exists(dispatch .md)` 且 `file_exists(dispatch .json)`；
- `contract.input_check` / `contract.outputs` / `contract.done` 三段 `non_empty`；
- `agent_id` `enum_in` 四个环节 Agent；`entry_command` `non_empty`；
- `tasks.status == pending` 且 `tasks.stage == copy`。

## 6. 失败处理

| 情况 | 处理 |
| --- | --- |
| 平台不存在 | 退出码 2，列出已配置平台；不改库 |
| 字数区间反了 / 越界 | 退出码 2，提示 `100 <= min <= max <= 2000`；不改库 |
| `config.yml` 缺段或 Skill 目录缺失 | 退出码 2，逐条列出问题（派单前自检不通过）；不改库 |
| 话题不存在 | 退出码 2；不新建话题 |
| 数据库不可写 | 退出码 2，打印数据库错误 |

## 7. 依赖
- `_shared/db.py`、`_shared/recording.py`（建话题/任务、登记步骤与产物）；
- `agents/orchestrator/config.yml`（PyYAML 读取；`pyyaml 6.0.3` 本机可用）；
- 不需要网络、不需要模型（离线可用，零费用）。

## 8. 不在本版范围
- 不做多任务批量派单、不做排期与并发调度（`max_parallel: 1`，由人决定何时派下一单）；
- 不自动执行下游 Skill 的命令（派单书只给命令，由 Agent 或人执行）；
- 不改任务后续环节的状态（`plan` 是只读）。

## 9. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | WP-07 首版：`dispatch` / `plan` / `agents` 三个子命令（N012） |
