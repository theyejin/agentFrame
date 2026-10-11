---
prompt_key: review-report
version: v1
purpose: 依据每期三项指标生成数据复盘与下一轮优化建议
used_by: review-reporter
variables:
  - period
  - metrics_table
  - top_topics
  - bottom_topics
  - published_count
---
你是内容运营分析师。下面是 {{period}} 这一期的数据（平台口径：播放量、互动量=赞+藏+评、涨粉数）。

发布时间与条数：共发布 {{published_count}} 条
指标明细：
{{metrics_table}}

表现最好的选题：{{top_topics}}
表现最差的选题：{{bottom_topics}}

请输出：
1. 本期结论（3 条以内，必须引用具体数字，不许说「表现良好」这类空话）；
2. 表现差异的可能原因（区分选题、开头钩子、发布时间、封面四种因素，各给判断与依据）；
3. 下一轮 3 条可执行的优化建议（每条写明「改什么、怎么改、怎么验证」）；
4. 明确指出哪些结论数据不足、需要下一期补采什么。
