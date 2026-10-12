#!/usr/bin/env python3
# 文件用途：WP-05 步骤 5 的模拟测试 —— 视觉线端到端（参考图 → 6×4 整图 → 切 24 张 → 一致性体检 → 视觉关口），全程离线，不联网不花钱。
# 对应需求：R-L1-06（图文素材生成）、R-L1-19（24 张图一致性与编号连续）、Q-11（先出整图再切、保留逐张重生成）、§8.3（风格确认/单张返工属调整态关口）、R-7-03（版本字段）、R-L1-18（校验失败必退回）、R-L2-02（每步模拟测试通过再下一步）。
# 对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html
# 维护提示：改 images.py 的切分命名规则或 image 链（registry.json）后要同步本测试；新增视觉线 skill 请补一条 CLI 端到端用例。
"""视觉线模拟测试。

运行：
    python3 tests/test_visual_line.py

全部通过 = WP-05 步骤 5 的完成门之一（另外两道门：structure_check 退出码 0、prompt-registry check 无问题）。
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / ".dsh" / "skills" / "_shared"
sys.path.insert(0, str(SHARED))

import hitl  # noqa: E402
import images as im  # noqa: E402
import recording as rec  # noqa: E402

PY = sys.executable
SHOTS = 24


def run_skill(skill: str, *args: str) -> subprocess.CompletedProcess:
    """按真实命令行方式调用 skill（与运营人员手动执行时走同一条路）。"""
    script = ROOT / ".dsh" / "skills" / skill / "run.py"
    return subprocess.run([PY, str(script), *args], capture_output=True, text=True, cwd=str(ROOT))


class BaseCase(unittest.TestCase):
    """每个用例一个临时库 + 临时产出目录，互不污染。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="visualline-"))
        self.db = str(self.tmp / "app.db")
        subprocess.run([PY, str(ROOT / "scripts" / "db_init.py"), "--db", self.db, "--force"],
                       capture_output=True, text=True, check=True)
        self.out = self.tmp / "out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(ROOT / "workspace" / "topic-1", ignore_errors=True)

    # ---- 常用动作 ----
    def make_task(self) -> int:
        r = run_skill("artifact-recorder", "--db", self.db, "topic-create",
                      "--title", "裸辞做自媒体第 91 天", "--keywords", "裸辞,复盘",
                      "--summary", "记录真实进展", "--task", "--type", "情绪冲突", "--platform", "抖音",
                      "--prompt", "写一条真实感强的口播稿", "--words", "300-500")
        self.assertEqual(r.returncode, 0, r.stderr)
        import re
        return int(re.search(r"任务 #(\d+)", r.stdout).group(1))

    def gate1(self, task_id: int) -> None:
        self.assertEqual(run_skill("copy-writer", "--db", self.db, "generate", "--task-id", str(task_id),
                                   "--out", str(self.out / "copy")).returncode, 0)
        self.assertEqual(run_skill("hitl-gate", "--db", self.db, "open", "--task-id", str(task_id),
                                   "--gate", "gate1_select_copy").returncode, 0)
        r = run_skill("hitl-gate", "--db", self.db, "resolve", "--task-id", str(task_id),
                      "--gate", "gate1_select_copy", "--action", "confirm", "--actor", "阿金", "--plan-no", "2")
        self.assertEqual(r.returncode, 0, r.stderr)

    def storyboard(self, task_id: int) -> None:
        r = run_skill("storyboard-builder", "--db", self.db, "build", "--task-id", str(task_id),
                      "--out", str(self.out / "storyboard"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def ready(self) -> int:
        """一路准备到「选定文案 + 24 条分镜」，这是视觉线的进场条件。"""
        task_id = self.make_task()
        self.gate1(task_id)
        self.storyboard(task_id)
        return task_id

    def reference(self, task_id: int, *extra: str) -> subprocess.CompletedProcess:
        return run_skill("reference-image-builder", "--db", self.db, "build", "--task-id", str(task_id),
                         "--out", str(self.out / "reference"), "--cell-w", "128", "--cell-h", "192", *extra)

    def grid(self, task_id: int, *extra: str) -> subprocess.CompletedProcess:
        return run_skill("grid-image-builder", "--db", self.db, "build", "--task-id", str(task_id),
                         "--out", str(self.out / "grid"), "--cell-w", "96", "--cell-h", "96", *extra)

    def split(self, task_id: int, *extra: str) -> subprocess.CompletedProcess:
        return run_skill("image-splitter", "--db", self.db, "split", "--task-id", str(task_id),
                         "--out", str(self.out / "shots"), *extra)


class GeometryTest(BaseCase):
    """切分与体检这两个纯本地能力（Pillow 离线），先把底盘测牢。"""

    def test_placeholder_grid_has_exact_size(self):
        path = self.tmp / "g.png"
        info = im.make_placeholder_grid(path, 6, 4, 32, 32, title="t")
        self.assertEqual(im.read_size(path), (192, 128))
        self.assertEqual(info["cols"], 6)
        self.assertEqual(info["cells"], 24)

    def test_slice_grid_row_major_and_naming(self):
        grid_path = self.tmp / "g.png"
        im.make_placeholder_grid(grid_path, 6, 4, 48, 48)
        shots = im.slice_grid(grid_path, 6, 4, self.tmp / "shots")
        self.assertEqual(len(shots), SHOTS)
        self.assertEqual([s["shot_no"] for s in shots], list(range(1, SHOTS + 1)))
        self.assertTrue((self.tmp / "shots" / "shot-01.png").is_file())
        self.assertTrue((self.tmp / "shots" / "shot-24.png").is_file())
        self.assertEqual({(s["width"], s["height"]) for s in shots}, {(48, 48)})

    def test_check_images_is_green_on_good_batch(self):
        grid_path = self.tmp / "g.png"
        im.make_placeholder_grid(grid_path, 6, 4, 96, 96)
        paths = [s["path"] for s in im.slice_grid(grid_path, 6, 4, self.tmp / "shots")]
        report = im.check_images(paths, expected=SHOTS, min_side=64)
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(report["count"], SHOTS)

    def test_check_images_flags_missing_and_size_mismatch(self):
        grid_path = self.tmp / "g.png"
        im.make_placeholder_grid(grid_path, 6, 4, 96, 96)
        paths = [Path(s["path"]) for s in im.slice_grid(grid_path, 6, 4, self.tmp / "shots")]
        paths[0].unlink()                      # 少一张 → 数量与编号连续性都该报
        paths[1].write_bytes(b"")              # 空文件
        report = im.check_images(paths, expected=SHOTS, min_side=64)
        self.assertFalse(report["ok"])
        joined = "；".join(report["problems"])
        self.assertIn("图片不存在", joined)
        self.assertIn("空文件", joined)
        self.assertIn("编号不连续", joined)
        fewer = im.check_images(paths[2:], expected=SHOTS, min_side=64)
        self.assertIn("数量", "；".join(fewer["problems"]))


class ReferenceImageBuilderTest(BaseCase):
    """参考图生成师：先卡关口①，再出图并登记。"""

    def test_rejects_when_copy_not_selected(self):
        task_id = self.make_task()             # 故意不过关口①
        r = self.reference(task_id)
        self.assertEqual(r.returncode, 2)
        self.assertIn("选定文案", r.stderr)

    def test_generates_files_with_version_fields(self):
        task_id = self.ready()
        r = self.reference(task_id, "--count", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(run_skill("reference-image-builder", "--db", self.db, "--json", "build",
                                       "--task-id", str(task_id), "--count", "1",
                                       "--out", str(self.out / "reference2"),
                                       "--cell-w", "128", "--cell-h", "192").stdout)
        self.assertEqual(payload["adapter_used"], "image.placeholder")
        self.assertEqual(payload["model_version"], "placeholder-v1")
        self.assertEqual(payload["prompt_version"], "v1")
        arts = [a for a in rec.list_artifacts(task_id, self.db) if json.loads(a["meta_json"] or "{}").get("role") == "reference"]
        self.assertEqual(len(arts), 3)         # 2 张 + 再出的 1 张
        for art in arts:
            self.assertTrue(art["model_version"])
            self.assertTrue(art["prompt_version"])

    def test_rejects_count_out_of_range(self):
        task_id = self.ready()
        r = self.reference(task_id, "--count", "5")
        self.assertEqual(r.returncode, 2)
        self.assertIn("1–3", r.stderr)

    def test_regeneration_keeps_previous_files(self):
        task_id = self.ready()
        self.assertEqual(self.reference(task_id).returncode, 0)
        self.assertEqual(self.reference(task_id).returncode, 0)
        files = sorted((self.out / "reference").glob("reference-*.png"))
        self.assertEqual(len(files), 4)        # 两代各 2 张，旧的没被覆盖

    def test_default_out_dir_is_under_workspace(self):
        task_id = self.ready()
        r = run_skill("reference-image-builder", "--db", self.db, "build", "--task-id", str(task_id),
                      "--count", "1", "--cell-w", "128", "--cell-h", "192")
        self.assertEqual(r.returncode, 0, r.stderr)
        art = [a for a in rec.list_artifacts(task_id, self.db) if a["kind"] == "image"][0]
        self.assertTrue(art["path"].startswith("workspace/topic-1/images/reference/"), art["path"])


class GridImageBuilderTest(BaseCase):
    """整图生成师：24 条分镜 → 一张 6×4 整图，尺寸必须精确。"""

    def test_grid_size_and_artifact_meta(self):
        task_id = self.ready()
        r = self.grid(task_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        art = [a for a in rec.list_artifacts(task_id, self.db) if a["kind"] == "image"][0]
        meta = json.loads(art["meta_json"])
        self.assertEqual(meta["role"], "grid")
        self.assertEqual((meta["cols"], meta["rows"], meta["cells"]), (6, 4, 24))
        self.assertEqual((meta["width"], meta["height"]), (576, 384))
        path = Path(rec.abs_path_of(art["path"]))
        self.assertEqual(im.read_size(path), (576, 384))

    def test_rejects_when_storyboard_missing(self):
        task_id = self.make_task()
        self.gate1(task_id)                    # 过了关口① 但没有分镜
        r = self.grid(task_id)
        self.assertEqual(r.returncode, 2)
        self.assertIn("分镜未就绪", r.stderr)

    def test_rejects_tiny_cell(self):
        task_id = self.ready()
        r = self.grid(task_id, "--cell-w", "16", "--cell-h", "16")
        self.assertEqual(r.returncode, 2)
        self.assertIn("单格尺寸", r.stderr)


class ImageSplitterTest(BaseCase):
    """切图师：整图 → 24 张 + 清单，并把任务推进到视频线。"""

    def test_split_produces_24_shots_and_manifest(self):
        task_id = self.ready()
        self.assertEqual(self.grid(task_id).returncode, 0)
        r = self.split(task_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        shots = sorted((self.out / "shots").glob("shot-*.png"))
        self.assertEqual(len(shots), SHOTS)
        self.assertEqual(shots[0].name, "shot-01.png")
        self.assertEqual(shots[-1].name, "shot-24.png")
        manifest = json.loads((self.out / "shots" / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["count"], SHOTS)
        self.assertEqual(len(manifest["shots"]), SHOTS)
        self.assertEqual(len({s["width"] for s in manifest["shots"]}), 1)
        self.assertEqual(rec.task_bundle(task_id, self.db)["task"]["stage"], "video")
        kinds = [a["kind"] for a in rec.list_artifacts(task_id, self.db)]
        self.assertEqual(kinds.count("image"), 1 + SHOTS)   # 整图 1 + 独立图 24
        self.assertEqual(kinds.count("manifest"), 1)

    def test_rejects_grid_that_cannot_be_divided(self):
        """8×3 的整图同样是 24 格，但宽 800 不能被 6 整除 —— 必须拒绝，不能切出半张图。"""
        task_id = self.ready()
        self.assertEqual(self.grid(task_id, "--cols", "8", "--rows", "3", "--cell-w", "100",
                                   "--cell-h", "100").returncode, 0)
        r = self.split(task_id)
        self.assertEqual(r.returncode, 2)
        self.assertIn("整除", r.stderr)

    def test_rejects_when_no_grid_artifact(self):
        task_id = self.ready()
        r = self.split(task_id)
        self.assertEqual(r.returncode, 2)
        self.assertIn("整图", r.stderr)


class ConsistencyCheckerTest(BaseCase):
    """图片一致性体检员：只出结论，不改产物、不置 blocked。"""

    def test_passes_on_good_batch(self):
        task_id = self.ready()
        self.assertEqual(self.grid(task_id).returncode, 0)
        self.assertEqual(self.split(task_id).returncode, 0)
        r = run_skill("image-consistency-checker", "--db", self.db, "check", "--task-id", str(task_id),
                      "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertTrue(info["ok"], info["problems"])
        self.assertEqual(info["count"], SHOTS)

    def test_flags_missing_file_without_blocking_task(self):
        task_id = self.ready()
        self.assertEqual(self.grid(task_id).returncode, 0)
        self.assertEqual(self.split(task_id).returncode, 0)
        first = sorted((self.out / "shots").glob("shot-*.png"))[0]
        first.unlink()
        r = run_skill("image-consistency-checker", "--db", self.db, "check", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 1)
        self.assertIn("编号不连续", r.stdout + r.stderr)
        self.assertIn("图片不存在", r.stdout + r.stderr)
        status = rec.task_bundle(task_id, self.db)["task"]["status"]
        self.assertNotEqual(status, "blocked")   # 体检不是生产，不该把任务卡死

    def test_missing_dir_is_input_error(self):
        task_id = self.ready()
        r = run_skill("image-consistency-checker", "--db", self.db, "check", "--task-id", str(task_id),
                      "--dir", str(self.tmp / "nope"))
        self.assertEqual(r.returncode, 2)


class VisualGateTest(BaseCase):
    """视觉线两个人关口：风格确认（选择/确认）与单张返工（必须给出范围）。"""

    def test_visual_style_gate_roundtrip(self):
        task_id = self.ready()
        self.assertEqual(self.reference(task_id).returncode, 0)
        open_r = run_skill("hitl-gate", "--db", self.db, "open", "--task-id", str(task_id),
                           "--gate", "gate_visual_style", "--note", "参考图待确认")
        self.assertEqual(open_r.returncode, 0, open_r.stderr)
        self.assertEqual(rec.task_bundle(task_id, self.db)["task"]["status"], "waiting_human")
        done = run_skill("hitl-gate", "--db", self.db, "resolve", "--task-id", str(task_id),
                         "--gate", "gate_visual_style", "--action", "confirm", "--actor", "阿金")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(rec.task_bundle(task_id, self.db)["task"]["status"], "running")

    def test_visual_fix_requires_shot_numbers(self):
        task_id = self.ready()
        self.assertEqual(run_skill("hitl-gate", "--db", self.db, "open", "--task-id", str(task_id),
                                   "--gate", "gate_visual_fix").returncode, 0)
        r = run_skill("hitl-gate", "--db", self.db, "resolve", "--task-id", str(task_id),
                      "--gate", "gate_visual_fix", "--action", "adjust", "--actor", "阿金")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("shot_nos", r.stdout + r.stderr)
        ok = run_skill("hitl-gate", "--db", self.db, "resolve", "--task-id", str(task_id),
                       "--gate", "gate_visual_fix", "--action", "adjust", "--actor", "阿金",
                       "--diff-json", '{"shot_nos": [3, 7]}')
        self.assertEqual(ok.returncode, 0, ok.stderr)
        events = hitl.list_events(task_id, self.db)
        gate = [e for e in events if e["gate"] == "gate_visual_fix"][-1]
        self.assertIn("shot_nos", gate["diff_json"])


class FullVisualLineTest(BaseCase):
    """整条视觉线连跑：文案 → 关口① → 分镜 → 参考图 → 整图 → 切 24 张 → 体检。"""

    def test_full_visual_line_offline(self):
        task_id = self.ready()
        self.assertEqual(self.reference(task_id, "--count", "2").returncode, 0)
        self.assertEqual(self.grid(task_id).returncode, 0)
        split = self.split(task_id)
        self.assertEqual(split.returncode, 0, split.stderr)
        check = run_skill("image-consistency-checker", "--db", self.db, "check", "--task-id", str(task_id),
                          "--json")
        self.assertEqual(check.returncode, 0, check.stderr)
        info = json.loads(check.stdout)
        self.assertTrue(info["ok"], info["problems"])

        progress = rec.task_progress(task_id, self.db)
        self.assertEqual(progress["stage"], "video")
        self.assertEqual(progress["status"], "running")
        steps = rec.list_steps(task_id, self.db)
        self.assertEqual([s["skill_id"] for s in steps if s["status"] == "ok"],
                         ["copy-writer", "storyboard-builder", "reference-image-builder",
                          "grid-image-builder", "image-splitter", "image-consistency-checker"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
