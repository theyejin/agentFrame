---
name: asset-packager
description: "素材打包员：把选定文案 + 24 张独立图 + 24 条分镜按顺序打包成视频线工程文件夹（含 manifest.json）。Use when 需要为图生视频准备图文包、需要重新打包某一代素材、或想确认「24 张图与 24 条分镜一一对应」这条契约时。"
---

# 素材打包员（asset-packager）

- 归属：视频线 / 打包
- 输入：任务号（+ 可选输出目录、每镜默认时长）
- 输出：`video/package/<时间戳>/`（图片 + copy.md + manifest.json）
- 不做：图片质检、改图、视频合成

## 用法
```bash
python3 .dsh/skills/asset-packager/run.py --help
```

## 契约（摘要）
- 输入校验：关口① 必须已选定文案（`tasks.selected_plan` 有值且该套 `status=active`），否则退回。
- 完成判据：清单里的镜号是 1–24 连续、不重不漏，且条数等于分镜条数与图片张数。
- 失败处理：自检不过最多重试 3 次，仍不过则登记 failed 并把任务置 blocked；输入校验不通过退出码 2。

完整九段说明见 `.dsh/skills/asset-packager/README.md`。
条目来源：`.dsh/skills/asset-packager/run.py`、`docs/skill-roster.md`。
