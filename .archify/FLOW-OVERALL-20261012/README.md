# FLOW-OVERALL-20261012 — 整体运营流程图

> 对应需求：R-L1-11（整体运营流程图）、R-L2-11（一律用 archify 生成）、R-L2-12（每张图单独目录）、R-L2-13（变更后必须重新校验）。
> 讨论来源：`docs/discussion-record.md` 节点 **N003**。

## 本目录内容

| 文件 | 说明 |
| ---- | ---- |
| `overall-operations.final.json` | **图源文件**（archify `architecture` 类型候选 JSON）。改动图必须改这个文件。 |
| `overall-operations.html` | **交付产物**：可交互独立 HTML（暗/亮主题、图例、路径透镜、导出）。 |
| `README.md` | 本说明（R-L1-14 要求的目录说明，正式版将由 WP-09《目录及文件说明》收录）。 |

## 这张图画什么

自媒体创作运营的**整体闭环**，12 个组件分三层：

1. **左列 · 人机接口**：`真人运营人员（三处关口）`、`编排者（唯一）`，另有 `飞书文档`、`热点源` 两个外部输入/输出。
2. **中列 · 环节 Agent 执行层**：`文案线`、`视觉线`、`视频线`、`分发数据线` 四条线（region 边界框住）。
3. **右列 · 外部服务适配层与本地留痕**：`生图服务适配器`（Flow / 豆包 / ComfyUI + 降级链）、`图生视频适配器`、`浏览器自动化`（region 边界框住）、`本地数据库`。

三张卡片写死三条约定：三层职责边界、三处人工关口（HITL 的选择 / 调整 / 授权三态）、红线与回写（C-01 / C-08 / C-09）。

图上每个节点与连接的标签都与规格条目对应，例如「待发布授权」对应 C-08「发布前必须停在待发布态」。

## 如何重新生成与校验

```bash
# 1) 产出 HTML（render 不走浏览器门，稳定可用）
node <archify-skill>/bin/archify.mjs render architecture \
  .archify/FLOW-OVERALL-20261012/overall-operations.final.json \
  .archify/FLOW-OVERALL-20261012/overall-operations.html --quality showcase

# 2) 静态校验，必须 ok:true
node <archify-skill>/bin/archify.mjs check \
  .archify/FLOW-OVERALL-20261012/overall-operations.html --json
```

`<archify-skill>` = `/Users/yejin/.dsh/profiles/desktop/node_modules/@tt-a1i/archify-dsh/skills/archify`。

## 已知环境限制（登记为 Action A-09）

`archify finalize` 的最后一关 `browser-check`、以及 `archify visual-check` 需要拉起 Chrome，本机系统沙箱会拦截
（`Failed to initialize sandbox` / `GPU process isn't usable` / `sandbox initialization failed: Operation not permitted`）。
因此本图按 R-L2-18 用 `render` + `check` 交付，并额外用 headless Chrome（`--no-sandbox` + 工作区内 `HOME`/`--user-data-dir`）
截图人工核对。**不要**因为 `browser-check` 报 runtime 错误而重画图——那是环境问题，不是图的问题。

## 为什么不是 workflow 类型（重要教训）

初版按泳道 + 列网格用 `workflow` 类型画，连续 16 版无法通过校验，根因是硬约束：

- `fixed-v1` 布局要求**相邻列相连节点满足 `列距 > (两节点宽度之和)/2 + 28px`**；
- 列距随节点宽度变化：宽 100 → 列距 80；**宽 ≥130 → 列距锁死 132**；于是节点宽必须 ≤52px 才可能不重叠，
  而中文 4 字标签实测就需 ≈122px。**workflow 类型装不下中文步骤名**。

`architecture` 类型用绝对坐标（`layout.mode` 只能填 `grid`），自由度足够。后续各环节流程图沿用同一类型。
布局经验：列与列之间留 ≥113px 间隙（否则 `composition/label-gap`），扇出多条带标签的边要给足行距（≥180px），
否则并行边标签会互相贴住（`composition/label-route-clearance`）。
