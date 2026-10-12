<!--
文件用途：运营控制台（dashboard/）与搭建过程报告页（仓库根目录 build-log.html）的说明 —— 页面清单、字段口径、流转路径、设计选择理由与自检方式。
对应需求：R-L3-01（本地可访问）、R-L3-02（页面 + 字段说明）、R-L3-03（页面流转与设计选择理由）、R-L3-04（五类操作可在页面完成）、R-L3-05（只调本地脚本、不持有凭据）、R-L2-05/R-L2-06（过程日志与报告页）、AC-3、Q-6。
对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（FLOW-9 运营人员操作面）。
维护提示：字段口径在 .dsh/skills/_shared/console.py（STAGE_LABELS / STATUS_LABELS / GATE_LABELS / RUN_WHITELIST）；页面改字段、白名单加 skill，都要同步本文件与 tests/test_dashboard.py。
-->

# 运营控制台与搭建过程报告页

运营人员每天用的那个界面：看环节、看待办、生成与选定文案、走发布、看数据、出复盘；以及一条任务从头到尾的留痕怎么查。**所有页面都只跟本机的本地服务说话**，不直连数据库、不持有任何平台账号与密钥。

## 怎么本地打开

```bash
python3 scripts/serve_dashboard.py            # 起本地服务（只监听 127.0.0.1:8787）
python3 scripts/serve_dashboard.py --port 9000
python3 scripts/serve_dashboard.py --check    # 只生成一次数据快照并打印摘要（自检用，不监听端口）
python3 scripts/build_log_report.py           # 重新生成根目录 build-log.html 与 build-log.data.json
python3 tests/test_dashboard.py               # 控制台与报告页的模拟测试
```

打开 <http://127.0.0.1:8787/> 是控制台；<http://127.0.0.1:8787/build-log.html> 是搭建过程报告页（Q-6：两个独立页面）。控制台只监听 `127.0.0.1`；直接双击 HTML 只能看到静态外壳（页面要靠本地服务取数），页面顶部会给出提示。

## 页面与字段说明

| 页面 | 文件 | 它回答的问题 |
| --- | --- | --- |
| 总览 | `dashboard/index.html` | 今天有多少任务、卡在哪、发布队列多长、这期数据怎么样 |
| 任务流转 | `dashboard/pages/tasks.html` | 一条任务现在谁在管、走到哪一步、下一步找谁、怎么退回 |
| 文案生成 | `dashboard/pages/copy.html` | 提示词与字数范围是什么、三套候选差在哪、选定哪一套 |
| 发布操作 | `dashboard/pages/publish.html` | 发布包齐不齐、红线过没过、谁授权的、链接回填了没 |
| 数据与复盘 | `dashboard/pages/metrics.html` | 三项指标多少、热点从哪来、复盘说了什么 |
| 搭建过程报告 | `build-log.html`（仓库根目录） | 整个过程哪天做了什么、结果如何 |

### 总览页字段

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| 任务总数 / 进行中 | 全部任务与状态为进行中的任务数 | `tasks` |
| 待人工决议 | 停在人工关口、且关口还没有决议的任务数 | `gate_todos` |
| 发布队列 | 成片齐备、停在发布环节的任务数（含填写状态） | 视图 `v_pending_publish` |
| 当期播放量 / 互动量 / 涨粉数 | 当前周期的三项指标合计 | `metrics` 表（口径见 `_shared/metrics.py`） |
| 互动率 | 互动量 ÷ 播放量 | 同上 |
| 环节看板 | 每个环节的任务数、进行中、等人工 | `stage_board()` |
| 最近过程日志 | 最近若干条 `logs/*.jsonl` 记录 | `logs_entries()` |

### 任务流转页字段

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| 任务 / 选题 / 平台 | 任务号、选题标题与关键词、目标平台 | `tasks` + `topics` |
| 环节 | 文案 / 视觉 / 视频 / 发布 / 指标 / 复盘 / 收尾 | `tasks.stage` |
| 状态 | 待开始 / 进行中 / 等人工 / 受阻 / 完成 / 失败 | `tasks.status` |
| 步骤 / 产物 | 已登记的步骤流水条数、产物条数 | `step_runs` / `artifacts` |
| 最后技能 | 最近一次登记的技能 | `step_runs` |
| 轨迹面板 | 步骤流水、产物（含角色与模型/提示词版本）、关口事件、指标与发布 | `task_trace()` |

### 文案生成页字段

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| 平台 / 类型 / 字数范围 | 派单时定下的输入（F-01/F-02/F-03） | `tasks` |
| 方案 1~3 · 侧重 | 开头钩子 / 情绪强度 / 行动号召（互不重复） | `copy_variants.focus` |
| 字数 | 该套文案字数（必须落在字数范围内） | `copy_variants.word_count` |
| 选定套号 | 关口① 选中了第几套；选定后卡片高亮 | `tasks.selected_plan` |

### 发布操作页字段

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| 分镜 / 成片 | 该任务的分镜与成片数量 | 视图 `v_pending_publish` |
| 填写状态 | 还没填写 / 已填写（等授权）/ 已填写（已授权）/ 已发布 / 填写失败 | `publish_records.status` |
| 最近授权 | 关口③ 最近一次授权时间（真人给的） | `hitl_events` |
| 发布链接 | 人工发布后回填的作品地址 | `publish_records.publish_url` |
| 填写清单 | 要填的标题 / 标签 / 封面 / 账号标签，`submitted` 恒为 `false` | 产物 `role=package` |

