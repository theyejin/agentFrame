#!/usr/bin/env python3
# 文件用途：WP-05 步骤 7 的模拟测试 —— 分发数据线端到端（热点采集 → 分类汇总表 → 文档同步 → 发布填写与红线自检 → 指标采集 → 复盘报告），全程离线，不联网不花钱。
# 对应需求：FLOW-6/7/8/9、R-7-01~R-7-05（热点/汇总/同步/发布红线）、R-8-14~R-8-16（指标口径/复盘/建议）、C-08/C-10（不得自动发布、发布授权必须真人）、Q-5/Q-13/Q-16/Q-19、R-L2-02（每步模拟测试通过再下一步）。
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
# 维护提示：改 publish_guard.py 的红线口径、metrics 的三项口径或 registry.json 的 browser/doc/metrics 链后，必须同步本测试。
"""分发数据线模拟测试。

运行：
    python3 tests/test_publish_line.py

复用视频线的 BaseCase（临时库 + 临时产出 + 一路跑到剪辑版），在其上把发布数据线跑到复盘。
全部通过 = WP-05 步骤 7 的完成门之一（另外两道门：structure_check 退出码 0、prompt-registry check 无问题）。
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SHARED = ROOT / ".dsh" / "skills" / "_shared"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(TESTS))

import db as dbm  # noqa: E402
import hotspots as hs  # noqa: E402
import metrics as mt  # noqa: E402
import publish_guard as pg  # noqa: E402
import recording as rec  # noqa: E402
from test_video_line import BaseCase, run_skill, SMALL, FPS  # noqa: E402

HOTSPOT_FIXTURE = "templates/mock/hotspot-source.v1.json"
METRICS_FIXTURE = "templates/mock/metrics.v1.json"
PERIOD = ("2026-10-05", "2026-10-11")


class PublishBaseCase(BaseCase):
    """在视频线 BaseCase 之上：再往前跑到「成片 + 封面 + 发布准备就绪」（stage=publish）。"""

    def to_publish_ready(self) -> int:
        task_id = self.to_edited_ready()
        r = run_skill("video-exporter", "--db", self.db, "--json", "export", "--task-id", str(task_id),
                      "--cover-at", "0.2")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("title-cover-prep", "--db", self.db, "--json", "prepare", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 0, r.stderr)
        return task_id

    # ---- 分发线的常用动作 ----
    def collect_hotspots(self, keyword: str = "打工人") -> dict:
        r = run_skill("hotspot-collector", "--db", self.db, "--json", "collect",
                      "--keyword", keyword, "--fixture", HOTSPOT_FIXTURE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def build_table(self, batch: str | None = None) -> dict:
        args = ["--db", self.db, "--json", "build"] + (["--batch", batch] if batch else ["--latest"])
        r = run_skill("table-builder", *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def collect_metrics(self, task_id: int, values: str = "播放量=1200,互动量=88,涨粉=12",
                        period: tuple[str, str] = PERIOD) -> dict:
        r = run_skill("metrics-collector", "--db", self.db, "--json", "collect", "--task-id", str(task_id),
                      "--values", values, "--period-start", period[0], "--period-end", period[1])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def metric_rows(self, task_id: int) -> list[dict]:
        return dbm.query("SELECT * FROM metrics WHERE task_id=?", (task_id,), self.db)

    def publish_rows(self, task_id: int) -> list[dict]:
        return dbm.query("SELECT * FROM publish_records WHERE task_id=? ORDER BY id", (task_id,), self.db)

    def task_status(self, task_id: int) -> str:
        return dbm.query_one("SELECT status FROM tasks WHERE id=?", (task_id,), self.db)["status"]


class TestHotspotCollector(PublishBaseCase):
    def test_collect_with_fixture_writes_batch_and_items(self):
        """离线夹具也能采出一批热点：批次表 + 条目表 + 清单文件三样都要有。"""
        info = self.collect_hotspots()
        self.assertEqual(info["count"], 8)
        self.assertEqual(info["collect_adapter"], "browser.local-fixture")
        self.assertEqual(info["classify_adapter"], "llm.mock")
        self.assertEqual(info["source"], "fixture")
        batch = dbm.query_one("SELECT * FROM hotspot_batches WHERE batch_key=?", (info["batch_key"],), self.db)
        self.assertIsNotNone(batch)
        rows = dbm.query("SELECT * FROM hotspot_items WHERE batch_id=?", (batch["id"],), self.db)
        self.assertEqual(len(rows), info["count"])
        self.assertTrue(all(r["title"].strip() for r in rows))
        self.assertTrue(all(r["category"] in hs.CATEGORIES for r in rows))
        self.assertEqual(sum(info["categories"].values()), info["count"])
        for rel in info["files"]:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_requires_keyword_or_keywords(self):
        r = run_skill("hotspot-collector", "--db", self.db, "collect", "--fixture", HOTSPOT_FIXTURE)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("关键词", r.stderr)

    def test_duplicate_batch_key_rejected(self):
        first = self.collect_hotspots()
        r = run_skill("hotspot-collector", "--db", self.db, "collect", "--keyword", "打工人",
                      "--fixture", HOTSPOT_FIXTURE, "--batch-key", first["batch_key"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("批次号已存在", r.stderr)

    def test_without_fixture_stops_at_human_adapter(self):
        """不给夹具时不联网瞎猜：浏览器链落到人工终点，退出 2 并说清缺什么。"""
        r = run_skill("hotspot-collector", "--db", self.db, "collect", "--keyword", "打工人")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("夹具", r.stderr + r.stdout)


class TestTableBuilder(PublishBaseCase):
    def test_build_writes_table_and_backfills_batch(self):
        info = self.collect_hotspots()
        table = self.build_table()
        self.assertEqual(table["batch_key"], info["batch_key"])
        self.assertEqual(table["count"], info["count"])
        md = ROOT / table["files"][0]
        csv = ROOT / table["files"][1]
        text = md.read_text(encoding="utf-8")
        self.assertIn("| 分类 | 条数 | 热度合计 | 热度均值 | 代表标题 |", text)
        self.assertIn("合计", text)
        self.assertEqual(table["table_path"], table["files"][0])
        self.assertTrue(csv.is_file())
        csv_text = csv.read_text(encoding="utf-8").strip()
        self.assertEqual(len(csv_text.splitlines()), table["count"] + 2)
        self.assertTrue(csv_text.startswith("分类,标题,热度,来源链接"))
        self.assertIn("| 分类 | 热度 | 标题 | 来源链接 |", text)
        batch = dbm.query_one("SELECT * FROM hotspot_batches WHERE batch_key=?", (info["batch_key"],), self.db)
        self.assertEqual(batch["table_path"], table["table_path"])

    def test_unknown_batch_exits_2(self):
        r = run_skill("table-builder", "--db", self.db, "build", "--batch", "nope")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("批次", r.stderr)

    def test_no_batch_at_all_exits_2(self):
        r = run_skill("table-builder", "--db", self.db, "build")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_category_filter_keeps_only_that_category(self):
        self.collect_hotspots()
        r = run_skill("table-builder", "--db", self.db, "--json", "build", "--latest",
                      "--category", "干货教程")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(info["categories"].get("情绪冲突", 0), 0)
        self.assertGreater(info["count"], 0)
        text = (ROOT / info["files"][0]).read_text(encoding="utf-8")
        self.assertIn("干货教程", text)


class TestFeishuSync(PublishBaseCase):
    def test_sync_degrades_to_local_export(self):
        """飞书 API 未接时走本地导出（Q-5 降级路径），并且要明说降级了。"""
        batch = self.collect_hotspots()
        self.build_table()
        r = run_skill("feishu-sync", "--db", self.db, "--json", "sync", "--batch", batch["batch_key"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(info["adapter_used"], "doc.local-export")
        self.assertTrue(info["degraded"])
        exported = Path(info["export_path"])
        self.assertTrue(exported.is_file())
        self.assertGreater(exported.stat().st_size, 0)
        self.assertEqual(exported.read_bytes(), (ROOT / info["source_file"]).read_bytes())
        row = dbm.query_one("SELECT * FROM hotspot_batches WHERE batch_key=?", (batch["batch_key"],), self.db)
        self.assertEqual(row["export_path"], info["export_path"])
        self.assertTrue(row["adapter_used"])

    def test_missing_file_exits_2(self):
        r = run_skill("feishu-sync", "--db", self.db, "sync", "--file", "workspace/nope.md")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_unknown_batch_exits_2(self):
        r = run_skill("feishu-sync", "--db", self.db, "sync", "--batch", "nope")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class TestBrowserPublisher(PublishBaseCase):
    def test_requires_final_video_and_cover(self):
        """没导出成片就不能准备发布：视频线与发布线的交接契约。"""
        task_id = self.to_shots_ready()
        r = run_skill("browser-publisher", "--db", self.db, "prepare", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("video", r.stderr)

    def test_prepare_creates_fill_plan_and_stops_before_publish(self):
        task_id = self.to_publish_ready()
        r = run_skill("browser-publisher", "--db", self.db, "--json", "prepare", "--task-id", str(task_id),
                      "--account-label", "主号")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        info = json.loads(r.stdout)
        self.assertFalse(info["submitted"])
        self.assertEqual(info["adapter_used"], "browser.fill-plan")
        plan = json.loads(Path(info["fill_plan"]).read_text(encoding="utf-8"))
        self.assertFalse(plan["submitted"])
        self.assertFalse(plan.get("auto_publish", False))
        self.assertTrue(plan.get("fields", {}).get("标题候选"))
        package = json.loads((ROOT / info["package_json"]).read_text(encoding="utf-8"))
        self.assertFalse(package["submitted"])
        art = self.artifact(task_id, "publish_package", "package")
        self.assertIsNotNone(art, "没有登记 publish_package 产物")
        rows = self.publish_rows(task_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "filled")
        self.assertTrue(rows[0]["filled_at"])
        self.assertEqual(self.task_status(task_id), "waiting_human")
        self.assertEqual(info["gate3_event"]["gate"], "gate3_publish_auth")

    def test_status_reports_pending_gate(self):
        task_id = self.to_publish_ready()
        self.assertEqual(run_skill("browser-publisher", "--db", self.db, "prepare",
                                   "--task-id", str(task_id)).returncode, 0)
        r = run_skill("browser-publisher", "--db", self.db, "--json", "status", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertFalse(info.get("published", False))
        self.assertIn("waiting_human", json.dumps(info, ensure_ascii=False))

    def test_mark_published_requires_actor(self):
        task_id = self.to_publish_ready()
        run_skill("browser-publisher", "--db", self.db, "prepare", "--task-id", str(task_id))
        r = run_skill("browser-publisher", "--db", self.db, "mark-published", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_mark_published_records_url_and_authorizes_gate3(self):
        task_id = self.to_publish_ready()
        run_skill("browser-publisher", "--db", self.db, "prepare", "--task-id", str(task_id))
        r = run_skill("browser-publisher", "--db", self.db, "--json", "mark-published", "--task-id", str(task_id),
                      "--actor", "运营小李", "--url", "https://example.com/v/1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = self.publish_rows(task_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "published")
        self.assertEqual(rows[0]["publish_url"], "https://example.com/v/1")
        self.assertEqual(rows[0]["operator"], "运营小李")
        self.assertTrue(rows[0]["published_at"])
        event = dbm.query_one("SELECT * FROM hitl_events WHERE task_id=? AND gate='gate3_publish_auth'"
                              " ORDER BY id DESC LIMIT 1", (task_id,), self.db)
        self.assertEqual(event["action"], "confirm")
        self.assertEqual(event["actor"], "运营小李")


class TestPublishGuard(PublishBaseCase):
    def guard(self, task_id: int, *extra: str) -> subprocess.CompletedProcess:
        return run_skill("publish-guard", "--db", self.db, "--json", "check", "--task-id", str(task_id), *extra)

    def test_check_passes_while_waiting_for_human(self):
        task_id = self.to_publish_ready()
        run_skill("browser-publisher", "--db", self.db, "prepare", "--task-id", str(task_id))
        r = self.guard(task_id)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        info = json.loads(r.stdout)
        self.assertTrue(info["ok"])
        self.assertFalse(info["gate3_authorized"])
        self.assertIn("待人工授权", info["gate3_note"])

    def test_live_blocks_without_gate3_authorization(self):
        """C-10：没人授权就不能按「要发布」的标准过。"""
        task_id = self.to_publish_ready()
        run_skill("browser-publisher", "--db", self.db, "prepare", "--task-id", str(task_id))
        r = self.guard(task_id, "--live")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        info = json.loads(r.stdout)
        self.assertTrue(info["blocked"])
        self.assertTrue(any("关口③" in p for p in info["problems"]))

    def test_live_passes_after_human_authorization(self):
        task_id = self.to_publish_ready()
        run_skill("browser-publisher", "--db", self.db, "prepare", "--task-id", str(task_id))
        run_skill("browser-publisher", "--db", self.db, "mark-published", "--task-id", str(task_id),
                  "--actor", "运营小李", "--url", "https://example.com/v/9")
        r = self.guard(task_id, "--live")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["gate3_authorized"])

    def test_missing_package_exits_2(self):
        task_id = self.to_publish_ready()
        r = self.guard(task_id)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("prepare", r.stderr)

    def test_detects_auto_publish_intent(self):
        """C-08：谁把 auto_publish 打开都要被拦下。"""
        task_id = self.to_publish_ready()
        r = run_skill("browser-publisher", "--db", self.db, "--json", "prepare", "--task-id", str(task_id))
        package_path = ROOT / json.loads(r.stdout)["package_json"]
        package = json.loads(package_path.read_text(encoding="utf-8"))
        package["auto_publish"] = True
        tampered = self.tmp / "tampered.json"
        tampered.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        r = self.guard(task_id, "--package", str(tampered))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        info = json.loads(r.stdout)
        self.assertTrue(info["blocked"])
        self.assertTrue(any("C-08" in p for p in info["problems"]))

    def test_guard_does_not_touch_state(self):
        task_id = self.to_publish_ready()
        run_skill("browser-publisher", "--db", self.db, "prepare", "--task-id", str(task_id))
        before = (self.task_status(task_id), len(self.publish_rows(task_id)))
        self.guard(task_id)
        self.guard(task_id, "--live")
        after = (self.task_status(task_id), len(self.publish_rows(task_id)))
        self.assertEqual(before, after)


class TestMetricsCollector(PublishBaseCase):
    def test_manual_values_are_written_with_period(self):
        task_id = self.to_publish_ready()
        info = self.collect_metrics(task_id)
        self.assertEqual(info["adapter_used"], "human")
        self.assertEqual(info["rows_written"], 3)
        self.assertEqual(info["totals"]["views"], 1200.0)
        self.assertEqual(info["totals"]["engagements"], 88.0)
        self.assertEqual(info["totals"]["follower_gain"], 12.0)
        self.assertEqual(info["stage"], "metrics")
        rows = self.metric_rows(task_id)
        self.assertEqual({r["metric_key"] for r in rows}, {"views", "engagements", "follower_gain"})
        self.assertTrue(all(r["period_start"] == PERIOD[0] and r["period_end"] == PERIOD[1] for r in rows))
        self.assertTrue(all(r["source"] == "manual" for r in rows))
        art = self.artifact(task_id, "table", "metrics")
        self.assertIsNotNone(art, "没有登记 metrics 产物")
        for rel in info["files"]:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_same_period_is_updated_not_duplicated(self):
        """同一期同一平台同一指标再采一次是更新，不是加一行（否则复盘会算两遍）。"""
        task_id = self.to_publish_ready()
        self.collect_metrics(task_id)
        info = self.collect_metrics(task_id, values="播放量=2000,互动量=100,涨粉=15")
        self.assertEqual(len(self.metric_rows(task_id)), 3)
        self.assertEqual(info["totals"]["views"], 2000.0)
        views = dbm.query_one("SELECT value FROM metrics WHERE task_id=? AND metric_key='views'",
                              (task_id,), self.db)
        self.assertEqual(views["value"], 2000.0)

    def test_missing_period_exits_2(self):
        task_id = self.to_publish_ready()
        r = run_skill("metrics-collector", "--db", self.db, "collect", "--task-id", str(task_id),
                      "--values", "播放量=1,互动量=1,涨粉=1")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("周期", r.stderr)

    def test_unknown_metric_key_exits_2(self):
        task_id = self.to_publish_ready()
        r = run_skill("metrics-collector", "--db", self.db, "collect", "--task-id", str(task_id),
                      "--values", "粉丝量=5", "--period-start", PERIOD[0], "--period-end", PERIOD[1])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_partial_needs_explicit_flag(self):
        task_id = self.to_publish_ready()
        base = ["--task-id", str(task_id), "--period-start", PERIOD[0], "--period-end", PERIOD[1]]
        r = run_skill("metrics-collector", "--db", self.db, "collect", *base, "--values", "播放量=5")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        r = run_skill("metrics-collector", "--db", self.db, "collect", *base, "--values", "播放量=5",
                      "--allow-partial")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.metric_rows(task_id)), 1)

    def test_fixture_uses_metrics_chain(self):
        task_id = self.to_publish_ready()
        r = run_skill("metrics-collector", "--db", self.db, "--json", "collect", "--task-id", str(task_id),
                      "--fixture", METRICS_FIXTURE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(info["adapter_used"], "metrics.local-fixture")
        self.assertEqual(info["records"], 2)
        self.assertEqual(info["rows_written"], 6)
        self.assertEqual(sorted(info["by_platform"]), ["小红书", "抖音"])


class TestReviewReporter(PublishBaseCase):
    def test_requires_metrics_first(self):
        task_id = self.to_publish_ready()
        r = run_skill("review-reporter", "--db", self.db, "report", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("指标", r.stderr)

    def test_report_generated_offline(self):
        task_id = self.to_publish_ready()
        self.collect_metrics(task_id)
        r = run_skill("review-reporter", "--db", self.db, "--json", "report", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(info["adapter_used"], "llm.mock")
        self.assertEqual(info["prompt_version"], "v1")
        self.assertGreaterEqual(info["report_chars"], 200)
        md = (ROOT / info["files"][0]).read_text(encoding="utf-8")
        body = json.loads((ROOT / info["files"][1]).read_text(encoding="utf-8"))
        self.assertIn("建议", body["report"])
        self.assertIn("## 复盘与建议", md)
        self.assertIn("2026-10-05", md)
        self.assertIn("不自动改提示词", body["note"])
        art = self.artifact(task_id, "report", "review")
        self.assertIsNotNone(art, "没有登记 review 报告产物")
        self.assertEqual(art["prompt_version"], "v1")
        self.assertEqual(self.task_status(task_id), "running")
        stage = dbm.query_one("SELECT stage FROM tasks WHERE id=?", (task_id,), self.db)["stage"]
        self.assertEqual(stage, "review")


class TestSharedLibraries(PublishBaseCase):
    """共享层单测：口径与红线都在库里，不该只靠命令行行为间接验证。"""

    def test_hotspot_parsing_and_aggregation(self):
        text = ("1. 打工人春节返乡 | 情绪 | 9800 | https://example.com/a\n"
                "2. 三招拆解爆款标题 | 干货 | 7600 | https://example.com/b\n"
                "3. 某综艺名场面 | 观点 | 15200 | https://example.com/c\n")
        items = hs.parse_items(text)
        self.assertEqual([i["title"] for i in items], ["打工人春节返乡", "三招拆解爆款标题", "某综艺名场面"])
        self.assertEqual([i["category"] for i in items], ["情绪冲突", "干货教程", "热点观点"])
        self.assertEqual([i["heat"] for i in items], [9800.0, 7600.0, 15200.0])
        self.assertEqual(hs.check_items(items), [])
        agg = hs.aggregate(items)
        self.assertEqual(agg["合计"]["count"], 3)
        self.assertEqual(agg["合计"]["heat_total"], 32600.0)
        self.assertEqual(agg["情绪冲突"]["top"], ["打工人春节返乡"])
        self.assertIn("| 分类 | 条数 | 热度合计 | 热度均值 | 代表标题 |", hs.summary_table(agg)
                      if hasattr(hs, "summary_table") else hs.render_summary(agg))
        self.assertIn("| 分类 | 热度 | 标题 | 来源链接 |", hs.render_table(items))
        self.assertEqual(hs.check_items([{"title": "", "category": "情绪冲突", "heat": 1.0}]),
                         ["第 1 条标题为空"])
        self.assertEqual(hs.normalize_category("情绪"), "情绪冲突")
        self.assertEqual(hs.normalize_category("没见过的类"), "其他")

    def test_metrics_parsing_and_validation(self):
        values = mt.parse_values("播放=10,互动量=2,涨粉=1")
        self.assertEqual(values, {"views": 10.0, "engagements": 2.0, "follower_gain": 1.0})
        self.assertEqual(mt.check_values(values), [])
        self.assertTrue(any("缺" in p for p in mt.check_values({"views": 1.0})))
        with self.assertRaises(mt.MetricsError):
            mt.parse_values("粉丝量=5")
        with self.assertRaises(mt.MetricsError):
            mt.parse_values("播放量=-1")

    def test_publish_guard_red_lines(self):
        pkg = pg.build_package(task_id=1, platform="抖音", video_path="workspace/v.mp4",
                               cover_path="workspace/c.png",
                               prep={"titles": ["正常标题"], "tags": ["a", "b"], "cover": "封面"},
                               package_dir="workspace/p", submit=True)
        result = pg.check_package(pkg, exists=lambda p: True)
        self.assertFalse(result["ok"])
        self.assertTrue(any("C-08" in p for p in result["problems"]))
        result = pg.check_package(pkg, gate3_authorized=False, live=True, exists=lambda p: True)
        self.assertTrue(any("关口③" in p for p in result["problems"]))


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
