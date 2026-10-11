# 辅助脚本（`scripts/`）

- 用途：跑测试、生成报告、体检目录一致性的小工具。
- 不放什么：不放业务实现。

## 计划内容

- build_log_report.py（扫 logs/ 生成 build-log.html）
- structure_check.py（检查目录说明与磁盘是否一致）

## 维护提示

- 每个脚本开头必须有四行文件头注释（R-L1-15）。
- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
