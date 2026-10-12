---
name: reference-image-builder
description: "参考图生成师：依据关口① 选定的文案生成 1–3 张风格参考图，作为 6×4 整图的视觉基准。Use when 需要为某个已选定文案的任务出参考图、需要重出参考图、或想演练视觉线的图像降级链与风格确认关口时。"
---

# 参考图生成师（reference-image-builder）

## 职责
拿关口① 选定的那套文案，生成 1–3 张风格参考图，作为后面 24 张图的一致性基准。只负责参考图：不做整图、不切图、不碰视频与发布。

## 用法

```bash
python3 .dsh/skills/reference-image-builder/run.py <子命令> --help
```

入口文件 `run.py`；人读说明见同目录 `README.md`。

## 完成判据
- 参考图张数等于 `--count`；
- 每张真实非空、单边 ≥ 128 像素、竖屏（高 > 宽）；
- `model_version` 与 `prompt_version` 已登记（R-7-03）。

## 退出码
- `0` 成功（体检类 skill 表示通过）；
- `1` 执行失败或自检不过（任务置 `blocked`，体检类不改任务状态）；
- `2` 输入校验不通过（上游没就绪，不产生任何产物）。

## 依赖
- `.dsh/skills/_shared/`：`db.py`、`recording.py`、`adapter_runtime.py`、`prompt_templates.py`、`images.py`
- `templates/prompts/image-reference.md`（提示词 `image-reference`）
- `templates/adapters/registry.json`（image 链：flow → doubao → comfyui → placeholder → manual）
- 不调用其他 skill（D-10）。

## 相关文件
- 流程图：`.archify/FLOW-VISUAL-20261012/visual-line.html`
- 岗位名册：`docs/skill-roster.md`
- README 契约：`docs/skill-readme-contract.md`
