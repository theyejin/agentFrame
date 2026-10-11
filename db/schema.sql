-- 文件用途：数据库结构唯一参考（target state）—— 建库、评审、比对迁移都以本文件为准。
-- 对应需求：规格 §7 数据模型要求（R-7-01~R-7-05）、R-L1-04（只入库结构与迁移脚本）、§8.3（hitl_events）、R-8-03（operator 软锁）、R-L2-16/17（适配器声明与实际使用记录）。
-- 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（本地数据库与日志留痕）
-- 维护提示：改结构必须同时 ① 新增 db/migrations/NNNN_*.sql；② 更新 db/README.md 的表与枚举清单；③ 更新 docs/directory-and-files.md；④ 跑 python3 tests/test_db.py。
--
-- 使用方式：
--   sqlite3 db/app.db < db/schema.sql          # 新建库
--   sqlite3 db/app.db < db/seed/0001_platform_templates.sql   # 灌种子数据
--   或 python3 scripts/db_init.py              # 一条命令完成上面两步
--
-- 约定：
--   1. 表名、字段名用英文小写；字段含义用 SQL 注释写在字段后。
--   2. 所有状态/枚举字段一律用 CHECK 约束限定取值，取值必须在本文件注释与 db/README.md 中枚举完整（R-7-02）。
--   3. 大文件（图片/视频）不入库，只在 artifacts 登记路径与元信息（R-7-01）。
--   4. 时间统一存 ISO-8601 文本（UTC+08:00 本地时区），例：2026-10-12T05:30:00+08:00。

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 迁移台账：记录已应用过哪些迁移脚本
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    revision    INTEGER PRIMARY KEY,          -- 迁移序号，与 db/migrations/NNNN_*.sql 的 NNNN 一致
    name        TEXT    NOT NULL,             -- 迁移文件名（不含路径）
    applied_at  TEXT    NOT NULL              -- 应用时间
);

-- ---------------------------------------------------------------------------
-- 话题 topic：一次选题的源头（人工提交或热点派生），一条 topic 派生多个 task（R-7-05）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,             -- 选题标题（人工填写或热点标题）
    source      TEXT    NOT NULL CHECK (source IN ('manual','hotspot')),
                                              -- 来源：manual=人工提交，hotspot=热点派生（R-7-05）
    keywords    TEXT    NOT NULL DEFAULT '',  -- 关键词，多个用英文逗号分隔（热点采集条件）
    summary     TEXT    NOT NULL DEFAULT '',  -- 思路 / 一段话 / 剧情脚本的原文摘要
    created_by  TEXT    NOT NULL,             -- 创建人（operator 字段，首版不做登录，Q-17）
    status      TEXT    NOT NULL DEFAULT 'new'
                CHECK (status IN ('new','in_progress','done','archived')),
                                              -- new=新建 in_progress=进行中 done=已完成 archived=归档
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topics_source  ON topics(source);
CREATE INDEX IF NOT EXISTS idx_topics_status  ON topics(status);

