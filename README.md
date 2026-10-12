# 自媒体创作运营团队（wemedia-agent）

用 DeepSeek Harness（DSH）在本机搭建一支「自媒体创作运营团队」：**Agent 负责编排与决策，Skill 负责模块化执行**，
把「选题 → 文案 → 分镜图片 → 视频剪辑 → 分发 → 数据分析报告」做成可追溯的本地闭环。

---

## 当前状态

| 项      | 值                                                            |
| ------ | ------------------------------------------------------------ |
| 阶段     | **已交付 v1.0.0**：目录骨架（步骤 1）+ 数据库结构与迁移（步骤 2）+ 外部服务适配器层与提示词注册表（步骤 3）+ 文案线（步骤 4）+ 视觉线（步骤 5）+ 视频线（步骤 6）+ 分发数据线（步骤 7）+ Agent 定义与编排者工具（WP-07）+ 运营控制台与搭建过程报告页（步骤 8）+ 端到端验收（步骤 9）已完成，九步全部收口，四个工作包（WP-01~WP-12）全部完成，打 tag `v1.0.0` |
| 已冻结基线  | [`docs/requirements-spec.md`](docs/requirements-spec.md)（v2.2-frozen） |
| 过程留痕   | [`docs/discussion-record.md`](docs/discussion-record.md)（N001–N014） |
| Skill 名册 | [`docs/skill-roster.md`](docs/skill-roster.md)（18 岗位 + 7 支撑件 = 25 个目录） |
| 目录与文件  | [`docs/directory-and-files.md`](docs/directory-and-files.md)（增删改必须同步） |
| 数据模型   | [`db/README.md`](db/README.md)（16 表 / 2 视图 / 枚举取值总表）；模拟测试 `python3 tests/test_db.py` |
| 外部服务   | [`templates/adapters/registry.json`](templates/adapters/registry.json)（7 类 23 条适配器 + 降级链）；入口 skill `llm-adapter`；测试 `python3 tests/test_adapters.py` |
| 文案线    | 5 个 skill（`copy-writer` / `storyboard-builder` / `artifact-recorder` / `hitl-gate` / `storyboard-validator`）；测试 `python3 tests/test_copy_line.py` |
| 视觉线    | 4 个 skill（`reference-image-builder` / `grid-image-builder` / `image-splitter` / `image-consistency-checker`）+ 离线图像能力（`image.placeholder` / `split.grid-slicer`）；测试 `python3 tests/test_visual_line.py` |
| 视频线    | 5 个 skill（`asset-packager` / `image-to-video` / `auto-editor` / `video-exporter` / `title-cover-prep`）+ 本地视频能力（`video.ffmpeg`，Remotion 未接时自动降级）；测试 `python3 tests/test_video_line.py` |
| 分发数据线  | 6 个 skill（`hotspot-collector` / `table-builder` / `feishu-sync` / `browser-publisher` / `metrics-collector` / `review-reporter`）+ 红线守卫 `publish-guard` + 本地兜底（`browser.local-fixture` / `browser.fill-plan` / `metrics.local-fixture`，只填写不提交）；测试 `python3 tests/test_publish_line.py` |
| Agent/编排者 | 五个 Agent 定义（`agents/`）+ 契约事实源 `agents/orchestrator/config.yml`；编排者工具 `task-decomposer` / `summary-writer`；测试 `python3 tests/test_orchestrator.py` |
| 控制台/报告页 | `dashboard/` 五页（总览 / 任务流转 / 文案生成 / 发布操作 / 数据与复盘）+ 本地服务 `scripts/serve_dashboard.py`（只监听 127.0.0.1，写操作走 skill 白名单）+ 仓库根搭建过程报告页 `build-log.html`（生成器 `scripts/build_log_report.py`）；打开方式见 [`dashboard/README.md`](dashboard/README.md)；测试 `python3 tests/test_dashboard.py` |
| 端到端验收  | 一条真实选题离线全链跑通（24 步 / 18 个 skill / 43 条产物，三个关口真人决议）；验收报告 [`docs/acceptance-report.md`](docs/acceptance-report.md)；一键复跑 `python3 scripts/run_tests.py`（9 套 243 项） |
| 实施进度   | **100%**（WP-01~WP-12 全部收口，详见需求规格 §12 总进度台账）                                     |

> ✅ 目录方案已确认（N005）并按 9 步顺序落地，**顶层目录已建成**；各步只建「本步真正要用的子目录」，不留空壳。
> 每一步的完成门：`python3 scripts/structure_check.py` 退出码 0（目录 / 各目录 README / 目录说明三者一致）**且**该步模拟测试通过，才进入下一步。

---

## 阅读顺序（新成员从这里开始）

