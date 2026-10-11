---
name: storyboard-validator
description: "分镜体检员：对一份分镜文件做结构体检 —— 条数是否正好 24、编号是否 1–24 连续、画面描述是否为空或重复、总时长是否落在目标区间，输出问题与提示清单。Use when 需要复核分镜脚本、需要在交接前挡住不合格分镜、或想单独验证一份分镜文件时。"
---

# storyboard-validator（分镜体检员）

**是什么**：分镜契约的独立检查器。输入一份分镜（JSON 或 `NN | 画面描述 | 镜头提示` 文本），输出问题清单（结构级）与提示清单（建议级），并用退出码表达结论。

**什么时候用**：
- 视觉线进场前复核上游交接物；
- 重新生成分镜后单独复检某个文件；
- 调提示词或样例后回归验证。

**入口**：

```bash
python3 .dsh/skills/storyboard-validator/run.py check --file workspace/topic-1/storyboard/storyboard-20261012T030707.json --target-seconds 72
python3 .dsh/skills/storyboard-validator/run.py check --file templates/mock/storyboard-split.v2.txt --shot-seconds 3 --json
```

**产出**：问题与提示清单、条数与总时长、退出码（0 通过 / 1 有结构问题 / 2 文件读不了）。

**详细说明与九段契约**见同目录 `README.md`；本文件只回答「是什么、什么时候用、入口在哪」。
