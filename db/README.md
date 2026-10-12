# 数据库（`db/`）

- 用途：存放本地数据库的**结构与迁移脚本** —— 一条自媒体内容从选题到复盘的全过程留痕（话题、任务、流水、产物、人工介入、指标、版本）。
- 不放什么：`*.db` 二进制文件（R-L1-04，由 `.gitignore` 排除）、图片视频等大文件（R-7-01，只登记路径）、真实密钥。

## 计划内容

| 文件 | 用途 |
| ---- | ---- |
| `schema.sql` | **结构唯一参考**：全部表、索引、触发器、视图；建库与评审都以它为准 |
| `migrations/0001_init.sql` | 首次建库迁移（内容与 `schema.sql` 一致 + 写 `schema_migrations`）；**已发布的历史不得再改** |
| `migrations/0002_add_visual_gates.sql` | 视觉线关口迁移（`hitl_events.gate` 由 3 值扩到 5 值，重建表并回填） |
| `migrations/0003_add_hotspots_and_publish.sql` | 分发数据线迁移：新增 `hotspot_batches` / `hotspot_items` / `publish_records` 三张表与索引 |
| `seed/0001_platform_templates.sql` | 平台预设模板种子（抖音 / 小红书 / B站 / 视频号） |
| `app.db` | 运行期数据库文件（**不入库**，用脚本生成） |

## 维护提示

- 改结构的三步铁律：① 新增 `migrations/NNNN_描述.sql`（不改旧迁移）；② 同步 `schema.sql`；③ 更新本文件的表与枚举清单 + `docs/directory-and-files.md`，再跑 `python3 tests/test_db.py`。
- 数据库二进制不入库；换机器用 `python3 scripts/db_init.py` 重建。

---

## 1. 建库与验证

```bash
python3 scripts/db_init.py                    # 按 schema.sql 建库 + 灌种子 → db/app.db
python3 scripts/db_init.py --from-migrations  # 按 migrations 顺序建库（验证迁移链）
python3 scripts/db_init.py --db /tmp/x.db --force
python3 tests/test_db.py                      # 28 项结构与约束模拟测试
```

`--force` 会删除已存在的数据库，默认拒绝覆盖（防误删）。

## 2. 表清单

| 表 | 中文名 | 回答什么问题 | 关键约束 |
| -- | ------ | ------------ | -------- |
| `topics` | 话题 | 选题从哪来、关键词、创建人、状态 | `source` 枚举 `manual`/`hotspot`（R-7-05） |
| `tasks` | 任务 | 属于哪个话题、走到哪步、状态、优先级、目标平台、内容类型、选定哪套文案、何时选定、当前处理人 | `word_min <= word_max`；`selected_plan ∈ 1..3` |
| `copy_variants` | 文案候选 | 3 套文案各自的侧重维度与正文 | `plan_no ∈ 1..3` 且每任务唯一；软删 `status` |
| `storyboards` | 分镜 | 24 条（6×4）分镜的画面描述与时长 | `shot_no ∈ 1..24` 且每任务唯一（R-L1-19） |
| `step_runs` | 步骤流水 | 第几步、哪个 skill、实际用哪个适配器、耗时、失败原因 | `status='failed'` 必须填 `error`（触发器） |
| `artifacts` | 产物 | 产物类型、路径、大小、指纹、模型版本、提示词版本 | `model_version`/`prompt_version` 非空（R-7-03）；图片视频 `size_bytes>0` |
| `hitl_events` | 人工介入 | 谁、何时、在哪个关口、确认/拒绝/调整、当时快照 | `gate` 五枚举；不可跳过（R-8-02、C-02） |
| `metrics` | 数据指标 | 每期三项指标的数值、统计周期、采集时间 | `metric_key` 三枚举；周期与采集时间非空（R-7-04） |
| `hotspot_batches` | 热点批次 | 哪一批热点、关键词、来源、周期、条目数、汇总表与导出文件落在哪 | `batch_key` 唯一；`source` 枚举（D-15） |
| `hotspot_items` | 热点条目 | 每条热点的标题、分类、热度、来源链接 | `batch_id` 外键 + 级联删除；`category` 四枚举 |
| `publish_records` | 发布记录 | 哪个任务、发到哪个平台与账号、发布包与成片在哪、状态与发布链接 | `status` 四枚举；`published` 只能由人回填（C-08、D-16） |
| `adapter_registry` | 适配器声明 | 能力、是否要密钥、是否计费、失败特征、降级顺序 | `adapter_id` 唯一；`fallback_order > 0`（R-L2-16） |
| `platform_templates` | 平台模板 | 各平台字数区间、标题写法、标签数、封面比例 | 平台名唯一；`word_min <= word_max`（R-8-01） |
| `prompt_versions` | 提示词版本 | 提示词标识 + 版本 + 仓库内文件路径 | `(prompt_key, version)` 唯一（R-7-03） |
| `versions` | 版本备份点 | 每次结构变更对应的 commit / tag 与摘要 | — |
| `schema_migrations` | 迁移台账 | 已应用过哪些迁移 | `revision` 主键 |

