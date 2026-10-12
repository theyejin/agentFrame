---
name: auto-editor
description: "自动剪辑师：按人工在关口② 给的参数（镜头顺序 / 每镜时长 / 单张素材替换）渲染剪辑版成片，并把参数留痕。Use when 需要按关口② 的调整重渲成片、需要试排镜头顺序、或想复现某一次人工干预参数时。"
---

# 自动剪辑师（auto-editor）

- 归属：视频线 / 剪辑
- 输入：任务号 + 顺序/时长/替换（或 `--from-hitl`）
- 输出：`video/edited/edited-<时间戳>.mp4` + 参数留痕
- 不做：导出成片、发布准备

## 用法
```bash
python3 .dsh/skills/auto-editor/run.py --help
```

## 契约（摘要）
- 输入校验：任务存在，且最近一代独立图正好 24 张（先跑 image-splitter）。
- 完成判据：顺序确实是 1–24 的排列、每镜时长都 > 0、替换素材都已生效。
- 失败处理：自检不过最多重试 3 次，仍不过则登记 failed 并把任务置 blocked；输入校验不通过退出码 2。

完整九段说明见 `.dsh/skills/auto-editor/README.md`。
条目来源：`.dsh/skills/auto-editor/run.py`、`docs/skill-roster.md`。
