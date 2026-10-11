# 提示词注册表（prompt-registry）

<!--
文件用途：提示词模板的列出、渲染、自检与版本登记 —— 让每一份生成物都能追到「是哪版提示词产出的」。
对应需求：R-7-03（提示词入仓为文件、版本可追溯）、R-L1-20（skill 三件套）、R-L1-18（判据写在 README 并由运行时校验）。
对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（prompt-registry 提供提示词版本）
维护提示：改接口或判据时，必须同步改本文件、docs/skill-roster.md、docs/directory-and-files.md 与相关流程图（规格 §15 变更同步检查表）。
-->

| 项 | 值 |
| -- | -- |
| skill_id | `prompt-registry` |
| 中文岗位名 | 提示词注册表 |
| 归属 | 基础设施 |
| 版本 | `0.1.0` |
| 入口文件 | `run.py` |
| 执行者 | 由编排者派单调用；任何生成类 skill 在调用模型前先经它取模板 |

## 1. 职责

输入一个 `prompt_key`（以及可选的版本与变量），输出**填好变量的提示词正文**，或输出「所有模板的版本清单」。它不生成内容、不调用模型 —— 只保证「要用的提示词是哪一份、哪一版、变量有没有漏」，并把版本登记进 `prompt_versions` 表，供产物表的 `prompt_version` 字段引用。

为什么不把提示词写在代码里：文案质量调优就是改提示词，写死在代码里会出现「改了代码但说不清是从哪版开始变好的」。所以提示词一律是 `templates/prompts/*.md` 文件，本 skill 是它唯一的读取入口（R-7-03）。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| ---- | ---- | ---- | ---- | ---- |
| `command` | enum | 是 | `list` / `get` / `render` / `check` / `sync` | 调用方 |
| `key` | string | `get`/`render` 时必填 | 提示词标识，如 `copy-generate` | 调用方（多来自 `docs/skill-roster.md` 中该 skill 声明的 prompt_key） |
| `version` | string | 否 | 期望版本；与文件内版本不一致时报错，防「以为用的是新版」 | 调用方 |
| `var` | `k=v` 列表 | `render` 时必填 | 模板变量；缺一个即报错 | 上游 skill 的产物 |
| `db` | path | 否 | 数据库路径，默认读 `.env` 的 `DB_PATH` | 环境 |

## 3. 输入校验（进场前，不通过直接退回）

- [ ] `file_exists(templates/prompts/<key>.md)`
- [ ] `enum_in(command, ["list","get","render","check","sync"])`
- [ ] `non_empty(prompt_key)` 且 `prompt_key == 文件名（不含扩展名）`
- [ ] `non_empty(version)`（frontmatter 必填）
- [ ] 渲染前：`variables` 声明的每一项都有对应 `--var`，且正文里每个 `{{占位符}}` 都在 `variables` 里声明

退回时返回：`{ok: false, missing: [...], reason: "<缺什么>"}`（进程退出码 2）

## 4. 输出

| 字段 | 类型 | 说明 | 落库位置 |
| ---- | ---- | ---- | -------- |
| 渲染后的提示词 | text | `render` 的标准输出，`--out` 时落盘 | 文件路径（可选） |
| 模板清单 | JSON | `list --json`：prompt_key / version / used_by / variables / path / purpose | — |
| 模板登记行 | row | `sync`：每个模板一行 | `prompt_versions(prompt_key, version, file_path, note, created_at)` |
| 自检问题清单 | JSON | `check --json`：`{ok, problems[]}` | — |

## 5. 完成判据（自检通过才交给下游）

- [ ] `count(template) >= 1`（`list` 至少列出 1 份模板）
- [ ] `count(problem) == 0`（`check` 必须零问题：声明变量 == 正文占位符，且 `purpose`/`used_by` 非空）
- [ ] `file_exists(<out>)`（给了 `--out` 时文件非零字节）
- [ ] `sync` 后 `prompt_versions` 中 `(prompt_key, version)` 无重复行

自检失败返回：`{ok: false, failed: [...], retry: <次数>}`（`check` 有问题时退出码 1）

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| -------- | ---- | ---- | ------ |
| 模板文件不存在 | **不降级**：直接退回编排者（提示词缺失属于配置错误，换服务没用） | 0 次 | 退回编排者，标「需人工」 |
| frontmatter 缺字段 / prompt_key 与文件名不一致 | 报错并指出文件名 | 0 次 | 同上 |
| 渲染时缺变量 | 报错并列出**全部**缺失变量（不是遇到第一个就停） | 0 次 | 退回上游 skill 补产物 |
| 多给了未声明变量 | 提示并忽略（不阻断） | — | — |
| `sync` 时数据库不存在 | 提示先跑 `python3 scripts/db_init.py` | 0 次 | 同上 |

## 7. 依赖

- 共享库：`.dsh/skills/_shared/prompt_templates.py`（模板解析与渲染）、`.dsh/skills/_shared/env_file.py`（读 `.env`）
- 数据表：`prompt_versions`（`db/schema.sql`）
- 上游：无（模板文件就是源头）
- 下游：`copy-writer`、`storyboard-builder`、`review-reporter` 等一切生成类 skill

## 8. 不在本版范围

- 不做提示词 A/B 自动择优（首版靠人选定，属 WP-12 之后的优化议题）
- 不做模板的可视化编辑页（首版直接改文件）
- 不做多语言模板分支（首版只有中文）
- 不把 `variables` 从正文自动推导（显式声明才能对账，见 `_shared/prompt_templates.py` 的设计取舍）

## 9. 变更记录

| 日期 | 变更 | 来源 |
| ---- | ---- | ---- |
| 2026-10-12 | 首版：list / get / render / check / sync 五个命令；三份模板（copy-generate、storyboard-split、review-report） | N007 |
