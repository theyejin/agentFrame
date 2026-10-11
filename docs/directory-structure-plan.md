# 目录与文件结构提案（Directory Structure Plan）

> 对应需求：R-L1-13（基础环境：路径下的文件目录与目录下的文件）、R-L1-14（目录与文件名都要有注释说明）、R-L2-09（《目录及文件说明》随增删改同步更新）。
> 用途：**这是给用户的确认稿，不是已建成的目录**。确认后才进入 WP-05 基础环境搭建。
> 讨论来源：N004（2026-10-12）。岗位名册见 `docs/skill-roster.md`，README 契约见 `docs/skill-readme-contract.md`。

---

## 1. 现状（磁盘为准）

| 路径 | 现有内容 |
| ---- | -------- |
| `docs/` | `requirements-spec.md`（v2.1.1 冻结）、`discussion-record.md`（N001–N003）、`skill-roster.md`、`skill-readme-contract.md`、`directory-structure-plan.md`（本文件） |
| `.archify/` | 5 张图的目录：`FLOW-OVERALL-20261012/`、`FLOW-COPY-20261012/`、`FLOW-VISUAL-20261012/`、`FLOW-VIDEO-20261012/`、`FLOW-PUBLISH-20261012/`（各有 `*.final.json` 图源 + `*.html` 交付 + `README.md`） |
| 根 | `README.md`、`.gitignore` |
| **尚无** | `agents/`、`.dsh/skills/`、`db/`、`dashboard/`、`build-log/`、`logs/`、`workflows/`、`workspace/`、`scripts/`、`templates/`、`tests/` |

---

## 2. 拟定目录树（每行都是「路径 + 用途」）

