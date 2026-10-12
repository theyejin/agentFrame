#!/usr/bin/env python3
# 文件用途：图生视频 —— 把打包好的 24 张图按顺序合成一条视频草稿（离线走 video.ffmpeg，外部服务未接时自动降级）。
# 对应需求：R-L1-07（图生视频）、§6.5/R-L2-14（统一接口 + 适配器）、R-L2-17（降级链）、Q-7（Remotion 首选、ffmpeg 兜底）、C-09。
# 对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html（打包文件夹 → image-to-video → 视频草稿 → 关口②）
# 维护提示：输出分辨率与帧率是下游锚点（剪辑与导出沿用），改了要同步 auto-editor / video-exporter 与测试。
"""图生视频（image-to-video）。

用法：
    python3 .dsh/skills/image-to-video/run.py build --task-id 1 [--package DIR] [--seconds-per-shot 3]
                                                    [--fps 30] [--size 720x1280] [--out FILE]
                                                    [--attempts 3] [--allow-paid] [--step-no N] [--json]

完成判据：
  ① 打包清单存在且 24 张图都在（缺一张就退回）；
  ② 产出 `workspace/topic-<选题号>/video/draft/draft-<时间戳>.mp4`，分辨率与时长可探测；
  ③ 成片时长与计划时长偏差不超过 15%（多了说明拼接出错）；
  ④ 登记 kind=video、role=draft 的产物，并提示下一步开「关口② 剪辑干预」。

退出码：0 = 成功；1 = 合成失败或自检不过（任务置 blocked）；2 = 输入校验不通过。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import adapter_runtime as ar  # noqa: E402
import db as dbm  # noqa: E402
import recording as rec  # noqa: E402
import video as vd  # noqa: E402

SKILL_ID = "image-to-video"
LINE = "video"
DEFAULT_FPS = 30
DEFAULT_SIZE = (720, 1280)
DURATION_TOLERANCE = 0.15


class InputError(ValueError):
    """上游没就绪或参数不合法。"""


def parse_size(text: str) -> tuple[int, int]:
    """把 `720x1280` 解析成 (720, 1280)。"""
    sep = "x" if "x" in text.lower() else "*"
    parts = text.lower().split(sep)
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise InputError(f"--size 需形如 720x1280，收到：{text}")
    return int(parts[0]), int(parts[1])


def latest_package(task_id: int, db: str | None) -> tuple[dict, dict]:
    """取最近一代打包清单（role=package）与其绝对路径。"""
    art = rec.latest_artifact(task_id, "manifest", role="package", path=db)
    if not art:
        raise InputError(f"任务 {task_id} 还没有打包产物：请先跑 asset-packager pack")
    path = dbm.REPO_ROOT / art["path"]
    if not path.is_file():
        raise InputError(f"登记的打包清单已不在：{art['path']}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise InputError(f"打包清单读不出来（{path}）：{exc}")
    if not data.get("shots"):
        raise InputError("打包清单里没有任何分镜（shots 为空）")
    return data, {"path": path, "artifact": art}


def validate_input(task_id: int, package: str | None, db: str | None) -> tuple[dict, dict, dict, list[Path]]:
    bundle = rec.task_bundle(task_id, path=db)
    if package:
        path = Path(package)
        if not path.is_absolute():
            path = dbm.REPO_ROOT / path
        if not path.is_file():
            raise InputError(f"--package 指向的清单不存在：{package}")
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise InputError(f"打包清单读不出来（{path}）：{exc}")
        src = {"path": path, "artifact": None}
    else:
        manifest, src = latest_package(task_id, db)
    shots = manifest.get("shots") or []
    images = [dbm.REPO_ROOT / s["image"] for s in shots]
    missing = [rec.rel_path(p) for p in images if not p.is_file()]
    if missing:
        raise InputError(f"这些图已不在：{'、'.join(missing[:3])}{'…' if len(missing) > 3 else ''}")
    return bundle["task"], bundle["topic"], {**src, "manifest": manifest}, images


def cmd_build(args: argparse.Namespace) -> int:
    started = dbm.now_iso()
    try:
        task, topic, src, images = validate_input(args.task_id, args.package, args.db)
        size = parse_size(args.size) if args.size else DEFAULT_SIZE
    except (InputError, rec.RecordingError) as exc:
        try:
            rec.record_step(args.task_id, SKILL_ID, "failed", step_no=args.step_no,
                            error=f"输入校验不通过：{exc}", path=args.db)
        except rec.RecordingError as inner:
            print(f"[提示] 无法登记这次退回：{inner}", file=sys.stderr)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2
    if args.seconds_per_shot <= 0 or args.fps < 1:
        print("[错误] 输入校验不通过：--seconds-per-shot 必须大于 0，--fps 至少为 1", file=sys.stderr)
        return 2

    out_dir = Path(args.out).parent if args.out else rec.workspace_dir(topic["id"], f"{LINE}/draft", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    draft = Path(args.out) if args.out else out_dir / f"draft-{rec.timestamp_slug()}.mp4"
    planned = round(len(images) * float(args.seconds_per_shot), 3)

    payload = {"images": [str(p) for p in images], "abs_out": str(draft), "seconds_per_image": float(args.seconds_per_shot),
               "fps": int(args.fps), "size": [size[0], size[1]], "task_id": task["id"]}
    result = ar.invoke("video", payload, allow_paid=args.allow_paid)
    problems: list[str] = []
    if not result.ok:
        problems.append(f"图生视频失败：{result.error}")
    else:
        produced = Path(result.output.get("path") or draft)
        report = vd.check_video(produced, min_seconds=0.5, expect_size=size)
        problems = list(report["problems"])
        actual = float(report["info"].get("duration_s") or 0.0)
        if planned > 0 and abs(actual - planned) / planned > DURATION_TOLERANCE:
            problems.append(f"成片时长 {actual}s 与计划 {planned}s 偏差超过 {int(DURATION_TOLERANCE * 100)}%")

    if problems:
        error = "；".join(problems)
        rec.record_step(task["id"], SKILL_ID, "failed", step_no=args.step_no,
                        adapter_used=result.adapter_id, error=error,
                        input_json={"package": src["path"].name if "path" in src else "", "count": len(images)},
                        output_json=result.to_dict(), duration_ms=rec.elapsed_ms(started), path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {error}", file=sys.stderr)
        return 1

    produced = Path(result.output["path"])
    duration_s = float(result.output.get("duration_s") or 0.0)
    duration_ms = rec.elapsed_ms(started)
    step_id = rec.record_step(task["id"], SKILL_ID, "ok", step_no=args.step_no,
                              adapter_used=result.adapter_id,
                              input_json={"count": len(images), "seconds_per_shot": args.seconds_per_shot,
                                          "fps": args.fps, "size": f"{size[0]}x{size[1]}"},
                              output_json={"draft": rec.rel_path(produced), "duration_s": duration_s},
                              duration_ms=duration_ms, path=args.db)
    art_id = rec.record_artifact(task["id"], "video", rec.rel_path(produced), step_run_id=step_id,
                                 model_version=result.model_version or "ffmpeg-slideshow-v1",
                                 prompt_version="none",
                                 meta={"role": "draft", "duration_s": duration_s, "count": len(images),
                                       "size": f"{size[0]}x{size[1]}", "adapter_used": result.adapter_id},
                                 path=args.db)

    info = {"task_id": task["id"], "topic_id": topic["id"], "skill": SKILL_ID,
            "adapter_used": result.adapter_id, "draft": rec.rel_path(produced),
            "duration_s": duration_s, "planned_duration_s": planned,
            "count": len(images), "size": f"{size[0]}x{size[1]}", "artifact_id": art_id, "step_run_id": step_id,
            "next": (f"关口② 剪辑干预：python3 .dsh/skills/hitl-gate/run.py open --task-id {task['id']} "
                     f"--gate gate2_edit_video；剪辑：python3 .dsh/skills/auto-editor/run.py edit --task-id {task['id']} --from-hitl")}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜适配器 {info['adapter_used']}｜草稿 {info['duration_s']}s（计划 {info['planned_duration_s']}s）"
              f"｜{info['count']} 镜｜{info['size']}")
        print(f"草稿文件：{info['draft']}")
        print("下一步：" + info["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="图生视频：24 张图 → 视频草稿")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="合成视频草稿")
    p_build.add_argument("--task-id", type=int, required=True)
    p_build.add_argument("--package", default=None, help="打包清单路径（默认取最近登记的 package 产物）")
    p_build.add_argument("--seconds-per-shot", type=float, default=3.0, help="每镜时长（秒）")
    p_build.add_argument("--fps", type=int, default=DEFAULT_FPS)
    p_build.add_argument("--size", default="720x1280", help="输出分辨率，形如 720x1280")
    p_build.add_argument("--out", default=None, help="输出文件（默认 workspace/topic-<id>/video/draft/draft-<时间戳>.mp4）")
    p_build.add_argument("--attempts", type=int, default=3)
    p_build.add_argument("--allow-paid", action="store_true", help="允许计费适配器（默认零付费，C-09）")
    p_build.add_argument("--step-no", type=int, default=None)
    p_build.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                         help="以 JSON 输出结果（也可写在子命令前）")
    p_build.set_defaults(func=cmd_build)

    for _action in parser._actions:  # 子命令也认 --json（写在子命令前后都行）
        if isinstance(_action, argparse._SubParsersAction):
            for _child in _action.choices.values():
                if not any("--json" in _a.option_strings for _a in _child._actions):
                    _child.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                                        help="以 JSON 输出结果（也可写在子命令前）")
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
