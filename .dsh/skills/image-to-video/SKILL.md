---
name: image-to-video
description: "图生视频师：把图文包里的 24 张图按镜号顺序与时长合成一支草稿视频（Remotion 首选、ffmpeg 兜底），产出后挂起关口② 等待人工调整。Use when 需要从图文包生成草稿视频、需要重出草稿、或想演练视频线的图像降级链与剪辑关口时。"
---

# 图生视频师（image-to-video）

- 归属：视频线 / 图生视频
- 输入：任务号（+ 可选图文包目录、帧率、分辨率）
- 输出：`video/draft/draft-<时间戳>.mp4`
- 不做：剪辑调整、导出成片、发布

## 用法
```bash
python3 .dsh/skills/image-to-video/run.py --help
```

## 契约（摘要）
- 输入校验：任务存在，且图文包清单可读（`role=package` 产物，清单里 count 必须等于 24）。
- 完成判据：成片可被 ffprobe 读出，时长 > 0.5s、分辨率等于目标尺寸。
- 失败处理：自检不过最多重试 3 次，仍不过则登记 failed 并把任务置 blocked；输入校验不通过退出码 2。

完整九段说明见 `.dsh/skills/image-to-video/README.md`。
条目来源：`.dsh/skills/image-to-video/run.py`、`docs/skill-roster.md`。
