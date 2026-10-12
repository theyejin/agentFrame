#!/usr/bin/env python3
# 文件用途：运营控制台与搭建过程报告页的模拟测试 —— 数据层聚合、build-log 生成、本地服务接口与白名单、页面约定。
# 对应需求：R-L2-05（过程日志与报告页）、R-L2-06（build-log 在根目录且数据可追溯）、R-L3-01~05（本地可访问、只调本地脚本、不持有凭据）、AC-3、Q-6。
# 维护提示：新增控制台页面或新增白名单 skill 时，本文件的 TestConsolePages / TestServeDashboard 要同步补断言。

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / ".dsh" / "skills" / "_shared"
sys.path.insert(0, str(SHARED))

import console as cs  # noqa: E402
import db as dbm  # noqa: E402
import recording as rec  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("serve_dashboard", ROOT / "scripts" / "serve_dashboard.py")
serve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serve)


def run_script(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *[str(a) for a in args]], capture_output=True, text=True, cwd=str(cwd or ROOT))


class DashboardBaseCase(unittest.TestCase):
    """一份临时库 + 一份临时日志目录，控制台相关测试都在里面跑，不碰仓库的 db/app.db 与 logs/。"""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="dashboard-"))
        self.db = self.tmp / "app.db"
        run_script(ROOT / "scripts" / "db_init.py", "--db", self.db, "--force")
        run_script(ROOT / "scripts" / "seed_adapters.py", "--db", self.db)
        self.logs = self.tmp / "logs"
        self.logs.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_task(self, *, stage: str = "copy", status: str = "running", platform: str = "抖音") -> int:
        topic_id = rec.create_topic("测试选题·控制台", keywords="打工人,返乡", path=str(self.db))
        task_id = rec.create_task(topic_id, stage=stage, target_platform=platform, prompt="写一条返乡情绪",
                                  path=str(self.db))
        if status != "pending":
            rec.update_task(task_id, status=status, path=str(self.db))
        return task_id

    def insert_metric(self, task_id: int, key: str, value: float, *, platform: str = "抖音",
                      start: str = "2026-10-05", end: str = "2026-10-11", source: str = "manual") -> None:
        dbm.execute(
            "INSERT INTO metrics (task_id, platform, metric_key, value, period_start, period_end,"
            " collected_at, source, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (task_id, platform, key, value, start, end, dbm.now_iso(), source, dbm.now_iso()), str(self.db))


class TestConsoleData(DashboardBaseCase):
    """数据层：整包快照、看板、待办、发布队列、指标、热点、轨迹、文案卡、产物正文。"""

    def test_snapshot_shape(self) -> None:
        self.make_task()
        snap = cs.snapshot(db=str(self.db), logs_dir=str(self.logs))
        for key in ("generated_at", "db", "tasks", "stage_board", "gate_todos", "publish_queue",
                    "metrics", "metrics_trend", "hotspots", "logs"):
            self.assertIn(key, snap)
        self.assertEqual(len(snap["tasks"]), 1)
        self.assertEqual(len(snap["stage_board"]), len(cs.STAGE_LABELS))
        self.assertEqual(snap["logs"]["count"], 0)

    def test_tasks_overview_labels_and_counts(self) -> None:
        task_id = self.make_task()
        row = cs.tasks_overview(db=str(self.db))[0]
        self.assertEqual(row["id"], task_id)
        self.assertEqual(row["stage_label"], "文案")
        self.assertEqual(row["status_label"], "进行中")
        self.assertEqual(row["gate"], "gate1_select_copy")
        self.assertEqual(row["topic_title"], "测试选题·控制台")
        self.assertEqual(row["step_count"], 0)

    def test_tasks_overview_filters(self) -> None:
        self.make_task(stage="copy")
        other = self.make_task(stage="video", platform="小红书")
        self.assertEqual([r["id"] for r in cs.tasks_overview(stage="video", db=str(self.db))], [other])
        self.assertEqual(cs.tasks_overview(status="blocked", db=str(self.db)), [])
        self.assertEqual([r["id"] for r in cs.tasks_overview(keyword="返乡", db=str(self.db))], [other, other - 1])

    def test_stage_board_counts(self) -> None:
        self.make_task(stage="copy")
        self.make_task(stage="copy", status="waiting_human")
        board = {row["stage"]: row for row in cs.stage_board(db=str(self.db))}
        self.assertEqual(board["copy"]["total"], 2)
        self.assertEqual(board["copy"]["waiting_human"], 1)
        self.assertEqual(board["review"]["total"], 0)

    def test_gate_todos_appear_then_clear(self) -> None:
        task_id = self.make_task()
        self.assertEqual([t["task_id"] for t in cs.gate_todos(db=str(self.db))], [])
        run_script(ROOT / ".dsh" / "skills" / "hitl-gate" / "run.py", "--db", self.db,
                   "open", "--task-id", task_id, "--gate", "gate1_select_copy")
        todos = cs.gate_todos(db=str(self.db))
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["gate_label"], "关口① 选定文案")
        # 关口① 是「三选一」：库里得真有候选文案，resolve 才认得 plan-no
        for no in (1, 2, 3):
            dbm.execute("INSERT INTO copy_variants (task_id, plan_no, focus, title, body, word_count,"
                        " created_at) VALUES (?,?,?,?,?,?,?)",
                        (task_id, no, ("hook", "emotion", "cta")[no - 1], f"标题{no}", "正文", 320,
                         dbm.now_iso()), str(self.db))
        proc = run_script(ROOT / ".dsh" / "skills" / "hitl-gate" / "run.py", "--db", self.db,
                          "resolve", "--task-id", task_id, "--gate", "gate1_select_copy", "--action", "confirm",
                          "--actor", "运营小李", "--plan-no", "1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(cs.gate_todos(db=str(self.db)), [])

    def test_publish_queue_and_no_auto_publish(self) -> None:
        task_id = self.make_task(stage="publish", status="waiting_human")
        dbm.execute("INSERT INTO publish_records (task_id, platform, account_label, package_path, video_path,"
                    " status, operator, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (task_id, "抖音", "主号", "workspace/topic-1/publish/package-x/package.json",
                     "workspace/topic-1/video/final.mp4", "filled", "运营小李", dbm.now_iso()), str(self.db))
        dbm.execute("INSERT INTO hitl_events (task_id, gate, actor, action, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (task_id, "gate3_publish_auth", "运营小李", "confirm", dbm.now_iso()), str(self.db))
        rows = cs.publish_queue(db=str(self.db))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_label"], "已填写（等授权）")
        self.assertFalse(rows[0]["can_auto_publish"])
        self.assertIsNotNone(rows[0]["last_auth_at"])

    def test_metrics_summary_and_trend(self) -> None:
        task_id = self.make_task(stage="metrics")
        self.insert_metric(task_id, "views", 1000)
        self.insert_metric(task_id, "engagements", 50)
        self.insert_metric(task_id, "follower_gain", 8)
        self.insert_metric(task_id, "views", 2000, platform="小红书", start="2026-10-12", end="2026-10-18")
        summary = cs.metrics_summary(db=str(self.db))
        self.assertEqual(summary["totals"]["views"], 3000.0)
        self.assertEqual(summary["totals"]["engagements"], 50.0)
        self.assertEqual(summary["totals"]["engagement_rate"], round(50 / 3000 * 100, 2))
        trend = cs.metrics_trend(db=str(self.db))
        self.assertEqual(len(trend), 2)
        self.assertEqual(trend[0]["views"], 1000.0)
        self.assertEqual(trend[0]["platforms"], ["抖音"])
        self.assertEqual(trend[1]["engagement_rate"], 0.0)

    def test_metrics_summary_reads_empty_db_gracefully(self) -> None:
        summary = cs.metrics_summary(db=str(self.db))
        self.assertEqual(summary["rows"], [])
        self.assertEqual(summary["totals"]["views"], 0)

    def test_hotspots_overview(self) -> None:
        dbm.execute("INSERT INTO hotspot_batches (batch_key, keyword, source, items_count, collected_at,"
                    " created_at) VALUES (?,?,?,?,?,?)",
                    ("hot-1", "打工人 春节", "fixture", 2, dbm.now_iso(), dbm.now_iso()), str(self.db))
        batch_id = dbm.query_one("SELECT id FROM hotspot_batches WHERE batch_key = 'hot-1'", (), str(self.db))["id"]
        dbm.execute("INSERT INTO hotspot_items (batch_id, title, category, heat, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (batch_id, "打工人返乡", "情绪冲突", 900.0, dbm.now_iso()), str(self.db))
        dbm.execute("INSERT INTO hotspot_items (batch_id, title, category, heat, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (batch_id, "三招拆解标题", "干货教程", 300.0, dbm.now_iso()), str(self.db))
        data = cs.hotspots_overview(db=str(self.db))
        self.assertEqual(len(data["batches"]), 1)
        self.assertEqual({row["category"] for row in data["categories"]}, {"情绪冲突", "干货教程"})
        self.assertEqual(sum(row["n"] for row in data["categories"]), 2)

    def test_task_trace(self) -> None:
        task_id = self.make_task()
        rec.record_step(task_id, "copy-writer", "ok", adapter_used="llm.mock", path=str(self.db))
        trace = cs.task_trace(task_id, db=str(self.db))
        for key in ("task", "steps", "artifacts", "gates", "metrics", "publishes"):
            self.assertIn(key, trace)
        self.assertEqual(len(trace["steps"]), 1)
        self.assertEqual(trace["task"]["topic_title"], "测试选题·控制台")

    def test_task_trace_unknown_task(self) -> None:
        with self.assertRaises(cs.ConsoleError):
            cs.task_trace(999, db=str(self.db))

    def test_copy_plans_labels(self) -> None:
        task_id = self.make_task()
        for no, focus in ((1, "hook"), (2, "emotion"), (3, "cta")):
            dbm.execute("INSERT INTO copy_variants (task_id, plan_no, focus, title, body, word_count,"
                        " created_at) VALUES (?,?,?,?,?,?,?)",
                        (task_id, no, focus, f"标题{no}", "正文", 320, dbm.now_iso()), str(self.db))
        data = cs.copy_plans(task_id, db=str(self.db))
        self.assertEqual([p["focus_label"] for p in data["plans"]], ["开头钩子", "情绪强度", "行动号召"])
        self.assertIsNone(data["selected_plan"])

    def test_artifact_texts_reads_text_and_flags_binary(self) -> None:
        task_id = self.make_task()
        md = self.tmp / "plan.md"
        md.write_text("# 方案 1\n正文", encoding="utf-8")
        img = self.tmp / "shot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        rec.record_artifact(task_id, "copy", str(md), model_version="mock-copy-v1",
                            prompt_version="v1", meta={"role": "plan-1"}, path=str(self.db))
        rec.record_artifact(task_id, "image", str(img), model_version="local", prompt_version="none",
                            meta={"role": "shot"}, path=str(self.db))
        data = cs.artifact_texts(task_id, db=str(self.db))
        self.assertEqual(len(data["artifacts"]), 2)
        text_item = [a for a in data["artifacts"] if a["path"].endswith(".md")][0]
        self.assertIn("方案 1", text_item["text"])
        self.assertFalse(text_item["binary"])
        image_item = [a for a in data["artifacts"] if a["path"].endswith(".png")][0]
        self.assertTrue(image_item["binary"])
        self.assertEqual(image_item["text"], "")
        self.assertEqual(len(cs.artifact_texts(task_id, role="plan-1", db=str(self.db))["artifacts"]), 1)


class TestBuildLog(DashboardBaseCase):
    """build-log：日志读取（坏行不致命）与根目录产物生成（数据可追溯）。"""

    def write_log(self, name: str, rows: list[dict]) -> None:
        (self.logs / name).write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                                     encoding="utf-8")

    def test_logs_entries_sorted_and_skips_bad_lines(self) -> None:
        self.write_log("2026-10-11.jsonl", [{"ts": "2026-10-11T09:00:00+08:00", "step": "WP-01", "action": "第一步"}])
        (self.logs / "2026-10-12.jsonl").write_text(
            json.dumps({"ts": "2026-10-12T10:00:00+08:00", "step": "WP-05-8", "actor": "agent",
                        "skill": "dashboard", "action": "写控制台", "result": "ok", "note": "备注"}, ensure_ascii=False)
            + "\n{坏行}\n", encoding="utf-8")
        entries = cs.logs_entries(self.logs)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["date"], "2026-10-12")
        self.assertEqual(entries[0]["title"], "写控制台")
        self.assertEqual(entries[1]["step"], "WP-01")

    def test_render_build_log_writes_html_and_data(self) -> None:
        self.write_log("2026-10-12.jsonl", [{"ts": "2026-10-12T10:00:00+08:00", "step": "WP-05-8",
                                             "action": "写控制台", "result": "ok"}])
        out = cs.render_build_log(cs.logs_entries(self.logs), root=self.tmp)
        data_path = Path(out["data"])
        html_path = Path(out["html"])
        self.assertTrue(data_path.is_file() and html_path.is_file())
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["generator"], "scripts/build_log_report.py")
        self.assertEqual(payload["dates"][0]["date"], "2026-10-12")
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("搭建过程记录", html)
        self.assertIn("写控制台", html)  # 数据内联进 HTML，file:// 也能打开

    def test_repo_root_build_log_is_current(self) -> None:
        html = (ROOT / "build-log.html")
        data = (ROOT / "build-log.data.json")
        self.assertTrue(html.is_file(), "仓库根目录应有 build-log.html")
        self.assertTrue(data.is_file(), "仓库根目录应有 build-log.data.json")
        payload = json.loads(data.read_text(encoding="utf-8"))
        self.assertGreater(payload["total"], 0)
        self.assertEqual(payload["generator"], "scripts/build_log_report.py")

    def test_build_log_script_cli(self) -> None:
        proc = run_script(ROOT / "scripts" / "build_log_report.py", "--logs-dir", self.logs,
                          "--root", self.tmp, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertIn("total", payload)
        self.assertTrue((self.tmp / "build-log.html").is_file())


class TestServeDashboard(DashboardBaseCase):
    """本地服务：白名单、命令行拼装、HTTP 接口与静态页面、控制台动作留痕。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server_tmp = Path(tempfile.mkdtemp(prefix="dashboard-serve-"))
        cls.server_db = cls.server_tmp / "app.db"
        cls.logs_dir = cls.server_tmp / "logs"
        cls.logs_dir.mkdir()
        serve.LOGS_DIR = cls.logs_dir  # 控制台动作写进临时目录，别污染仓库 logs/
        run_script(ROOT / "scripts" / "db_init.py", "--db", cls.server_db, "--force")
        run_script(ROOT / "scripts" / "seed_adapters.py", "--db", cls.server_db)
        topic_id = rec.create_topic("服务测试选题", path=str(cls.server_db))
        cls.task_id = rec.create_task(topic_id, target_platform="抖音", prompt="测试", path=str(cls.server_db))
        serve.Handler.db = str(cls.server_db)
        cls.httpd = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.server_tmp, ignore_errors=True)

    def get(self, path: str):
        # 路径里可能有中文，URL 里要转义；但 query 分隔符不能被转义
        url = self.base + urllib.parse.quote(path, safe="/?&=%")
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # 404/400 也是预期结果（页面要给出可读错误）
            return exc.code, exc.read().decode("utf-8")

    def post(self, path: str, payload: dict):
        request = urllib.request.Request(self.base + path, method="POST",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_check_mode_reports_summary(self) -> None:
        proc = run_script(ROOT / "scripts" / "serve_dashboard.py", "--db", self.db, "--check", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("tasks", payload)

    def test_health_and_snapshot(self) -> None:
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        health = json.loads(body)
        self.assertTrue(health["ok"])
        self.assertIn("copy-writer", health["whitelist"])
        status, body = self.get("/api/snapshot")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(json.loads(body)["tasks"]), 1)

    def test_task_and_copy_endpoints(self) -> None:
        status, body = self.get(f"/api/task?id={self.task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["task"]["id"], self.task_id)
        status, body = self.get(f"/api/copy?id={self.task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["plans"], [])
        status, body = self.get("/api/task?id=99999")
        self.assertEqual(status, 400)
        self.assertIn("任务不存在", json.loads(body)["error"])

    def test_static_pages_served(self) -> None:
        for path in ("/", "/index.html", "/assets/app.js", "/assets/style.css",
                     "/pages/tasks.html", "/pages/copy.html", "/pages/publish.html",
                     "/pages/metrics.html", "/build-log.html"):
            status, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body.strip(), path)
        status, body = self.get("/pages/没有这个页面.html")
        self.assertEqual(status, 404)

    def test_path_traversal_blocked(self) -> None:
        status, _ = self.get("/../../etc/passwd")
        self.assertEqual(status, 404)

    def test_whitelist_rejects_unknown_skill_and_action(self) -> None:
        status, body = self.post("/api/run", {"skill": "rm", "action": "-rf", "args": ["/"]})
        self.assertEqual(status, 400)
        self.assertIn("白名单", body["error"])
        status, body = self.post("/api/run", {"skill": "copy-writer", "action": "explode", "args": []})
        self.assertEqual(status, 400)
        self.assertIn("不支持子命令", body["error"])

    def test_forbidden_args_rejected(self) -> None:
        status, body = self.post("/api/run", {"skill": "copy-writer", "action": "generate",
                                              "args": ["--task-id", "1", "--db", "/tmp/other.db"]})
        self.assertEqual(status, 400)
        self.assertIn("不允许", body["error"])
        status, body = self.post("/api/run", {"skill": "copy-writer", "action": "generate",
                                              "args": ["--task-id", "1", "--allow-paid"]})
        self.assertEqual(status, 400)

    def test_build_command_shape(self) -> None:
        command = serve.build_command("copy-writer", "generate", ["--task-id", "7"], self.db)
        self.assertEqual(command[0], PY)
        self.assertIn("--db", command)
        self.assertEqual(command[-1], "--json")
        self.assertLess(command.index("--db"), command.index("generate"))

    def test_run_whitelisted_skill_writes_log(self) -> None:
        status, body = self.post("/api/run", {"skill": "artifact-recorder", "action": "list",
                                              "args": ["--task-id", str(self.task_id)]})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["json"])
        day = datetime.now(serve.CST).strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{day}.jsonl"
        self.assertTrue(log_file.is_file())
        rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(any(row.get("step") == "L3-console" and row.get("skill") == "artifact-recorder"
                            for row in rows))

    def test_run_returning_failure_is_reported(self) -> None:
        status, body = self.post("/api/run", {"skill": "copy-writer", "action": "generate",
                                              "args": ["--task-id", "99999"]})
        self.assertEqual(status, 400)
        self.assertEqual(body["returncode"], 2)

    def test_unknown_api_endpoint(self) -> None:
        status, body = self.post("/api/nope", {})
        self.assertEqual(status, 404)
        self.assertIn("没有这个接口", body["error"])


class TestConsolePages(unittest.TestCase):
    """页面约定：区块注释（R-L2-08）、页面互相可达（R-L3-01/03）、不持有凭据（R-L3-05）。"""

    PAGES = ["dashboard/index.html", "dashboard/pages/tasks.html", "dashboard/pages/copy.html",
             "dashboard/pages/publish.html", "dashboard/pages/metrics.html"]

    def test_pages_have_required_header_comments(self) -> None:
        for rel in self.PAGES:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("<!-- 文件用途：", text, rel)
            self.assertIn("对应需求：", text, rel)
            self.assertIn("维护提示：", text, rel)

    def test_pages_inline_scripts_parse(self) -> None:
        """页面渲染全靠内联脚本，语法错会让整页空白（曾发生：tasks.html 少一个括号）——用 node --check 守住。"""
        node = shutil.which("node")
        if not node:
            self.skipTest("本机没有 node，跳过语法检查")
        for rel in self.PAGES + ["dashboard/assets/app.js"]:
            text = (ROOT / rel).read_text(encoding="utf-8")
            if rel.endswith(".html"):
                sources = re.findall(r"<script>(.*?)</script>", text, re.S)
                self.assertTrue(sources, f"{rel} 没有内联脚本")
                code = "\n".join(sources)
            else:
                code = text
            with tempfile.TemporaryDirectory() as tmp:
                js = Path(tmp) / "check.js"
                js.write_text(code, encoding="utf-8")
                proc = subprocess.run([node, "--check", str(js)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{rel} 脚本语法错误：{proc.stderr.strip()[:300]}")

    def test_pages_do_not_hold_credentials(self) -> None:
        for rel in self.PAGES + ["dashboard/assets/app.js"]:
            text = (ROOT / rel).read_text(encoding="utf-8").lower()
            for bad in ("password", "passwd", "cookie", "secret", "token=", "authorization:"):
                self.assertNotIn(bad, text, f"{rel} 不应出现 {bad}（R-L3-05：控制台不持有凭据）")

    def test_pages_are_reachable_from_index(self) -> None:
        text = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
        for rel in ("pages/tasks.html", "pages/copy.html", "pages/publish.html", "pages/metrics.html"):
            self.assertIn(rel, text, f"首页应能走到 {rel}")
        self.assertIn("../build-log.html", text)

    def test_readme_documents_fields_flow_and_rationale(self) -> None:
        text = (ROOT / "dashboard/README.md").read_text(encoding="utf-8")
        for section in ("页面与字段说明", "页面流转路径", "设计选择理由", "怎么本地打开"):
            self.assertIn(section, text)
        for field in ("待人工决议", "发布队列", "互动率", "填写状态"):
            self.assertIn(field, text)

    def test_console_data_layer_is_read_only(self) -> None:
        source = (ROOT / ".dsh" / "skills" / "_shared" / "console.py").read_text(encoding="utf-8")
        for bad in ("INSERT", "UPDATE ", "DELETE", "DROP"):
            self.assertNotIn(bad, source, f"控制台数据层不应有写操作：{bad}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
