---
name: prompt-registry
description: "提示词模板的登记、渲染、自检与版本对照（文件在 templates/prompts/*.md）。Use when 需要列出或渲染提示词模板、检查模板变量是否对得上、把模板版本登记进数据库，或任何生成类 skill 在调用模型前要按版本取模板时。"
---

# prompt-registry（提示词注册表）

**是什么**：提示词的唯一入口。提示词一律以文件形式放在 `templates/prompts/`，本 skill 负责列出、渲染、自检和把版本登记进 `prompt_versions` 表 —— 目的是「文案变了能追到是哪版提示词生成的」（R-7-03）。

**什么时候用**：
- 生成文案 / 分镜 / 复盘报告之前，需要拿到可渲染的提示词；
- 改了提示词正文之后，要确认变量声明与正文占位符仍一致（`check`）；
- 想知道某个 prompt_key 当前有哪些版本、文件在哪（`list` / `get`）；
- 需要把当前模板版本登记到数据库，供产物表引用（`sync`）。

**入口**：

```bash
python3 .dsh/skills/prompt-registry/run.py list
python3 .dsh/skills/prompt-registry/run.py get    --key copy-generate
python3 .dsh/skills/prompt-registry/run.py render --key copy-generate --var topic_title=... --out /tmp/p.txt
python3 .dsh/skills/prompt-registry/run.py check
python3 .dsh/skills/prompt-registry/run.py sync
```

**产出**：渲染好的提示词文本（可选落盘）、`prompt_versions` 表的登记行、自检问题清单。

**详细说明与九段契约**见同目录 `README.md`；本文件只回答「是什么、什么时候用、入口在哪」。
