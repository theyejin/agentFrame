# 决策摘要索引（Decision Log）

- 用途：把各讨论节点里**已经定下来的事**浓缩成一行一条，方便快速查「现在以什么为准」。
- 不放什么：不放讨论过程（过程在 `discussion-record.md`）、不放未决问题。
- 权威性：本文件只是索引；冲突时以 `requirements-spec.md` 与对应讨论节点为准。

| 编号 | 决议 | 来源节点 | 层级 |
| ---- | ---- | -------- | ---- |
| D-01 | 需求规格 v2.1-frozen 为实施基线；S1～S14 全部采纳 | N002 | 红线 |
| D-02 | Q-1～Q-19 全部落定（见规格 §11）；推翻须新开讨论节点 | N002 | 结构级 |
| D-03 | 编排者有且仅有一个；环节 Agent 四个（文案/视觉/视频/分发数据） | N002 | 结构级 |
| D-04 | 所有图表一律用 archify，`architecture` 类型（workflow 装不下中文步骤名） | N003 | 结构级 |
| D-05 | Skill 岗位 = 18 执行岗 + 7 支撑件（共 25 个目录） | N004 | 可低成本变更 |
| D-06 | 目录结构按 `docs/directory-structure-plan.md` 建立，保留 `.dsh/skills/` 作顶层 | N005 | 结构级 |
| D-07 | 每个 skill 目录含 `SKILL.md`（DSH 入口）+ `README.md`（人读）+ `run.py`；`.dsh/skills/` 是 DSH 技能发现根目录（已实测） | N005 | 结构级 |
| D-08 | 按 9 步落地，每步模拟测试通过再下一步 | N005 | 可低成本变更 |
| D-09 | 数据库里只存「当前状态」，历史靠带时间戳的产物文件 + `step_runs` 留痕（重生成用 `ON CONFLICT(task_id, plan_no) DO UPDATE` 覆盖同套号） | N008 | 结构级 |
| D-10 | 跨 skill 的复用逻辑一律下沉 `.dsh/skills/_shared/`；skill 之间不互相调用，skill 只做自己的动作 | N008 | 结构级 |
| D-11 | 视觉线新增两个调整态关口（`gate_visual_style` 风格确认 / `gate_visual_fix` 单张返工），关口枚举共五个；SQLite 不能改 CHECK，用迁移 `0002_add_visual_gates.sql` 重建 `hitl_events` 表 | N009 | 结构级 |
| D-12 | 产物定位按 `artifacts.meta.role`（reference / grid / shot / shots-manifest），不按路径关键字 —— 产物目录会被 `--out` 改掉；离线图像能力由 `image.placeholder`（画图）与 `split.grid-slicer`（切图）两个本地运行时提供，不联网不花钱 | N009 | 可低成本变更 |
| D-13 | 视频线用本地 ffmpeg 兜底（`video.ffmpeg` 标 `implemented=true`，`settings.runtime=ffmpeg_render`）：Remotion 未接时降级链自动落到它，成片与封面帧都由它产出、不联网不花钱；ffmpeg 命令只出现在 `_shared/video.py` 一个文件里 | N010 | 可低成本变更 |
| D-14 | 统一 CLI 约定：`--json` / `--db` 写在子命令前后都行 —— 子命令里加 `--json` 必须带 `default=argparse.SUPPRESS`，否则子命令的默认值会覆盖父级已解析的值（踩过一次）；所有 16 个 skill 统一补齐 | N010 | 可低成本变更 |

