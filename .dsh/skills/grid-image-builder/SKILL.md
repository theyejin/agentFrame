---
name: grid-image-builder
description: "整图生成师：把 24 条分镜按 6×4 画进一张整图，供切图师等分（先出整图再切，Q-11）。Use when 需要从分镜生成 6×4 整图、需要重出整图、或想验证「整图尺寸必须正好等于 cols×cell_w 与 rows×cell_h」这条判据时。"
---

# 整图生成师（grid-image-builder）

## 职责
把 24 条分镜一次性画进一张 6×4 的整图，保证 24 个格子与 24 条分镜一一对应；不做切分、不做参考图、不做视频。

## 用法

```bash
python3 .dsh/skills/grid-image-builder/run.py <子命令> --help
```

入口文件 `run.py`；人读说明见同目录 `README.md`。

## 完成判据
- 整图真实存在且非空；
- 尺寸必须正好等于 `(cols×cell_w) × (rows×cell_h)`，差一个像素都不通过；
- 格数等于分镜条数；`model_version` 与 `prompt_version` 已登记。

## 退出码
- `0` 成功（体检类 skill 表示通过）；
- `1` 执行失败或自检不过（任务置 `blocked`，体检类不改任务状态）；
- `2` 输入校验不通过（上游没就绪，不产生任何产物）。

## 依赖
- `.dsh/skills/_shared/`：`db.py`、`recording.py`、`adapter_runtime.py`、`prompt_templates.py`、`images.py`、`text_utils.py`
- `templates/prompts/image-grid.md`（提示词 `image-grid`）
- `templates/adapters/registry.json`（image 链）
- 上游：`storyboard-builder`（分镜）；下游：`image-splitter`（切分）。不直接调用它们（D-10）。

## 相关文件
- 流程图：`.archify/FLOW-VISUAL-20261012/visual-line.html`
- 岗位名册：`docs/skill-roster.md`
- README 契约：`docs/skill-readme-contract.md`
