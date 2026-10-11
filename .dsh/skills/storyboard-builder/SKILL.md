---
name: storyboard-builder
description: "分镜拆解师：把关口① 选定的那套文案拆成 24 条分镜场景内容（6×4 网格，每条含画面描述、镜头提示与时长），供视觉线出图。Use when 文案已选定需要拆分镜、需要重跑分镜、或想确认「没选定文案就不能往下走」这条契约时。"
---

# storyboard-builder（分镜拆解师）

**是什么**：文案线最后一道工序，也是与视觉线的接缝。输入**已经过关口①选定的文案**，输出 **24 条分镜**（编号 01–24 连续），写进 `storyboards` 并落产物，然后把任务推进到视觉环节。

**什么时候用**：
- 运营人员在关口① 选定了某套文案之后；
- 分镜不满意要重跑（`storyboards` 按任务整体替换，历史留在产物文件里）；
- 想验证「没选定文案直接拆分镜」会被拒绝（前置卡口，R-L1-18）。

**入口**：

```bash
python3 .dsh/skills/storyboard-builder/run.py build --task-id 1
python3 .dsh/skills/storyboard-builder/run.py build --task-id 1 --shot-seconds 3 --style-hint "真实感、竖屏 9:16" --json
```

**产出**：`storyboards` 24 行、`storyboard-<时间戳>.json`、`storyboard.md`、`step_runs` 与 `artifacts` 留痕；任务 `stage` 变为 `visual`。

**详细说明与九段契约**见同目录 `README.md`；本文件只回答「是什么、什么时候用、入口在哪」。
