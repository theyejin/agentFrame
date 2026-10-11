# FLOW-PUBLISH-20261012 — 分发数据线分环节操作流程图

> 对应需求：R-L1-11、R-L2-11~13；红线 C-01（未经授权绝不发布）、C-08（发布前必须停在待发布态）。
> 覆盖主流程：**FLOW-6 / FLOW-7 / FLOW-8**（账号准备 → 热点采集 → 发布准备 → 发布授权 → 指标采集 → 复盘）。
> 讨论来源：`docs/discussion-record.md` 节点 **N004**。

## 本目录内容

| 文件 | 说明 |
| ---- | ---- |
| `publish-line.final.json` | **图源文件**（archify `architecture` 类型）。 |
| `publish-line.html` | **交付产物**。 |
| `README.md` | 本说明。 |

## 这张图画什么

三列 region：**流程步骤／执行的 Skill 与依赖／产出物与留痕**。

主链路：`运营人员提供平台账号与会话（Q-13 需登录走人工授权）` → `编排者` → `hotspot-collector（按周期 / 自定义关键词搜热点）`
→ `table-builder（分类汇总成表）` → `feishu-sync（同步到飞书文档）` → `title-cover-prep（标题 / 标签 / 封面）`
→ `browser-publisher（自动登录并填写，**停在发布前**）` → **关口③ 发布授权（授权态：核对信息 → 人工点击发布）**
→ `metrics-collector（按周期采集播放 / 互动 / 涨粉）` → `指标与流水入库` → `review-reporter（复盘报告与优化建议，回写下一轮提示词版本）`。

- 侧向依赖：`skill-readme`、`feishu-sync` 与 `metrics-collector` 的汇回编排者连线。
- 产出物：热点表（分类 / 关键词 / 时间）、发布包（标题 / 标签 / 封面 / 账号）、**待发布态（只填不发，C-08 红线）**、复盘报告。
- 卡片写死：输入校验 / 完成判据 / 机制说明（`publish-guard` 守卫任何发布路径）/ 红线（C-01、C-08：agent 只填不发，发布动作永远由人点击）。

## 如何重新生成与校验

```bash
node <archify-skill>/bin/archify.mjs render architecture \
  .archify/FLOW-PUBLISH-20261012/publish-line.final.json \
  .archify/FLOW-PUBLISH-20261012/publish-line.html --quality showcase

node <archify-skill>/bin/archify.mjs check \
  .archify/FLOW-PUBLISH-20261012/publish-line.html --json   # 必须 ok:true、composition=pass
```

## 布局经验

同其余三张线图：三列 `40 / 380 / 720`、行距 140、列间隙 ≥113px。本图**回边最多**（热点表汇回、指标汇回、复盘回写），
是本套图中最易触发 `composition/proper-crossing` 的一张；如要加节点，优先把新节点放进中列而不是跨列连线。
