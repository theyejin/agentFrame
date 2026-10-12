# 分发数据线 Agent（`publish-agent`）

<!--
文件用途：分发数据线环节 Agent 的定义：管什么、不管什么、派单范围与交接契约（R-L1-18），含发布红线说明。
对应需求：R-L1-05（Agent 定义）、R-L1-06（边界）、R-L1-18（交接契约）、R-L1-19（校验失败退回）、FLOW-11~FLOW-15、C-08（不自动发布）、C-10（关口③）。
对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
维护提示：改职责或派单范围先改 agents/orchestrator/config.yml，再同步本文件；两侧不一致时以 config.yml 为准。
-->

| 项目 | 内容 |
| --- | --- |
| agent_id | `publish-agent` |
| 中文名 | 分发数据线 Agent |
| 所属环节 | 分发数据线（`entry_stage: publish` → `exit_stage: review`） |
| 可派单 Skill | `hotspot-collector`、`table-builder`、`feishu-sync`、`browser-publisher`、`publish-guard`、`metrics-collector`、`review-reporter`、`hitl-gate`、`artifact-recorder` |
| 涉及关口 | 关口③ 发布授权（`gate3_publish_auth`，**必须真人拍板**） |
| 定义位置 | 本文件 + `agents/orchestrator/config.yml` |
| 版本 | v0.1.0 |

## 1. 管什么

两件事：**选题供给**（按关键词采热点 → 分类汇总成表 → 同步到文档存档）与**发布与复盘**（组装发布包并只做填写 → 关口③ 等真人授权与提交 → 采指标 → 出复盘报告与下一轮优化建议）。

| 序 | Skill | 子命令 | 干什么 |
| --- | --- | --- | --- |
| 1 | `hotspot-collector` | `collect` | 按关键词采热点并归类（话题级，不挂任务） |
| 2 | `table-builder` | `build` | 按类汇总成表格（Markdown + CSV） |
| 3 | `feishu-sync` | `sync` | 同步到飞书文档；未接 API 时降级为本地导出（Q-5） |
| 4 | `browser-publisher` | `prepare` / `mark-published` / `status` | 组装发布包 + 生成填写清单（停在发布前）；人工发布后回填链接 |
| 5 | `publish-guard` | `check` | 发布红线自检：C-08 不自动发布、C-10 关口③ 授权、标题标签封面齐备 |
| 6 | `metrics-collector` | `collect` | 采集播放量 / 互动量 / 涨粉数三项并按周期落库 |
| 7 | `review-reporter` | `report` | 出数据复盘与优化建议（只建议，不改提示词） |
| 8 | `hitl-gate` | `open` / `resolve` / `status` | 挂起关口③，记录真人授权 |
| 9 | `artifact-recorder` | `step-run` / `artifact` | 步骤与产物留痕 |

## 2. 不管什么

- 不管文案、图片、视频的制作（前三条线的活）；
- **不自动发布**：任何情况下都不得代替真人点击提交（C-08）；填写清单里 `submitted` 必须为 `false`；
- 不代答关口③：授权与提交都必须由真人完成，Agent 只挂待办、只回填事实；
- 不登录陌生账号、不绕过平台风控；需要登录态由运营人员提供（Q-13）；
- 不改提示词：复盘只给建议，改动由运营人员决定并另行升版。

## 3. 派单契约（R-L1-18）

**起手命令**（任务在 `publish`）：`python3 .dsh/skills/browser-publisher/run.py prepare --task-id <N> --json`
**选题供给**（话题级，不挂任务）：`python3 .dsh/skills/hotspot-collector/run.py collect --keyword "关键词" --json`

### 3.1 输入校验（进场前，不通过退回编排者）

1. `tasks.stage` `enum_in` [publish, metrics, review]；
2. 成片（`role=final`）与封面（`role=cover`）`file_exists` 且 `non_empty`；
3. 平台 `enum_in` `platform_templates.platform`（未知平台直接退回并列出已配置平台）。

### 3.2 产出物清单

| 产物 | kind | role | 说明 |
| --- | --- | --- | --- |
| 发布包 + 填写清单 | `publish_package` | `package` | `package.json` + `fill-plan.json`，`submitted=false` |
| 关口③ 决议 | —（`hitl_events`） | — | `gate=gate3_publish_auth`，`actor` 必须为真人 |
| 发布记录 | —（`publish_records`） | — | `status ∈ filled / pending / published / failed` |
| 指标 | —（`metrics`） | — | `views` / `engagements` / `follower_gain` 三项 |
| 指标快照 | `table` | `metrics` | `metrics-<时间戳>.{json,md}` |
| 复盘报告 | `report` | `review` | `report-<时间戳>.{md,json}` |

### 3.3 完成判据（逐条机器可判定）

- `no_auto_publish`：Agent 写入的记录不得为 `published`（`mark-published` 必须带真人 `--actor` 才允许回填）；
- `count(metrics.metric_key) == 3`（部分口径需显式允许，Q-16）；
- `file_exists(role=review)`；
- `tasks.stage == review`。

## 4. 失败与退回

| 情况 | 动作 |
| --- | --- |
| 发布红线自检不过 | `publish-guard` 阻断（退出码 1），任务置 `blocked`，把问题清单转述给运营人员 |
| 关口③ 未授权 | 只挂待办、不发布；`--live` 校验时直接判不通过 |
| 飞书不可用 | `feishu-sync` 降级为本地导出并在输出里写明（`degraded=true`），不得静默失败 |
| 指标缺失 | 允许按 `--allow-partial` 部分采集并标注；复盘报告须写明缺口，不得编数字 |
| 需要真实账号 / 付费接口 | 就地停下（C-09），向运营人员报告 |

## 5. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | WP-07 首版：分发数据线 Agent 定义与交接契约，含发布红线说明（N012） |
