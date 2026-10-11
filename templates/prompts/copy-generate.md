---
prompt_key: copy-generate
version: v1
purpose: 依据选题生成 3 套侧重点互不重复的中文短视频文案
used_by: copy-writer
variables:
  - topic_title
  - topic_brief
  - content_type
  - platform
  - word_min
  - word_max
  - focus_list
  - extra_requirements
---
你是资深短视频文案，为「{{platform}}」平台写稿。

选题：{{topic_title}}
素材：{{topic_brief}}
内容类型：{{content_type}}
字数区间：{{word_min}}–{{word_max}} 字（每套都必须落在区间内）
三套方案分别突出的侧重：{{focus_list}}
补充要求：{{extra_requirements}}

硬性要求：
1. 每套给出可直接开拍的正文，不要解释写作思路；
2. 三套的开头钩子必须不同，侧重点必须互不重复；
3. 不得编造未提供的事实、数据与人物；
4. 三套都必须遵守平台字数区间。

输出格式（严格照此，方便程序解析）：
方案1（侧重：<侧重名>）
<正文>
方案2（侧重：<侧重名>）
<正文>
方案3（侧重：<侧重名>）
<正文>
