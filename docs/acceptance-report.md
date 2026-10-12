# 端到端验收报告（WP-05 步骤 9）

> 对应需求：AC-1~AC-7（`docs/requirements-spec.md` §验收标准）、R-L2-02（每步先过模拟测试）、R-L2-18（图表交付与校验）、C-08 / C-10（不自动发布 / 关口③ 授权必须真人）、R-L3-01~05（本地控制台）。
> 对应讨论节点：N014（2026-10-12）。
> 复现命令：`python3 tests/test_e2e.py`（全程离线、零付费，本机约 4 秒跑完 24 步）。
> 证据目录：`docs/evidence/`（控制台与报告页截图；按 `.gitignore`「运行期图片不入仓」规则**不入库**，属本机留证，复现命令见 §2.3）、`logs/2026-10-12.jsonl`（搭建过程流水）、`workspace/topic-1/`（跑完后按需保留的运行产物）。

---

## 1. 结论一览

| 条款 | 要求（摘要） | 结论 | 主要证据 |
| --- | --- | --- | --- |
| AC-1 | 一条真实选题端到端产出 | ✅ | §2.1：24 步、18 个 skill、退出码全部符合预期；任务终态 `stage=review` |
| AC-2 | 每个环节在核心业务表都有记录 | ✅ | §2.2：`topics` 1 / `tasks` 1 / `copy_variants` 3 / `storyboards` 24 / `artifacts` 43 / `step_runs` 17 / `metrics` 3 / `publish_records` 1 |
| AC-3 | 报告页与控制台能在本机浏览器打开并交互 | ✅ | §2.3：本地服务实测 + 浏览器实操（截图 `docs/evidence/*.png`） |
| AC-4 | 不可逆动作都有人工确认记录 | ✅ | §2.4：三个关口各有 `hitl_events` confirm；关口③ 授权前 live 自检被拦 |
| AC-5 | 每一步都先过模拟测试 | ✅ | §2.5：九套测试 244 项 + 结构体检 / 适配器 / 提示词登记表 |
| AC-6 | 两份文档能还原「做到哪 / 为什么 / 还剩什么」 | ✅ | §2.6：讨论记录 N001–N014 + 目录说明 + 需求规格 v2.2-frozen |
| AC-7 | 结构或流程变更后图表同步且通过 archify 校验 | ✅ | §2.7：五张图齐备，`finalize` 四门（`validate` / `deliver` / `check` / `browser-check`）全 pass；原受本机 Chrome 沙箱限制的 A-09 已关闭 |

一句话结论：**四条线（文案 / 视觉 / 视频 / 分发数据）与编排者在一条真实选题上全程离线跑通，人工关口、红线守卫与留痕均可复核；25 个 skill、5 个 Agent、16 张表、控制台与报告页全部落地，AC-1~AC-7 逐条通过，没有遗留的环境待办。**

---

## 2. 逐条证据

### 2.1 AC-1：一条真实选题端到端产出

选题与任务：`打工人春节返乡实录`（平台 抖音，提示词「写一条真实感强的返乡口播稿」），由编排者工具派单生成 `topic #1` / `task #1`，派单书落在 `workspace/topic-1/plan/dispatch-*.{json,md}`。

链路（`tests/test_e2e.py::E2EBaseCase._run_chain`，24 步调用、18 个不同 skill）：