1. [`docs/requirements-spec.md`](docs/requirements-spec.md) — **唯一需求来源**。要看懂项目做什么、有哪些红线、哪些决议已定，读这一份。
2. [`docs/discussion-record.md`](docs/discussion-record.md) — 过程留痕。要知道「为什么这么做、做到哪、还剩什么」，读这一份。
3. [`docs/skill-roster.md`](docs/skill-roster.md) — 有哪些 Skill 岗位、各自输入输出与判据。
4. [`docs/skill-readme-contract.md`](docs/skill-readme-contract.md) — 每个 skill 的 README 必须怎么写（含机器可判定的校验表达式）。
5. [`docs/directory-structure-plan.md`](docs/directory-structure-plan.md) — 目录树与分步落地顺序（N005 已确认）。
6. [`docs/directory-and-files.md`](docs/directory-and-files.md) — 《目录及文件说明》：每个目录/文件是干什么的，改东西要同步哪些地方。
7. [`docs/decision-log.md`](docs/decision-log.md) — 决议摘要（D-01～D-23）：现在以什么为准。

前两份合起来可完整还原项目状态（成功判据 AC-6）。

---

## 流程图一览（全部由 archify 生成）

| 图 | 内容 | 源与产物 |
| -- | ---- | -------- |
| 整体运营流程 | 三层职责、四条环节线、外部适配器、三处人工关口 | [`.archify/FLOW-OVERALL-20261012/overall-operations.html`](.archify/FLOW-OVERALL-20261012/overall-operations.html) |
| 文案线 | FLOW-1：3 套文案 → 关口① 选定 → 24 条分镜 | [`.archify/FLOW-COPY-20261012/copy-line.html`](.archify/FLOW-COPY-20261012/copy-line.html) |
| 视觉线 | FLOW-2/3：参考图 → 6×4 整图 → 切 24 张 | [`.archify/FLOW-VISUAL-20261012/visual-line.html`](.archify/FLOW-VISUAL-20261012/visual-line.html) |
| 视频线 | FLOW-4/5：图文打包 → 图生视频 → 关口② 剪辑 → 导出成片与封面 | [`.archify/FLOW-VIDEO-20261012/video-line.html`](.archify/FLOW-VIDEO-20261012/video-line.html) |
| 分发数据线 | FLOW-6/7/8：热点 → 发布准备 → 关口③ 授权 → 指标 → 复盘 | [`.archify/FLOW-PUBLISH-20261012/publish-line.html`](.archify/FLOW-PUBLISH-20261012/publish-line.html) |

每张图目录内都有 `README.md`（画什么、为什么、怎么重新生成与校验）；改图必须重新跑 `archify check` 并保持 `ok:true`（R-L2-13）。

---

## 核心概念：三级职责边界

| 层                  | 只做                                        | 不做                        |
| ------------------ | ----------------------------------------- | ------------------------- |
| 编排者 `orchestrator` | 判定流程走向、决定找哪个 Agent、汇总汇报、维护任务状态            | 不写文件、不调外部 API、不做内容加工     |
| 环节 Agent（4 个）      | 把本环节的多个 Skill 串起来，处理重试与失败分支               | 不跨环节调度、不改别环节数据            |
| Skill              | 单一动作：输入 → 处理 → 输出，可独立测试                   | 不做流程判断、不决定下一步、不调其他 Skill |

判据：**一段逻辑在决定「接下来做什么」，它属于 Agent；只是「把这件事做完」，它属于 Skill。**

---

## 三条不可越过的红线

| 红线   | 内容                                              |
| ---- | ----------------------------------------------- |
| C-01 | **不自动对外发布**：平台发布的最后一步必须由真人点击确认                  |
| C-08 | 只在运营人员本人已登录的浏览器会话中操作；不代持账号密码、不绕过平台风控与验证码        |
| C-09 | **零付费门禁**：默认只用免费额度，付费调用须显式批准并设上限，超限暂停转人工        |

---

## 外部服务与降级链（步骤 3 落地）

业务代码**只认能力类别（`kind`），不认服务名**（R-L2-14）。7 类能力共 23 条适配器声明集中在
[`templates/adapters/registry.json`](templates/adapters/registry.json)，统一入口是 skill
[`llm-adapter`](.dsh/skills/llm-adapter/README.md)：

| kind | 降级链（从左到右尝试） |
| ---- | -------------------- |
| `llm` | 离线假模型 → DeepSeek（需密钥、计费） → **人工撰写兜底** |
| `image` | Flow → 豆包 → ComfyUI（本地） → **人工出图兜底** |
| `split` | 本地网格切分 → **人工裁切兜底** |
| `video` | Remotion → ffmpeg → 外部图生视频 → **人工兜底** |
| `browser` | Playwright + 已登录会话 → **人工填写兜底** |
| `doc` | 飞书开放平台 API → **本地导出兜底** |
| `metrics` | 浏览器采集 → **人工录入兜底** |

三条硬规则：① 每条链的最后一条必须是**不需要密钥、不计费、已接入**的兜底（断网也能收尾，由测试强制）；
② 计费适配器默认不调用，必须显式批准且单次预估 ≤ `LLM_COST_LIMIT`（**C-09 零付费门禁**）；
③ 每次调用都要回答「实际用了哪个适配器 / 哪个模型版本」，否则不算完成（R-L2-17、R-7-03）。

换服务只需改登记表并跑 `python3 scripts/seed_adapters.py`；提示词在
[`templates/prompts/`](templates/prompts/) 里按 `version` 入仓，改正文必须升版本（R-7-03）。