-- ---------------------------------------------------------------------------
-- 任务 task：一条内容从文案到复盘的全周期；operator + 软锁字段实现任务级单处理人（R-8-03）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id        INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                                              -- 所属话题（一对多）
    stage           TEXT    NOT NULL DEFAULT 'copy'
                    CHECK (stage IN ('copy','visual','video','publish','metrics','review','closed')),
                                              -- 当前流程阶段：文案/视觉/视频/分发/数据/复盘/结束
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','waiting_human','blocked','done','failed','cancelled')),
                                              -- pending=待处理 running=执行中 waiting_human=等人工确认
                                              -- blocked=阻塞 done=完成 failed=失败 cancelled=取消
    priority        INTEGER NOT NULL DEFAULT 2 CHECK (priority BETWEEN 1 AND 3),
                                              -- 优先级：1=高 2=中 3=低
    target_platform TEXT    NOT NULL DEFAULT '',  -- 目标平台（抖音/小红书/B站/视频号…），空=未定
    content_type    TEXT    NOT NULL DEFAULT '情绪冲突'
                    CHECK (content_type IN ('情绪冲突','干货教程','热点观点','其他')),
                                              -- 文案类型 F-03（Q-3 沿用三项 + 其他）
    prompt          TEXT    NOT NULL DEFAULT '',  -- 文案 Prompt（F-01）
    word_min        INTEGER NOT NULL DEFAULT 300 CHECK (word_min > 0),
                                              -- 字数下限（F-02）
    word_max        INTEGER NOT NULL DEFAULT 500 CHECK (word_max > 0),
                                              -- 字数上限（F-02），入库时校验 word_min <= word_max（见触发器）
    selected_plan   INTEGER,                  -- 关口①选定的文案套号 1/2/3；NULL=尚未选定（§8.3）
    selected_at     TEXT,                     -- 选定时间
    operator        TEXT    NOT NULL DEFAULT '',  -- 当前处理人（R-8-03）
    locked_at       TEXT,                     -- 软锁时间；非空表示已被 operator 锁定，他人只读
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    CHECK (word_min <= word_max)              -- F-02：下限不得大于上限
);
CREATE INDEX IF NOT EXISTS idx_tasks_topic  ON tasks(topic_id);
CREATE INDEX IF NOT EXISTS idx_tasks_stage  ON tasks(stage, status);
CREATE INDEX IF NOT EXISTS idx_tasks_operator ON tasks(operator);

-- ---------------------------------------------------------------------------
-- 文案候选 copy_variants：每个任务固定生成 3 套，侧重点互不重复（R-L1-19）
-- 删除/重新生成一律软删（status），不做物理删除（§8.2 留痕要求）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS copy_variants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    plan_no     INTEGER NOT NULL CHECK (plan_no BETWEEN 1 AND 3),
                                              -- 第几套（1/2/3），对应 tasks.selected_plan
    focus       TEXT    NOT NULL CHECK (focus IN ('hook','emotion','cta')),
                                              -- 该套侧重维度：hook=开头钩子 emotion=情绪强度 cta=行动号召
    focus_note  TEXT    NOT NULL DEFAULT '',  -- 侧重点说明（给运营人员看的一句话）
    title       TEXT    NOT NULL DEFAULT '',  -- 文案标题
    body        TEXT    NOT NULL,             -- 文案正文
    word_count  INTEGER NOT NULL DEFAULT 0,   -- 字数（按中文计）
    status      TEXT    NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','deleted','superseded')),
                                              -- active=有效 deleted=已删（软删）superseded=被重新生成取代
    model_version    TEXT NOT NULL DEFAULT '',-- 产出模型版本（R-7-03）
    prompt_version   TEXT NOT NULL DEFAULT '',-- 产出提示词版本（R-7-03）
    created_at  TEXT    NOT NULL,
    UNIQUE (task_id, plan_no)
);
CREATE INDEX IF NOT EXISTS idx_copy_task ON copy_variants(task_id, status);

-- ---------------------------------------------------------------------------
-- 分镜 storyboards：一个任务 24 条（6×4），编号 1–24 连续（R-L1-19）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS storyboards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    shot_no     INTEGER NOT NULL CHECK (shot_no BETWEEN 1 AND 24),
                                              -- 分镜号 1–24（6×4 = 24）
    scene_text  TEXT    NOT NULL,             -- 该格的画面描述（用于生图）
    camera_note TEXT    NOT NULL DEFAULT '',  -- 镜头/构图提示（可选）
    duration_s  REAL    NOT NULL DEFAULT 0 CHECK (duration_s >= 0),
                                              -- 该镜头时长（秒），0=未定
    created_at  TEXT    NOT NULL,
    UNIQUE (task_id, shot_no)
);
CREATE INDEX IF NOT EXISTS idx_story_task ON storyboards(task_id);