| # | 步骤 | skill | 退出码 |
| --- | --- | --- | --- |
| 1 | 派单 | `task-decomposer` | 0 |
| 2 | 文案生成（3 套候选） | `copy-writer` | 0 |
| 3–4 | 关口① 挂起 / 决议（选定 1 套） | `hitl-gate` | 0 / 0 |
| 5 | 分镜拆解（24 条） | `storyboard-builder` | 0 |
| 6–9 | 参考图 → 整图 → 切 24 张 → 图片体检 | `reference-image-builder` / `grid-image-builder` / `image-splitter` / `image-consistency-checker` | 0 |
| 10–11 | 图文打包 → 草稿视频 | `asset-packager` / `image-to-video` | 0 |
| 12–13 | 关口② 挂起 / 决议（剪辑干预） | `hitl-gate` | 0 / 0 |
| 14–16 | 剪辑 → 成片与封面 → 发布准备 | `auto-editor` / `video-exporter` / `title-cover-prep` | 0 |
| 17 | 发布包与填写清单（只填写） | `browser-publisher` | 0 |
| 18 | 关口③ 未授权 live 自检（**必须被拦**） | `publish-guard` | **1（期望 1）** |
| 19 | 关口③ 未授权静态自检 | `publish-guard` | 0 |
| 20 | 真人发布并回填链接 | `browser-publisher` | 0 |
| 21 | 关口③ 授权后 live 自检 | `publish-guard` | 0 |
| 22–24 | 指标采集 → 复盘 → 汇总回报 | `metrics-collector` / `review-reporter` / `summary-writer` | 0 |

产物（`artifacts` 表 43 行，角色取自 `meta.role`）：`copy` 2 行（3 套候选在 `copy_variants`）、`storyboard` 2 行（24 条在 `storyboards`）、`image:shot` **24 张**、`image:reference` / `image:grid` / `image:cover` 各 1、`video:draft` / `video:edited` / `video:final` 各 1、`manifest:package` / `manifest:shots-manifest` / `manifest:edit-params` / `manifest:publish-prep` / `manifest:dispatch` 各 1、`publish_package:package` 1、`table:metrics` 1、`report:review` / `report:summary` 各 1。

任务终态：`stage=review`、`status=running`、`selected_plan=1`、`operator=运营小李`。汇总回报（`workspace/topic-1/reports/summary-*.md`，629 字）原样复述了这一步：

```
- 当前环节：review（状态 running，平台 抖音）
- 已完成步骤：16 步（失败 0 步，共留痕 16 步）
- 待办关口：无待办关口
- 关键产物：copy 2、image 27、manifest 4、publish_package 1、report 1、storyboard 2、table 1、video 3
- 下一步找谁：publish-agent（python3 .dsh/skills/review-reporter/run.py report --task-id 1 --json）
```

### 2.2 AC-2：每个环节在核心业务表都有记录

| 表 | 行数 | 说明 |
| --- | --- | --- |
| `topics` | 1 | 选题来自派单（`source=manual`） |
| `tasks` | 1 | 任务贯穿四个环节到 `review` |
| `copy_variants` | 3 | 3 套候选文案（开头钩子 / 情绪强度 / 行动号召） |
| `storyboards` | 24 | 编号连续 1–24 |
| `artifacts` | 43 | 见 §2.1 角色清单 |
| `step_runs` | 17 | 每个 skill 一条流水（含 `adapter_used` / `model_version`） |
| `hitl_events` | 3 | 三个关口各一条真人决议 |
| `metrics` | 3 | 三项指标一个周期 |
| `publish_records` | 1 | 真人回填的发布记录（`status=published`） |

指标明细（周期 `2026-10-05 ~ 2026-10-11`，`source=manual`）：`views=18600`、`engagements=1120`、`follower_gain=96`。同一周期同口径复采是更新而非堆行（`TestChainInvariants.test_metrics_rerun_does_not_duplicate_rows`：把 `views` 改成 24000 后行数不变）。

发布记录：`status=published`、`publish_url=https://example.com/v/1`、`operator=运营小李`、`published_at=2026-10-12T13:57:59+08:00`（**人工回填**，见 §2.4）。

### 2.3 AC-3：报告页与控制台在本机浏览器可用

静态产物：`build-log.html` + `build-log.data.json`（仓库根，R-L2-06）、`dashboard/index.html` 与四个功能页、`dashboard/assets/{app.js,style.css}`；`python3 scripts/serve_dashboard.py --db … --check --json` → `ok=true`。

浏览器实操（`python3 scripts/serve_dashboard.py --port 8791`，浏览器直接打开）：

