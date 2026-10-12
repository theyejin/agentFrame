-- 文件用途：迁移 0003 —— 新增热点批次/热点条目/发布记录三张表
-- 对应需求：FLOW-7（热点采集与分类汇总）、FLOW-6 + C-08（只填不发与发布留痕）、L3 控制台数据来源
-- 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
-- 维护提示：只追加，不改历史迁移；改结构必须同步 db/schema.sql 与 tests/test_db.py

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 热点批次 hotspot_batches：一次采集的汇总（话题级，不挂任务）
-- 与热点条目一对多；表格文件与文档导出路径回填在这里
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotspot_batches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_key   TEXT    NOT NULL UNIQUE,       -- 批次号（时间戳 slug，命令行与文件名都用它）
    keyword     TEXT    NOT NULL,              -- 采集关键词（多个用逗号分隔）
    source      TEXT    NOT NULL DEFAULT 'manual'
                CHECK (source IN ('manual','browser','fixture','api','export')),
                                              -- fixture=本地夹具（离线演练）browser=浏览器采集
    period_start TEXT   NOT NULL DEFAULT '',   -- 统计周期开始
    period_end   TEXT   NOT NULL DEFAULT '',   -- 统计周期结束
    items_count INTEGER NOT NULL DEFAULT 0 CHECK (items_count >= 0),
    table_path  TEXT    NOT NULL DEFAULT '',   -- 分类汇总表格文件（相对仓库根）
    export_path TEXT    NOT NULL DEFAULT '',   -- 同步到外部文档后的导出文件（Q-5 降级路径）
    adapter_used TEXT   NOT NULL DEFAULT '',   -- 实际使用的采集适配器（R-L2-17）
    collected_at TEXT   NOT NULL,              -- 采集时间
    created_at  TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- 热点条目 hotspot_items：一条热点一行，分类是后续选题与汇总的分组依据
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotspot_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    INTEGER NOT NULL REFERENCES hotspot_batches(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL,
    category    TEXT    NOT NULL DEFAULT '其他'
                CHECK (category IN ('情绪冲突','干货教程','热点观点','其他')),
    heat        REAL    NOT NULL DEFAULT 0 CHECK (heat >= 0),
    source_url  TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hotspot_batch ON hotspot_items(batch_id, category);
CREATE INDEX IF NOT EXISTS idx_hotspot_cat ON hotspot_items(category);

-- ---------------------------------------------------------------------------
-- 发布记录 publish_records：发布包落地与人工发布回填（C-08：Agent 只填不发）
-- status 由人工发布的动作推进，Agent 不得写 published
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS publish_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    platform    TEXT    NOT NULL,
    account_label TEXT  NOT NULL DEFAULT '',   -- 运营人员提供的账号标识（不存密码）
    package_path TEXT   NOT NULL DEFAULT '',   -- 发布包目录（相对仓库根）
    video_path  TEXT    NOT NULL DEFAULT '',   -- 待发布成片
    status      TEXT    NOT NULL DEFAULT 'filled'
                CHECK (status IN ('filled','pending','published','failed')),
                                              -- filled=已填好待人工发布 pending=等待授权 published=已发布（人工）
    filled_at   TEXT,                          -- 填写完成时间
    published_at TEXT,                         -- 人工发布/回填时间
    publish_url TEXT    NOT NULL DEFAULT '',   -- 发布后的作品链接（人工回填）
    operator    TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_publish_task ON publish_records(task_id, platform);

-- ---------------------------------------------------------------------------
-- 登记本次迁移
-- ---------------------------------------------------------------------------
INSERT OR REPLACE INTO schema_migrations (revision, name, applied_at)
VALUES (3, '0003_add_hotspots_and_publish.sql', strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime'));
