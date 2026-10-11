# 模板库（`templates/`）

- 用途：平台预设模板与可复用的提示词/排版模板。
- 不放什么：不放密钥、不放账号信息（C-05）。

## 计划内容

- platforms/（每个平台一份：字数区间 / 标题写法 / 标签数量 / 封面比例）

## 维护提示

- 新增平台模板时同步 `db/seed/` 与 `docs/directory-and-files.md`。
- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