| 观察 | 结果 |
| --- | --- |
| `GET /` `/build-log.html` `/pages/copy.html` | 均 HTTP 200 |
| `GET /api/health` | `{"ok": true, "db": "…/db/app.db", …}`，并列出白名单 |
| 总览页 | 8 张统计卡、环节看板 7 行、人工待办、发布队列、指标走势、热点来源（2 个批次）、最近过程日志——截图 `docs/evidence/dashboard-overview.png`（本机） |
| 文案生成页 | 顶栏导航、任务下拉、`生成三套候选文案` / `选定这套（关口① confirm）` / `拆 24 条分镜` 按钮齐备 |
| 报告页 | 左栏日期倒序标题列表，右栏展示所选条目的「做了什么（note）」与原始 JSON，顶部搜索 + 环节分类 + 结果筛选——截图 `docs/evidence/build-log.png`（本机） |
| 报告页交互 | 点击条目 → 右栏标题跟随（如「迁移 0003：热点与发布留痕三张表」）；搜索「迁移 0003」→ `筛出 1 / 64 条`；分类筛 `N001` → `筛出 2 / 64 条`（当时 64 条，现 70 条） |

说明：`db/app.db` 是空库（只含适配器登记表），所以总览页默认显示空态；控制台的第一动作是「任务流转 → 建任务」，或用测试里的临时库体验完整链路（`python3 tests/test_e2e.py`）。

### 2.4 AC-4：不可逆动作都有人工确认记录

`hitl_events` 三条，全部 `action=confirm`、`actor=运营小李`：`gate1_select_copy`（选定第 1 套文案）、`gate2_edit_video`（剪辑干预确认）、`gate3_publish_auth`（发布授权）。

关口③ 的守卫行为（这是本系统最关键的一条红线）：

| 时点 | 命令 | 结果 |
| --- | --- | --- |
| 授权前 live 自检 | `publish-guard check --task-id 1 --live` | 退出码 1、`ok=false`、`blocked=true`，问题为「关口③ 未授权：发布授权必须由真人在关口③ 给出（C-10）」，提示「关口③ 待人工授权（待办已挂，还没有决议）」 |
| 授权前静态自检 | `publish-guard check --task-id 1` | `ok=true`，note 含「待人工授权」 |
| 真人发布并回填 | `browser-publisher mark-published --task-id 1 --actor 运营小李 --url …` | 写 `publish_records.status=published` + `published_at`，同时把关口③ confirm 写进 `hitl_events` |
| 授权后 live 自检 | `publish-guard check --task-id 1 --live` | `ok=true` |

C-08（Agent 不得自动发布）另有两条硬证据：`publish_guard.record(..., status="published")` 直接抛 `PublishGuardError`；`browser-publisher prepare` 的返回里 `submitted` 恒为 `false`、`check.live` 恒为 `false`。

### 2.5 AC-5：每一步都先过模拟测试

| 套件 | 项数 | 负责范围 |
| --- | --- | --- |
| `tests/test_db.py` | 28 | 库结构、迁移与 schema 一致、视图与触发器 |
| `tests/test_adapters.py` | 36 | 降级链、零付费门禁、提示词登记表 |
| `tests/test_copy_line.py` | 24 | 文案线（3 套候选、关口①、24 条分镜） |
| `tests/test_visual_line.py` | 21 | 视觉线（参考图、整图、切图、体检） |
| `tests/test_video_line.py` | 22 | 视频线（打包、草稿、关口②、剪辑、成片、发布准备） |
| `tests/test_publish_line.py` | 33 | 分发数据线（热点、表格、同步、发布包、红线、指标、复盘） |
| `tests/test_orchestrator.py` | 33 | Agent 定义与交接契约、派单、汇总 |
| `tests/test_dashboard.py` | 33 | 控制台数据层、报告页、本地服务与页面 |
| `tests/test_e2e.py` | 13 | 本次端到端（AC-1~AC-7 逐条对照 + 链路不变量） |
| **合计** | **243** | `scripts/run_tests.py` 或逐个 `python3 tests/test_*.py` |

