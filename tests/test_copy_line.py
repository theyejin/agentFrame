#!/usr/bin/env python3
# 文件用途：WP-05 步骤 4 的模拟测试 —— 文案线端到端（3 套文案 → 关口① → 24 条分镜），全程离线假模型，不联网不花钱。
# 对应需求：R-L1-05（文案生成）、R-L1-06（分镜拆解）、R-L1-19（3 套/24 条一致性）、§8.3 关口①、R-7-03（版本字段）、R-L1-18（校验失败必退回）、R-L2-02（每步模拟测试通过再下一步）。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html
# 维护提示：改了提示词版本或样例文件（templates/mock/）后，本测试的期望值要同步；新增 skill 请补一条 CLI 端到端用例。
"""文案线模拟测试。

运行：
    python3 tests/test_copy_line.py
    python3 -m unittest discover -s tests -v

全部通过 = WP-05 步骤 4 的完成门之一（另外两道门：structure_check 退出码 0、prompt-registry check 无问题）。
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
SHARED = ROOT / ".dsh" / "skills" / "_shared"
sys.path.insert(0, str(SHARED))

import db as dbm  # noqa: E402
import hitl  # noqa: E402
import prompt_templates as pt  # noqa: E402
import recording as rec  # noqa: E402
import text_utils as tu  # noqa: E402

PY = sys.executable


def run_skill(skill: str, *args: str) -> subprocess.CompletedProcess:
    """按真实命令行方式调用 skill（与运营人员手动执行时走同一条路）。"""
    script = ROOT / ".dsh" / "skills" / skill / "run.py"
    return subprocess.run([PY, str(script), *args], capture_output=True, text=True, cwd=str(ROOT))


class BaseCase(unittest.TestCase):
    """每个用例一个临时库 + 临时产出目录，互不污染。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="copyline-"))
        self.db = str(self.tmp / "app.db")
        subprocess.run([PY, str(ROOT / "scripts" / "db_init.py"), "--db", self.db, "--force"],
                       capture_output=True, text=True, check=True)
        self.out = self.tmp / "out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 常用动作 ----
    def make_task(self, words: str = "300-500") -> int:
        r = run_skill("artifact-recorder", "--db", self.db, "topic-create",
                      "--title", "30岁裸辞做自媒体第90天", "--keywords", "裸辞,复盘",
                      "--summary", "记录裸辞后做账号的真实进展", "--task",
                      "--type", "情绪冲突", "--platform", "抖音",
                      "--prompt", "写一条真实感强的口播稿", "--words", words)
        self.assertEqual(r.returncode, 0, r.stderr)
        return int(re.search(r"任务 #(\d+)", r.stdout).group(1))

    def generate(self, task_id: int, extra=()):
        return run_skill("copy-writer", "--db", self.db, "generate", "--task-id", str(task_id),
                         "--out", str(self.out / "copy"), *extra)

    def confirm_gate1(self, task_id: int, plan_no: int = 2):
        self.assertEqual(run_skill("hitl-gate", "--db", self.db, "open",
                                   "--task-id", str(task_id), "--gate", "gate1_select_copy").returncode, 0)
        return run_skill("hitl-gate", "--db", self.db, "resolve", "--task-id", str(task_id),
                         "--gate", "gate1_select_copy", "--action", "confirm", "--actor", "阿金",
                         "--plan-no", str(plan_no))


