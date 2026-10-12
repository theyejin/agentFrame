#!/usr/bin/env python3
# 文件用途：WP-05 步骤 9 的端到端模拟测试 —— 一条选题从派单到复盘全程离线跑通，并逐条对照 AC-1~AC-7 留证。
# 对应需求：AC-1~AC-7（验收标准）、AC-5 / R-L2-02（每步模拟测试通过再下一步）、R-L1-18（交接契约）、C-08 / C-10（不自动发布、关口③ 授权必须真人）、§8.3（三类人工介入）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
# 维护提示：本文件把整条链路真跑一遍（十几秒），改任一线 skill 的入口、产物口径或关口顺序后必须同步本测试；验收结论另见 docs/acceptance-report.md。

"""端到端模拟测试（验收：AC-1~AC-7）。

运行：
    python3 tests/test_e2e.py

整条链路只在 setUpClass 里跑一次，各用例共享同一次运行的观测结果，
既保证「一条真实选题端到端产出」是真实发生过的，也避免重复跑几十秒。
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / ".dsh" / "skills" / "_shared"))

from test_video_line import FPS, PY, SMALL, run_skill  # noqa: E402
from test_publish_line import PERIOD  # noqa: E402

import db as dbm  # noqa: E402
import recording as rec  # noqa: E402
import publish_guard as pg  # noqa: E402

LOGS_DIR = ROOT / "logs"


def rows(db: str, sql: str, params=()) -> list[dict]:
    return dbm.query(sql, params, path=db)


def one(db: str, sql: str, params=()) -> dict:
    got = rows(db, sql, params)
    return got[0] if got else {}


class E2EBaseCase(unittest.TestCase):
    """一条选题、一条链路、一次运行。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="e2e-"))
        cls.db = str(cls.tmp / "app.db")
        subprocess.run([PY, str(ROOT / "scripts" / "db_init.py"), "--db", cls.db, "--force"],
                       capture_output=True, check=True)
        subprocess.run([PY, str(ROOT / "scripts" / "seed_adapters.py"), "--db", cls.db],
                       capture_output=True, check=True)
        cls.steps: list[dict] = []
        cls.obs: dict = {}
        cls.task_id = cls._run_chain()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        shutil.rmtree(ROOT / "workspace" / "topic-1", ignore_errors=True)

    # ---- 跑链路 ----
    @classmethod
    def _run(cls, label: str, skill: str, *args: str, expect: int = 0) -> subprocess.CompletedProcess:
        r = run_skill(skill, "--db", cls.db, *args)
        cls.steps.append({"label": label, "skill": skill, "rc": r.returncode, "expect": expect})
        if r.returncode != expect:
            raise AssertionError(
                f"[{label}] {skill} 退出码 {r.returncode}（期望 {expect}）\n"
                f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        return r

    @classmethod
    def _json(cls, label: str, skill: str, *args: str, expect: int = 0) -> dict:
        return json.loads(cls._run(label, skill, *args, expect=expect).stdout)

    @classmethod
    def _run_chain(cls) -> int:
        # 环节 0：派单（编排者工具）
        info = cls._json("派单", "task-decomposer", "--json", "dispatch",
                         "--title", "打工人春节返乡实录", "--platform", "抖音",
                         "--prompt", "写一条真实感强的返乡口播稿", "--out-dir", str(cls.tmp / "plan"))
        cls.obs["dispatch"] = info
        tid = info["task_id"]

        # 环节 1：文案线（3 套候选 → 关口① 选定 1 套 → 24 条分镜）
        cls._run("文案生成", "copy-writer", "--json", "generate", "--task-id", str(tid))
        cls._run("关口①挂起", "hitl-gate", "open", "--task-id", str(tid), "--gate", "gate1_select_copy")
        cls._run("关口①决议", "hitl-gate", "resolve", "--task-id", str(tid), "--gate", "gate1_select_copy",
                 "--action", "confirm", "--actor", "运营小李", "--plan-no", "1")
        cls._run("分镜拆解", "storyboard-builder", "--json", "build", "--task-id", str(tid))

        # 环节 2：视觉线（参考图 → 整图 → 切 24 张 → 体检）
        cls._run("参考图", "reference-image-builder", "build", "--task-id", str(tid), "--count", "1",
                 "--cell-w", "128", "--cell-h", "160", "--json")
        cls._run("整图", "grid-image-builder", "build", "--task-id", str(tid),
                 "--cell-w", "64", "--cell-h", "64", "--json")
        cls._run("切图", "image-splitter", "split", "--task-id", str(tid), "--json")
        cls._run("图片体检", "image-consistency-checker", "check", "--task-id", str(tid), "--json")

        # 环节 3：视频线（打包 → 草稿 → 关口② → 剪辑 → 成片与封面 → 发布准备）
        cls._run("图文打包", "asset-packager", "pack", "--task-id", str(tid), "--shot-seconds", "0.4", "--json")
        cls._run("草稿视频", "image-to-video", "build", "--task-id", str(tid), "--seconds-per-shot", "0.4",
                 "--fps", FPS, "--size", SMALL, "--json")
        cls._run("关口②挂起", "hitl-gate", "open", "--task-id", str(tid), "--gate", "gate2_edit_video")
        cls._run("关口②决议", "hitl-gate", "resolve", "--task-id", str(tid), "--gate", "gate2_edit_video",
                 "--action", "confirm", "--actor", "运营小李")
        cls._run("剪辑", "auto-editor", "edit", "--task-id", str(tid), "--from-hitl",
                 "--shot-seconds", "0.4", "--fps", FPS, "--size", SMALL, "--json")
        cls._run("导出成片", "video-exporter", "--json", "export", "--task-id", str(tid), "--cover-at", "0.2")
        cls._run("发布准备", "title-cover-prep", "--json", "prepare", "--task-id", str(tid))

        # 环节 4：分发线（发布包只填写 → 关口③ 授权前 live 自检必须被拦 → 真人发布回填）
        cls.obs["publish_prepare"] = cls._json("发布包与填写清单", "browser-publisher", "--json",
                                               "prepare", "--task-id", str(tid))
        cls.obs["live_before"] = cls._json("关口③未授权 live 自检", "publish-guard", "--json",
                                           "check", "--task-id", str(tid), "--live", expect=1)
        cls.obs["static_before"] = cls._json("关口③未授权 静态自检", "publish-guard", "--json",
                                             "check", "--task-id", str(tid))
        cls._run("真人发布并回填", "browser-publisher", "--json", "mark-published", "--task-id", str(tid),
                 "--actor", "运营小李", "--url", "https://example.com/v/1")
        cls.obs["live_after"] = cls._json("关口③授权后 live 自检", "publish-guard", "--json",
                                          "check", "--task-id", str(tid), "--live")

        # 环节 5：指标与复盘
        cls._run("指标采集", "metrics-collector", "--json", "collect", "--task-id", str(tid),
                 "--values", "播放量=18600,互动量=1120,涨粉=96",
                 "--period-start", PERIOD[0], "--period-end", PERIOD[1])
        cls._run("复盘", "review-reporter", "--json", "report", "--task-id", str(tid),
                 "--period-start", PERIOD[0], "--period-end", PERIOD[1])

        # 环节 6：汇总回报（编排者工具，只读）
        cls.obs["summary"] = cls._json("汇总回报", "summary-writer", "--json", "summarize", "--task-id", str(tid))
        return tid

    # ---- 通用查询 ----
    def roles(self) -> dict:
        """(kind, role) → 条数，角色从 artifacts.meta_json 里读。"""
        out: dict = {}
        for art in rec.list_artifacts(self.task_id, path=self.db):
            meta = json.loads(art.get("meta_json") or "{}")
            key = (art["kind"], meta.get("role", ""))
            out[key] = out.get(key, 0) + 1
        return out

    def summary_text(self) -> str:
        for path in self.obs.get("summary", {}).get("files", []):
            if str(path).endswith(".md"):
                return Path(path).read_text(encoding="utf-8")
        self.fail("汇总回报没有产出 .md 文件")


class TestAcceptanceCriteria(E2EBaseCase):
    """AC-1~AC-7 逐条对照。"""

    def test_ac1_chain_runs_without_failure(self):
        """AC-1：一条选题从派单到复盘，每个环节都真实跑过且退出码为 0。"""
        self.assertGreaterEqual(len(self.steps), 20)
        self.assertEqual([s["label"] for s in self.steps if s["rc"] != s["expect"]], [])
        skills = {s["skill"] for s in self.steps}
        for skill in ("task-decomposer", "copy-writer", "storyboard-builder", "reference-image-builder",
                      "grid-image-builder", "image-splitter", "image-consistency-checker", "asset-packager",
                      "image-to-video", "auto-editor", "video-exporter", "title-cover-prep", "browser-publisher",
                      "publish-guard", "metrics-collector", "review-reporter", "summary-writer"):
            self.assertIn(skill, skills, f"链路没有经过 {skill}")

    def test_ac1_task_reaches_review_after_publish(self):
        """AC-1：产物状态最终落在复盘环节，且发布记录是真人事后回填的。"""
        task = one(self.db, "SELECT stage, status, selected_plan FROM tasks WHERE id=?", (self.task_id,))
        self.assertEqual(task["stage"], "review")
        self.assertEqual(task["selected_plan"], 1)
        pub = one(self.db, "SELECT status, publish_url, operator, published_at FROM publish_records WHERE task_id=?",
                  (self.task_id,))
        self.assertEqual(pub["status"], "published")
        self.assertEqual(pub["publish_url"], "https://example.com/v/1")
        self.assertTrue(pub["operator"])
        self.assertTrue(pub["published_at"])

    def test_ac1_artifacts_cover_every_line(self):
        """AC-1：每条线都留下了产物（文案 / 分镜 / 24 张图 / 成片与封面 / 发布包 / 指标 / 复盘 / 汇总）。"""
        roles = self.roles()
        self.assertGreaterEqual(roles.get(("copy", ""), 0), 1)            # 候选文案（3 套见 AC-2 的 copy_variants 断言）
        self.assertGreaterEqual(roles.get(("storyboard", ""), 0), 1)      # 24 条分镜（条数见 AC-2）
        self.assertEqual(roles.get(("image", "shot")), 24)                # 24 张独立图
        self.assertIn(("manifest", "package"), roles)                     # 图文包
        self.assertIn(("video", "draft"), roles)                          # 草稿视频
        self.assertIn(("video", "edited"), roles)                         # 剪辑版
        self.assertIn(("manifest", "edit-params"), roles)                 # 关口② 参数留痕
        self.assertIn(("video", "final"), roles)                          # 成片
        self.assertIn(("image", "cover"), roles)                          # 封面帧
        self.assertIn(("manifest", "publish-prep"), roles)                # 发布准备
        self.assertIn(("publish_package", "package"), roles)              # 发布包（只填写）
        self.assertIn(("table", "metrics"), roles)                        # 指标表
        self.assertIn(("report", "review"), roles)                        # 复盘报告
        self.assertIn(("report", "summary"), roles)                       # 汇总回报

    def test_ac2_every_line_has_core_business_rows(self):
        """AC-2：每个环节都在核心业务表里留下了对应记录。"""
        self.assertEqual(one(self.db, "SELECT COUNT(*) n FROM topics")["n"], 1)
        self.assertEqual(one(self.db, "SELECT COUNT(*) n FROM tasks")["n"], 1)
        self.assertEqual(one(self.db, "SELECT COUNT(*) n FROM copy_variants WHERE task_id=?",
                             (self.task_id,))["n"], 3)
        self.assertEqual(one(self.db, "SELECT COUNT(*) n FROM storyboards WHERE task_id=?",
                             (self.task_id,))["n"], 24)
        self.assertGreaterEqual(one(self.db, "SELECT COUNT(*) n FROM artifacts WHERE task_id=?",
                                    (self.task_id,))["n"], 30)
        self.assertEqual(one(self.db, "SELECT COUNT(*) n FROM metrics WHERE task_id=?",
                             (self.task_id,))["n"], 3)
        self.assertEqual(one(self.db, "SELECT COUNT(*) n FROM publish_records WHERE task_id=?",
                             (self.task_id,))["n"], 1)
        steps = rows(self.db, "SELECT DISTINCT skill_id FROM step_runs WHERE task_id=?", (self.task_id,))
        self.assertEqual(len(steps), len({s["skill_id"] for s in steps}))
        self.assertGreaterEqual(len(steps), 15)
        for skill in ("copy-writer", "image-splitter", "auto-editor", "browser-publisher", "review-reporter"):
            self.assertIn(skill, {s["skill_id"] for s in steps})

    def test_ac3_console_and_buildlog_are_local_pages(self):
        """AC-3：build-log 与控制台都能在本机打开（这里验静态产物与本地服务自检，浏览器实测见验收报告）。"""
        r = subprocess.run([PY, str(ROOT / "scripts" / "serve_dashboard.py"), "--db", self.db,
                            "--check", "--json"], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["ok"])
        for rel in ("dashboard/index.html", "dashboard/pages/copy.html", "dashboard/pages/tasks.html",
                    "dashboard/pages/publish.html", "dashboard/pages/metrics.html",
                    "dashboard/assets/app.js", "dashboard/assets/style.css", "build-log.html"):
            self.assertTrue((ROOT / rel).is_file(), f"缺页面：{rel}")
        html = (ROOT / "build-log.html").read_text(encoding="utf-8")
        self.assertIn("搭建过程记录", html)
        data = json.loads((ROOT / "build-log.data.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(data["total"], 57)
        self.assertEqual(data["total"], len(LOGS_DIR.joinpath("2026-10-12.jsonl").read_text(
            encoding="utf-8").strip().splitlines()))

    def test_ac4_irreversible_actions_have_human_records(self):
        """AC-4：不可逆动作都有人工确认记录；关口③ 授权前 live 自检被拦，授权后才放行。"""
        events = rows(self.db, "SELECT gate, action, actor FROM hitl_events WHERE task_id=? ORDER BY id",
                      (self.task_id,))
        gates = {e["gate"]: e for e in events}
        for gate in ("gate1_select_copy", "gate2_edit_video", "gate3_publish_auth"):
            self.assertIn(gate, gates, f"关口 {gate} 没有人工记录")
            self.assertEqual(gates[gate]["action"], "confirm")
            self.assertTrue(gates[gate]["actor"])
        self.assertFalse(self.obs["live_before"]["ok"])
        self.assertTrue(any("关口③" in p for p in self.obs["live_before"]["problems"]))
        self.assertTrue(self.obs["static_before"]["ok"])
        self.assertTrue(self.obs["live_after"]["ok"])

    def test_ac4_agent_cannot_write_published(self):
        """AC-4 / C-08：Agent 侧没有任何「直接标已发布」的入口，只有真人回填才写 published。"""
        with self.assertRaises(pg.PublishGuardError):
            pg.record(self.task_id, platform="抖音", status="published", operator="运营小李",
                      package_path="x", path=self.db)
        self.assertTrue(self.obs["publish_prepare"]["submitted"] is False)
        self.assertFalse(self.obs["publish_prepare"]["check"]["live"])

    def test_ac5_all_simulated_suites_exist_and_structure_ok(self):
        """AC-5：每一步都先过模拟测试 —— 各线测试文件齐备，结构体检退出码 0。"""
        for name in ("test_db.py", "test_adapters.py", "test_copy_line.py", "test_visual_line.py",
                     "test_video_line.py", "test_publish_line.py", "test_orchestrator.py",
                     "test_dashboard.py", "test_e2e.py"):
            self.assertTrue((ROOT / "tests" / name).is_file(), f"缺测试：{name}")
        r = subprocess.run([PY, str(ROOT / "scripts" / "structure_check.py"), "--json"],
                           capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["ok"])

    def test_ac6_two_docs_restore_current_state(self):
        """AC-6：《讨论记录》与《目录及文件说明》能还原「做到哪 / 为什么 / 还剩什么」。"""
        record = (ROOT / "docs" / "discussion-record.md").read_text(encoding="utf-8")
        self.assertIn("## N014", record)
        for action in ("A-78", "A-79", "A-80"):
            self.assertIn(action, record)
        files = (ROOT / "docs" / "directory-and-files.md").read_text(encoding="utf-8")
        for token in ("dashboard/", "build-log.html", "console.py", "test_dashboard.py", "acceptance-report.md"):
            self.assertIn(token, files)
        spec = (ROOT / "docs" / "requirements-spec.md").read_text(encoding="utf-8")
        self.assertIn("v2.1.12", spec)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("N001–N014", readme)

    def test_ac7_flow_diagrams_synced(self):
        """AC-7：五份流程图齐备、分发线图里能看到步骤 7 落地的 skill，且每份图 README 都记着四门校验的命令
        （含让本机 Chrome 可跑 browser-check 的 ARCHIFY_CHROME_NO_SANDBOX=1，A-09 已在收尾时关闭）。"""
        dirs = ("FLOW-OVERALL-20261012", "FLOW-COPY-20261012", "FLOW-VISUAL-20261012",
                "FLOW-VIDEO-20261012", "FLOW-PUBLISH-20261012")
        for name in dirs:
            d = ROOT / ".archify" / name
            self.assertTrue((d / "README.md").is_file(), f"{name} 缺 README")
            self.assertTrue(list(d.glob("*.final.json")), f"{name} 缺 final.json")
            htmls = list(d.glob("*.html"))
            self.assertTrue(htmls, f"{name} 缺 html")
            spec = json.loads(list(d.glob("*.final.json"))[0].read_text(encoding="utf-8"))
            self.assertIn("components", spec)
            self.assertTrue(spec["components"], f"{name} 图里没有组件")
            readme = (d / "README.md").read_text(encoding="utf-8")
            for token in ("archify.mjs check", "ARCHIFY_CHROME_NO_SANDBOX=1", "browser-check"):
                self.assertIn(token, readme, f"{name} README 没写四门校验（缺 {token}）")
        publish_html = (ROOT / ".archify" / "FLOW-PUBLISH-20261012" / "publish-line.html").read_text(encoding="utf-8")
        for skill in ("hotspot-collector", "table-builder", "feishu-sync", "browser-publisher",
                      "metrics-collector", "review-reporter", "publish-guard"):
            self.assertIn(skill, publish_html)
        overall = (ROOT / ".archify" / "FLOW-OVERALL-20261012" / "overall-operations.html").read_text(encoding="utf-8")
        self.assertIn("build-log", overall)


class TestChainInvariants(E2EBaseCase):
    """链路自身的几条不变量（跑完再验一次）。"""

    def test_metrics_rerun_does_not_duplicate_rows(self):
        """同一周期同口径再采一次是更新，不是堆行。"""
        before = one(self.db, "SELECT COUNT(*) n FROM metrics WHERE task_id=?", (self.task_id,))["n"]
        self._run("指标复采", "metrics-collector", "--json", "collect", "--task-id", str(self.task_id),
                  "--values", "播放量=24000,互动量=1120,涨粉=96",
                  "--period-start", PERIOD[0], "--period-end", PERIOD[1])
        after = one(self.db, "SELECT COUNT(*) n FROM metrics WHERE task_id=?", (self.task_id,))["n"]
        self.assertEqual(before, after)
        got = one(self.db, "SELECT value FROM metrics WHERE task_id=? AND metric_key='views' AND period_start=?",
                  (self.task_id, PERIOD[0]))
        self.assertEqual(got["value"], 24000.0)
        self._run("指标还原", "metrics-collector", "--json", "collect", "--task-id", str(self.task_id),
                  "--values", "播放量=18600,互动量=1120,涨粉=96",
                  "--period-start", PERIOD[0], "--period-end", PERIOD[1])

    def test_summary_writer_reports_end_state(self):
        """汇总回报能说清「当前环节 / 关键产物 / 下一步找谁」，且带上当期指标。"""
        text = self.summary_text()
        for label in ("当前环节", "已完成步骤", "待办关口", "关键产物", "下一步找谁"):
            self.assertIn(label, text)
        self.assertIn("18600", text)
        self.assertIn("复盘", text)

    def test_task_state_unchanged_by_readonly_console(self):
        """控制台数据层只读：跑一遍快照后任务状态与留痕行数不变。"""
        sys.path.insert(0, str(ROOT / ".dsh" / "skills" / "_shared"))
        import console as cs  # noqa: E402

        before = one(self.db, "SELECT COUNT(*) n FROM step_runs WHERE task_id=?", (self.task_id,))["n"]
        snap = cs.snapshot(db=self.db)
        trace = cs.task_trace(self.task_id, db=self.db)
        self.assertEqual(trace["task"]["id"], self.task_id)
        self.assertTrue(snap["generated_at"])
        after = one(self.db, "SELECT COUNT(*) n FROM step_runs WHERE task_id=?", (self.task_id,))["n"]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