| D-15 | 话题级留痕自建两张表：热点批次与条目（`hotspot_batches` / `hotspot_items`）—— `artifacts.task_id` 与 `step_runs.task_id` 都是 NOT NULL，热点采集发生在选题之前、没有 task_id 可挂，所以不能硬塞进那两张表；批次表本身即「哪一批、什么关键词、落在哪个文件」的索引 | N011 | 可低成本变更 |
| D-16 | 发布线「只填写、不提交」：新增三个离线适配器 `browser.local-fixture`（读夹具采集）、`browser.fill-plan`（只产填写清单，恒 `submitted=false`）、`metrics.local-fixture`（读指标夹具），各插在人工终点之前；`publish_records.status` 只允许 Agent 写 `filled` / `pending` / `failed`，写 `published` 直接报错，真实发布由人在关口③ 完成后经 `browser-publisher mark-published` 回填（C-08 / C-10） | N011 | 可低成本变更 |
| D-17 | Agent 定义的唯一事实源是 `agents/orchestrator/config.yml`：五个 Agent 的档案、可派单 Skill、交接契约三段（`input_check` / `outputs` / `done`）、五个关口、环节路由都写在这一处；`agents/*/README.md` 只给人读，运行时校验由 `task-decomposer agents`（内部 `check_contract`）执行 —— 声明与校验分离，避免两处口径漂移（R-L1-18 / R-L1-19） | N012 | 结构级 |
| D-18 | 完成判据必须用最小词汇表写（`count` / `ids_continuous` / `unique` / `in_range` / `all_resolution_equal` / `file_exists` / `non_empty` / `enum_in` / `no_auto_publish`），不许自由发挥文字 —— 这样「什么算完成」可以被机器读，而不是只靠人理解 | N012 | 结构级 |
| D-19 | 编排者的两个工具各只有一个实现：`task-decomposer`（建话题与任务、产派单书、按任务当前环节路由）与 `summary-writer`（只读汇总五项：当前环节 / 已完成步骤 / 待办关口 / 关键产物 / 下一步找谁）。派单书按 `kind=manifest` + `meta.role=dispatch` + `prompt_version='none'` 留痕，并**不算内容产物**（汇总回报里按 kind 排除 `manifest`）；汇总缺口照实写（没指标就写「本期还没有指标」，挂在关口上写「有 N 个关口待人工决议」但绝不代答） | N012 | 可低成本变更 |

| D-20 | 控制台的读写边界写死在两处：页面**只读**数据层 `_shared/console.py`（口径只写一遍：环节 / 状态 / 关口中文标签、互动率 = 互动量 ÷ 播放量），**写操作一律经本地服务调 skill 白名单** `RUN_WHITELIST`，页面传来的 `--db` / `--allow-paid` 一律被拒 —— 页面既不能换库，也不能绕开零付费门禁（C-09）；服务只监听 127.0.0.1 | N013 | 可低成本变更 |
| D-21 | build-log 报告页放在**仓库根目录**（R-L2-06），由 `scripts/build_log_report.py` 从 `logs/*.jsonl` 生成 `build-log.html` + 可追溯的 `build-log.data.json`，并把数据内联进 HTML（`file://` 双击也能看）；它与控制台是**两个独立页面**（Q-6），控制台首页只放入口链接 —— 报告页与库解耦，日志坏行不致命 | N013 | 结构级 |

| D-22 | 端到端验收以「一条真实选题离线全链跑通」为准：`tests/test_e2e.py` 在临时库里真跑一遍（24 步 / 18 个 skill），把 AC-1~AC-7 逐条变成可执行断言，结论与证据写进 `docs/acceptance-report.md` —— 验收不靠口头结论，靠可复跑的命令与实测数值（AC-1~AC-7、R-L2-02） | N014 | 结构级 |
| D-23 | 受限项如实登记、不伪造通过：本机 Chrome 沙箱导致 archify 的 `browser-check` 门跑不完，就在验收报告与决议里写明「`validate` / `deliver` / `check` 三门 pass、`browser-check` fail（A-09）」——图的交付按 R-L2-18 用 `render` + `check` + 截图，绝不把未跑的检查写成通过 | N014 | 可低成本变更 |

## 维护提示

- 每次讨论节点收尾时，把新定下来的事项追加到本表（R-D-01、R-D-03）。
