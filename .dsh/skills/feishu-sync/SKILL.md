---
name: feishu-sync
description: "文档同步员：把汇总表同步到飞书文档，未接开放平台 API 时降级为本地导出文件。Use when 热点表或复盘报告需要存档共享、飞书不可用需要导出留档、或想验证文档降级链时。"
---

# 文档同步员（feishu-sync）

- 归属：分发数据线 / 同步
- 输入：批次号或一份要同步的文件
- 输出：`workspace/exports/<时间戳>/<原文件名>` + 回填批次 `export_path`
- 副作用：只写导出文件与批次表字段，不改任务状态

## 用法
```bash
python3 .dsh/skills/feishu-sync/run.py --help
```

## 契约（摘要）
- 输入校验：`--batch` 或 `--file` 至少一个；批次要有 table_path；降级链必须落在已接适配器上。
- 完成判据：导出文件与源文件内容一致，输出写明用了哪条链与降级原因。
- 失败处理：链不可用退出 2；写盘失败退出 1。

完整九段说明见 `.dsh/skills/feishu-sync/README.md`。
条目来源：`.dsh/skills/feishu-sync/run.py`、`docs/skill-roster.md`。
