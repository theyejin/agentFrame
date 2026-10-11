# 目录及文件说明（Directory & Files）

> 对应需求：R-L2-09（生成一份目录及文件说明文档，供其他运营人员查看；增删改必须同步更新）、R-L1-14（目录与文件名都要有注释说明）。
> 维护规则：**任何目录、文件的增 / 删 / 改，必须在同一次提交内更新本文件**；体检脚本 `scripts/structure_check.py` 会检查本文件是否覆盖了全部顶层目录。
> 最近更新：WP-05 步骤 2（2026-10-12：数据库结构与迁移、建库脚本、数据库模拟测试）。

---

## 0. 怎么用这份文档

1. 想知道「某个目录是干什么的」→ 查第 2 节。
2. 想知道「根目录这些文件各自的作用」→ 查第 3 节。
3. 想知道「我改完东西要不要动这里」→ 查第 5 节同步规则。
4. 想验证文档没写漏 → 跑 `python3 scripts/structure_check.py`。

---

## 1. 顶层总览

```
agentFrame/                     项目根：一支自媒体创作运营团队的全部资产
├── README.md                   仓库入口（状态 / 阅读顺序 / 三级职责 / 红线）
├── .gitignore                  不入库清单（密钥、数据库、大文件、临时目录）
├── .env.example                环境变量样例（只有键名，无真实值）
├── docs/                       文档区：需求、留痕、设计、目录说明
├── .archify/                   图表区：全部 archify 生成的图（一张图一个目录）
├── agents/                     Agent 定义：编排者 + 四条环节 Agent
├── .dsh/skills/                Skill 模块：25 个可独立执行的 skill（DSH 技能根目录）
├── db/                         数据库：结构 DDL + 迁移 + 种子数据（app.db 不入库）
├── dashboard/                  运营控制台页面 + 执行轨迹报告页
├── workflows/                  流程编排定义
├── templates/                  平台预设模板与可复用模板
├── scripts/                    辅助脚本：建库、结构体检、报告生成
├── tests/                      模拟测试：不调用真实外部服务（tests/test_db.py…）
├── logs/                       运行记录（按日期分文件，build-log 数据源）
└── workspace/                  运行期工作区（产物目录，不入库）
```

---

## 2. 目录逐条说明

| 目录 | 中文名 | 用途 | 不放什么 | 何时建成 |
| ---- | ------ | ---- | -------- | -------- |
| `docs/` | 文档区 | 需求规格、讨论留痕、Skill 与目录设计、目录及文件说明 | 代码实现、运行期产物 | WP-01（已有） |
| `.archify/` | 图表区 | 全部 archify 图（整体流程图 + 4 张分环节图），一图一目录 | Mermaid 交付图、中间候选 JSON | N003（已有） |
| `agents/` | Agent 定义 | 编排者与四条环节 Agent 的职责、派单契约、边界 | Skill 实现、运行期数据 | WP-07 |
| `.dsh/skills/` | Skill 模块 | 25 个 skill（18 执行岗 + 7 支撑件），每个只做一件事 | 流程判断、跨 skill 编排 | WP-05 建骨架；WP-07 起逐个落地 |
| `db/` | 数据库 | `schema.sql` 唯一结构来源、`migrations/` 迁移、`seed/` 种子数据 | `*.db` 二进制（不入库） | **WP-05 步骤 2（已建成）** |
| `dashboard/` | 运营控制台 | L3 多人任务管理页面 + L2 执行轨迹报告页 | 业务逻辑实现（页面只调本地数据与 Agent 接口） | WP-08 / WP-11 |
| `workflows/` | 流程编排定义 | 四条线流程与端到端流程：每步交给哪个 skill、何时推进 | Skill 内部逻辑（在 skill 的 README.md） | WP-07 |
| `templates/` | 模板库 | 平台预设模板（字数区间/标题写法/标签数/封面比例）、可复用提示词 | 密钥、账号信息 | WP-06 / WP-07 |
| `scripts/` | 辅助脚本 | `structure_check.py` 结构体检、`build_log_report.py` 报告生成 | 业务实现 | WP-05 起 |
| `tests/` | 模拟测试 | 每步的模拟测试与假数据（fixtures） | 真实账号、真实素材、大体积产物 | 每步同步 |
| `logs/` | 运行记录 | `YYYY-MM-DD.jsonl`，每行一条执行流水 | 手工编辑历史记录 | WP-05 起 |
| `workspace/` | 运行期工作区 | 一条 topic 的产物：文案/分镜/图片/视频工程/发布包 | 需长期保存的关键产物（要另行备份 + 入 `artifacts` 表） | 运行时自动生成 |

