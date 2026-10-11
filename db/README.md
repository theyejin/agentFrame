# 数据库（`db/`）

- 用途：本地库的结构定义与迁移：任务、产物、指标、人工关口记录、步骤流水。
- 不放什么：不入库数据库二进制文件（`*.db` 已在 .gitignore），不放运行期数据。

## 计划内容

- README.md（表清单与关系说明）
- schema.sql（唯一结构来源）
- migrations/（NNNN_描述.sql）
- seed/（平台预设模板、指标字典）

## 维护提示

- WP-06 落地；改结构必须新增迁移脚本并同步 `docs/directory-and-files.md`。
- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
