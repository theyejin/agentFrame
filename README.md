# 自媒体创作运营团队（wemedia-agent）

用 DeepSeek Harness（DSH）在本机搭建一支「自媒体创作运营团队」：**Agent 负责编排与决策，Skill 负责模块化执行**，
把「选题 → 文案 → 分镜图片 → 视频剪辑 → 分发 → 数据分析报告」做成可追溯的本地闭环。

---

## 当前状态

| 项      | 值                                                            |
| ------ | ------------------------------------------------------------ |
| 阶段     | 设计阶段收尾：流程图与 Skill 岗位设计已完成，等待**目录结构提案**确认后开始搭建                     |
| 已冻结基线  | [`docs/requirements-spec.md`](docs/requirements-spec.md)（v2.1.2） |
| 过程留痕   | [`docs/discussion-record.md`](docs/discussion-record.md)（N001–N004） |
| Skill 名册 | [`docs/skill-roster.md`](docs/skill-roster.md)（18 岗位 + 7 支撑件） |
| 实施进度   | 约 55%（详见需求规格 §12 总进度台账）                                     |

> ⚠️ 本轮处于「先讨论、后动手」阶段：**基础环境（业务目录）尚未创建**。
> 目录草案见 [`docs/directory-structure-plan.md`](docs/directory-structure-plan.md)，**经确认后**才按其中的 9 步顺序逐个建立，不提前铺开。

---

## 阅读顺序（新成员从这里开始）

1. [`docs/requirements-spec.md`](docs/requirements-spec.md) — **唯一需求来源**。要看懂项目做什么、有哪些红线、哪些决议已定，读这一份。
2. [`docs/discussion-record.md`](docs/discussion-record.md) — 过程留痕。要知道「为什么这么做、做到哪、还剩什么」，读这一份。
3. [`docs/skill-roster.md`](docs/skill-roster.md) — 有哪些 Skill 岗位、各自输入输出与判据。
4. [`docs/skill-readme-contract.md`](docs/skill-readme-contract.md) — 每个 skill 的 README 必须怎么写（含机器可判定的校验表达式）。
5. [`docs/directory-structure-plan.md`](docs/directory-structure-plan.md) — 目录树提案与分步落地顺序。

前两份合起来可完整还原项目状态（成功判据 AC-6）。

---

## 流程图一览（全部由 archify 生成）

| 图 | 内容 | 源与产物 |
| -- | ---- | -------- |
| 整体运营流程 | 三层职责、四条环节线、外部适配器、三处人工关口 | [`.archify/FLOW-OVERALL-20261012/overall-operations.html`](.archify/FLOW-OVERALL-20261012/overall-operations.html) |
| 文案线 | FLOW-1：3 套文案 → 关口① 选定 → 24 条分镜 | [`.archify/FLOW-COPY-20261012/copy-line.html`](.archify/FLOW-COPY-20261012/copy-line.html) |
| 视觉线 | FLOW-2/3：参考图 → 6×4 整图 → 切 24 张 | [`.archify/FLOW-VISUAL-20261012/visual-line.html`](.archify/FLOW-VISUAL-20261012/visual-line.html) |
| 视频线 | FLOW-4/5：打包 → 图生视频 → 关口② 剪辑 → 导出 | [`.archify/FLOW-VIDEO-20261012/video-line.html`](.archify/FLOW-VIDEO-20261012/video-line.html) |
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
受影响目录的 `README.md`、代码文件头注释块（用途/输入/输出/依赖/对应需求 ID）、
目录及文件说明文档、受影响的图、以及 build-log 记录。完整清单见需求规格 §15。