-- ---------------------------------------------------------------------------
-- 步骤流水 step_runs：某任务的第几步、用了哪个 Skill、走哪个适配器、耗时与失败原因
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS step_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_no     INTEGER NOT NULL CHECK (step_no > 0),  -- 该任务内第几步（从 1 递增）
    skill_id    TEXT    NOT NULL,             -- 执行的 skill（与 docs/skill-roster.md 一致）
    status      TEXT    NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','ok','failed','skipped')),
                                              -- pending=待执行 running=执行中 ok=成功 failed=失败 skipped=跳过
    adapter_used TEXT   NOT NULL DEFAULT '',  -- 实际使用的适配器（降级后记录真实值，R-L2-17）
    input_json  TEXT    NOT NULL DEFAULT '{}',-- 输入快照（JSON 文本）
    output_json TEXT    NOT NULL DEFAULT '{}',-- 输出摘要（JSON 文本；大产物只记路径）
    error       TEXT    NOT NULL DEFAULT '',  -- 失败原因（status=failed 时必填，见触发器）
    started_at  TEXT,                         -- 开始时间
    ended_at    TEXT,                         -- 结束时间
    duration_ms INTEGER NOT NULL DEFAULT 0,   -- 耗时毫秒
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_step_task ON step_runs(task_id, step_no);
CREATE INDEX IF NOT EXISTS idx_step_skill ON step_runs(skill_id, status);

-- ---------------------------------------------------------------------------
-- 产物 artifact：登记路径与元信息，不存大文件（R-7-01）；必须记模型与提示词版本（R-7-03）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_run_id INTEGER REFERENCES step_runs(id) ON DELETE SET NULL,
                                              -- 由哪一步产出（可空：人工补录）
    kind        TEXT    NOT NULL
                CHECK (kind IN ('copy','storyboard','image','video','audio','manifest','table','report','publish_package')),
                                              -- copy=文案 storyboard=分镜 image=图片 video=视频 audio=音频
                                              -- manifest=打包清单 table=表格 report=报告 publish_package=发布包
    path        TEXT    NOT NULL,             -- 文件路径（相对仓库根，例：workspace/topic-1/images/shot-01.png）
    size_bytes  INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    sha256      TEXT    NOT NULL DEFAULT '',  -- 内容指纹（用于「同一张图是否变过」）
    model_version  TEXT NOT NULL,             -- 产出模型版本（R-7-03，人工产物填 'human'）
    prompt_version TEXT NOT NULL,             -- 产出提示词版本（R-7-03，人工产物填 'none'）
    meta_json   TEXT    NOT NULL DEFAULT '{}',-- 其他元信息（分辨率、时长、编号等）
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_art_task ON artifacts(task_id, kind);
CREATE INDEX IF NOT EXISTS idx_art_step ON artifacts(step_run_id);

-- ---------------------------------------------------------------------------
-- 人工介入 hitl_events：三类关口（选择/调整/授权）每一次动作都留痕（R-8-02、C-02）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hitl_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    gate        TEXT    NOT NULL
                CHECK (gate IN ('gate1_select_copy','gate2_edit_video','gate3_publish_auth')),
                                              -- gate1=选定文案(选择态) gate2=剪辑干预(调整态) gate3=发布授权(授权态)
    actor       TEXT    NOT NULL,             -- 谁做的（operator 名）
    action      TEXT    NOT NULL CHECK (action IN ('confirm','reject','adjust')),
                                              -- confirm=确认 reject=拒绝 adjust=调整参数
    snapshot_json TEXT  NOT NULL DEFAULT '{}',-- 动作发生时的待执行内容快照（防止事后篡改语义）
    diff_json   TEXT    NOT NULL DEFAULT '{}',-- 与动作前的差异（adjust 时记录参数前后值）
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hitl_task ON hitl_events(task_id, gate);

