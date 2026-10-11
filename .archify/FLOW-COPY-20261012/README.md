# FLOW-COPY-20261012 — 文案线分环节操作流程图

> 对应需求：R-L1-11（分环节操作流程图）、R-L2-11（一律用 archify 生成）、R-L2-12（每张图单独目录）、R-L2-13（变更后必须重新校验）。
> 覆盖主流程：**FLOW-1**（思路/选题/脚本 → 3 套文案 → 选定 → 24 条分镜）。
> 讨论来源：`docs/discussion-record.md` 节点 **N004**；岗位细节见 `docs/skill-roster.md`。

## 本目录内容

| 文件 | 说明 |
| ---- | ---- |
| `copy-line.final.json` | **图源文件**（archify `architecture` 类型）。改图只改它。 |
| `copy-line.html` | **交付产物**：可交互独立 HTML。 |
| `README.md` | 本说明（R-L1-14 目录说明）。 |

## 这张图画什么

三列 region 边界固定为：**流程步骤（人与 Agent 的动作）／执行的 Skill 与依赖（模块化执行）／产出物与留痕（可追溯）**。

主链路：`运营人员（给思路·选题·一段话·剧情脚本）` → `编排者（派单给 copy-writer，校验返回值）` → `copy-writer（一套输入 → 3 套不同侧重点）`
→ **关口① 选定文案（选择态：三选一对比卡）** → `storyboard-builder（选定文案 → 24 条分镜场景）` → 入库与留痕。

- 侧向依赖：`llm-adapter`（统一模型接口，可换模型）、`prompt-registry`（提示词版本注册表）、`skill-readme`（每个 skill 自带 README.md）。
- 产出物：`3 套候选文案`（侧重点/理由/字数区间）、`选定记录`（hitl_events 选择态留痕）、`storyboard.json`（24 条、编号连续）、`版本字段`（model_version / prompt_version）。
- 回边：`关口① → copy-writer`「不满意 → 带反馈重生成」，带反馈文本回到 copy-writer，不重跑无关环节。
- 卡片写死：输入校验 / 完成判据（3 套且侧重点互不重复、分镜 24 条且编号连续）/ 机制说明 / 关口①三条规则。

## 如何重新生成与校验

```bash
node <archify-skill>/bin/archify.mjs render architecture \
  .archify/FLOW-COPY-20261012/copy-line.final.json \
  .archify/FLOW-COPY-20261012/copy-line.html --quality showcase

node <archify-skill>/bin/archify.mjs check \
  .archify/FLOW-COPY-20261012/copy-line.html --json   # 必须 ok:true、composition=pass
```

`<archify-skill>` = `/Users/yejin/.dsh/profiles/desktop/node_modules/@tt-a1i/archify-dsh/skills/archify`。

## 布局经验（改图前先读）

- 三列 x 坐标固定 `40 / 380 / 720`，行 y 从 120 起、步进 140；列间横向间隙须 ≥113px，否则报 `composition/label-gap`。
- 正反两条边若走同一段走廊，标签会 0px 相撞（`composition/label-route-clearance`）——本图曾因此把标签缩短为「待抽查」「单张返工」「整组返工」才通过。
- `browser-check` / `visual-check` 在本机被 Chrome 沙箱拦截（见 `../FLOW-OVERALL-20261012/README.md` 与 Action A-09），本图按 R-L2-18 用 `render` + `check` + 截图核对交付。