```
agentFrame/                             # 项目根：一支自媒体创作运营团队的全部资产
├── README.md                           # 仓库入口：状态、阅读顺序、红线（已有）
├── .gitignore                          # 不入库清单：密钥/数据库/大文件（已有）
├── .env.example                        # 环境变量样例（只放键名，不放值；C-05）
│
├── docs/                               # 文档区：需求、讨论留痕、设计与说明
│   ├── requirements-spec.md            # 【唯一需求来源】冻结的规格 v2.1.1（已有）
│   ├── discussion-record.md            # 【过程留痕】9 字段讨论节点 N001…（已有）
│   ├── skill-roster.md                 # Skill 岗位名册：18 岗位 + 7 支撑件（已有）
│   ├── skill-readme-contract.md        # 每个 skill 的 README 必填模板（已有）
│   ├── directory-structure-plan.md     # 本文件：目录提案（确认稿）
│   ├── directory-and-files.md          # WP-09 产出：《目录及文件说明》正式版，随增删改同步
│   └── decision-log.md                 # 决议摘要索引（按需，从讨论记录摘出「已定事项」一行一条）
│
├── .archify/                           # 全部图表（archify 产物，一张图一个目录）
│   ├── FLOW-OVERALL-20261012/          # 整体运营流程图（已有）
│   ├── FLOW-COPY-20261012/             # 文案线分环节流程图（已有）
│   ├── FLOW-VISUAL-20261012/           # 视觉线分环节流程图（已有）
│   ├── FLOW-VIDEO-20261012/            # 视频线分环节流程图（已有）
│   └── FLOW-PUBLISH-20261012/          # 分发数据线分环节流程图（已有）
│                                       # 每个目录内固定四个文件：
│                                       #   <name>.final.json（图源，改图只改它）
│                                       #   <name>.html（交付产物）
│                                       #   README.md（这张图画什么、怎么重新生成）
│                                       #   （可选）<name>.png（截图留档）
│
├── agents/                             # Agent 定义：谁负责编排、谁负责哪条线
│   ├── orchestrator/                   # 编排者（唯一）：拆解派单、汇总回报、复盘
│   │   ├── README.md                   # 它管什么、不管什么、派单契约、边界（R-L1-06）
│   │   └── config.yml                  # 编排者配置：可派单的 skill 白名单、并发上限
│   ├── copy-agent/README.md            # 文案线 Agent：派单范围与交接契约（R-L1-18）
│   ├── visual-agent/README.md          # 视觉线 Agent：同上
│   ├── video-agent/README.md           # 视频线 Agent：同上
│   └── publish-agent/README.md         # 分发数据线 Agent：同上（含发布红线说明）
│
├── .dsh/skills/                        # Skill 模块（25 个目录：18 岗位 + 7 支撑件）
│   ├── copy-writer/                    # 文案生成：3 套不同侧重点
│   ├── storyboard-builder/             # 分镜拆解：24 条（6×4）
│   ├── reference-image-builder/        # 参考图生成
│   ├── grid-image-builder/             # 6×4 整图生成
│   ├── image-splitter/                 # 整图切分 24 张
│   ├── asset-packager/                 # 素材打包 + manifest.json
│   ├── image-to-video/                 # 图生视频
│   ├── auto-editor/                    # 自动剪辑（参数化）
│   ├── video-exporter/                 # 成片导出 + 封面帧
│   ├── title-cover-prep/               # 标题/标签/封面（平台模板）
│   ├── browser-publisher/              # 浏览器填写，停在发布前
│   ├── hotspot-collector/              # 热点采集
│   ├── table-builder/                  # 汇总成表
│   ├── feishu-sync/                    # 飞书同步
│   ├── metrics-collector/              # 三项指标采集
│   ├── review-reporter/                # 复盘报告与优化建议
│   ├── llm-adapter/                    # 统一模型接口 + 适配器 + 降级链
│   ├── prompt-registry/                # 提示词入仓与版本
│   ├── artifact-recorder/              # 产物/流水/留痕登记（支撑件）
│   ├── hitl-gate/                      # 三态人工关口（支撑件）
│   ├── storyboard-validator/           # 分镜校验（质量门）
│   ├── image-consistency-checker/      # 图片一致性校验（质量门）
│   ├── publish-guard/                  # 发布红线守卫（质量门）
│   ├── task-decomposer/                # 任务拆解（编排者工具）
│   └── summary-writer/                 # 汇总回报（编排者工具）
│                                       # 每个目录内固定两个文件：
│                                       #   README.md（按 docs/skill-readme-contract.md 填写）
│                                       #   run.py（或 index.ts，入口固定名）
│
├── db/                                 # 数据库：只入库结构与迁移脚本，不入库 .db 文件
│   ├── README.md                       # 表清单与关系图说明（指向 architecture 图）
│   ├── schema.sql                      # 建表 DDL（唯一结构来源）
│   ├── migrations/                     # 迁移脚本，按序命名 0001_xxx.sql…
│   └── seed/                           # 初始化数据：平台预设模板、指标字典
│
├── dashboard/                          # 运营控制台（L3 多人任务管理页面）
│   ├── README.md                       # 页面清单、每页给谁用、怎么启动
│   ├── index.html                      # 控制台首页：待办与任务流转
│   ├── pages/                          # 各功能页（文案生成/分镜/图片/视频/发布/数据）
│   ├── build-log.html                  # L2 要求的执行轨迹报告页（左时间轴 + 右轨迹）
│   └── assets/                         # 样式与脚本（页面代码保留注释，R-L2-08）
│
├── workflows/                          # 流程编排定义（可执行的流程描述）
│   ├── README.md                       # 流程清单与触发方式
│   └── *.yml                           # 四条线各一份 + 端到端一份
│
├── templates/                          # 平台预设模板（Q-18）
│   ├── README.md                       # 模板字段说明
│   └── platforms/                      # 每个平台一份：字数区间/标题写法/标签数/封面比例
│
├── scripts/                            # 辅助脚本（跑测试、生成报告、体检）
│   ├── README.md                       # 每个脚本干什么、怎么跑
│   ├── build_log_report.py             # 扫描 logs/ 生成 build-log.html（R-L2-06）
│   └── structure_check.py              # 检查目录说明与磁盘是否一致（R-L2-09）
│
├── tests/                              # 模拟测试：不调用真实外部服务
│   ├── README.md                       # 怎么跑、覆盖了哪几步
│   ├── fixtures/                       # 假数据：假 brief、假图片、假指标
│   └── test_*.py                       # 每步至少一个「跑通即过」的用例
│
├── logs/                               # 运行记录（按日期分文件，支撑 build-log 页面）
│   └── YYYY-MM-DD.jsonl                # 每行一条：时间/环节/skill/结果/耗时
│
└── workspace/                          # 运行期产物（不入库，超大文件走这里）
    ├── topic-<id>/                     # 一个话题一个工作目录
    │   ├── copy/                       # 3 套候选文案 + 选定记录
    │   ├── storyboard/                 # 24 条分镜 JSON
    │   ├── images/                     # 参考图 / 整图 / 24 张独立图
    │   ├── video/                      # 工程文件夹 / 草稿 / 成片
    │   └── publish/                    # 发布包 / 待发布截图
    └── README.md                       # 说明：这里的东西可随时删、可重建
```