-- ---------------------------------------------------------------------------
-- 数据指标 metrics：首版三项（播放量/互动量/涨粉数），必须带统计周期与采集时间（R-7-04）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                                              -- 归属任务（可空：话题级/账号级汇总）
    platform    TEXT    NOT NULL,             -- 平台名
    metric_key  TEXT    NOT NULL
                CHECK (metric_key IN ('views','engagements','follower_gain')),
                                              -- views=播放量 engagements=互动量(赞+藏+评) follower_gain=涨粉数
    value       REAL    NOT NULL CHECK (value >= 0),
    period_start TEXT   NOT NULL,             -- 统计周期开始（不记周期则不同期数据不可比）
    period_end  TEXT    NOT NULL,             -- 统计周期结束
    collected_at TEXT   NOT NULL,             -- 采集时间（R-7-04）
    source      TEXT    NOT NULL DEFAULT 'manual'
                CHECK (source IN ('manual','browser','api','export')),
                                              -- 数据来源：manual=人工录入 browser=浏览器采集 api=接口 export=导入
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metric_task ON metrics(task_id, metric_key);
CREATE INDEX IF NOT EXISTS idx_metric_period ON metrics(period_start, period_end);

-- ---------------------------------------------------------------------------
-- 适配器声明 adapter_registry：能力/密钥/计费/失败特征/降级顺序（R-L2-16）
-- 运行时「实际用了哪个」记在 step_runs.adapter_used（R-L2-17）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS adapter_registry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    adapter_id  TEXT    NOT NULL UNIQUE,      -- 适配器标识，例：image.flow、image.doubao、video.remotion
    kind        TEXT    NOT NULL
                CHECK (kind IN ('llm','image','split','video','browser','doc','metrics')),
                                              -- llm=文本 image=生图 split=切图 video=图生视频/渲染
                                              -- browser=浏览器自动化 doc=飞书等文档 metrics=数据采集
    provider    TEXT    NOT NULL DEFAULT '',  -- 服务方名称
    capabilities TEXT   NOT NULL DEFAULT '',  -- 能力范围（自然语言，例：文生图、支持 6×4 拼图）
    needs_key   INTEGER NOT NULL DEFAULT 0 CHECK (needs_key IN (0,1)),
                                              -- 是否需要密钥（1=需要）
    billable    INTEGER NOT NULL DEFAULT 0 CHECK (billable IN (0,1)),
                                              -- 是否计费（1=计费；受 C-09 零付费门禁约束）
    failure_signals TEXT NOT NULL DEFAULT '', -- 典型失败特征（用于识别该换适配器了）
    fallback_order  INTEGER NOT NULL DEFAULT 1 CHECK (fallback_order > 0),
                                              -- 降级顺序：数字小的先试（R-L2-17）
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
                                              -- 是否启用（0=停用）
    note        TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adapter_kind ON adapter_registry(kind, fallback_order);

-- ---------------------------------------------------------------------------
-- 平台预设模板 platform_templates：选平台自动带出字数/标题/标签/封面（R-8-01、Q-18）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT    NOT NULL UNIQUE,      -- 平台名
    word_min    INTEGER NOT NULL CHECK (word_min > 0),
    word_max    INTEGER NOT NULL CHECK (word_max > 0),
    title_style TEXT    NOT NULL DEFAULT '',  -- 标题写法（例：前 12 字出钩子，带数字/疑问）
    tag_count   INTEGER NOT NULL DEFAULT 0 CHECK (tag_count >= 0),
                                              -- 标签数量
    cover_ratio TEXT    NOT NULL DEFAULT '',  -- 封面比例（例：3:4、9:16）
    note        TEXT    NOT NULL DEFAULT '',
    CHECK (word_min <= word_max)
);

