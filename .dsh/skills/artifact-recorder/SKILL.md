---
name: artifact-recorder
description: "留痕登记员：把「建了选题 / 派了任务 / 某步骤成功或失败 / 产出了什么文件 / 人工做了什么决定」写进本地数据库，是五张留痕表的唯一写入口。Use when 需要新建选题与任务、登记步骤流水、登记产物（含模型版本与提示词版本）、回填任务状态，或想查看某任务的进度、步骤、产物与关口事件时。"
---

# artifact-recorder（留痕登记员）

**是什么**：本地留痕的唯一写入口。业务动作发生时，由它往 `topics` / `tasks` / `step_runs` / `artifacts` / `hitl_events` 里落一行，保证「谁、什么时候、做了什么、产出在哪、用的哪个模型版本」都查得到（R-L1-03、R-7-03、R-L2-07）。

**什么时候用**：
- 运营人员扔来一个选题 → 建 `topics` 行，并顺手派生一个 `tasks` 行；
- 任何 skill 开始/结束一个步骤（成功或失败）→ 登记 `step_runs`；
- 任何 skill 写出文件 → 登记 `artifacts`（自动算 sha256 与字节数）；
- 想查某任务现在到哪一步、有哪些产物 → `list`。

**入口**：

```bash
python3 .dsh/skills/artifact-recorder/run.py topic-create --title "选题" --task --type 情绪冲突 --words 300-500
python3 .dsh/skills/artifact-recorder/run.py task-update  --task-id 1 --status running --operator 阿金
python3 .dsh/skills/artifact-recorder/run.py step-run     --task-id 1 --skill copy-writer --status ok
python3 .dsh/skills/artifact-recorder/run.py artifact     --task-id 1 --kind copy --path workspace/topic-1/copy/variants.md --model-version mock-v1 --prompt-version v2
python3 .dsh/skills/artifact-recorder/run.py list         --task-id 1 --what all
```

**产出**：五张留痕表的行、每行分配的 id，以及任务进度视图（`v_task_progress`）的当前快照。

**详细说明与九段契约**见同目录 `README.md`；本文件只回答「是什么、什么时候用、入口在哪」。
