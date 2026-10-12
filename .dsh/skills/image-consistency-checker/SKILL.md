---
name: image-consistency-checker
description: "图片一致性体检员：检查 24 张独立图的数量、编号连续、非空、尺寸一致，并与数据库分镜对齐，输出问题与提示。Use when 需要在交到视频线前挡住不合格图片、需要复核某一代切图、或想单独体检一个图片目录时。"
---

# 图片一致性体检员（image-consistency-checker）

## 职责
对一代独立图片做体检：数量、编号连续、非空、尺寸一致、与分镜条数对齐；只出结论，不修改产物。

## 用法

```bash
python3 .dsh/skills/image-consistency-checker/run.py <子命令> --help
```

入口文件 `run.py`；人读说明见同目录 `README.md`。

## 完成判据
- 张数正好 `--expect`、编号 1..expect 连续、每张非空且单边 ≥ `--min-side`、所有图尺寸一致、与数据库分镜条数一致 ⇒ 通过（退出码 0）。
- 提示项（不影响退出码）：分镜缺少画面描述、文件名与分镜编号对不上。

## 退出码
- `0` 成功（体检类 skill 表示通过）；
- `1` 执行失败或自检不过（任务置 `blocked`，体检类不改任务状态）；
- `2` 输入校验不通过（上游没就绪，不产生任何产物）。

## 依赖
- `.dsh/skills/_shared/`：`db.py`、`recording.py`、`images.py`
- 上游 `image-splitter` 的产物与清单；不调用其他 skill（D-10）。

## 相关文件
- 流程图：`.archify/FLOW-VISUAL-20261012/visual-line.html`
- 岗位名册：`docs/skill-roster.md`
- README 契约：`docs/skill-readme-contract.md`
