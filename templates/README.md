# 模板库（`templates/`）

- 用途：**文件形态的配置与模板** —— 平台预设模板、提示词模板、适配器登记表。这里放的都是「改内容不改代码」的东西。
- 不放什么：不放密钥（C-05）、不放账号信息、不放产物文件（产物进 `workspace/`）。

## 计划内容

| 子目录 | 放什么 | 谁读它 |
| ------ | ------ | ------ |
| `adapters/registry.json` | **适配器登记表**：7 类服务共 19 条声明（能力 / 是否要密钥 / 是否计费 / 失败特征 / 降级顺序） | `llm-adapter`（运行时按它选服务）、`scripts/seed_adapters.py`（同步进 `adapter_registry` 表） |
| `prompts/*.md` | **提示词模板**：frontmatter 声明 `prompt_key`/`version`/`variables`，正文用 `{{变量}}` 占位 | `prompt-registry`（渲染与登记版本）、各生成类 skill |
| `platforms/` | 平台预设模板（字数区间 / 标题写法 / 标签数量 / 封面比例）；数据已进 `db/seed/0001_platform_templates.sql` | 发布前准备、控制台（WP-05 步骤 7 后细化为文件） |

## 两条规则

1. **换服务只改 `adapters/registry.json`，然后跑 `python3 scripts/seed_adapters.py`**；业务代码里不允许出现 Flow / 豆包 / ComfyUI 这类服务名（R-L2-14）。
2. **改提示词正文必须同时改 `version`**，否则产物表记录的 `prompt_version` 会指向不同内容（R-7-03）；改完跑 `python3 .dsh/skills/prompt-registry/run.py check`。

## 维护提示

- 增删模板文件后同步更新 `docs/directory-and-files.md`（R-L2-09）。
- `registry.json` 里除数据库列以外，还有两个**仅运行时用**的字段：`implemented`（本版是否已接入代码）与 `cost_per_call`/`settings`（计费预估与协议参数），同步脚本会有意跳过它们。
