---
name: hitl-gate
description: "人工关口器：管理三类必须由真人拍板的关口、共五个关口点 —— 关口① 选定文案（选择态）；调整态四个：人的风格确认、人工修图/单张返工、剪辑干预；关口③ 发布授权（授权态）。把待办挂起并把决定写进 hitl_events。Use when 需要让任务停在某个人工关口等确认、需要记录谁在什么时候批准或退回、或想查看某任务经历过哪些关口时。"
---

# hitl-gate（人工关口器）

**是什么**：三类形态（选择 / 调整 / 授权）共五个关口点的开关与留痕。开启关口 = 把任务置为 `waiting_human`（流水线停下等人）；决议关口 = 写一行 `hitl_events` 并把任务放回 `running`（关口① 还会记下选定的方案）。

五个关口点：`gate1_select_copy`（选择态·选定文案）、`gate_visual_style`（调整态·人的风格确认）、`gate_visual_fix`（调整态·人工修图/单张返工）、`gate2_edit_video`（调整态·剪辑干预）、`gate3_publish_auth`（授权态·发布授权）。

**什么时候用**：
- 三套文案生成完，要请运营人员选一套（关口①，选择态）；
- 参考图出来后要人确认风格、24 张图出来后要人抽查并指定重做的张（视觉线调整态）；
- 图生视频出草稿，要请运营人员改顺序/时长/素材（关口②，调整态）；
- 发布信息填写完，要请运营人员核对并亲自点发布（关口③，授权态，C-08）；
- 想知道某任务卡在谁那儿、谁批的、批的时候内容长什么样（`list` / `status`）。

**入口**：

```bash
python3 .dsh/skills/hitl-gate/run.py open    --task-id 1 --gate gate1_select_copy --note "三套候选待选"
python3 .dsh/skills/hitl-gate/run.py resolve --task-id 1 --gate gate1_select_copy --action confirm --actor 阿金 --plan-no 2
python3 .dsh/skills/hitl-gate/run.py open    --task-id 1 --gate gate_visual_style --note "参考图待确认风格"
python3 .dsh/skills/hitl-gate/run.py resolve --task-id 1 --gate gate_visual_fix --action adjust --actor 阿金 --diff-json '{"shot_nos":[3,7]}'
python3 .dsh/skills/hitl-gate/run.py list    --task-id 1
python3 .dsh/skills/hitl-gate/run.py status  --task-id 1
```

**产出**：`hitl_events` 行（gate / actor / action / 快照 / 差异）、任务状态与 `selected_plan`。

**详细说明与九段契约**见同目录 `README.md`；本文件只回答「是什么、什么时候用、入口在哪」。
