---
name: browser-publisher
description: "浏览器发布员：把成片、标题、标签、封面组装成发布包并只做填写（停在发布前），发布授权与提交都由真人完成。Use when 成片已导出需要准备发布、需要生成填写清单、或人工发布后回填链接时。"
---

# 浏览器发布员（browser-publisher）

- 归属：分发数据线 / 发布
- 输入：任务号（+ 平台、账号标签）
- 输出：`publish/fill-plan-<时间戳>.json` + publish_package 产物 + filled 发布记录 + 关口③ 待办
- 副作用：写产物与发布记录、挂关口③、任务置 waiting_human；不提交发布

## 用法
```bash
python3 .dsh/skills/browser-publisher/run.py --help
```

## 契约（摘要）
- 输入校验：成片与封面必须成对存在；平台必须有模板；发布准备必须存在。
- 完成判据：清单 `submit=false` 且自检无阻断项；任务停在 waiting_human 等关口③。
- 失败处理：缺产物/缺模板退出 2；发现自动提交意图退出 1 并拒绝登记。

完整九段说明见 `.dsh/skills/browser-publisher/README.md`。
条目来源：`.dsh/skills/browser-publisher/run.py`、`docs/skill-roster.md`。