---

## 3. 命名与注释规则（R-L1-14）

| 对象 | 规则 | 例子 |
| ---- | ---- | ---- |
| 目录 | 小写英文，复数表示集合；一个目录一件事 | `agents/`、`templates/`、`workspace/` |
| 中文名 | 目录**必须有**中文名注释，写在它自己的 `README.md` 第一行或本文件第 2 节 | `dashboard/` → 运营控制台 |
| Skill 目录 | `kebab-case`，与 `docs/skill-roster.md` 的 `skill_id` 完全一致 | `image-to-video` |
| 代码文件 | 小写 + 下划线；入口固定 `run.py` / `index.ts` | `build_log_report.py` |
| 图目录 | `FLOW-<线名>-<YYYYMMDD>` | `FLOW-COPY-20261012` |
| 迁移脚本 | `NNNN_描述.sql`，序号连续 | `0001_init.sql` |
| 产物目录 | `topic-<id>/<环节>/` | `topic-20261012-01/images/` |
| 日期文件 | `YYYY-MM-DD.jsonl`（日志）/ `YYYY-MM-DD`（报告） | `logs/2026-10-12.jsonl` |

---

## 4. 哪些不入库（已写进 `.gitignore`）

`.env*`（除 `.env.example`）、`*.db` / `*.sqlite*`、`workspace/`、`output/`、`outputs/`、
`*.mp4` / `*.mov` / `*.wav` / `*.png` / `*.jpg` / `*.jpeg` / `*.webp`、`__pycache__/`、`node_modules/`、`.DS_Store`。

保留入库的「产物示例」如需入库，放 `tests/fixtures/` 且体积受控。

---

## 5. 分步落地顺序（每步都要模拟测试通过再下一步，R-L1-13 / R-L2-02）

| 步 | 内容 | 测试通过标准 |
| -- | ---- | ------------ |
| 1 | 建顶层目录 + 每个目录 `README.md` + `.env.example` | 目录说明与磁盘一致（`scripts/structure_check.py` 通过） |
| 2 | `db/schema.sql` + 迁移 + `seed/` 平台模板 | 建库成功、表可查、模板可读 |
| 3 | `llm-adapter` + `prompt-registry`（假模型也可跑） | 用假适配器跑通一次调用并登记产物 |
| 4 | 文案线两个 skill + `hitl-gate` 关口① | 出一份 3 套文案 + 选定记录入库 |
| 5 | 视觉线三个 skill | 24 张独立图产出且校验通过 |
| 6 | 视频线五个 skill | 出一份可播放成片（可用极短假素材） |
| 7 | 分发数据线六个 skill | 出待发布态 + 指标入库 + 复盘报告 |
| 8 | `dashboard/` 控制台与 build-log 页面 | 页面能打开、能搜索、能看轨迹 |
| 9 | 端到端模拟（一条 topic 全流程） | AC-1～AC-7 全过 |

---

## 6. 需要你确认的三件事

1. 目录树是否照此建立？（可增删目录，确认后我按第 5 节的 9 步逐步搭建并在 `docs/discussion-record.md` 记进度）
2. 顶层目录是否要更名？（如 `dashboard/` 改叫 `console/`、`.dsh/skills/` 改叫 `skills/`——后者会影响 DSH 的 skill 自动发现，建议保持 `.dsh/skills/`）
3. 是否同意「先建目录骨架 + 每个目录的 README，再填内容」这个顺序？