---

## 3. 根目录与各目录文件清单

### 3.1 根目录

| 文件 | 用途 | 对应需求 |
| ---- | ---- | -------- |
| `README.md` | 仓库入口：当前状态、阅读顺序、三级职责边界、三条红线、图表与备份约定 | R-L1-01 |
| `.gitignore` | 排除密钥、数据库二进制、运行期大文件、临时目录 | R-L1-04、C-05 |
| `.env.example` | 环境变量**样例**（只有键名与说明，绝无真实值） | C-05、R-L2-14 |
| `docs/README.md` | 文档区索引 | R-L1-14 |
| `.archify/README.md` | 图表区索引与图表命名/交付约定 | R-L2-11~13、R-L2-18 |

### 3.2 `docs/`

| 文件 | 用途 | 对应需求 |
| ---- | ---- | -------- |
| `requirements-spec.md` | **唯一需求来源**（冻结基线，条款编号 R-xx-xx / C-xx / AC-x） | 全文 |
| `discussion-record.md` | 讨论留痕：9 字段节点模板 + N001…N005 | R-D-01~R-D-06 |
| `skill-roster.md` | Skill 岗位名册：18 执行岗 + 7 支撑件（输入/输出/判据/失败处理） | R-L1-12 |
| `skill-readme-contract.md` | `SKILL.md` / `README.md` 必填模板 + 机器可判定校验词汇表 | R-L1-05、R-L1-18 |
| `directory-structure-plan.md` | 目录结构提案与 9 步落地顺序（N005 已确认） | R-L1-13 |
| `directory-and-files.md` | **本文件**：目录及文件说明正式版 | R-L2-09 |
| `decision-log.md` | 决议摘要索引（一行一条「现在以什么为准」） | R-D-01、R-D-03 |

### 3.3 `.archify/`（每张图一个目录）

| 目录 | 内容 | 讨论节点 |
| ---- | ---- | -------- |
| `FLOW-OVERALL-20261012/` | 整体运营流程：`overall-operations.final.json` + `.html` + `README.md` | N003 |
| `FLOW-COPY-20261012/` | 文案线（FLOW-1）：`copy-line.final.json` + `.html` + `README.md` | N004 |
| `FLOW-VISUAL-20261012/` | 视觉线（FLOW-2/3）：`visual-line.final.json` + `.html` + `README.md` | N004 |
| `FLOW-VIDEO-20261012/` | 视频线（FLOW-4/5）：`video-line.final.json` + `.html` + `README.md` | N004 |
| `FLOW-PUBLISH-20261012/` | 分发数据线（FLOW-6/7/8）：`publish-line.final.json` + `.html` + `README.md` | N004 |

### 3.4 `scripts/`

| 文件 | 用途 | 对应需求 |
| ---- | ---- | -------- |
| `structure_check.py` | 目录结构体检：目录/README/说明文档三者一致性 + 禁止项扫描 | R-L1-14、R-L2-09 |
| `db_init.py` | 建库脚本：按 `db/schema.sql`（或 `--from-migrations`）建库并灌种子 | R-L1-04、§7、R-8-01 |
| `build_log_report.py` | 扫 `logs/` 生成 `dashboard/build-log.html` 报告页 | R-L2-05、R-L2-06（WP-08） |

### 3.4.1 `db/`

| 文件 | 用途 | 对应需求 |
| ---- | ---- | -------- |
| `schema.sql` | **结构唯一参考**：13 张表 + 2 个视图 + 3 个一致性触发器 | §7、R-7-01~R-7-05 |
| `migrations/0001_init.sql` | 首次建库迁移（与 `schema.sql` 一致 + 登记 `schema_migrations`）；历史文件不得再改 | R-L1-04 |
| `seed/0001_platform_templates.sql` | 平台预设模板：抖音 / 小红书 / B站 / 视频号 | R-8-01、Q-18 |
| `app.db` | 运行期数据库（不入库，`python3 scripts/db_init.py` 生成） | R-L1-04 |
| `README.md` | 表清单、枚举取值总表、建库与改结构流程 | R-L1-14、R-7-02 |

