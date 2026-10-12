#!/usr/bin/env python3
# 文件用途：WP-05 步骤 2 的模拟测试 —— 验证数据库结构、迁移链、种子数据与各项约束（不碰真实外部服务）。
# 对应需求：R-L2-02（每步模拟测试通过再下一步）、规格 §7（数据模型要求）、R-7-01~R-7-05、R-8-01、R-8-03、R-L1-19。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（本地数据库与日志留痕）
# 维护提示：新增迁移或种子文件后，本测试会自动覆盖；改了表结构请同步补一条断言。
"""数据库结构模拟测试。

运行：
    python3 tests/test_db.py            # 人读
    python3 -m unittest discover -s tests -v

全部用例通过 = WP-05 步骤 2 的完成门之一（另一个是 `python3 scripts/structure_check.py` 退出码 0）。
"""

import os
import sqlite3
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "db", "schema.sql")
MIGRATIONS_DIR = os.path.join(ROOT, "db", "migrations")
SEED_DIR = os.path.join(ROOT, "db", "seed")

TS = "2026-10-12T06:00:00+08:00"


def new_conn():
    """内存库 + 打开外键约束（与建库脚本一致的运行前提）。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_sql_file(conn, path):
    with open(path, encoding="utf-8") as f:
        conn.executescript(f.read())


def build_from_schema(with_seed=True):
    conn = new_conn()
    apply_sql_file(conn, SCHEMA)
    if with_seed:
        apply_seed(conn)
    return conn


def build_from_migrations(with_seed=False):
    conn = new_conn()
    for path in sorted(os.listdir(MIGRATIONS_DIR)):
        if path.endswith(".sql"):
            apply_sql_file(conn, os.path.join(MIGRATIONS_DIR, path))
    if with_seed:
        apply_seed(conn)
    return conn


def apply_seed(conn):
    for path in sorted(os.listdir(SEED_DIR)):
        if path.endswith(".sql"):
            apply_sql_file(conn, os.path.join(SEED_DIR, path))


def structure_of(conn):
    """取出可比对的结构指纹：(类型, 名称) 列表。排除 sqlite_ 内部对象与迁移台账。"""
    rows = conn.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND name != 'schema_migrations' "
        "ORDER BY type, name"
    ).fetchall()
    return [(t, n) for t, n in rows]


def insert_topic(conn, title="测试选题", source="manual"):
    cur = conn.execute(
        "INSERT INTO topics (title, source, keywords, summary, created_by, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (title, source, "测试,关键词", "一段话思路", "yip", "new", TS, TS),
    )
    return cur.lastrowid


def insert_task(conn, topic_id, **kw):
    fields = {
        "stage": "copy", "status": "pending", "priority": 2, "target_platform": "抖音",
        "content_type": "情绪冲突", "prompt": "给我一个选题", "word_min": 300, "word_max": 500,
        "selected_plan": None, "selected_at": None, "operator": "yip", "locked_at": None,
    }
    fields.update(kw)
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO tasks (topic_id, {cols}, created_at, updated_at) VALUES (?, {marks}, ?, ?)",
        (topic_id, *fields.values(), TS, TS),
    )
    return cur.lastrowid


def insert_24_shots(conn, task_id):
    for i in range(1, 25):
        conn.execute(
            "INSERT INTO storyboards (task_id, shot_no, scene_text, camera_note, duration_s, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (task_id, i, f"第 {i} 格画面", "中景", 3.0, TS),
        )


class TestStructure(unittest.TestCase):
    """① 结构可建、迁移链与 schema 一致。"""

    def test_schema_creates_expected_tables(self):
        conn = build_from_schema()
        names = {n for t, n in structure_of(conn) if t == "table"}
        for expected in ["topics", "tasks", "copy_variants", "storyboards", "step_runs",
                         "artifacts", "hitl_events", "metrics", "adapter_registry",
                         "platform_templates", "prompt_versions", "versions",
                         "hotspot_batches", "hotspot_items", "publish_records"]:
            self.assertIn(expected, names, f"缺表 {expected}")

    def test_migrations_match_schema(self):
        """迁移链建出来的结构与 schema.sql 完全一致（防止两者漂移）。"""
        a = structure_of(build_from_schema(with_seed=False))
        b = structure_of(build_from_migrations())
        self.assertEqual(a, b, "db/migrations 建出的结构与 db/schema.sql 不一致")

    def test_schema_is_idempotent(self):
        """重复执行 schema.sql 不报错（便于「随时同步到最新结构」）。"""
        conn = build_from_schema(with_seed=False)
        apply_sql_file(conn, SCHEMA)
        self.assertTrue(structure_of(conn))

    def test_migration_registered(self):
        conn = build_from_migrations()
        rows = conn.execute("SELECT revision, name FROM schema_migrations ORDER BY revision").fetchall()
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1], "0001_init.sql")


class TestSeed(unittest.TestCase):
    """② 种子数据可重复灌入且不重复。"""

    def test_platform_templates_seeded(self):
        conn = build_from_schema()
        rows = conn.execute("SELECT platform, word_min, word_max, cover_ratio FROM platform_templates").fetchall()
        self.assertGreaterEqual(len(rows), 4)
        got = {r[0] for r in rows}
        self.assertTrue({"抖音", "小红书", "B站", "视频号"}.issubset(got))

    def test_seed_is_idempotent(self):
        conn = build_from_schema()
        apply_seed(conn)
        n1 = conn.execute("SELECT COUNT(*) FROM platform_templates").fetchone()[0]
        self.assertEqual(n1, 4, "种子应使用 INSERT OR REPLACE，重复灌入不增行")


class TestContentModel(unittest.TestCase):
    """③ 内容模型：24 条分镜、3 套文案、软删、选定套号。"""

    def setUp(self):
        self.conn = build_from_schema()
        self.topic_id = insert_topic(self.conn)
        self.task_id = insert_task(self.conn, self.topic_id)

    def test_24_storyboards_ok(self):
        insert_24_shots(self.conn, self.task_id)
        n = self.conn.execute("SELECT COUNT(*) FROM storyboards WHERE task_id=?", (self.task_id,)).fetchone()[0]
        self.assertEqual(n, 24)
        nums = [r[0] for r in self.conn.execute(
            "SELECT shot_no FROM storyboards WHERE task_id=? ORDER BY shot_no", (self.task_id,))]
        self.assertEqual(nums, list(range(1, 25)), "分镜编号必须 1–24 连续")

    def test_25th_storyboard_rejected(self):
        insert_24_shots(self.conn, self.task_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO storyboards (task_id, shot_no, scene_text, created_at) VALUES (?,?,?,?)",
                (self.task_id, 25, "越界分镜", TS))

    def test_duplicate_shot_no_rejected(self):
        insert_24_shots(self.conn, self.task_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO storyboards (task_id, shot_no, scene_text, created_at) VALUES (?,?,?,?)",
                (self.task_id, 1, "重复编号", TS))

    def test_three_copy_variants_with_distinct_focus(self):
        for plan, focus in [(1, "hook"), (2, "emotion"), (3, "cta")]:
            self.conn.execute(
                "INSERT INTO copy_variants (task_id, plan_no, focus, focus_note, title, body, "
                "word_count, status, model_version, prompt_version, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (self.task_id, plan, focus, "侧重说明", f"标题{plan}", "正文", 380, "active",
                 "deepseek-chat@2026-10", "copy-writer.default@0.1.0", TS))
        n = self.conn.execute("SELECT COUNT(*) FROM copy_variants WHERE task_id=?", (self.task_id,)).fetchone()[0]
        self.assertEqual(n, 3)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO copy_variants (task_id, plan_no, focus, body, created_at) VALUES (?,?,?,?,?)",
                (self.task_id, 1, "hook", "重复套号", TS))

    def test_copy_variant_soft_delete_keeps_row(self):
        self.conn.execute(
            "INSERT INTO copy_variants (task_id, plan_no, focus, body, status, created_at) VALUES (?,?,?,?,?,?)",
            (self.task_id, 1, "hook", "正文", "active", TS))
        self.conn.execute("UPDATE copy_variants SET status='deleted' WHERE task_id=? AND plan_no=1", (self.task_id,))
        row = self.conn.execute(
            "SELECT status FROM copy_variants WHERE task_id=? AND plan_no=1", (self.task_id,)).fetchone()
        self.assertEqual(row[0], "deleted", "删除必须是软删，行仍在（便于留痕）")

    def test_selected_plan_must_be_1_to_3(self):
        self.conn.execute("UPDATE tasks SET selected_plan=3, selected_at=? WHERE id=?", (TS, self.task_id))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE tasks SET selected_plan=4 WHERE id=?", (self.task_id,))

    def test_word_range_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            insert_task(self.conn, self.topic_id, word_min=800, word_max=200)

    def test_content_type_enum_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            insert_task(self.conn, self.topic_id, content_type="随便写的类型")

    def test_topic_source_enum_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            insert_topic(self.conn, source="wechat")

    def test_task_requires_existing_topic(self):
        with self.assertRaises(sqlite3.IntegrityError):
            insert_task(self.conn, 999999)


class TestPipelineModel(unittest.TestCase):
    """④ 流水/产物/人工介入/指标：版本字段、失败原因、关口留痕。"""

    def setUp(self):
        self.conn = build_from_schema()
        self.tid = insert_task(self.conn, insert_topic(self.conn))

    def test_step_run_records_adapter_and_error_rule(self):
        self.conn.execute(
            "INSERT INTO step_runs (task_id, step_no, skill_id, status, adapter_used, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (self.tid, 1, "copy-writer", "ok", "llm.deepseek", TS))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO step_runs (task_id, step_no, skill_id, status, error, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (self.tid, 2, "copy-writer", "failed", "", TS))

    def test_artifact_requires_model_and_prompt_version(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO artifacts (task_id, kind, path, size_bytes, model_version, prompt_version, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (self.tid, "image", "workspace/topic-1/images/shot-01.png", 1024, "x", None, TS))

    def test_artifact_media_must_have_size(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO artifacts (task_id, kind, path, size_bytes, model_version, prompt_version, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (self.tid, "video", "workspace/topic-1/video/final.mp4", 0, "remotion@4", "none", TS))

    def test_artifact_registers_path_not_blob(self):
        """R-7-01：只登记路径与元信息（表里没有二进制列）。"""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(artifacts)")]
        for forbidden in ("data", "blob", "content", "bytes_content"):
            self.assertNotIn(forbidden, cols)

    def test_hitl_gate_enum_and_snapshot(self):
        self.conn.execute(
            "INSERT INTO hitl_events (task_id, gate, actor, action, snapshot_json, diff_json, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (self.tid, "gate1_select_copy", "yip", "confirm", '{"plan_no":2}', '{}', TS))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO hitl_events (task_id, gate, actor, action, created_at) VALUES (?,?,?,?,?)",
                (self.tid, "gate9_unknown", "yip", "confirm", TS))

    def test_metrics_need_period_and_collected_at(self):
        self.conn.execute(
            "INSERT INTO metrics (task_id, platform, metric_key, value, period_start, period_end, collected_at, source, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (self.tid, "抖音", "views", 1234, "2026-10-01", "2026-10-07", TS, "browser", TS))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO metrics (task_id, platform, metric_key, value, period_start, period_end, collected_at, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (self.tid, "抖音", "views", 1, "2026-10-01", "2026-10-07", None, TS))

    def test_metric_key_limited_to_three(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO metrics (task_id, platform, metric_key, value, period_start, period_end, collected_at, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (self.tid, "抖音", "shares", 1, "2026-10-01", "2026-10-07", TS, TS))

    def test_adapter_registry_fallback_order(self):
        self.conn.execute(
            "INSERT INTO adapter_registry (adapter_id, kind, provider, capabilities, needs_key, billable, "
            "failure_signals, fallback_order, enabled, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("image.flow", "image", "Flow", "文生图", 1, 0, "超时/额度用尽", 1, 1, TS))
        self.conn.execute(
            "INSERT INTO adapter_registry (adapter_id, kind, provider, capabilities, needs_key, billable, "
            "failure_signals, fallback_order, enabled, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("image.doubao", "image", "豆包", "文生图", 1, 0, "超时", 2, 1, TS))
        order = [r[0] for r in self.conn.execute(
            "SELECT adapter_id FROM adapter_registry WHERE kind='image' ORDER BY fallback_order")]
        self.assertEqual(order, ["image.flow", "image.doubao"], "降级顺序必须可排序")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO adapter_registry (adapter_id, kind, fallback_order, updated_at) VALUES (?,?,?,?)",
                ("image.flow", "image", 3, TS))

    def test_prompt_version_unique_per_key(self):
        self.conn.execute(
            "INSERT INTO prompt_versions (prompt_key, version, file_path, created_at) VALUES (?,?,?,?)",
            ("copy-writer.default", "0.1.0", "templates/prompts/copy-writer.default.md", TS))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO prompt_versions (prompt_key, version, file_path, created_at) VALUES (?,?,?,?)",
                ("copy-writer.default", "0.1.0", "templates/prompts/dup.md", TS))


class TestViews(unittest.TestCase):
    """⑤ 看板视图可用（控制台后续页面直接读视图）。"""

    def test_task_progress_view(self):
        conn = build_from_schema()
        tid = insert_task(conn, insert_topic(conn))
        conn.execute("INSERT INTO step_runs (task_id, step_no, skill_id, status, created_at) VALUES (?,?,?,?,?)",
                     (tid, 1, "copy-writer", "ok", TS))
        conn.execute("INSERT INTO step_runs (task_id, step_no, skill_id, status, error, created_at) VALUES (?,?,?,?,?,?)",
                     (tid, 2, "storyboard-builder", "failed", "分镜条数不足 24", TS))
        row = conn.execute("SELECT done_steps, failed_steps, last_step_no FROM v_task_progress WHERE task_id=?",
                           (tid,)).fetchone()
        self.assertEqual(tuple(row), (1, 1, 2))

    def test_pending_publish_view(self):
        conn = build_from_schema()
        tid = insert_task(conn, insert_topic(conn, title="待发布选题"), stage="publish", status="waiting_human")
        row = conn.execute("SELECT task_id, title, shots, videos FROM v_pending_publish").fetchone()
        self.assertEqual(row[0], tid)
        self.assertEqual(row[1], "待发布选题")
        self.assertEqual((row[2], row[3]), (0, 0))


class TestRealDatabaseFile(unittest.TestCase):
    """⑥ 走一遍真实建库脚本（--db 指向临时文件），确认脚本可用。"""

    def test_db_init_script(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db_file = os.path.join(tmp, "t.db")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "db_init.py"),
                                "--db", db_file, "--force"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            conn = sqlite3.connect(db_file)
            n = conn.execute("SELECT COUNT(*) FROM platform_templates").fetchone()[0]
            self.assertEqual(n, 4, "建库脚本应同时灌入 4 条平台模板")
            conn.close()


if __name__ == "__main__":
    print(__doc__)
    unittest.main(verbosity=2)
