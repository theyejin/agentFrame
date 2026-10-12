#!/usr/bin/env python3
# 文件用途：WP-07 的模拟测试 —— Agent 定义与编排者两个工具（派单员 task-decomposer、汇总回报员 summary-writer），全程离线。
# 对应需求：R-L1-05~R-L1-09（Agent 定义与边界）、R-L1-18/R-L1-19（交接契约由运行时校验、失败退回）、§5.2.1（编排者不写文件）、§16.2 统一执行流程。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
# 维护提示：改 agents/orchestrator/config.yml 的契约结构、或改两个工具的 CLI 后，必须同步本测试。
"""Agent 定义与编排者工具模拟测试。

运行：
    python3 tests/test_orchestrator.py

覆盖三块：① `agents/` 五个定义文件与 config.yml 的契约完整性；② task-decomposer 的 dispatch/plan/agents；
③ summary-writer 的回报五项、只读性与缺口照实写。
全部通过 = WP-07 的完成门之一（另外两道门：structure_check 退出码 0、全套测试全绿）。
"""

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SHARED = ROOT / ".dsh" / "skills" / "_shared"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(TESTS))

import db as dbm  # noqa: E402
import hitl  # noqa: E402
import recording as rec  # noqa: E402
from test_video_line import BaseCase, run_skill  # noqa: E402

CONFIG = ROOT / "agents" / "orchestrator" / "config.yml"
AGENT_DIRS = ("orchestrator", "copy-agent", "visual-agent", "video-agent", "publish-agent")
LINE_AGENTS = ("copy-agent", "visual-agent", "video-agent", "publish-agent")


def load_module(name: str, rel: str):
    """按文件路径加载 skill 的 run.py（用于直接单测其中的纯函数）。"""
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TD = load_module("task_decomposer_run", ".dsh/skills/task-decomposer/run.py")
SW = load_module("summary_writer_run", ".dsh/skills/summary-writer/run.py")


