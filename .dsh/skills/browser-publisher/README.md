# 浏览器发布员（browser-publisher）

<!--
文件用途：浏览器发布员 的人读操作说明（岗位职责、输入输出、判据与失败处理）。
对应需求：FLOW-8 发布 / C-08（Agent 不得自动发布）/ C-10（发布授权必须真人给）/ R-7-05（填写而非提交）/ R-8-03（谁做的要留痕）。
对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
维护提示：改行为先改本文件与 SKILL.md，再改 run.py；提示词变更要同时升 templates/prompts 的 version。
-->

| 项目 | 内容 |
| --- | --- |
| skill_id | `browser-publisher` |
| 中文岗位名 | 浏览器发布员 |
| 归属 | 分发数据线 / 发布 |
| 版本 | v0.1.0 |
| 入口文件 | `.dsh/skills/browser-publisher/run.py` |
| 执行者 | 人（命令行）或 Agent 编排者派单 |

## 1. 职责
把最终成片、发布准备（标题/标签/封面文案）、封面与平台模板组装成发布包与填写清单，写 `publish_records`（filled），挂关口③ 待办并把任务置 waiting_human。**任何情况下都不提交发布**：真人发布后用 `mark-published` 回填链接。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| --- | --- | --- | --- | --- |
| `prepare --task-id` | 整数 | 是 | 要准备发布的任务号 | 编排者派单 |
| `prepare --platform` | 文本 | 否 | 平台；缺省用任务的 target_platform | 命令行/任务表 |
| `prepare --account-label` | 文本 | 否 | 账号标识（只记标签，绝不存密码） | 命令行/人工 |
| `prepare --live` | 开关 | 否 | 按「要真正发布」的标准自检（会检查关口③ 授权） | 命令行 |
| `mark-published --task-id --actor` | 整数/文本 | 是 | 人工发布后回填：谁发的 | 真人 |
| `mark-published --url` | 文本 | 否 | 发布后的作品链接 | 真人 |
| `status --task-id` | 整数 | 是 | 查看发布准备到哪一步 | 命令行 |

## 3. 输入校验（进场前，不通过直接退回）
1. 任务存在，且能找到 final 成片（role=final）与封面（role=cover）产物——两者必须成对。
2. 平台必须有模板（`platform_templates`），否则退回并列出已配置平台。
3. 发布准备必须存在（role=publish-prep，由 title-cover-prep 产出）。
4. `submit` 恒为 false；任何把它置 true 的路径都要在自检里被拦下（C-08）。

## 4. 输出
- `workspace/topic-<选题号>/publish/fill-plan-<时间戳>.json`（填写清单：平台、标题候选、标签、封面文案、成片与封面路径、`submit=false`）。
- `artifacts` 一条：kind=publish_package（meta.role=package）。
- `publish_records` 一条 status=filled（filled_at 非空）。
- `hitl_events` 关口③ 待办一条；`tasks.status` → waiting_human。

## 5. 完成判据（自检通过才交给下游）
- 填写清单里 `submit=false`、`auto_publish=false`，且没有任何提交动作被执行。
- 清单里标题/标签/封面/成片路径齐全，`publish_guard.check_package` 无阻断项。
- 发布记录能从任务追到链接（人工发布后 `publish_url` 非空）。

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| --- | --- | --- | --- |
| 缺成片或封面产物 | 退出 2，提示先跑 video-exporter export | — | — |
| 平台没有模板 | 退出 2 并列出已配置平台 | — | — |
| 自检发现 submit/auto_publish 被打开 | 退出 1，登记失败并拒绝写发布记录 | 1 次 | 转人工排查调用方 |

## 7. 依赖
`_shared/publish_guard.py`（组装/自检/发布记录）、`_shared/adapter_runtime.py`（browser 链，本版不真正驱动浏览器）、`_shared/hitl.py`、`_shared/recording.py`。

## 8. 不在本版范围
不实现真正的浏览器自动填写与提交（`browser.playwright-cdp` 仍未接，Q-13 要求登录前先人工授权）；不存任何账号密码。

## 9. 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v0.1.0 | 2026-10-12 | 首版：组装发布包 + 填写清单（停在发布前）（WP-05 步骤 7） |