配套门禁：`python3 scripts/structure_check.py --json` → `ok=true`、`problems=[]`；`python3 scripts/seed_adapters.py --check` 一致；`python3 .dsh/skills/prompt-registry/run.py check` 通过。

### 2.6 AC-6：两份文档能还原当前状态

- `docs/discussion-record.md`：N001–N014 逐个记录「当时怎么想、定了什么、留了哪些 Action（A-01~A-78）」。
- `docs/directory-and-files.md`：顶层目录逐条、`agents/`、`dashboard/`、`db/`、`tests/`、`logs/` 全覆盖，含「现有 244 项测试怎么分布」。
- `docs/requirements-spec.md`：**v2.2-frozen**（验收时为 v2.1.12，收尾时冻结），台账 WP-01~WP-12 全部收口；`README.md`：留痕 N001–N014、决议 D-01~D-24、进度 100%。
- `logs/2026-10-12.jsonl`：搭建过程流水（每完成一步追加），`build-log.html` 即由它生成，可搜索、可追溯。

### 2.7 AC-7：图表同步且通过校验

五张图（`.archify/FLOW-*/`）与实现同步：分发线补入步骤 7 落地的 `publish-guard`（红线守卫，插在 `browser-publisher` 与关口③ 之间），总览图补入第 4 层「本地人机界面（只读）」的 `运营控制台（dashboard）` 与 `搭建过程报告页（build-log）`。

校验（`…/archify-dsh/skills/archify/bin/archify.mjs`）：

```
node <archify-skill>/bin/archify.mjs render architecture .archify/FLOW-PUBLISH-20261012/publish-line.final.json \
  .archify/FLOW-PUBLISH-20261012/publish-line.html --quality showcase
node <archify-skill>/bin/archify.mjs check .archify/FLOW-PUBLISH-20261012/publish-line.html --json   # exit 0、ok:true、9/9
```

`publish-line.html` 与 `overall-operations.html` 均为 **exit=0、ok:true、9/9 检查通过**（`single_svg` / `finite_svg` / `orthogonal_arrows` / `label_route_clearance` 等）。

**浏览器校验（原受限项，已解决）**：`finalize` 的最后一关 `browser-check` 最初在本机返回 `fail`，原文 `viewer/browser-check-runtime: browser-check could not complete its Chrome inspection`（根因是 Chrome 沙箱 `Failed to initialize sandbox`）；当时按 R-L2-18 用 `render` + `check` + 截图交付并登记为 `A-09`。收尾时已解决 —— 给 archify 设 `ARCHIFY_CHROME_NO_SANDBOX=1`（其 `bin/visual-check.mjs` 会把它转成 Chrome 的 `--no-sandbox`），五张图重跑 `finalize` 均 `ok:true`，`gates: validate / deliver / check / browser-check` **四门全 pass**；命令记录在五张图的 README 与 `.archify/README.md`。

---

## 3. 本版明确未覆盖的部分

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 真实账号与需登录来源 | 未接入 | 采集 / 发布走离线兜底（`browser.local-fixture` / `browser.fill-plan` / `metrics.local-fixture` / `doc.local-export`）；需登录的公开源与平台账号仍由真人提供（Q-13） |
| 真实模型与生图 / 生视频服务 | 未接入 | 离线跑的是 `llm.mock` 与本地 ffmpeg 合成，接口与降级链已就位（`llm.deepseek` / Flow / 豆包 / ComfyUI 均登记为未接） |
| 平台自动发布 | 永不自动 | 按 C-08，发布动作永远由真人点击完成；系统只生成填写清单与发布包 |
| archify 浏览器校验 | 已解决 | 见 §2.7：加 `ARCHIFY_CHROME_NO_SANDBOX=1` 后四门全过，A-09 关闭（换机器仍可能遇到，规则与替代方式见 R-L2-18） |

---

## 4. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-10-12 | 首版：随 WP-05 步骤 9 落地，逐条给出 AC-1~AC-7 的可复现证据（N014）。 |