class OrchestratorBaseCase(BaseCase):
    """在视频线 BaseCase 之上加两条与编排相关的便捷动作。"""

    def dispatch(self, title: str = "打工人春节返乡", platform: str = "抖音", *extra: str) -> dict:
        r = run_skill("task-decomposer", "--db", self.db, "--json", "dispatch",
                      "--title", title, "--platform", platform, "--prompt", "写一条返乡情绪", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def summarize(self, task_id: int, *extra: str) -> tuple[dict, str]:
        r = run_skill("summary-writer", "--db", self.db, "--json", "summarize",
                      "--task-id", str(task_id), *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        info = json.loads(r.stdout)
        text = rec.abs_path_of(info["files"][0]).read_text(encoding="utf-8")
        return info, text


# ---------------------------------------------------------------------------
# ① Agent 定义与 config.yml
# ---------------------------------------------------------------------------

class TestAgentDefinitions(unittest.TestCase):
    def load(self) -> dict:
        import yaml
        return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    def test_five_agent_dirs_exist(self):
        """五个 Agent 目录一个不少，编排者的 config.yml 也在。"""
        for name in AGENT_DIRS:
            self.assertTrue((ROOT / "agents" / name).is_dir(), f"缺 Agent 目录：agents/{name}")
            self.assertTrue((ROOT / "agents" / name / "README.md").is_file(), f"缺 README：agents/{name}")
        self.assertTrue(CONFIG.is_file(), "缺 agents/orchestrator/config.yml")

    def test_config_parses_with_all_agents(self):
        cfg = self.load()
        self.assertEqual(cfg["version"], 1)
        ids = [a["agent_id"] for a in cfg["agents"]]
        for name in LINE_AGENTS:
            self.assertIn(name, ids)
        self.assertEqual(cfg["orchestrator"]["agent_id"], "orchestrator")
        self.assertEqual(cfg["orchestrator"]["max_parallel"], 1)

    def test_every_agent_has_three_part_contract(self):
        """R-L1-18：交接契约三段（进场校验 / 产出物清单 / 完成判据）每个 Agent 都要齐。"""
        for agent in self.load()["agents"]:
            handoff = agent["handoff"]
            for key in ("input_check", "outputs", "done"):
                self.assertTrue(handoff.get(key), f"{agent['agent_id']} 缺 {key}")
            self.assertTrue(agent["entry_stage"] and agent["exit_stage"])

    def test_declared_skills_all_exist_on_disk(self):
        """config.yml 声明的每个 Skill 目录都必须真实存在（否则派单就是空头支票）。"""
        self.assertEqual(TD.check_contract(self.load()), [])

    def test_human_gates_complete(self):
        """五个关口一个不少，且与 recording.GATES 完全一致（避免两处口径漂移）。"""
        self.assertEqual(set(self.load()["human_gates"]), set(rec.GATES))

    def test_stage_routing_covers_every_stage(self):
        routing = self.load()["stage_routing"]
        for stage in ("copy", "visual", "video", "publish", "metrics", "review", "closed"):
            self.assertIn(stage, routing, f"stage_routing 缺 {stage}")

    def test_agent_readmes_state_boundaries(self):
        """每个环节 Agent 的 README 必须写清「管什么 / 不管什么 / 派单契约」三段。"""
        for name in LINE_AGENTS:
            text = (ROOT / "agents" / name / "README.md").read_text(encoding="utf-8")
            for heading in ("管什么", "不管什么", "派单契约"):
                self.assertIn(heading, text, f"agents/{name}/README.md 缺「{heading}」")
            self.assertIn("完成判据", text)
            self.assertIn("交接契约", text + (ROOT / "agents" / "README.md").read_text(encoding="utf-8"))

    def test_orchestrator_readme_forbids_writing_and_gate_answering(self):
        text = (ROOT / "agents" / "orchestrator" / "README.md").read_text(encoding="utf-8")
        self.assertIn("不直接写文件", text)
        self.assertIn("不直接调用外部 API", text)
        self.assertIn("不代答人工关口", text)
        self.assertIn("task-decomposer", text)
        self.assertIn("summary-writer", text)

    def test_publish_agent_declares_no_auto_publish(self):
        text = (ROOT / "agents" / "publish-agent" / "README.md").read_text(encoding="utf-8")
        self.assertIn("C-08", text)
        self.assertIn("不自动发布", text)
        self.assertIn("gate3_publish_auth", text)

    def test_contract_check_catches_missing_piece(self):
        """契约自检要真的能挑出问题：少一段、或引用不存在的 Skill 目录。"""
        cfg = self.load()
        cfg["agents"][0]["handoff"].pop("done")
        cfg["agents"][1]["skills"] = list(cfg["agents"][1]["skills"]) + ["no-such-skill"]
        problems = TD.check_contract(cfg)
        self.assertTrue(any("缺 done" in p for p in problems), problems)
        self.assertTrue(any("no-such-skill" in p for p in problems), problems)

    def test_contract_words_use_minimal_vocabulary(self):
        """完成判据必须用最小词汇表里的词（count / file_exists / in_range …），不能是自由发挥。"""
        vocab = ("count", "ids_continuous", "unique", "in_range", "all_resolution_equal",
                 "file_exists", "non_empty", "enum_in", "no_auto_publish")
        for agent in self.load()["agents"]:
            done = " ".join(agent["handoff"]["done"])
            self.assertTrue(any(v in done for v in vocab), f"{agent['agent_id']} 的完成判据没有词汇表用词：{done}")


# ---------------------------------------------------------------------------
# ② task-decomposer
# ---------------------------------------------------------------------------

class TestTaskDecomposer(OrchestratorBaseCase):
    def test_dispatch_creates_topic_task_and_book(self):
        """一次派单要落下四样：话题、任务、派单书两份、留痕两行。"""
        info = self.dispatch()
        task_id, topic_id = info["task_id"], info["topic_id"]
        self.assertEqual(info["agent_id"], "copy-agent")
        self.assertEqual(info["stage"], "copy")
        self.assertTrue(info["contract"]["input_check"] and info["contract"]["done"])
        for rel in (info["dispatch_json"], info["dispatch_md"]):
            self.assertTrue(rec.abs_path_of(rel).is_file(), f"派单书没落盘：{rel}")
        self.assertEqual(dbm.query_one("SELECT stage, status FROM tasks WHERE id=?", (task_id,), self.db),
                         {"stage": "copy", "status": "pending"})
        self.assertEqual(dbm.query_one("SELECT title FROM topics WHERE id=?", (topic_id,), self.db)["title"],
                         "打工人春节返乡")
        art = dbm.query("SELECT * FROM artifacts WHERE task_id=? AND kind='manifest'", (task_id,), self.db)
        self.assertEqual(len(art), 1)
        self.assertEqual(json.loads(art[0]["meta_json"])["role"], "dispatch")
        self.assertEqual(art[0]["prompt_version"], "none")
        self.assertEqual(len(rec.list_steps(task_id, self.db)), 1)

    def test_dispatch_entry_command_points_to_first_skill(self):
        info = self.dispatch()
        self.assertEqual(info["entry_skill"], "copy-writer")
        self.assertIn("copy-writer/run.py generate --task-id", info["entry_command"])
        self.assertEqual(info["gates"], ["gate1_select_copy"])

    def test_dispatch_uses_platform_template_word_range(self):
        """不给字数就用平台模板的字数区间（平台口径只有一处事实源）。"""
        tpl = dbm.query_one("SELECT word_min, word_max FROM platform_templates WHERE platform='小红书'",
                           (), self.db)
        info = self.dispatch(platform="小红书")
        self.assertEqual(info["word_range"], [tpl["word_min"], tpl["word_max"]])

    def test_dispatch_rejects_unknown_platform(self):
        r = run_skill("task-decomposer", "--db", self.db, "dispatch", "--title", "x", "--platform", "快手")
        self.assertEqual(r.returncode, 2)
        self.assertIn("平台不存在", r.stderr)
        self.assertIn("抖音", r.stderr)
        self.assertEqual(dbm.query("SELECT COUNT(*) AS n FROM tasks", (), self.db)[0]["n"], 0)

    def test_dispatch_requires_title_for_new_topic(self):
        r = run_skill("task-decomposer", "--db", self.db, "dispatch", "--platform", "抖音")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--title", r.stderr)

    def test_dispatch_rejects_bad_word_range(self):
        r = run_skill("task-decomposer", "--db", self.db, "dispatch", "--title", "x", "--platform", "抖音",
                      "--word-min", "800", "--word-max", "300")
        self.assertEqual(r.returncode, 2)
        self.assertIn("字数区间不合法", r.stderr)

    def test_dispatch_can_reuse_existing_topic(self):
        first = self.dispatch()
        second = self.dispatch("第二单", "抖音", "--topic-id", str(first["topic_id"]))
        self.assertEqual(second["topic_id"], first["topic_id"])
        self.assertNotEqual(second["task_id"], first["task_id"])
        self.assertEqual(dbm.query("SELECT COUNT(*) AS n FROM topics", (), self.db)[0]["n"], 1)
        self.assertEqual(dbm.query("SELECT COUNT(*) AS n FROM tasks", (), self.db)[0]["n"], 2)

    def test_plan_routes_by_current_stage(self):
        """任务走到视频线后，plan 就该指向视频线 Agent 与打包员。"""
        info = self.dispatch()
        task_id = info["task_id"]
        rec.update_task(task_id, stage="video", status="running", path=self.db)
        r = run_skill("task-decomposer", "--db", self.db, "--json", "plan", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 0, r.stderr)
        plan = json.loads(r.stdout)
        self.assertEqual(plan["agent_id"], "video-agent")
        self.assertIn("asset-packager", plan["entry_command"])
        self.assertEqual(plan["dispatch_book"], info["dispatch_json"])

    def test_plan_rejects_unknown_task(self):
        r = run_skill("task-decomposer", "--db", self.db, "plan", "--task-id", "999")
        self.assertEqual(r.returncode, 2)
        self.assertIn("任务不存在", r.stderr)

    def test_agents_subcommand_lists_five_and_no_problems(self):
        r = run_skill("task-decomposer", "--db", self.db, "--json", "agents")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(len(info["agents"]), 4)
        self.assertEqual(info["orchestrator"]["agent_id"], "orchestrator")
        self.assertEqual(info["problems"], [])
        for agent in info["agents"]:
            self.assertEqual(agent["skills_missing"], [], f"{agent['agent_id']} 有缺失的 Skill")


# ---------------------------------------------------------------------------
# ③ summary-writer
# ---------------------------------------------------------------------------

class TestSummaryWriter(OrchestratorBaseCase):
    def test_summary_has_five_items_and_lands_files(self):
        info, text = self.summarize(self.dispatch()["task_id"])
        for label in ("当前环节", "已完成步骤", "待办关口", "关键产物", "下一步找谁"):
            self.assertIn(label, text)
        self.assertEqual(info["agent_id"], "copy-agent")
        self.assertIn("copy-writer", info["next_command"])
        self.assertTrue(rec.abs_path_of(info["files"][0]).is_file())

    def test_summary_is_read_only_for_business_tables(self):
        """汇总只读：任务状态、环节、指标、发布记录在汇总前后必须一致。"""
        task_id = self.dispatch()["task_id"]
        before = dbm.query_one("SELECT stage, status FROM tasks WHERE id=?", (task_id,), self.db)
        self.summarize(task_id)
        after = dbm.query_one("SELECT stage, status FROM tasks WHERE id=?", (task_id,), self.db)
        self.assertEqual(before, after)

    def test_summary_reports_missing_metrics_honestly(self):
        _, text = self.summarize(self.dispatch()["task_id"])
        self.assertIn("本期还没有指标", text)
        self.assertNotIn("播放 0", text)

    def test_summary_includes_metrics_when_present(self):
        task_id = self.dispatch()["task_id"]
        r = run_skill("metrics-collector", "--db", self.db, "--json", "collect", "--task-id", str(task_id),
                      "--values", "播放量=24000,互动量=1730,涨粉=137",
                      "--period-start", "2026-10-05", "--period-end", "2026-10-11")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        info, text = self.summarize(task_id)
        self.assertIn("24000", text)
        self.assertEqual(int(info["metrics"]["views"]), 24000)

    def test_summary_flags_pending_gate_without_answering_it(self):
        """挂在关口上要照实写，但不能代答：汇总后任务仍是 waiting_human、没有关口决议。"""
        task_id = self.dispatch()["task_id"]
        r = run_skill("hitl-gate", "--db", self.db, "open", "--task-id", str(task_id),
                      "--gate", "gate1_select_copy")
        self.assertEqual(r.returncode, 0, r.stderr)
        info, text = self.summarize(task_id)
        self.assertIn("有 1 个关口待人工决议", text)
        self.assertTrue(info["waiting_human"])
        self.assertEqual(hitl.list_events(task_id, self.db), [])
        self.assertEqual(dbm.query_one("SELECT status FROM tasks WHERE id=?", (task_id,), self.db)["status"],
                         "waiting_human")

    def test_summary_links_existing_review_report(self):
        task_id = self.dispatch()["task_id"]
        rel = "workspace/topic-1/review/report-2026.md"
        rec.record_artifact(task_id, "report", rel, model_version="mock-copy-v1", prompt_version="v1",
                            meta={"role": "review"}, path=self.db)
        info, text = self.summarize(task_id)
        self.assertTrue(info["has_review"])
        self.assertIn(rel, text)

    def test_summary_excludes_dispatch_book_from_content_artifacts(self):
        """派单书是编排文件，不算内容产物（关键产物里不该出现 manifest 1）。"""
        info, _ = self.summarize(self.dispatch()["task_id"])
        self.assertNotIn("manifest", info["artifacts_by_kind"])

    def test_summary_rejects_unknown_task(self):
        r = run_skill("summary-writer", "--db", self.db, "summarize", "--task-id", "999")
        self.assertEqual(r.returncode, 2)
        self.assertIn("任务不存在", r.stderr)

    def test_summary_self_check_blocks_too_short_report(self):
        """回报字数门槛由命令行控制；门槛调高后自检必须拦下，且不落盘不合格回报。"""
        task_id = self.dispatch()["task_id"]
        r = run_skill("summary-writer", "--db", self.db, "summarize", "--task-id", str(task_id),
                      "--min-chars", "5000")
        self.assertEqual(r.returncode, 2)
        self.assertIn("回报自检不通过", r.stderr)
        self.assertEqual(dbm.query("SELECT COUNT(*) AS n FROM artifacts WHERE kind='report'", (), self.db)[0]["n"], 0)

    def test_summary_render_counts_roles_from_meta(self):
        """角色一律从 meta.role 读（产物目录可被 --out 改掉，角色不会）。"""
        text = "x"
        self.assertEqual(SW._roles({"meta_json": json.dumps({"role": "shot"})}), ["shot"])
        self.assertEqual(SW._roles({"meta_json": "not-json"}), [])
        self.assertEqual(SW._roles({"meta_json": None}), [])

    def test_summary_check_report_catches_missing_label(self):
        problems = SW.check_report("# 回报\n- 当前环节：copy\n- 已完成步骤：1 步\n- 待办关口：无\n- 关键产物：无",
                                   min_chars=1)
        self.assertTrue(any("下一步找谁" in p for p in problems), problems)

    def test_summary_route_table_covers_all_stages(self):
        for stage in ("copy", "visual", "video", "publish", "metrics", "review"):
            agent_id, skill_id, sub = SW.route_of(stage)
            self.assertTrue(agent_id and skill_id and sub, f"{stage} 没有路由")
            self.assertTrue((ROOT / ".dsh" / "skills" / skill_id / "run.py").is_file(), skill_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
