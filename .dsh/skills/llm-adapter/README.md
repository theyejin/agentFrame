# 外部服务统一入口（llm-adapter）

<!--
文件用途：所有外部服务调用的唯一出口 —— 按 templates/adapters/registry.json 组降级链，逐个尝试并在失败时自动换下一个，最终兜底转人工。
对应需求：R-L2-14（业务代码不认服务名）、R-L2-15（统一接口）、R-L2-16（能力/密钥/计费/失败特征/降级顺序）、R-L2-17（失败自动降级并记录实际适配器）、C-09（零付费门禁）、R-7-03（记录 model_version）。
对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（外部服务适配层：可替换 / 可降级）
维护提示：新增或调整适配器只改 templates/adapters/registry.json（再跑 scripts/seed_adapters.py 同步数据库）；改命令行参数请同步本文件与 docs/directory-and-files.md。
-->

| 项 | 值 |
| -- | -- |
| skill_id | `llm-adapter` |
| 中文岗位名 | 外部服务统一入口（文本模型 + 六类适配器） |
| 归属 | 基础设施 |
| 版本 | `0.1.0` |
| 入口文件 | `run.py` |
| 执行者 | 由编排者派单调用；各环节 skill 需要外部能力时经它调用 |

## 1. 职责

输入「我要哪类能力（`kind`）+ 业务参数」，输出**调用结果 + 完整的尝试记录**（依次试了哪些适配器、各是什么结果、最后实际用了哪个、模型版本是什么）。

它解决的三个问题：

1. **可替换**：业务代码里永远不出现 Flow / 豆包 / ComfyUI / Remotion 这些名字，只出现 `image`、`video`（R-L2-14）。
2. **可降级**：主服务限流、登录态过期、本地服务没起来时，自动按登记顺序换下一个，最后兜底转人工（R-L2-17）。
3. **不花钱**：计费适配器默认不调用，必须显式 `--allow-paid`，且单次预估超过 `LLM_COST_LIMIT` 就停下（C-09）。默认零付费。

它**不是**具体服务的封装集合，而是「决策 + 记录」的那一层；真正的协议差异（如 OpenAI 兼容接口）集中在共享库 `_shared/adapter_runtime.py` 的运行时函数里。

## 2. 输入

| 字段 | 类型 | 必填 | 说明 | 来源 |
| ---- | ---- | ---- | ---- | ---- |
| `kind` | enum | 是 | `llm` / `image` / `split` / `video` / `browser` / `doc` / `metrics` | 调用方（环节 skill） |
| `payload` | object | 是 | 该 kind 的业务参数，见下 | 调用方 |
| `prompt_key` | string | `generate` 必填 | 取哪份提示词模板 | `prompt-registry` |
| `var` | `k=v` 列表 | `generate` 必填 | 模板变量 | 上游产物 |
| `allow_paid` | bool | 否 | 是否批准计费调用，默认否（C-09） | 运营人员显式批准 |
| `out` | path | 否 | 生成物落盘路径 | 调用方 |

各 kind 的业务参数（统一接口，R-L2-15）：

| kind | 参数 | 说明 |
| ---- | ---- | ---- |
| `llm` | `prompt`, `plan_count`, `focuses`, `system`, `temperature` | 文本生成 |
| `image` | `prompt`, `count`, `size`, `reference_image` | `generate_images(prompt, count, size)` |
| `split` | `grid_path`, `rows`, `cols` | 整图 → 独立图片 |
| `video` | `images`, `audio`, `params` | `image_to_video(images, audio)` |
| `browser` | `publish_package`（标题/正文/标签/封面/账号） | 只填不发（C-08） |
| `doc` | `title`, `table` | 写飞书文档 / 导出本地 |
| `metrics` | `platform`, `period` | 采集三项指标 |

## 3. 输入校验（进场前，不通过直接退回）

