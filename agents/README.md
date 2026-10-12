# Agent 定义（`agents/`）

<!--
文件用途：`agents/` 目录的导航与维护约定：五个 Agent 的目录、各自定义文件与运行时配置。
对应需求：R-L1-05（Agent 定义）、R-L1-06（边界）、R-L1-18（交接契约）、R-L2-09（目录变更同步）。
对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
维护提示：任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）与 `agents/orchestrator/config.yml`。
-->

- 用途：编排者与四条环节 Agent 的定义：谁负责拆解派单、谁负责哪条线、各自的交接契约。
- 不放什么：不放 Skill 实现（在 `.dsh/skills/`）、不放运行期数据（在 `workspace/`）。

## 目录内容（WP-07 落地）

| 目录 | 角色 | 定义文件 | 备注 |
| --- | --- | --- | --- |
| `orchestrator/` | 编排者（唯一） | `README.md` + `config.yml` | `config.yml` 是机器可读的单一事实源：skill 白名单、环节路由、五个 Agent 的交接契约 |
| `copy-agent/` | 文案线 Agent | `README.md` | `entry_stage: copy` → `exit_stage: visual`；关口① |
| `visual-agent/` | 视觉线 Agent | `README.md` | `visual` → `video`；风格确认与单张返工两个关口 |
| `video-agent/` | 视频线 Agent | `README.md` | `video` → `publish`；关口② |
| `publish-agent/` | 分发数据线 Agent | `README.md` | `publish` → `review`；关口③ 与发布红线 |

## 约定

- 每个 Agent 的 `README.md` 固定三段：**管什么 / 不管什么 / 派单契约**（输入校验、产出物清单、完成判据），另有失败与退回、变更记录。
- 交接契约两侧必须一致：`agents/orchestrator/config.yml`（机器读）与各 Agent `README.md`（人读）；不一致时以 `config.yml` 为准，并由 `task-decomposer` 在派单时校验。
- 判据词汇表（R-L1-18）：`count`、`ids_continuous`、`unique`、`in_range`、`all_resolution_equal`、`file_exists`、`non_empty`、`enum_in`、`no_auto_publish`。

## 相关入口

- 派单：`python3 .dsh/skills/task-decomposer/run.py dispatch --title "…" --json`
- 汇总回报：`python3 .dsh/skills/summary-writer/run.py summarize --task-id <N> --json`

## 维护提示

- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
