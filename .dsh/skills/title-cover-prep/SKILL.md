---
name: title-cover-prep
description: "发布准备师：按平台模板（标题写法 / 标签数量 / 封面比例）生成三条标题候选、标签与封面文案，供关口③ 核对。Use when 成片已导出需要准备发布信息、需要换平台重新准备、或想演练发布前信息核对与红线检查时。"
---

# 发布准备师（title-cover-prep）

- 归属：分发数据线 / 发布准备
- 输入：任务号（+ 可选平台）
- 输出：`publish/prep/prep-<时间戳>.{json,md}`
- 不做：登录、填表、发布

## 用法
```bash
python3 .dsh/skills/title-cover-prep/run.py --help
```

## 契约（摘要）
- 输入校验：任务存在，且有成片产物（`role=final`）——发布信息必须对应一支真成片。
- 完成判据：标题正好 3 条，且每条 ≤ 30 字、不含绝对化用语（C-01）。
- 失败处理：自检不过最多重试 3 次，仍不过则登记 failed 并把任务置 blocked；输入校验不通过退出码 2。

完整九段说明见 `.dsh/skills/title-cover-prep/README.md`。
条目来源：`.dsh/skills/title-cover-prep/run.py`、`docs/skill-roster.md`。
