# FLOW-VIDEO-20261012 — 视频线分环节操作流程图

> 对应需求：R-L1-11、R-L2-11~13。
> 覆盖主流程：**FLOW-4 / FLOW-5**（图文打包 → 图生视频 → 人工剪辑干预 → 导出成片）。
> 讨论来源：`docs/discussion-record.md` 节点 **N004**。

## 本目录内容

| 文件 | 说明 |
| ---- | ---- |
| `video-line.final.json` | **图源文件**（archify `architecture` 类型）。 |
| `video-line.html` | **交付产物**。 |
| `README.md` | 本说明。 |

## 这张图画什么

三列 region：**流程步骤／执行的 Skill 与依赖／产出物与留痕**。

主链路：`图文包（文案 + 24 张图）` → `编排者` → `asset-packager（打包 + manifest.json）` → `image-to-video（图生视频草稿）`
→ **关口② 剪辑干预（调整态：改顺序 / 时长 / 素材替换 + 实时预览）** → `auto-editor（按参数化剪辑单执行）`
→ `video-exporter（导出 mp4 + 封面帧）` → `title-cover-prep（套平台模板：标题 / 标签 / 封面）` → 交回编排者。

- 侧向依赖：`k6` 图生视频适配器（Remotion 为主 / ffmpeg 兜底，Q-7）、`k7` 渲染导出、`skill-readme`。
- 产出物：打包文件夹（含 manifest.json）、剪辑参数单、成片 mp4 与封面帧、产出登记。
- 卡片写死：输入校验（图文齐全、manifest 可解析）/ 完成判据（成片可播放、时长与参数单一致）/ 机制说明（为什么剪辑是「参数化 + 可回退」而不是直接改视频）/ 红线或规则（人工干预必须落成参数记录，可复现）。

## 如何重新生成与校验

```bash
node <archify-skill>/bin/archify.mjs render architecture \
  .archify/FLOW-VIDEO-20261012/video-line.final.json \
  .archify/FLOW-VIDEO-20261012/video-line.html --quality showcase

node <archify-skill>/bin/archify.mjs check \
  .archify/FLOW-VIDEO-20261012/video-line.html --json   # 必须 ok:true、composition=pass

# 3) 四门全过（含浏览器内检查）：本机 Chrome 需要 --no-sandbox，archify 用环境变量开启（A-09 已关闭）
ARCHIFY_CHROME_NO_SANDBOX=1 node <archify-skill>/bin/archify.mjs finalize architecture \
  .archify/FLOW-VIDEO-20261012/video-line.final.json .archify/FLOW-VIDEO-20261012/video-line.html --quality showcase --json
# → ok:true；gates: validate / deliver / check / browser-check 全 pass
```

## 布局经验

同文案线：三列 `40 / 380 / 720`、行距 140、列间隙 ≥113px。本图节点最多（含两处依赖与三处产出），
若再加节点需同步调大整体高度，避免 `composition/viewport-height`。
