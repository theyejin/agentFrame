# FLOW-VISUAL-20261012 — 视觉线分环节操作流程图

> 对应需求：R-L1-11、R-L2-11~13。
> 覆盖主流程：**FLOW-2 / FLOW-3**（参考图 → 6×4 整图 → 切成 24 张独立图）。
> 讨论来源：`docs/discussion-record.md` 节点 **N004**。

## 本目录内容

| 文件 | 说明 |
| ---- | ---- |
| `visual-line.final.json` | **图源文件**（archify `architecture` 类型）。 |
| `visual-line.html` | **交付产物**。 |
| `README.md` | 本说明。 |

## 这张图画什么

三列 region：**流程步骤／执行的 Skill 与依赖／产出物与留痕**。

主链路：`选定文案 + 24 条分镜` → `编排者` → `reference-image-builder（参考图 1–3 张）` → `人工风格确认`
→ `grid-image-builder（6×4 整图，一次出图）` → `image-splitter（切成 24 张独立图）` → `修图关口（可只重生成某一张）` → 入库。

- 侧向依赖：`llm-adapter`、生图适配器 `k4`（Flow / 豆包 / ComfyUI **+ 降级链**）、切分适配器 `k5`、`skill-readme`。
- 产出物：参考图、整图（6×4）、`shot-01 … shot-24`（命名固定、编号连续）、产出登记。
- 回边：`修图关口 → image-splitter`「单张返工」、`修图关口 → 编排者`「整组返工」。
- 卡片写死：输入校验 / 完成判据（24 张、编号连续、分辨率一致）/ 机制说明（为什么先整图后切分：Q-11）/ 红线或规则（单张重生成不重跑整组）。

## 如何重新生成与校验

```bash
node <archify-skill>/bin/archify.mjs render architecture \
  .archify/FLOW-VISUAL-20261012/visual-line.final.json \
  .archify/FLOW-VISUAL-20261012/visual-line.html --quality showcase

node <archify-skill>/bin/archify.mjs check \
  .archify/FLOW-VISUAL-20261012/visual-line.html --json   # 必须 ok:true、composition=pass
```

## 布局经验

同文案线：三列 `40 / 380 / 720`、行距 140、列间隙 ≥113px。本图核心难点是**正反边共存**（修图关口既有出边又有两条回边），
标签必须短且彼此错开，否则触发 `composition/label-route-clearance`。