### 3.4.2 `tests/`

| 文件 | 用途 | 对应需求 |
| ---- | ---- | -------- |
| `test_db.py` | 数据库模拟测试 28 项：结构可建 / 迁移链与 schema 一致 / 种子幂等 / 24 条分镜与编号唯一 / 3 套文案与侧重 / 软删 / 枚举与触发器 / 视图可用 / 建库脚本可用 | R-L2-02、R-L1-19 |
| `fixtures/` | 模拟测试的假数据（随步骤新增） | R-L2-02 |

### 3.5 `logs/`

| 文件 | 用途 | 对应需求 |
| ---- | ---- | -------- |
| `YYYY-MM-DD.jsonl` | 当天执行流水，每行一条 JSON：`{ts, step, actor, skill, action, result, note}` | R-L2-05 |
| `2026-10-12.jsonl` | 本项目首日记录（N001–N005 与 WP-05 步骤 1） | R-L2-05 |

---

## 4. 命名与注释规则

| 对象 | 规则 | 示例 |
| ---- | ---- | ---- |
| 顶层目录 | 小写英文；一个目录一件事 | `dashboard/`、`templates/` |
| 目录中文名 | 每个目录的 `README.md` 必须写「用途：」行，并在本文件第 2 节登记 | `logs/` → 运行记录 |
| Skill 目录 | `kebab-case`，与 `docs/skill-roster.md` 的 `skill_id` 完全一致 | `image-to-video` |
| Skill 三件套 | `SKILL.md`（DSH 入口，带 `name`/`description` frontmatter）+ `README.md`（人读九段模板）+ `run.py` | — |
| 代码文件 | 小写 + 下划线；入口固定 `run.py`（或 `index.ts`） | `structure_check.py` |
| 代码文件头 | 固定四行注释块：文件用途 / 对应需求 / 对应流程图 / 维护提示 | 见 `scripts/structure_check.py` 开头 |
| 图目录 | `FLOW-<线名>-<YYYYMMDD>` | `FLOW-COPY-20261012` |
| 迁移脚本 | `NNNN_描述.sql`，序号连续 | `0001_init.sql` |
| 产物目录 | `workspace/topic-<id>/<环节>/` | `workspace/topic-20261012-01/images/` |
| 日志文件 | `YYYY-MM-DD.jsonl` | `logs/2026-10-12.jsonl` |

---

## 5. 同步规则（改完东西必须动哪些文件）

| 你改了什么 | 必须同步 |
| ---------- | -------- |
| 新增 / 删除 / 改名目录 | 本文件第 1、2 节 + 该目录的 `README.md` + 受影响的 archify 图 + 规格 §12 台账 |
| 新增 / 删除文件 | 本文件第 3 节对应表 + 该目录 `README.md`（若改变了目录职责） |
| 改 skill 接口或判据 | 该 skill 的 `README.md` / `SKILL.md` + `docs/skill-roster.md` + 相关流程图 + 本文件 |
| 改数据库结构 | 新增 `db/migrations/NNNN_*.sql`（不改旧迁移）+ 同步 `db/schema.sql` + `db/README.md` 表与枚举清单 + 本文件 + 规格 §7；再跑 `python3 tests/test_db.py` |
| 改图表 | 用 archify 重新 `render` + `check`（R-L2-13）+ 图的 `README.md` |
| 任何改动 | 追加 `logs/YYYY-MM-DD.jsonl` 一条；跑一次 `scripts/structure_check.py` |

---

## 6. 怎么验证这份文档没写漏

```bash
python3 scripts/structure_check.py          # 人读报告
python3 scripts/structure_check.py --json   # 机器可读（退出码 0 = 通过）
```

检查内容：① 计划内顶层目录是否都在且各有 README.md（含「用途：」行）；② 必需文件是否齐全非空；③ 本文件是否覆盖全部顶层目录；④ 工作区是否混入 `.env` / `*.db` / `.tmp/`。