视图：

| 视图 | 用途 |
| ---- | ---- |
| `v_task_progress` | 每个任务走到第几步、成功几步、失败几步（控制台任务列表直接读它） |
| `v_pending_publish` | 待发布清单：分镜数、成片数、最近一次发布授权时间（关口③核对页用） |

## 3. 状态与枚举取值（R-7-02：文档未列出的取值一律非法）

| 字段 | 允许取值 |
| ---- | -------- |
| `topics.source` | `manual` 人工提交 / `hotspot` 热点派生 |
| `topics.status` | `new` 新建 / `in_progress` 进行中 / `done` 已完成 / `archived` 归档 |
| `tasks.stage` | `copy` 文案 / `visual` 视觉 / `video` 视频 / `publish` 分发 / `metrics` 数据 / `review` 复盘 / `closed` 结束 |
| `tasks.status` | `pending` 待处理 / `running` 执行中 / `waiting_human` 等人工 / `blocked` 阻塞 / `done` 完成 / `failed` 失败 / `cancelled` 取消 |
| `tasks.priority` | `1` 高 / `2` 中 / `3` 低 |
| `tasks.content_type` | `情绪冲突` / `干货教程` / `热点观点` / `其他`（F-03、Q-3） |
| `copy_variants.plan_no` | `1` / `2` / `3` |
| `copy_variants.focus` | `hook` 开头钩子 / `emotion` 情绪强度 / `cta` 行动号召 |
| `copy_variants.status` | `active` 有效 / `deleted` 已删（软删） / `superseded` 被重新生成取代 |
| `storyboards.shot_no` | `1`–`24` |
| `step_runs.status` | `pending` / `running` / `ok` / `failed` / `skipped` |
| `artifacts.kind` | `copy` / `storyboard` / `image` / `video` / `audio` / `manifest` / `table` / `report` / `publish_package` |
| `hitl_events.gate` | `gate1_select_copy` 选定文案（选择）/ `gate2_edit_video` 剪辑干预（调整）/ `gate3_publish_auth` 发布授权（授权） |
| `hitl_events.action` | `confirm` 确认 / `reject` 拒绝 / `adjust` 调整 |
| `metrics.metric_key` | `views` 播放量 / `engagements` 互动量（赞+藏+评） / `follower_gain` 涨粉数 |
| `metrics.source` | `manual` / `browser` / `api` / `export` |
| `hotspot_batches.source` | `manual` 人工给 / `browser` 浏览器采集 / `fixture` 离线夹具 / `api` 接口 / `export` 导入 |
| `hotspot_items.category` | `情绪冲突` / `干货教程` / `热点观点` / `其他`（未识别的分类一律归 `其他`） |
| `publish_records.status` | `filled` 已生成填写清单 / `pending` 待发布 / `published` 已发布（仅真人回填）/ `failed` 发布失败 |
| `adapter_registry.kind` | `llm` / `image` / `split` / `video` / `browser` / `doc` / `metrics` |

## 4. 与需求条款的对应

| 需求 | 落地位置 |
| ---- | -------- |
| R-7-01 大文件不入库 | `artifacts.path` + `size_bytes` + `sha256`，表内无二进制列（测试断言） |
| R-7-02 状态取值枚举完整 | 全部枚举字段带 `CHECK`，取值见本文件第 3 节 |
| R-7-03 版本可复现 | `artifacts.model_version` / `prompt_version` 非空；`prompt_versions` 登记提示词文件路径 |
| R-7-04 三项指标带周期 | `metrics`：`metric_key` 三枚举 + `period_start/period_end/collected_at` 非空 |
| R-7-05 topic 一对多 | `tasks.topic_id` 外键；`topics.source` 枚举 |
| R-8-01 平台模板 | `platform_templates` + 种子数据 |
| R-8-03 处理人软锁 | `tasks.operator` + `tasks.locked_at` |
| R-L1-19 交接校验 | `storyboards` 24 条与编号唯一、`copy_variants` 3 套与侧重唯一 |
| R-L2-16/17 适配器 | `adapter_registry` 声明；`step_runs.adapter_used` 记实际值 |
| C-08 发布红线 | `hitl_events.gate3_publish_auth` 是唯一放行凭据（§8.3） |

## 5. 时间与路径约定

- 时间：ISO-8601 文本，本地时区，例 `2026-10-12T06:00:00+08:00`。
- 产物路径：相对仓库根，例 `workspace/topic-1/images/shot-01.png`。
- 换机器恢复：`git clone` → `python3 scripts/db_init.py` → 数据靠 `logs/*.jsonl` 与 `workspace/` 备份恢复（不入库）。
