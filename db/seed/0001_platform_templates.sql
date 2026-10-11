-- 文件用途：种子数据 —— 平台预设模板（R-8-01、Q-18）：选平台后自动带出字数区间/标题写法/标签数/封面比例。
-- 对应需求：R-8-01（平台预设模板）、§8.1（F-02 字数范围默认值参考）。
-- 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html（发布准备 title-cover-prep）
-- 维护提示：模板值可被运营人员在页面上手动覆盖；改这里请同步 db/README.md 的模板表。
--
-- 执行方式：sqlite3 db/app.db < db/seed/0001_platform_templates.sql

INSERT OR REPLACE INTO platform_templates
    (platform, word_min, word_max, title_style, tag_count, cover_ratio, note)
VALUES
    ('抖音',     200,  400, '前 8 字出钩子，带悬念或反差；不超过 30 字',        5, '9:16', '竖版短视频，节奏快，钩子前置'),
    ('小红书',   300,  800, '第一人称 + 数字清单，标题带 emoji 与关键词',       8, '3:4',  '图文/视频皆可，标签权重高'),
    ('B站',      500, 1500, '标题写清「看完能获得什么」，可用书名号与系列名',    6, '16:9', '中长视频，前 15 秒留人'),
    ('视频号',   200,  600, '口语化、熟人转述感，避免夸张词',                  4, '9:16', '偏私域传播，标题不宜过长');
