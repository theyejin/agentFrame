---
name: llm-adapter
description: "文本模型调用的统一入口：渲染提示词、按降级链选适配器、落实零付费门禁、记录实际用了哪个适配器与模型版本。Use when 需要用文本模型生成文案/分镜/复盘结论，想查看或演练某个业务环节的降级链（图像、切图、视频、浏览器、文档、指标），或需要以统一接口调用任何外部服务而不在业务代码里写死服务名时。"
---

# llm-adapter（文本模型与外部服务的统一入口）

**是什么**：所有「要调用外部服务」的动作都必须经过这里。业务代码只说「我要一段文本」或「我要文生图」，由本 skill 读 `templates/adapters/registry.json` 决定用哪家服务、按什么顺序降级（R-L2-14/15/16/17）。

**什么时候用**：
- 生成文案、分镜描述、复盘结论等需要文本模型的工作；
- 想知道某类服务（llm / image / split / video / browser / doc / metrics）当前的降级链与失败特征；
- 演练「主服务不可用时会不会自动换到下一个、最终转人工」；
- 需要显式批准一次计费调用（默认零付费，C-09）。

**入口**：

```bash
python3 .dsh/skills/llm-adapter/run.py chain  --kind llm            # 看降级链
python3 .dsh/skills/llm-adapter/run.py adapters                     # 看全部适配器
python3 .dsh/skills/llm-adapter/run.py generate --prompt-key copy-generate \
        --var topic_title=... --var topic_brief=... --out workspace/topic-1/copy/plan.txt
python3 .dsh/skills/llm-adapter/run.py call --kind image --payload-json '{"prompt":"...","count":3}'
```

默认走离线假模型（`llm.mock`），不联网、不花钱；`--allow-paid` 才会尝试计费服务，且受 `LLM_COST_LIMIT` 限制。

**产出**：生成文本（或 `--out` 落盘文件）、本次调用的完整尝试记录（含实际使用的 `adapter_id` 与 `model_version`，供 `step_runs.adapter_used` 与 `artifacts` 登记）。

**详细说明与九段契约**见同目录 `README.md`；本文件只回答「是什么、什么时候用、入口在哪」。
