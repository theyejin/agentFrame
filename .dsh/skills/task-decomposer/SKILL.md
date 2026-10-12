---
name: task-decomposer
description: "派单员：把运营输入变成一条任务，并按 agents/orchestrator/config.yml 的交接契约生成派单书（派给哪个环节 Agent、怎么起手、进场校验什么、做完什么算完）。Use when 需要新建选题与任务、需要看某条任务下一步该找谁、或想核对五个 Agent 的可派单 Skill 与交接契约时。"
---

# 派单员（task-decomposer）

- 归属：支撑件 / 编排者工具
- 入口：`.dsh/skills/task-decomposer/run.py`
- 契约来源：`agents/orchestrator/config.yml`（机器可读单一事实源）
- 详细字段与判据以同目录 `README.md` 为准

```bash
# 建任务并出派单书
python3 .dsh/skills/task-decomposer/run.py --db db/app.db dispatch \
  --title "打工人春节返乡" --platform 抖音 --prompt "写一条返乡情绪" --json

# 按当前环节看下一步找谁（只读，不改库）
python3 .dsh/skills/task-decomposer/run.py --db db/app.db plan --task-id 1

# 核对五个 Agent 与各自可派单 Skill
python3 .dsh/skills/task-decomposer/run.py --db db/app.db agents
```

- 派单书落 `workspace/topic-<选题号>/plan/dispatch-<时间戳>.{json,md}`，并登记 `kind=manifest`、`meta.role=dispatch`。
- 本 skill 只建话题/任务与出派单书；不执行下游命令、不改其他环节的状态。