-- ---------------------------------------------------------------------------
-- 提示词版本 prompt_versions：提示词以文件形式入仓，这里登记版本与路径（R-7-03）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prompt_versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_key  TEXT    NOT NULL,             -- 提示词标识，例：copy-writer.default
    version     TEXT    NOT NULL,             -- 版本号，例：0.1.0
    file_path   TEXT    NOT NULL,             -- 仓库内文件路径（不许写死在代码里）
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    UNIQUE (prompt_key, version)
);

-- ---------------------------------------------------------------------------
-- 版本备份点 versions：每次结构变更对应的 commit / tag（§7 版本对象、R-L2-04、Q-8）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha  TEXT    NOT NULL,             -- 备份提交号
    tag         TEXT    NOT NULL DEFAULT '',  -- 备份 tag
    summary     TEXT    NOT NULL,             -- 本次变更摘要
    created_at  TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- 触发器：把「字段级一致性」交给数据库兜底，避免脏数据进入后续环节
-- ---------------------------------------------------------------------------
-- 失败步骤必须写原因（否则复盘查不出为什么停下）
CREATE TRIGGER IF NOT EXISTS trg_step_failed_has_error
BEFORE INSERT ON step_runs
FOR EACH ROW WHEN NEW.status = 'failed' AND TRIM(NEW.error) = ''
BEGIN
    SELECT RAISE(ABORT, 'step_runs.status=failed 必须填写 error 失败原因');
END;

-- 选定文案时套号只能是 1/2/3
CREATE TRIGGER IF NOT EXISTS trg_task_selected_plan_valid
BEFORE UPDATE OF selected_plan ON tasks
FOR EACH ROW WHEN NEW.selected_plan IS NOT NULL
     AND (NEW.selected_plan < 1 OR NEW.selected_plan > 3)
BEGIN
    SELECT RAISE(ABORT, 'tasks.selected_plan 只能是 1/2/3');
END;

-- 媒体类产物必须有非零大小（空文件视为失败产物）
CREATE TRIGGER IF NOT EXISTS trg_artifact_media_size
BEFORE INSERT ON artifacts
FOR EACH ROW WHEN NEW.kind IN ('image','video') AND NEW.size_bytes = 0
BEGIN
    SELECT RAISE(ABORT, 'artifacts：图片/视频产物的 size_bytes 必须大于 0');
END;

-- ---------------------------------------------------------------------------
-- 便于看板/复盘的视图
-- ---------------------------------------------------------------------------
-- 每个任务当前进度：走到第几步、最近一次流水结果
DROP VIEW IF EXISTS v_task_progress;
CREATE VIEW v_task_progress AS
SELECT  t.id            AS task_id,
        t.stage,
        t.status,
        t.operator,
        t.target_platform,
        (SELECT COUNT(*) FROM step_runs s WHERE s.task_id = t.id AND s.status = 'ok')     AS done_steps,
        (SELECT COUNT(*) FROM step_runs s WHERE s.task_id = t.id AND s.status = 'failed') AS failed_steps,
        (SELECT MAX(s.step_no) FROM step_runs s WHERE s.task_id = t.id)                   AS last_step_no
FROM tasks t;

-- 待发布任务清单（供控制台「发布」页与关口③核对页使用）
DROP VIEW IF EXISTS v_pending_publish;
CREATE VIEW v_pending_publish AS
SELECT  t.id AS task_id,
        tp.title,
        t.target_platform,
        (SELECT COUNT(*) FROM storyboards s WHERE s.task_id = t.id)                        AS shots,
        (SELECT COUNT(*) FROM artifacts a WHERE a.task_id = t.id AND a.kind = 'video')     AS videos,
        (SELECT MAX(h.created_at) FROM hitl_events h
          WHERE h.task_id = t.id AND h.gate = 'gate3_publish_auth')                        AS last_auth_at
FROM tasks t
JOIN topics tp ON tp.id = t.topic_id
WHERE t.stage = 'publish' AND t.status IN ('pending','running','waiting_human');
