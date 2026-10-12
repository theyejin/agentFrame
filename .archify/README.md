# 图表区（`.archify/`）

- 用途：存放全部用 **archify** 生成的图（可交互独立 HTML）。
- 不放什么：不放 Mermaid 作为交付图（R-L2-11：一律 archify）；不放中间候选（只留 `.final.json`）。

## 图目录一览

| 目录 | 图 | 讨论节点 |
| ---- | -- | -------- |
| `FLOW-OVERALL-20261012/` | 整体运营流程 | N003 |
| `FLOW-COPY-20261012/` | 文案线分环节 | N004 |
| `FLOW-VISUAL-20261012/` | 视觉线分环节 | N004 |
| `FLOW-VIDEO-20261012/` | 视频线分环节 | N004 |
| `FLOW-PUBLISH-20261012/` | 分发数据线分环节 | N004 |

## 命名与内容约定

- 目录名：`FLOW-<线名>-<YYYYMMDD>`；一张图一个目录。
- 每个目录固定：`<name>.final.json`（图源，改图只改它）、`<name>.html`（交付产物）、`README.md`（画什么/怎么重新生成校验）。
- 交付流程（R-L2-18）：`archify render` → `archify check` 必须 `ok:true` 且 `composition=pass` → 人工/截图核对。
- **本机 Chrome 沙箱**：`browser-check` / `visual-check` 需要拉起 Chrome，本机要加环境变量 `ARCHIFY_CHROME_NO_SANDBOX=1`（archify 会转成 `--no-sandbox`）；五张图已四门全过（Action A-09 已关闭）。若换机器后仍失败，按各目录 README 的替代方式处理并在讨论记录登记，不得静默跳过。

## 维护提示

- 任何结构变更后，受影响的图必须重新生成并校验（R-L2-13、规格 §15）。