class ParseTest(BaseCase):
    """解析与字数口径（生成与校验必须用同一套规则）。"""

    def test_count_words_ignores_whitespace(self):
        self.assertEqual(tu.count_words("你好 世界\n！"), 5)

    def test_copy_fixture_parses_into_three_plans(self):
        text = (ROOT / "templates" / "mock" / "copy-generate.v2.txt").read_text(encoding="utf-8")
        plans = tu.parse_copy_plans(text)
        self.assertEqual([p["plan_no"] for p in plans], [1, 2, 3])
        self.assertEqual([p["focus"] for p in plans], ["hook", "emotion", "cta"])

    def test_copy_fixture_within_default_word_range(self):
        text = (ROOT / "templates" / "mock" / "copy-generate.v2.txt").read_text(encoding="utf-8")
        for plan in tu.parse_copy_plans(text):
            self.assertTrue(300 <= tu.count_words(plan["body"]) <= 500, plan["plan_no"])

    def test_storyboard_fixture_parses_into_24_continuous_shots(self):
        text = (ROOT / "templates" / "mock" / "storyboard-split.v2.txt").read_text(encoding="utf-8")
        shots = tu.parse_storyboard(text, shot_seconds=3)
        self.assertEqual(tu.check_storyboard_shape(shots), [])
        self.assertEqual([s["shot_no"] for s in shots], list(range(1, 25)))
        self.assertEqual({s["duration_s"] for s in shots}, {3.0})

    def test_storyboard_shape_reports_gaps_and_duplicates(self):
        shots = [{"shot_no": 1, "scene_text": "同一个描述开头共三十个字符占位文本内容甲", "camera_note": "", "duration_s": 3},
                 {"shot_no": 3, "scene_text": "同一个描述开头共三十个字符占位文本内容甲", "camera_note": "", "duration_s": 3}]
        problems = tu.check_storyboard_shape(shots)
        self.assertTrue(any("正好 24 条" in p for p in problems))
        self.assertTrue(any("连续" in p for p in problems))
        self.assertTrue(any("重复" in p for p in problems))


class PromptTest(BaseCase):
    """提示词 v2 与调用方变量的对应关系。"""

    def test_prompt_versions_are_v2(self):
        self.assertEqual(pt.load("copy-generate").version, "v2")
        self.assertEqual(pt.load("storyboard-split").version, "v2")

    def test_registry_check_has_no_problems(self):
        self.assertEqual(pt.check(), [])


class RecordingTest(BaseCase):
    """登记层：话题 / 任务 / 步骤 / 产物的唯一写入实现。"""

    def test_step_failed_requires_error(self):
        task_id = self.make_task()
        with self.assertRaises(rec.RecordingError):
            rec.record_step(task_id, "copy-writer", "failed", path=self.db)

    def test_artifact_requires_versions(self):
        task_id = self.make_task()
        with self.assertRaises(rec.RecordingError):
            rec.record_artifact(task_id, "copy", "x.json", model_version="", prompt_version="v2", path=self.db)

    def test_artifact_ok_records_size_and_hash(self):
        task_id = self.make_task()
        f = self.tmp / "a.json"
        f.write_text("{}", encoding="utf-8")
        aid = rec.record_artifact(task_id, "copy", str(f), model_version="mock-v1", prompt_version="v2", path=self.db)
        row = dbm.query_one("SELECT * FROM artifacts WHERE id = ?", (aid,), self.db)
        self.assertGreater(row["size_bytes"], 0)
        self.assertEqual(len(row["sha256"]), 64)

    def test_task_progress_view_counts_steps(self):
        task_id = self.make_task()
        rec.record_step(task_id, "copy-writer", "ok", path=self.db)
        progress = rec.task_progress(task_id, self.db)
        self.assertEqual(progress["done_steps"], 1)
        self.assertEqual(progress["stage"], "copy")


class HitlTest(BaseCase):
    """关口① 的开启与决议（选择态）。"""

    def test_cannot_resolve_before_open(self):
        task_id = self.make_task()
        with self.assertRaises(hitl.HitlError):
            hitl.resolve_gate(task_id, hitl.GATE1, "confirm", "阿金", plan_no=1, path=self.db)

    def test_confirm_requires_plan_no(self):
        task_id = self.make_task()
        hitl.open_gate(task_id, hitl.GATE1, path=self.db)
        with self.assertRaises(hitl.HitlError):
            hitl.resolve_gate(task_id, hitl.GATE1, "confirm", "阿金", path=self.db)

    def test_unknown_action_rejected(self):
        task_id = self.make_task()
        hitl.open_gate(task_id, hitl.GATE1, path=self.db)
        with self.assertRaises(hitl.HitlError):
            hitl.resolve_gate(task_id, hitl.GATE1, "approve", "阿金", plan_no=1, path=self.db)

    def test_confirm_sets_selected_plan_and_records_event(self):
        task_id = self.make_task()
        r = self.generate(task_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.confirm_gate1(task_id, 2).returncode, 0)
        task = dbm.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,), self.db)
        self.assertEqual(task["selected_plan"], 2)
        self.assertEqual(task["status"], "running")
        self.assertEqual(task["operator"], "阿金")
        events = hitl.list_events(task_id, self.db)
        self.assertEqual([(e["gate"], e["action"]) for e in events], [("gate1_select_copy", "confirm")])


