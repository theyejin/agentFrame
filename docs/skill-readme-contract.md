# Skill README 契约模板（Skill README Contract）

> 对应需求：R-L1-05~09（Agent / Skill 模块化）、R-L1-14（目录与文件命名注释要求）、R-L1-15（代码文件头注释块）、R-L1-18（交接契约写在 README 并由运行时校验）。
> 用途：**每个 skill 目录下的 `README.md` 必须按本模板填写**，运行时按其中「输入校验 / 完成判据 / 失败处理」三段做校验。
> 讨论来源：N004（2026-10-12）。名册见 `docs/skill-roster.md`。

---

## 1. 为什么要有这份契约

Skill 是「模块化执行」单元，它的可替换性完全依赖 README 写清楚三件事：**要什么（输入校验）、算做完没（完成判据）、坏了怎么办（失败处理）**。
这三段不是给人看的说明，而是**运行时真的会读**的校验规则——所以字段名、机器可判定的写法必须统一。

---

## 1.1 每个 skill 目录的三件套（决策 D-07，N005 实测确认）

> 实测结论：工作区 `.dsh/skills/` **就是 DSH 的技能发现根目录**，DSH 读取的入口文件是 `SKILL.md`（不是 `README.md`）。
> 用一个探针 skill 验证过：建 `.dsh/skills/<id>/SKILL.md` 后即可被 `skill` 工具加载，删除后立即从技能目录消失。

因此每个 skill 目录固定三件套，文件名不得更改：

| 文件 | 给谁看 | 作用 | 是否必需 |
| ---- | ------ | ---- | -------- |
| `SKILL.md` | DSH 运行时 | 自动发现入口：YAML frontmatter（`name` = 目录名、`description` 含「什么时候用」）+ 简短用法正文 | 必需 |
| `README.md` | 运营人员 + 运行时校验 | 按本文件第 2 节九段模板填写，机器可判定的判据从这里读 | 必需 |
| `run.py` | 运行时 | 实现入口（或 `index.ts`） | 必需 |

`SKILL.md` 最小形态：

```markdown
---
name: copy-writer
description: "按给定主题生成 3 套不同侧重点的文案，供人工选定。Use when 编排者需要新增一条内容的候选文案时。"
---

# 文案生成（copy-writer）

用法与判据见同目录 `README.md`（人读说明）。入口：`run.py`。
```

---

## 2. 模板（复制到 `<skill 目录>/README.md` 后逐项填写）

```markdown
# <中文岗位名>（<skill_id>）

<!--
文件用途：<一句话说明这个 skill 干什么>
对应需求：<R-xx-xx、...>
对应流程图：<.archify/FLOW-XXX-.../xxx.html>
维护提示：改接口或判据时，必须同步改本文件、docs/skill-roster.md 与相关流程图（见规格 §15 变更同步检查表）
-->

| 项 | 值 |
| -- | -- |
| skill_id | `<kebab-case>` |
| 中文岗位名 | <通俗命名，与 skill-roster.md 一致> |
| 归属 | <文案线 / 视觉线 / 视频线 / 分发数据线 / 基础设施> |
| 版本 | `0.1.0` |
| 入口文件 | `run.py` |
| 执行者 | <节奏：由编排者派单调用> |

## 1. 职责
<一段话：输入什么 → 做什么 → 输出什么。不写实现细节。>

## 2. 输入
| 字段 | 类型 | 必填 | 说明 | 来源 |
| ---- | ---- | ---- | ---- | ---- |
| `task_id` | string | 是 | 任务编号 | 编排者派单 |
| ... | ... | ... | ... | ... |

## 3. 输入校验（进场前，不通过直接退回）
- [ ] <可机器判定的规则 1，例如：分镜条数 == 24>
- [ ] <规则 2>
退回时返回：`{ok: false, missing: [...], reason: "<缺什么>"}`

## 4. 输出
| 字段 | 类型 | 说明 | 落库位置 |
| ---- | ---- | ---- | -------- |
| ... | ... | ... | `artifacts` / `step_runs` / 文件路径 |

## 5. 完成判据（自检通过才交给下游）
- [ ] <可机器判定的规则 1，例如：编号 1–24 连续无重复>
- [ ] <规则 2>
自检失败返回：`{ok: false, failed: [...], retry: <次数>}`

## 6. 失败处理
| 失败情形 | 处理 | 上限 | 超限后 |
| -------- | ---- | ---- | ------ |
| <模型/服务失败> | <按适配器降级链重试> | 3 次 | 退回编排者并标记「需人工」 |

## 7. 依赖
- 统一接口：`llm-adapter`（不直接调用具体服务名，R-L2-14）
- 提示词：`prompt-registry`（记录 `prompt_version`）
- 留痕：`artifact-recorder`（产物表、步骤流水表）

## 8. 不在本版范围
- <显式推迟的能力，避免被误解为漏做>

## 9. 变更记录
| 日期 | 变更 | 来源 |
| ---- | ---- | ---- |
| YYYY-MM-DD | 首版 | N0NN |
```