- [ ] `enum_in(kind, ["llm","image","split","video","browser","doc","metrics"])`
- [ ] `non_empty(chain(kind))`：该 kind 在 `registry.json` 里至少有一条启用中的适配器
- [ ] `non_empty(payload)`：调用参数不能为空
- [ ] `generate`：`file_exists(templates/prompts/<prompt_key>.md)` 且渲染所需变量齐全
- [ ] 计费适配器：`allow_paid == true` 且 `cost_per_call <= LLM_COST_LIMIT`
- [ ] 需要密钥的适配器：`non_empty(<api_key_env>)`（缺失则跳过该条，不算整体失败）

退回时返回：`{ok: false, missing: [...], reason: "<缺什么>"}`（退出码 2）

## 4. 输出

| 字段 | 类型 | 说明 | 落库位置 |
| ---- | ---- | ---- | -------- |
| `adapter_id` | string | **实际使用**的适配器 | `step_runs.adapter_used`（R-L2-17） |
| `model_version` | string | 实际模型版本 | `artifacts.model_version`（R-7-03） |
| `output.text` | text | 生成文本（`--out` 时落盘） | `artifacts.path`（R-7-01，文件不入库） |
| `output.usage` | object | 计费/用量信息（有则记） | `step_runs` 备注 |
| `attempts[]` | array | 依次尝试过的适配器与状态 | `logs/*.jsonl`（build-log 报告页数据源） |
| `needs_human` | bool | 是否已降级到人工兜底 | `tasks.status = waiting_human` |

## 5. 完成判据（自检通过才交给下游）

- [ ] `non_empty(adapter_id)`：必须明确「这次到底用的哪一个」，不允许含糊
- [ ] `non_empty(model_version)`：版本可追溯，否则产物无法复现（R-7-03）
- [ ] `count(attempt) >= 1`：尝试记录不为空
- [ ] 走人工兜底时 `needs_human == true`（而不是假装成功）
- [ ] `generate` 给了 `--out` 时 `file_exists(<out>)`

自检失败返回：`{ok: false, failed: [...], retry: <次数>}`（全部适配器都没成功时退出码 1）

## 6. 失败处理

| 失败情形 | 处理 | 上限 | 超限后 |
| -------- | ---- | ---- | ------ |
| 缺密钥 | 跳过该适配器，换下一条（`missing_key`） | 走完整条链 | — |
| 调用失败（401/429/超时/服务未启动） | 记录失败特征，换下一条（`failed`） | 每条适配器 1 次；首版不做链内重试 | 转人工并发 `waiting_human` |
| 计费适配器未被批准 | 不调用，记 `skipped_needs_approval`（C-09） | — | — |
| 单次预估超成本上限 | 记 `cost_limit_exceeded` 并停止后续计费尝试 | — | 转人工（C-09：超限暂停） |
| 该 kind 尚未接入 | 记 `not_implemented` 并继续降级 | — | 走完则转人工 |
| 全链失败 | 返回可读原因串（逐条 adapter=status） | — | 退回编排者，标「需人工」 |

## 7. 依赖

- 登记表：`templates/adapters/registry.json`（18 条适配器；改这里就换服务）
- 共享库：`.dsh/skills/_shared/adapter_runtime.py`（降级链与调用）、`env_file.py`（读 `.env` 取密钥）、`prompt_templates.py`（`generate` 取提示词）
- 数据表：`adapter_registry`（由 `python3 scripts/seed_adapters.py` 从登记表同步）
- 下游：所有环节 skill（copy-writer、reference-image-builder、image-to-video、browser-publisher 等）

## 8. 不在本版范围

- 链内重试与退避（首版失败即换下一条；重试策略等真实服务接入后再定）
- 并发与排队调度（首版串行调用）
- 用量统计报表（只在 `attempts` 与 `usage` 里记录原始数据）
- 付费适配器的自动预算池（C-09 只做单次上限）
- 非 OpenAI 协议的模型服务（需要时在 `_shared/adapter_runtime.py` 加一个 runtime 即可）

## 9. 变更记录

| 日期 | 变更 | 来源 |
| ---- | ---- | ---- |
| 2026-10-12 | 首版：`chains` / `adapters` / `generate` / `call` 四个命令；7 类 kind 共 18 条适配器声明；离线 `llm.mock` 与人工兜底已可用 | N007 |
