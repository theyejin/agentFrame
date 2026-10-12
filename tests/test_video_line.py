#!/usr/bin/env python3
# 文件用途：WP-05 步骤 6 的模拟测试 —— 视频线端到端（图文打包 → 草稿视频 → 关口② 剪辑干预 → 剪辑版 → 导出成片与封面 → 发布准备），全程离线，不联网不花钱。
# 对应需求：R-L1-07（图生视频）、R-L1-08（自动剪辑与人工干预）、R-L1-09（发布前准备）、R-8-01（平台模板）、§8.3（关口② 调整态）、C-01/C-08/C-09（红线与零付费）、R-L2-02（每步模拟测试通过再下一步）。
# 对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html
# 维护提示：改 video.py 的合成/抽帧口径或 video 链（registry.json）后要同步本测试；视频用例一律用极小分辨率与帧率，避免测试变慢。
"""视频线模拟测试。

运行：
    python3 tests/test_video_line.py

全部通过 = WP-05 步骤 6 的完成门之一（另外两道门：structure_check 退出码 0、prompt-registry check 无问题）。
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

import adapter_runtime as ar  # noqa: E402
import recording as rec  # noqa: E402
import text_utils as tu  # noqa: E402
import video as vd  # noqa: E402

PY = sys.executable
SHOTS = 24
SMALL = "64x64"          # 视频用例统一用极小分辨率（快）
FPS = "5"


def run_skill(skill: str, *args: str) -> subprocess.CompletedProcess:
    """按真实命令行方式调用 skill（与运营人员手动执行时走同一条路）。"""
    script = ROOT / ".dsh" / "skills" / skill / "run.py"
    return subprocess.run([PY, str(script), *args], capture_output=True, text=True, cwd=str(ROOT))


class BaseCase(unittest.TestCase):
    """每个用例一个临时库 + 临时产出目录，互不污染。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="videoline-"))
        self.db = str(self.tmp / "app.db")
        subprocess.run([PY, str(ROOT / "scripts" / "db_init.py"), "--db", self.db, "--force"],
                       capture_output=True, text=True, check=True)
        subprocess.run([PY, str(ROOT / "scripts" / "seed_adapters.py"), "--db", self.db],
                       capture_output=True, text=True, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(ROOT / "workspace" / "topic-1", ignore_errors=True)

    # ---- 常用动作 ----
    def make_task(self, platform: str = "抖音") -> int:
        r = run_skill("artifact-recorder", "--db", self.db, "topic-create",
                      "--title", "裸辞做自媒体第 91 天", "--keywords", "裸辞,复盘",
                      "--summary", "记录真实进展", "--task", "--type", "情绪冲突", "--platform", platform,
                      "--prompt", "写一条真实感强的口播稿", "--words", "300-500")
        self.assertEqual(r.returncode, 0, r.stderr)
        import re
        return int(re.search(r"任务 #(\d+)", r.stdout).group(1))

    def solve_gate1(self, task_id: int, plan_no: int = 1) -> None:
        r = run_skill("hitl-gate", "--db", self.db, "open", "--task-id", str(task_id),
                      "--gate", "gate1_select_copy")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("hitl-gate", "--db", self.db, "resolve", "--task-id", str(task_id),
                      "--gate", "gate1_select_copy", "--action", "confirm", "--actor", "测试",
                      "--plan-no", str(plan_no))
        self.assertEqual(r.returncode, 0, r.stderr)

    def to_shots_ready(self) -> int:
        """一路跑到「24 张独立图就绪」：文案线 + 关口① + 分镜 + 视觉线（全部离线小图）。"""
        task_id = self.make_task()
        r = run_skill("copy-writer", "--db", self.db, "--json", "generate", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.solve_gate1(task_id)
        r = run_skill("storyboard-builder", "--db", self.db, "--json", "build", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("reference-image-builder", "--db", self.db, "build", "--task-id", str(task_id),
                      "--count", "1", "--cell-w", "128", "--cell-h", "160", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("grid-image-builder", "--db", self.db, "build", "--task-id", str(task_id),
                      "--cell-w", "64", "--cell-h", "64", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("image-splitter", "--db", self.db, "split", "--task-id", str(task_id), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return task_id

    def to_draft_ready(self) -> int:
        """再往前一步：图文打包 + 草稿视频（极小分辨率）。"""
        task_id = self.to_shots_ready()
        r = run_skill("asset-packager", "--db", self.db, "pack", "--task-id", str(task_id),
                      "--shot-seconds", "0.4", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("image-to-video", "--db", self.db, "build", "--task-id", str(task_id),
                      "--seconds-per-shot", "0.4", "--fps", FPS, "--size", SMALL, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return task_id

    def to_edited_ready(self) -> int:
        task_id = self.to_draft_ready()
        r = run_skill("hitl-gate", "--db", self.db, "open", "--task-id", str(task_id),
                      "--gate", "gate2_edit_video")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("hitl-gate", "--db", self.db, "resolve", "--task-id", str(task_id),
                      "--gate", "gate2_edit_video", "--action", "confirm", "--actor", "测试")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("auto-editor", "--db", self.db, "edit", "--task-id", str(task_id),
                      "--from-hitl", "--shot-seconds", "0.4", "--fps", FPS, "--size", SMALL, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return task_id

    def artifact(self, task_id: int, kind: str, role: str):
        return rec.latest_artifact(task_id, kind, role=role, path=self.db)

    def meta(self, art: dict) -> dict:
        return json.loads(art.get("meta_json") or "{}")


class TestPackager(BaseCase):
    def test_requires_selected_copy(self):
        """没过关口① 就不能打包（文案线契约在视频线仍然把门）。"""
        task_id = self.make_task()
        r = run_skill("asset-packager", "--db", self.db, "pack", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("关口", r.stderr)
        self.assertIsNone(self.artifact(task_id, "manifest", "package"))

    def test_pack_writes_manifest_and_copy(self):
        task_id = self.to_shots_ready()
        r = run_skill("asset-packager", "--db", self.db, "pack", "--task-id", str(task_id),
                      "--shot-seconds", "0.4", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        package = ROOT / info["package"]
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["count"], SHOTS)
        self.assertEqual([s["shot_no"] for s in manifest["shots"]], list(range(1, SHOTS + 1)))
        self.assertTrue(all((ROOT / s["image"]).is_file() for s in manifest["shots"]))
        self.assertTrue((package / "copy.md").is_file())
        self.assertAlmostEqual(manifest["total_seconds"], 24 * 0.4, places=3)
        art = self.artifact(task_id, "manifest", "package")
        self.assertEqual(art["model_version"], "local")

    def test_second_pack_same_second_does_not_overwrite(self):
        """同一秒连打两次包：目录要加后缀，上一代不能被覆盖（留痕可追溯）。"""
        task_id = self.to_shots_ready()
        first = run_skill("asset-packager", "--db", self.db, "pack", "--task-id", str(task_id))
        second = run_skill("asset-packager", "--db", self.db, "pack", "--task-id", str(task_id))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        dirs = sorted((ROOT / "workspace" / "topic-1" / "video" / "package").iterdir())
        self.assertGreaterEqual(len(dirs), 2)


class TestImageToVideo(BaseCase):
    def test_requires_package(self):
        task_id = self.to_shots_ready()
        r = run_skill("image-to-video", "--db", self.db, "build", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("package", r.stderr)

    def test_draft_uses_local_ffmpeg_adapter(self):
        """离线也能出草稿：video 链落到 video.ffmpeg，模型版本与产物角色都要能查。"""
        task_id = self.to_draft_ready()
        art = self.artifact(task_id, "video", "draft")
        self.assertIsNotNone(art, "没有登记 draft 产物")
        self.assertTrue((ROOT / art["path"]).is_file())
        self.assertTrue(art["model_version"].startswith("ffmpeg-"), art["model_version"])
        info = vd.probe(ROOT / art["path"])
        self.assertEqual((info["width"], info["height"]), (64, 64))
        self.assertGreater(info["duration_s"], 8.0)                       # 24 镜 × 0.4s
        self.assertLess(info["duration_s"], 24 * 0.4 * 1.5)
        steps = [s for s in rec.list_steps(task_id, self.db) if s["skill_id"] == "image-to-video"]
        self.assertEqual(steps[-1]["adapter_used"], "video.ffmpeg")


class TestAutoEditor(BaseCase):
    def test_rejects_bad_order(self):
        task_id = self.to_shots_ready()
        r = run_skill("auto-editor", "--db", self.db, "edit", "--task-id", str(task_id),
                      "--order", "1,2,3")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("排列", r.stderr)

    def test_rejects_missing_replacement(self):
        task_id = self.to_shots_ready()
        r = run_skill("auto-editor", "--db", self.db, "edit", "--task-id", str(task_id),
                      "--replace", "7=workspace/nope.png")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("不存在", r.stderr)

    def test_from_hitl_requires_resolved_gate(self):
        task_id = self.to_draft_ready()
        r = run_skill("auto-editor", "--db", self.db, "edit", "--task-id", str(task_id), "--from-hitl")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("关口②", r.stderr)

    def test_hitl_adjust_changes_duration_and_keeps_params(self):
        """关口② adjust：换顺序 + 改两镜时长，剪辑版要真的按参数变（而不是原样重渲）。"""
        task_id = self.to_draft_ready()
        run_skill("hitl-gate", "--db", self.db, "open", "--task-id", str(task_id), "--gate", "gate2_edit_video")
        diff = json.dumps({"order": list(range(24, 0, -1)), "durations": {"1": 1.5, "2": 0.2}})
        r = run_skill("hitl-gate", "--db", self.db, "resolve", "--task-id", str(task_id),
                      "--gate", "gate2_edit_video", "--action", "adjust", "--actor", "运营-小李",
                      "--diff-json", diff)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("auto-editor", "--db", self.db, "edit", "--task-id", str(task_id), "--from-hitl",
                      "--shot-seconds", "0.4", "--fps", FPS, "--size", SMALL, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(info["order"][0], 24)
        self.assertAlmostEqual(info["planned_duration_s"], 1.5 + 0.2 + 22 * 0.4, places=3)
        params = json.loads((ROOT / info["params"]).read_text(encoding="utf-8"))
        self.assertEqual(params["durations"]["1"], 1.5)
        self.assertEqual(params["hitl"]["actor"], "运营-小李")
        art = self.artifact(task_id, "video", "edited")
        self.assertEqual(self.meta(art)["role"], "edited")


class TestExporter(BaseCase):
    def test_requires_edited(self):
        task_id = self.to_draft_ready()
        r = run_skill("video-exporter", "--db", self.db, "export", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("剪辑版", r.stderr)

    def test_export_writes_final_and_cover_and_advances_stage(self):
        task_id = self.to_edited_ready()
        r = run_skill("video-exporter", "--db", self.db, "export", "--task-id", str(task_id),
                      "--cover-at", "0.2", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertTrue((ROOT / info["final"]).is_file())
        self.assertTrue((ROOT / info["cover"]).is_file())
        self.assertEqual(self.artifact(task_id, "video", "final")["model_version"], "ffmpeg-render-v1")
        self.assertEqual(self.artifact(task_id, "image", "cover")["model_version"], "ffmpeg-cover-v1")
        self.assertEqual(rec.task_progress(task_id, self.db)["stage"], "publish")


class TestTitleCoverPrep(BaseCase):
    def test_requires_final_video(self):
        task_id = self.to_shots_ready()
        r = run_skill("title-cover-prep", "--db", self.db, "prepare", "--task-id", str(task_id))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("成片", r.stderr)

    def test_unknown_platform_lists_configured(self):
        task_id = self.to_edited_ready()
        r = run_skill("title-cover-prep", "--db", self.db, "prepare", "--task-id", str(task_id),
                      "--platform", "快手")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("抖音", r.stderr)

    def test_prep_matches_platform_template(self):
        task_id = self.to_edited_ready()
        run_skill("video-exporter", "--db", self.db, "export", "--task-id", str(task_id), "--cover-at", "0.2")
        r = run_skill("title-cover-prep", "--db", self.db, "prepare", "--task-id", str(task_id), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(len(info["titles"]), 3)
        self.assertEqual(len(info["tags"]), 5)                # 抖音模板：标签 5 个
        self.assertTrue(info["cover"])
        data = json.loads((ROOT / info["json"]).read_text(encoding="utf-8"))
        self.assertEqual(data["cover_ratio"], "9:16")
        self.assertEqual(data["adapter_used"], "llm.mock")
        self.assertEqual(data["prompt_version"], "v1")
        art = self.artifact(task_id, "manifest", "publish-prep")
        self.assertEqual(art["prompt_version"], "v1")

    def test_absolute_words_are_rejected(self):
        """命中 C-01 绝对化用语：必须失败（不能把「最强」这种词发出去）。"""
        fixture = ROOT / "templates" / "mock" / "publish-prep.v1.txt"
        backup = fixture.read_text(encoding="utf-8")
        task_id = self.to_edited_ready()
        run_skill("video-exporter", "--db", self.db, "export", "--task-id", str(task_id), "--cover-at", "0.2")
        try:
            fixture.write_text("标题1：全网最强的选题方法\n标题2：三步搭好选题表\n标题3：先看这条复盘\n"
                               "标签：自媒体运营,内容选题,数据分析,涨粉,复盘\n封面：选题表这么搭\n",
                               encoding="utf-8")
            r = run_skill("title-cover-prep", "--db", self.db, "prepare", "--task-id", str(task_id),
                          "--attempts", "1")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("绝对化", r.stderr)
            self.assertEqual(rec.task_progress(task_id, self.db)["status"], "blocked")
        finally:
            fixture.write_text(backup, encoding="utf-8")


class TestVideoChainEndToEnd(BaseCase):
    def test_full_video_line(self):
        """整条视频线连跑：打包 → 草稿 → 关口② 调整 → 剪辑 → 导出 → 发布准备。"""
        task_id = self.to_edited_ready()
        r = run_skill("video-exporter", "--db", self.db, "export", "--task-id", str(task_id),
                      "--cover-at", "0.2", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_skill("title-cover-prep", "--db", self.db, "prepare", "--task-id", str(task_id), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)

        progress = rec.task_progress(task_id, self.db)
        self.assertEqual(progress["stage"], "publish")
        self.assertEqual(progress["status"], "running")
        skills = [s["skill_id"] for s in rec.list_steps(task_id, self.db) if s["status"] == "ok"]
        for expected in ("asset-packager", "image-to-video", "auto-editor", "video-exporter",
                         "title-cover-prep"):
            self.assertIn(expected, skills)
        # 关口② 的事件必须留痕（谁在什么时候做了什么决定）
        events = rec.dbm.query("SELECT gate, action, actor FROM hitl_events WHERE task_id = ? ORDER BY id",
                               (task_id,), self.db) if hasattr(rec, "dbm") else []
        self.assertTrue(any(e["gate"] == "gate2_edit_video" and e["actor"] == "测试" for e in events))


class TestSharedUnits(unittest.TestCase):
    """共享库的单元用例（不需要数据库）：合成、校验与发布准备解析。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="videounit-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _images(self, count: int = 3) -> list[Path]:
        from PIL import Image
        out = []
        for i in range(1, count + 1):
            path = self.tmp / f"c{i}.png"
            Image.new("RGB", (48, 48), (10 * i, 60, 120)).save(path)
            out.append(path)
        return out

    def test_make_slideshow_honours_per_shot_durations(self):
        images = self._images(3)
        out = self.tmp / "out.mp4"
        info = vd.make_slideshow(images, out, fps=5, size=(64, 64), durations=[0.4, 1.2, 0.4])
        self.assertTrue(out.is_file())
        self.assertAlmostEqual(info["planned_duration_s"], 2.0, places=3)
        self.assertGreater(vd.probe(out)["duration_s"], 1.5)

    def test_make_slideshow_rejects_bad_input(self):
        with self.assertRaises(vd.VideoError) as ctx:
            vd.make_slideshow([], self.tmp / "x.mp4")
        self.assertIn("至少要有一张图片", str(ctx.exception))
        images = self._images(2)
        with self.assertRaises(vd.VideoError) as ctx:
            vd.make_slideshow(images, self.tmp / "y.mp4", durations=[1.0])
        self.assertIn("时长个数", str(ctx.exception))
        with self.assertRaises(vd.VideoError) as ctx:
            vd.make_slideshow(self._images(1), self.tmp / "z.mp4", size=(10, 10))
        self.assertIn("太小", str(ctx.exception))
        with self.assertRaises(vd.VideoError) as ctx:
            vd.make_slideshow(images, self.tmp / "w.mp4", fps=0)
        self.assertIn("帧率", str(ctx.exception))

    def test_check_video_flags_missing_file(self):
        report = vd.check_video(self.tmp / "nope.mp4")
        self.assertFalse(report["ok"])
        self.assertTrue(report["problems"])

    def test_publish_prep_parse_and_redline(self):
        prep = tu.parse_publish_prep("标题1：A\n标题2：B\n标题3：C\n标签：x,y\n封面：短封面\n")
        self.assertEqual(prep["titles"], ["A", "B", "C"])
        self.assertEqual(prep["tags"], ["x", "y"])
        self.assertEqual(prep["cover"], "短封面")
        self.assertEqual(tu.check_publish_prep(prep, tag_count=2), [])
        bad = tu.parse_publish_prep("标题1：全网最强的方法\n标题2：B\n标题3：C\n标签：x\n封面：\n")
        problems = tu.check_publish_prep(bad, tag_count=2)
        self.assertTrue(any("绝对化" in p for p in problems))
        self.assertTrue(any("标签应为 2 个" in p for p in problems))
        self.assertTrue(any("封面文案为空" in p for p in problems))


    def test_video_chain_terminal_is_local_ffmpeg(self):
        """video 链的离线终点必须是本地免费的 video.ffmpeg（Remotion 未接时自动降级，C-09 零付费）。"""
        chain = ar.chain("video")
        self.assertEqual([a["adapter_id"] for a in chain],
                         ["video.remotion", "video.ffmpeg", "video.external-i2v", "video.manual"])
        implemented = [a for a in chain if a.get("implemented")]
        self.assertEqual(implemented[0]["adapter_id"], "video.ffmpeg")
        self.assertFalse(implemented[0]["needs_key"])
        self.assertFalse(implemented[0]["billable"])
        self.assertEqual(implemented[0]["settings"]["runtime"], "ffmpeg_render")

    def test_matrix_equality_for_video_size(self):
        """视频分辨率必须是偶数（编码器要求），这条口径与 images.py 的整图等式一致。"""
        images = self._images(2)
        out = self.tmp / "even.mp4"
        vd.make_slideshow(images, out, fps=5, size=(65, 65), durations=[0.4, 0.4])
        info = vd.probe(out)
        self.assertEqual((info["width"], info["height"]), (64, 64))


if __name__ == "__main__":
    unittest.main(verbosity=2)
