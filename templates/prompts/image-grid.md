---
prompt_key: image-grid
version: v1
purpose: 把 24 条分镜画进一张 6×4 整图（按分镜号顺序排列，供后续切分成 24 张独立图）
used_by: grid-image-builder
variables:
  - topic_title
  - shots_brief
  - grid
  - cell_size
  - platform
  - style_hint
---
你是短视频分镜画师，请按「{{grid}}」的网格画**一张**整图，共 24 格。

选题：{{topic_title}}
平台：{{platform}}
单格画幅：{{cell_size}}
风格基准（必须全程保持一致）：{{style_hint}}

24 格画面内容（从左到右、从上到下，严格按编号顺序）：
{{shots_brief}}

硬性要求：
1. **只输出一张图**：6 列 4 行共 24 格，每格之间留 2% 间距的浅色分隔线，便于后续等分切图；
2. 每格只画该编号对应的画面，不得跨格、不得少格、不得合并；
3. 全图色调、光线、人物造型、镜头语言保持统一（这是切分成 24 张后仍像同一支片子的前提）；
4. 任何位置都不得出现文字、字幕、水印、logo、二维码；
5. 第 1 格与第 24 格的关系要能看出开场与收尾。
