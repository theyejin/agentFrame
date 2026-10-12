---
name: publish-guard
description: "发布红线守卫：发布前自检填写清单（C-08 不自动发布、C-10 关口③ 授权、标题标签封面齐备），不通过就阻断。Use when 发布前要过一次红线、需要确认某个任务能不能发、或想复核人工授权状态时。"
---

# 发布红线守卫（publish-guard）

- 归属：支撑件 / 发布红线
- 输入：任务号（+ 可选发布包路径、平台、`--live`）
- 输出：自检报告（文本或 JSON）+ 退出码 0/1/2
- 副作用：只读检查，不写任何库表

## 用法
```bash
python3 .dsh/skills/publish-guard/run.py --help
```

## 契约（摘要）
- 输入校验：任务必须存在且有发布包；发布包 JSON 必须可解析。
- 完成判据：阻断项为空才返回 0；检查不改变任何库表状态。
- 失败处理：缺发布包/坏 JSON 退出 2；发现自动提交意图退出 1。

完整九段说明见 `.dsh/skills/publish-guard/README.md`。
条目来源：`.dsh/skills/publish-guard/run.py`、`docs/skill-roster.md`。