### 数据与复盘页字段

| 字段 | 含义 | 来源 |
| --- | --- | --- |
| 三项指标 | 播放量 / 互动量（赞藏评合计）/ 涨粉数 | `metrics` 表 |
| 互动率 | 互动量 ÷ 播放量 | `metrics_trend()` |
| 周期 | 指标的统计区间（`period_start ~ period_end`） | `metrics` 表 |
| 批次 / 分类分布 | 热点从哪一批来、每个分类多少条、热度多少 | `hotspot_batches` / `hotspot_items` |
| 复盘报告 | 当期数据复盘与下一轮优化建议（只建议，不改提示词） | 产物 `role=review` |

## 页面流转路径

```
派单（总览 / 任务流转）
   └─► 文案生成：生成三套 ──► 关口① 选定（记：谁、第几套、当时的候选快照）
          └─► 分镜 24 条 ──► 参考图 ──► 整图 ──► 切图 ──► 一致性体检
                 └─► 打包图文 ──► 草稿视频 ──► 关口② 调整 ──► 剪辑版 ──► 成片+封面 ──► 发布准备
                        └─► 发布操作：准备发布包 ──► 红线自检 ──► 关口③ 授权 ──► 人工手工发布 ──► 回填链接
                               └─► 数据与复盘：采一期指标 ──► 出复盘报告
                                      （热点线：采集 ──► 汇总表 ──► 飞书同步 ──► 复盘报告引用）
```

环节之间「下一步找谁」与交接契约不在页面里写死，页面按任务当前环节去调对应 skill；派单书（`workspace/topic-<id>/plan/`）里带着进场校验、产出物清单与完成判据。

## 设计选择理由

- **静态 HTML + 本地服务，不用前端框架**：控制台是内网自用的小工具，两三百行原生 JS 足够；不引构建链，任何装了 Python 3 的机器 `python3 scripts/serve_dashboard.py` 就能开，页面文件也能被 `structure_check` 与测试直接检查。
- **页面绝不直连数据库**：所有数据走 `/api/*`，落在只读数据层 `_shared/console.py`。口径只写一遍（例如「互动率 = 互动量 ÷ 播放量」），页面改版不会改坏口径；`tests/test_dashboard.py` 还断言这一层里没有写操作。
- **写操作全部经本地服务调 skill，走白名单**：页面按钮不是「随便跑命令」，而是 `/api/run` 上的白名单（见下表）。白名单与参数校验在服务端，页面传入 `--db`、`--allow-paid` 一律被拒——页面既不能换库，也不能绕开 C-09 的付费门禁。
- **控制台不持有任何账号凭据**（R-L3-05）：账号只以「标签」形式记录（`publish_records.account_label`），浏览器自动化与飞书同步都是本地脚本里的事，真实账号与密钥不进页面、不进库。
- **系统不自动发布**（C-08）：填写清单里 `submitted` 恒为 `false`，发布队列里 `can_auto_publish` 恒为 `false`；页面只准备、只记录，发布由真人手工完成后回填链接。
- **build-log 与库解耦**：报告页的数据源是 `logs/*.jsonl`（每一步都追加），生成器 `scripts/build_log_report.py` 同时写出 `build-log.data.json`（可追溯）并把它内联进 `build-log.html`，所以报告页双击也能看；控制台首页只做入口链接（Q-6：两个独立页面）。

## 本地服务接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/health` | 服务与库状态、当前可用白名单 |
| `GET /api/snapshot` | 整包数据（任务 / 环节看板 / 待办 / 发布队列 / 指标 / 热点 / 最近日志） |
| `GET /api/task?id=N` | 一条任务的完整轨迹 |
| `GET /api/copy?id=N` | 三套候选文案与选定套号 |
| `GET /api/artifacts?id=N&kind=…&role=…` | 文字类产物正文（对比卡 / 填写清单 / 复盘报告） |
| `POST /api/run` | 调用白名单里的本地脚本（参数按列表传，无 shell） |

## 白名单（页面能调的脚本）

`copy-writer generate`、`storyboard-builder build`、`storyboard-validator check`、`reference-image-builder build`、`grid-image-builder build`、`image-splitter split`、`image-consistency-checker check`、`asset-packager pack`、`image-to-video build`、`auto-editor edit`、`video-exporter export`、`title-cover-prep prepare`、`hitl-gate open|resolve|status`、`browser-publisher prepare|mark-published|status`、`publish-guard check`、`metrics-collector collect`、`review-reporter report`、`hotspot-collector collect`、`table-builder build`、`feishu-sync sync`、`task-decomposer dispatch|plan`、`summary-writer summarize`、`artifact-recorder topic-create|task-create|task-update|task-show|list`。

新增可调用脚本要改两处：`_shared/console.py` 的 `RUN_WHITELIST`、本文件上面的清单。

## 不在本版范围

- 不做登录与多用户权限（本机自用，操作人用文本框记名）；
- 不代持平台账号、不提供「一键发布」（C-08）；
- 不做实时推送（手动刷新页面即可）；
- 控制台不写库：所有写操作都必须经过 skill（页面只是触发器）。

## 变更记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-10-12 | v0.2.0 | 随 WP-05 步骤 8 落地：总览、任务流转、文案生成、发布操作、数据与复盘五页 + 本地服务（`/api/*` + 白名单）+ build-log 报告页。 |
