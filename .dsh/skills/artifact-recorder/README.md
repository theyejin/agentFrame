# 留痕登记员（artifact-recorder）

<!--
文件用途：五张留痕表（选题 / 任务 / 步骤流水 / 产物 / 人工关口事件）的唯一写入口，保证每一步可追溯（R-L1-03、R-7-03、R-L2-07）。
对应需求：R-L1-03（本地数据库）、R-7-03（产物记 model_version / prompt_version）、R-L2-07（步骤流水）、R-8-03（操作人）、C-05（密钥不入库）。
对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（入库与留痕 · 版本字段）
维护提示：表结构改动请同步 db/schema.sql、db/README.md 与本文件；本 skill 只是 _shared/recording.py 的命令行外壳，业务逻辑改那里。
-->

| 项 | 值 |
| -- | -- |
| skill_id | `artifact-recorder` |
| 中文岗位名 | 留痕登记员 |
| 归属 | 基础设施（支撑件） |
| 版本 | `0.1.0` |
| 入口文件 | `run.py` |
| 执行者 | 各环节 skill 与编排者在每个动作前后调用 |

## 1. 职责

把「发生了什么」写成库里的行：建选题、派任务、步骤成功或失败、写出产物、人工做了决定。它不做业务判断，只保证**事实被记下来且记全**：产物必带 `model_version` 与 `prompt_version`（R-7-03），失败步骤必带 `error`，人工动作必带 `actor`（R-8-03）。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| ---- | ---- | ---- | ---- | ---- |
| 动作 | 子命令 | 是 | `topic-create` / `task-create` / `task-update` / `task-show` / `step-run` / `artifact` / `list` | 调用方 |
| `--task-id` | int | 视动作 | 任务编号 | 编排者派单 |
| `--skill` `--status` | str | `step-run` 必填 | 哪个 skill、什么结果（`running`/`ok`/`failed`/`skipped`） | 执行中的 skill |
| `--kind` `--path` | str | `artifact` 必填 | 产物类型与路径（相对仓库根） | 产出文件的 skill |
| `--model-version` `--prompt-version` | str | `artifact` 必填 | 用了哪个模型、哪版提示词 | llm-adapter / prompt-registry |
| `--db` | str | 否 | 数据库路径，缺省读 `.env` 的 `DB_PATH` | 环境 |

## 3. 输入校验（进场前，不通过直接退回）

- [ ] 引用的 `task_id` / `topic_id` 必须已存在（外键约束兜底）
- [ ] `step-run --status failed` 必须同时给 `--error`
- [ ] `artifact` 必须给 `--model-version` 与 `--prompt-version`
- [ ] `artifact --kind image|video|audio` 的 `size_bytes > 0`（DB 触发器 `trg_artifact_media_size` 兜底）
- [ ] `--path` 记相对仓库根的 POSIX 路径；仓库外的绝对路径会被原样记录并提示

退回时返回：`{"ok": false, "reason": "<缺什么>"}`（退出码 2）。

## 4. 输出

| 字段 | 类型 | 说明 | 落库位置 |
| ---- | ---- | ---- | -------- |
| 新行 id | int | 本次登记的行号 | `topics` / `tasks` / `step_runs` / `artifacts` / `hitl_events` |
| 进度快照 | dict | 阶段、状态、已完成/失败步骤数 | 视图 `v_task_progress` |
| `size_bytes` / `sha256` | int / str | 由文件真实内容算出，调用方不用自己算 | `artifacts` |

## 5. 完成判据（自检通过才交给下游）

- [ ] 返回的 id 能在库中查到该行
- [ ] 产物行的 `size_bytes` 与磁盘上文件一致
- [ ] 同一路径重复登记会产生多行（**不去重**：历史留痕优先于整洁）

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| -------- | ---- | ---- | ------ |
| 数据库约束不通过 | 整条动作不写半行，返回错误与原因 | — | 调用方按错误修输入重试 |
| 路径不存在 | 记 0 字节并提示（媒体类会被触发器拒绝） | — | 调用方先产出文件再登记 |

## 7. 依赖

- 共享库：`_shared/recording.py`（唯一写入实现）、`_shared/db.py`（连接与事务）
- 数据库：`db/app.db`（结构见 `db/schema.sql`、`db/README.md`）

## 8. 不在本版范围

- 不做身份鉴权与权限控制（首版用 `operator` 字段记录操作人，Q-17）
- 不做批量导入/导出报表（控制台与 build-log 页负责展示）
- 不做产物清理与归档策略

## 9. 变更记录

| 日期 | 变更 | 来源 |
| ---- | ---- | ---- |
| 2026-10-12 | 首版：七个子命令 + 五张表写入 | N008 |