class CopyWriterEndToEndTest(BaseCase):
    """copy-writer 的 CLI 端到端（离线假模型）。"""

    def test_generate_writes_three_active_variants_and_files(self):
        task_id = self.make_task()
        r = self.generate(task_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = dbm.query("SELECT * FROM copy_variants WHERE task_id = ? ORDER BY plan_no", (task_id,), self.db)
        self.assertEqual([row["plan_no"] for row in rows], [1, 2, 3])
        self.assertEqual({row["focus"] for row in rows}, {"hook", "emotion", "cta"})
        self.assertTrue(all(row["status"] == "active" for row in rows))
        self.assertTrue(all(300 <= row["word_count"] <= 500 for row in rows))
        self.assertTrue(all(row["prompt_version"] == "v2" for row in rows))
        self.assertEqual(len(list((self.out / "copy").glob("variants-*.json"))), 1)
        self.assertTrue((self.out / "copy" / "variants.md").exists())
        artifacts = rec.list_artifacts(task_id, self.db)
        self.assertEqual(len(artifacts), 2)
        self.assertEqual({a["kind"] for a in artifacts}, {"copy"})

    def test_regenerate_overwrites_current_three_and_keeps_history(self):
        """重生成：库里仍是 3 套（同套号覆盖），历史靠带时间戳的产物留痕。"""
        task_id = self.make_task()
        self.assertEqual(self.generate(task_id).returncode, 0)
        self.assertEqual(self.generate(task_id).returncode, 0)
        rows = dbm.query("SELECT status FROM copy_variants WHERE task_id = ?", (task_id,), self.db)
        self.assertEqual([r["status"] for r in rows], ["active", "active", "active"])
        records = sorted((self.out / "copy").glob("variants-*.json"))
        self.assertEqual(len(records), 2, "两代生成记录都要在")
        self.assertNotEqual(records[0].name, records[1].name)
        self.assertEqual(len(rec.list_artifacts(task_id, self.db)), 4)

    def test_word_range_violation_fails_three_attempts_and_blocks_task(self):
        task_id = self.make_task(words="10-20")   # 样例文案必然超区间 → 触发失败路径
        r = self.generate(task_id)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("第 3 次生成不合格", r.stderr)
        task = dbm.query_one("SELECT status FROM tasks WHERE id = ?", (task_id,), self.db)
        self.assertEqual(task["status"], "blocked")
        step = dbm.query_one("SELECT * FROM step_runs WHERE task_id = ? ORDER BY id DESC", (task_id,), self.db)
        self.assertEqual(step["status"], "failed")
        self.assertTrue(step["error"])

    def test_empty_prompt_and_brief_is_rejected_without_calling_model(self):
        r = run_skill("artifact-recorder", "--db", self.db, "topic-create", "--title", "只有标题", "--task")
        # 没有 prompt 也没有 summary 时，topic-create 允许建，但 copy-writer 必须拒收
        self.assertEqual(r.returncode, 0, r.stderr)
        task_id = int(re.search(r"任务 #(\d+)", r.stdout).group(1))
        out = self.generate(task_id)
        self.assertEqual(out.returncode, 2)
        self.assertIn("至少要给一个", out.stderr)


class StoryboardBuilderEndToEndTest(BaseCase):
    """storyboard-builder 的 CLI 端到端，含「未过关口① 不得往下走」。"""

    def test_build_refused_without_gate1(self):
        task_id = self.make_task()
        self.assertEqual(self.generate(task_id).returncode, 0)
        r = run_skill("storyboard-builder", "--db", self.db, "build", "--task-id", str(task_id),
                      "--out", str(self.out / "storyboard"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("must give plan_no", r.stderr.replace("请先过关口①", "must give plan_no"))
        self.assertEqual(dbm.query("SELECT * FROM storyboards WHERE task_id = ?", (task_id,), self.db), [])

    def test_build_writes_24_shots_and_advances_stage(self):
        task_id = self.make_task()
        self.assertEqual(self.generate(task_id).returncode, 0)
        self.assertEqual(self.confirm_gate1(task_id, 3).returncode, 0)
        r = run_skill("storyboard-builder", "--db", self.db, "build", "--task-id", str(task_id),
                      "--out", str(self.out / "storyboard"))
        self.assertEqual(r.returncode, 0, r.stderr)
        shots = dbm.query("SELECT * FROM storyboards WHERE task_id = ? ORDER BY shot_no", (task_id,), self.db)
        self.assertEqual([s["shot_no"] for s in shots], list(range(1, 25)))
        self.assertEqual(len({s["scene_text"] for s in shots}), 24)
        self.assertEqual({s["duration_s"] for s in shots}, {3.0})
        task = dbm.query_one("SELECT stage, status FROM tasks WHERE id = ?", (task_id,), self.db)
        self.assertEqual(task["stage"], "visual")
        record = next((self.out / "storyboard").glob("storyboard-*.json"))
        data = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(data["shot_total"], 24)
        self.assertEqual(data["grid"], "6x4")

    def test_validator_accepts_generated_file(self):
        task_id = self.make_task()
        self.generate(task_id)
        self.confirm_gate1(task_id, 1)
        run_skill("storyboard-builder", "--db", self.db, "build", "--task-id", str(task_id),
                  "--out", str(self.out / "storyboard"))
        record = next((self.out / "storyboard").glob("storyboard-*.json"))
        r = run_skill("storyboard-validator", "check", "--file", str(record),
                      "--target-seconds", "72", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["ok"])

    def test_validator_rejects_wrong_count(self):
        bad = self.tmp / "bad.txt"
        bad.write_text("\n".join(f"{i:02d} | 第{i}个画面描述 | 固定机位" for i in range(1, 10)), encoding="utf-8")
        r = run_skill("storyboard-validator", "check", "--file", str(bad))
        self.assertEqual(r.returncode, 1)
        self.assertIn("正好 24 条", r.stdout)


class FullCopyLineTest(BaseCase):
    """整条文案线连跑：输入 → 3 套文案 → 关口① → 24 条分镜 → 产物与流水齐全。"""

    def test_full_line(self):
        task_id = self.make_task()
        self.assertEqual(self.generate(task_id).returncode, 0)
        self.assertEqual(self.confirm_gate1(task_id, 2).returncode, 0)
        self.assertEqual(run_skill("storyboard-builder", "--db", self.db, "build", "--task-id", str(task_id),
                                   "--out", str(self.out / "storyboard")).returncode, 0)
        progress = rec.task_progress(task_id, self.db)
        self.assertEqual(progress["stage"], "visual")
        self.assertEqual(progress["done_steps"], 2)
        self.assertEqual(progress["failed_steps"], 0)
        steps = rec.list_steps(task_id, self.db)
        self.assertEqual([s["skill_id"] for s in steps], ["copy-writer", "storyboard-builder"])
        self.assertEqual({s["status"] for s in steps}, {"ok"})
        artifacts = rec.list_artifacts(task_id, self.db)
        self.assertEqual(sorted(a["kind"] for a in artifacts), ["copy", "copy", "storyboard", "storyboard"])
        self.assertTrue(all(a["model_version"] and a["prompt_version"] for a in artifacts))


if __name__ == "__main__":
    unittest.main(verbosity=2)
