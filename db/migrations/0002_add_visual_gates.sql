-- 文件用途：迁移 0002 —— 扩展 hitl_events.gate 枚举，纳入视觉线的两个人工关口（风格确认 / 单张返工）。
-- 对应需求：规格 §8.3（三类 HITL 形态）、R-L1-06、R-L1-19、R-8-03（谁做的决定要留痕）。
-- 对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html（人的风格确认 / 人工修图关口）
-- 维护提示：本文件是「已发布的历史」，不得再修改；后续结构变更请新增 0003_*.sql 并同步 db/schema.sql。
--
-- 背景：gite 枚举在 SQLite 里只能用 CHECK 表达，而 CHECK 无法 ALTER，故重建表并搬数据。
-- 执行方式：python3 scripts/db_init.py --from-migrations（或 sqlite3 db/app.db < 本文件）

PRAGMA foreign_keys = OFF;

ALTER TABLE hitl_events RENAME TO hitl_events_old;

CREATE TABLE IF NOT EXISTS hitl_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    gate        TEXT    NOT NULL
                CHECK (gate IN ('gate1_select_copy','gate2_edit_video','gate3_publish_auth',
                                'gate_visual_style','gate_visual_fix')),
                                              -- gate1=选定文案(选择态) gate2=剪辑干预(调整态) gate3=发布授权(授权态)
                                              -- gate_visual_style=人的风格确认(调整态) gate_visual_fix=人工修图/单张返工(调整态)
    actor       TEXT    NOT NULL,             -- 谁做的（operator 名）
    action      TEXT    NOT NULL CHECK (action IN ('confirm','reject','adjust')),
                                              -- confirm=确认 reject=拒绝 adjust=调整参数
    snapshot_json TEXT  NOT NULL DEFAULT '{}',-- 动作发生时的待执行内容快照（防止事后篡改语义）
    diff_json   TEXT    NOT NULL DEFAULT '{}',-- 与动作前的差异（adjust 时记录参数前后值）
    created_at  TEXT    NOT NULL
);

INSERT INTO hitl_events (id, task_id, gate, actor, action, snapshot_json, diff_json, created_at)
SELECT id, task_id, gate, actor, action, snapshot_json, diff_json, created_at FROM hitl_events_old;

DROP TABLE hitl_events_old;

CREATE INDEX IF NOT EXISTS idx_hitl_task ON hitl_events(task_id, gate);

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 登记本次迁移
-- ---------------------------------------------------------------------------
INSERT OR REPLACE INTO schema_migrations (revision, name, applied_at)
VALUES (2, '0002_add_visual_gates.sql', strftime('%Y-%m-%dT%H:%M:%S+08:00','now','localtime'));
