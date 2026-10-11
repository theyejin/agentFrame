# Agent 定义（`agents/`）

- 用途：编排者与四条环节 Agent 的定义：谁负责拆解派单、谁负责哪条线、各自的交接契约。
- 不放什么：不放 Skill 实现（在 `.dsh/skills/`）、不放运行期数据（在 `workspace/`）。

## 计划内容

- orchestrator/（编排者，唯一）
- copy-agent/ 文案线
- visual-agent/ 视觉线
- video-agent/ 视频线
- publish-agent/ 分发数据线

## 维护提示

- WP-07 落地；每个 Agent 一个目录，目录内 README.md（管什么/不管什么/派单契约）+ orchestrator 另有 config.yml。
- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