---

## 文案线（步骤 4 落地）

一条选题从「对话框 Prompt + 字数范围 + 类型」到「24 条分镜入库」的完整闭环，四个 skill 加两个共享库支撑：

| 环节 | 谁做 | 动作 | 留下的东西 |
| ---- | ---- | ---- | ---------- |
| 建选题与任务 | `artifact-recorder` | `topic-create` / `task-create` | `topics`、`tasks` 行（含 F-01 Prompt、字数范围、类型、平台） |
| 出 3 套文案 | `copy-writer` | 渲染 `copy-generate v2` → 调 `llm` 降级链 → 自检 | `copy_variants` 三行（侧重 `hook`/`emotion`/`cta`）+ `copy/variants-<时间戳>.json` |
| 关口① 选定 | `hitl-gate`（真人拍板） | `open` → 运营人员三选一 → `resolve --action confirm --plan-no N` | `hitl_events` 一行 + `tasks.selected_plan/selected_at` |
| 拆 24 条分镜 | `storyboard-builder` | 校验「已选定文案」→ 渲染 `storyboard-split v2` → 自检 | `storyboards` 24 行 + `storyboard/storyboard-<时间戳>.json` |
| 分镜体检 | `storyboard-validator` | `check --file … --target-seconds …` | 问题与提示清单（不通过就退回） |

设计要点（详见 `docs/decision-log.md` D-09/D-10）：
① **数据库只存当前状态**，每一代生成的完整正文写进带时间戳的文件并登记成 `artifacts`，重生成用同套号覆盖，历史靠产物追溯；
② **skill 之间不互相调用**，跨 skill 的复用逻辑全部下沉 `.dsh/skills/_shared/`；
③ 自检连续 3 次不通过 → 该步骤记 `failed` 且任务置 `blocked`，由编排者决定重试还是转人工。

---

## 图表约定

所有关系图、流程图、结构图**一律使用 `archify` skill 生成**（可交互独立 HTML），不使用 Mermaid 作为交付图表。
每张图单独一个目录存放（候选 JSON + HTML），带类型与时间戳，便于版本对比（R-L2-11、R-L2-12）。

---

## 备份约定

每完成一个实施步骤：提交 → 打 tag → 推送 GitHub（R-L2-04、Q-8）。
远端：`https://github.com/theyejin/agentFrame.git`

---

## 文档维护要求

任何目录、文件的增 / 删 / 改，必须在**同一次提交**内同步更新：
受影响目录的 `README.md`、代码文件头注释块（`# 文件用途 / # 对应需求 / # 对应流程图 / # 维护提示`）、
[`docs/directory-and-files.md`](docs/directory-and-files.md)、受影响的图、以及 `logs/` 流水。完整清单见需求规格 §15。

收尾动作（每一步都做）：

```bash
python3 scripts/structure_check.py          # 必须退出码 0
python3 tests/test_db.py                    # 数据库相关改动必跑（28 项）
python3 tests/test_adapters.py              # 适配器 / 提示词相关改动必跑（36 项）
python3 tests/test_copy_line.py             # 文案线相关改动必跑（24 项）
python3 tests/test_visual_line.py           # 视觉线相关改动必跑（21 项）
python3 tests/test_video_line.py            # 视频线相关改动必跑（22 项）
python3 tests/test_publish_line.py          # 分发数据线相关改动必跑（33 项）
python3 tests/test_orchestrator.py          # Agent 定义 / 编排者工具相关改动必跑（33 项）
python3 tests/test_dashboard.py             # 控制台 / 报告页相关改动必跑（34 项）
python3 tests/test_e2e.py                   # 端到端验收相关改动必跑（13 项，全程约 4 秒）
python3 scripts/run_tests.py                # 一键跑完全部 9 套 244 项
python3 scripts/build_log_report.py         # 有新的实施步骤记录后重生成 build-log 报告页
python3 scripts/serve_dashboard.py          # 本地打开控制台：http://127.0.0.1:8787/
python3 scripts/seed_adapters.py --check    # 改了 registry.json 必跑（登记表与数据库是否一致）
git add -A && git commit -m "..." && git push origin main --tags
```

---

## 目录地图（一眼版）

```
docs/            文档区（需求 / 留痕 / 设计 / 目录说明 / 决议）
.archify/        图表区（整体图 + 4 张分环节图，一图一目录）
agents/          Agent 定义（编排者 + 四条环节 Agent）
.dsh/skills/     Skill 模块（25 个 skill + _shared 共享库；入口 SKILL.md）
db/              数据库结构与迁移
dashboard/       运营控制台 + build-log 报告页
workflows/       流程编排定义
templates/       适配器登记表 + 提示词模板 + 平台预设模板
scripts/         辅助脚本（结构体检、建库、适配器同步、报告生成）
tests/           模拟测试与假数据
logs/            运行流水（build-log 数据源）
workspace/       运行期产物（不入库）
```

每个目录内都有 `README.md`（含「用途：」行）；完整说明见 [`docs/directory-and-files.md`](docs/directory-and-files.md)。
