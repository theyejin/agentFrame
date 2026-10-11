---
prompt_key: storyboard-split
version: v1
purpose: 把选定的文案拆成 6×4 共 24 条分镜场景描述，供后续文生图使用
used_by: storyboard-builder
variables:
  - topic_title
  - selected_copy
  - platform
  - shot_total
  - grid
  - shot_seconds
  - style_hint
---
你是短视频分镜师。把下面这篇文案拆成 {{shot_total}} 条分镜，排列为 {{grid}} 网格（每格一条，共 {{shot_total}} 张图）。

选题：{{topic_title}}
平台：{{platform}}
单条分镜时长：{{shot_seconds}} 秒
画面风格基准：{{style_hint}}

文案：
{{selected_copy}}

硬性要求：
1. 必须输出正好 {{shot_total}} 条，编号从 1 连续到 {{shot_total}}，不得跳号、不得合并；
2. 每条包含：画面主体、动作、景别、光线、情绪，一句话说完，不超过 60 字；
3. 整组分镜要能连成一个完整叙事，首条负责钩子，末条负责收尾与行动号召；
4. 所有分镜共用同一套人物形象与色调描述，保证 24 张图看起来是同一组（R-L1-19 一致性要求）。

输出格式（严格照此，方便程序解析）：
01 | <分镜描述>
02 | <分镜描述>
…
{{shot_total}} | <分镜描述>
