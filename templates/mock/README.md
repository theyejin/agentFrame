# 离线样例库（`templates/mock/`）

- 用途：给**离线假模型**（适配器 `llm.mock`）提供固定样例文本，让模拟测试与流程演练拿到和真实模型同构的输出（3 套文案、24 条分镜），不联网、不花钱。
- 不放什么：不放真实账号信息、不放真实素材与产物、不放密钥。

## 命名与用法

文件名固定为 `<prompt_key>.<prompt_version>.txt`，与 `templates/prompts/` 里的模板版本一一对应：

| 文件 | 对应提示词 | 内容结构 |
| ---- | ---------- | -------- |
| `copy-generate.v2.txt` | `prompts/copy-generate.md` v2 | 3 个「方案N（侧重：hook/emotion/cta \| 说明）」块，每块正文 300–500 字 |
| `storyboard-split.v2.txt` | `prompts/storyboard-split.md` v2 | 24 行「NN \| 画面描述 \| 镜头提示」，编号 01–24 连续 |

调用链：skill 通过 `llm-adapter generate --prompt-key K` 传入 `prompt_key`/`prompt_version` → `_shared/adapter_runtime.py` 的 `_mock_fixture()` 按名字取样例 → 返回给调用方解析。没有对应样例文件时退回「按输入临时造一段假文案」的通用行为。

## 维护提示

- 提示词升版本（如 `v2` → `v3`）后必须补一份同名样例，否则模拟测试会退回通用假文案而解析失败。
- 改样例内容要保证结构约束不变（3 套 / 24 条 / 编号连续 / 字数区间），这些约束由 `tests/test_copy_line.py` 守着。
- 增删文件后同步更新 `docs/directory-and-files.md`。