---

## 3. 机器可读的三段（运行时校验用）

`输入校验` / `完成判据` 两段的复选框条目，必须是**可判定表达式**，推荐用下面这套最小词汇（首版只支持这些）：

| 表达式写法 | 含义 | 例子 |
| ---------- | ---- | ---- |
| `count(x) == N` | 条数等于 N | `count(shot) == 24` |
| `ids_continuous(x)` | 编号从 1 连续 | `ids_continuous(shot)` |
| `unique(field)` | 字段无重复 | `unique(draft.angle)` |
| `in_range(field, a, b)` | 数值 / 长度落在区间 | `in_range(draft.length, 300, 500)` |
| `all_resolution_equal(x)` | 分辨率一致 | `all_resolution_equal(shot_image)` |
| `file_exists(path)` | 文件存在且非零字节 | `file_exists(manifest.json)` |
| `non_empty(field)` | 非空 | `non_empty(brief)` |
| `enum_in(field, [...])` | 取值在枚举内 | `enum_in(platform, ["情绪冲突","干货教程","热点观点"])` |
| `no_auto_publish()` | 红线守卫 | 任何发布路径必过 `publish-guard` |

> 校验器映射：`storyboard-validator` 负责 `count/ids_continuous`；`image-consistency-checker` 负责 `all_resolution_equal/file_exists`；`publish-guard` 负责 `no_auto_publish`；其余通用表达式由 `artifact-recorder` 在登记前统一跑一遍。

---

## 4. 目录级 README（每个业务目录都要有）

除 skill 自身的 README，**每个目录**（`agents/`、`db/`、`dashboard/`、`logs/`、`workflows/`、`workspace/` 等）都必须有一份 `README.md`，按下面三行起头：

```markdown
# <目录中文名>（<目录名>/）
- 用途：<这个目录放什么，不放什么>
- 维护提示：增删文件后同步更新 `docs/directory-and-files.md`（WP-09 产出）
```

---

## 5. 代码文件头注释块（R-L1-15）

每个 `.py` / `.ts` / `.sql` 文件**开头必须有注释块**，固定四行：

```python
# 文件用途：<一句话>
# 对应需求：R-xx-xx（多个用逗号分隔）
# 对应流程图：.archify/FLOW-XXX-.../xxx.html
# 维护提示：<改了这里要同步改什么>
```

数据库文件额外写：本次迁移的 `revision` 与回滚方式。

---

## 6. 变更同步（照规格 §15 逐项打勾）

改任何一个 skill 的接口或判据，都必须同步：
1. 该 skill 的 `README.md`；
2. 该 skill 的 `SKILL.md`（若 `description` 或用法有变）；
3. `docs/skill-roster.md` 对应行；
4. 相关流程图用 archify 重新生成并通过 `archify check`；
5. `docs/directory-and-files.md`（N005 已产出，实时维护）；
6. 本文件（若动了模板本身）；
7. 讨论记录追加一条（若属结构级变更）。
