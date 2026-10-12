---
name: image-splitter
description: "切图师：把 6×4 整图等分成 24 张独立图 shot-01…shot-24，写出清单并登记留痕。Use when 需要把整图切成 24 张、需要重切一代、或想确认 24 张与 24 条分镜一一对应且任务推进到视频线时。"
---

# 切图师（image-splitter）

## 职责
把整图按行列等分成 24 张独立图片，命名连续，写清单 `latest.json`，把任务阶段推进到 `video`。不做体检判定、不做视频。

## 用法

```bash
python3 .dsh/skills/image-splitter/run.py <子命令> --help
```

入口文件 `run.py`；人读说明见同目录 `README.md`。

## 完成判据
- 张数正好等于 `cols×rows`（默认 24），命名连续从 `--start-no` 起；
- 每张非空、单边 ≥ 64 像素、同代尺寸一致；
- 清单文件已写出且条数与图片一致。

## 退出码
- `0` 成功（体检类 skill 表示通过）；
- `1` 执行失败或自检不过（任务置 `blocked`，体检类不改任务状态）；
- `2` 输入校验不通过（上游没就绪，不产生任何产物）。

## 依赖
- `.dsh/skills/_shared/`：`db.py`、`recording.py`、`adapter_runtime.py`、`images.py`、`text_utils.py`
- `templates/adapters/registry.json`（split 链：grid-slicer → manual）
- 上游 `grid-image-builder`；下游 `image-consistency-checker`、`asset-packager`。不直接调用它们（D-10）。

## 相关文件
- 流程图：`.archify/FLOW-VISUAL-20261012/visual-line.html`
- 岗位名册：`docs/skill-roster.md`
- README 契约：`docs/skill-readme-contract.md`
