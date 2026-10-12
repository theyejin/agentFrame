---
name: video-exporter
description: "成片导出师：把剪辑版定稿为最终成片并用 ffmpeg 抽一帧做封面，把任务推进到分发环节。Use when 剪辑已确认需要导出成片与封面帧、需要复核成片时长与分辨率、或要把任务交到发布准备时。"
---

# 成片导出师（video-exporter）

- 归属：视频线 / 导出
- 输入：任务号（+ 可选剪辑版路径、抽帧时间点）
- 输出：`video/final/final-<时间戳>.mp4` + `cover-<时间戳>.png`
- 副作用：任务阶段推进到 `publish`

## 用法
```bash
python3 .dsh/skills/video-exporter/run.py --help
```

## 契约（摘要）
- 输入校验：任务存在，且能找到剪辑版产物（`role=edited`）或显式 `--edited` 文件。
- 完成判据：成片可被 ffprobe 读出、时长 > 0.5s、分辨率与剪辑版一致。
- 失败处理：自检不过最多重试 3 次，仍不过则登记 failed 并把任务置 blocked；输入校验不通过退出码 2。

完整九段说明见 `.dsh/skills/video-exporter/README.md`。
条目来源：`.dsh/skills/video-exporter/run.py`、`docs/skill-roster.md`。
