#!/usr/bin/env python3
# 文件用途：成片导出 —— 把剪辑版定稿为最终成片，并用 ffmpeg 抽一帧做封面图，任务推进到分发环节。
# 对应需求：R-L1-08（导出成片）、R-7-03（产物登记模型版本）、§6.5（视频能力走适配器）、Q-7、C-09。
# 对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html（auto-editor → video-exporter → 成片 mp4 + 封面帧）
# 维护提示：封面帧抽取用 video.ffmpeg（ffmpeg 已接），最终成片是剪辑版的定稿副本，不重复编码。
"""成片导出（video-exporter）。

用法：
    python3 .dsh/skills/video-exporter/run.py export --task-id 1 [--edited FILE] [--cover-at 1.0]
                                                     [--out-dir DIR] [--allow-paid] [--step-no N] [--json]

完成判据：
  ① 已存在剪辑版产物（role=edited，见 auto-editor）或显式给了 --edited；
  ② 产出 `workspace/topic-<选题号>/video/final/final-<时间戳>.mp4` 与 `cover-<时间戳>.png`；
  ③ 成片可被 ffprobe 读出、分辨率与成片一致、封面帧文件非空；
  ④ 登记 kind=video（role=final）与 kind=image（role=cover）两条产物，任务 stage 推进到 publish。

退出码：0 = 成功；1 = 导出失败或自检不过（任务置 blocked）；2 = 输入校验不通过。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import db as dbm  # noqa: E402
import recording as rec  # noqa: E402
import video as vd  # noqa: E402

SKILL_ID = "video-exporter"
LINE = "video"
COVER_MODEL_VERSION = "ffmpeg-cover-v1"


class InputError(ValueError):
    """上游没就绪或参数不合法。"""


def resolve_edited(task_id: int, explicit: str | None, db: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = dbm.REPO_ROOT / path
        if not path.is_file():
            raise InputError(f"--edited 给的文件不存在：{explicit}")
        return path
    art = rec.latest_artifact(task_id, "video", role="edited", path=db)
    if not art:
        raise InputError(f"任务 {task_id} 还没有剪辑版产物：请先跑 auto-editor edit")
    path = dbm.REPO_ROOT / art["path"]
    if not path.is_file():
        raise InputError(f"剪辑版产物文件不存在：{art['path']}")
    return path


def cmd_export(args: argparse.Namespace) -> int:
    started = dbm.now_iso()
    try:
        task = rec.task_bundle(args.task_id, path=args.db)["task"]
        vd.require_ffmpeg()
        edited = resolve_edited(task["id"], args.edited, args.db)
    except (InputError, rec.RecordingError, vd.VideoError) as exc:
        try:
            rec.record_step(args.task_id, SKILL_ID, "failed", step_no=args.step_no,
                            error=f"输入校验不通过：{exc}", path=args.db)
        except rec.RecordingError as inner:
            print(f"[提示] 无法登记这次退回：{inner}", file=sys.stderr)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else rec.workspace_dir(task["topic_id"], f"{LINE}/final", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rec.timestamp_slug()
    final = out_dir / f"final-{stamp}.mp4"
    cover = out_dir / f"cover-{stamp}.png"

    problems: list[str] = []
    try:
        shutil.copy2(edited, final)
        vd.extract_cover(edited, cover, at_s=float(args.cover_at))
    except (OSError, vd.VideoError) as exc:
        problems.append(f"导出失败：{exc}")

    report: dict = {"problems": [], "warnings": [], "info": {}}
    if not problems:
        report = vd.check_video(final, min_seconds=0.5, cover=cover)
        problems = list(report["problems"])

    if problems:
        error = "；".join(problems)
        rec.record_step(task["id"], SKILL_ID, "failed", step_no=args.step_no,
                        adapter_used="video.ffmpeg", error=error,
                        input_json={"edited": rec.rel_path(edited)}, duration_ms=rec.elapsed_ms(started),
                        path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {error}", file=sys.stderr)
        return 1

    info_video = report["info"]
    duration_ms = rec.elapsed_ms(started)
    step_id = rec.record_step(task["id"], SKILL_ID, "ok", step_no=args.step_no,
                              adapter_used="video.ffmpeg",
                              input_json={"edited": rec.rel_path(edited), "cover_at_s": args.cover_at},
                              output_json={"final": rec.rel_path(final), "cover": rec.rel_path(cover),
                                           "duration_s": info_video.get("duration_s"),
                                           "size": [info_video.get("width"), info_video.get("height")]},
                              duration_ms=duration_ms, path=args.db)
    art_id = rec.record_artifact(task["id"], "video", rec.rel_path(final), step_run_id=step_id,
                                 model_version="ffmpeg-render-v1", prompt_version="none",
                                 meta={"role": "final", "source": rec.rel_path(edited),
                                       "duration_s": info_video.get("duration_s"),
                                       "width": info_video.get("width"), "height": info_video.get("height")},
                                 path=args.db)
    cover_id = rec.record_artifact(task["id"], "image", rec.rel_path(cover), step_run_id=step_id,
                                   model_version=COVER_MODEL_VERSION, prompt_version="none",
                                   meta={"role": "cover", "at_s": args.cover_at,
                                         "from": rec.rel_path(final)},
                                   path=args.db)
    rec.update_task(task["id"], stage="publish", path=args.db)

    out = {"task_id": task["id"], "topic_id": task["topic_id"], "skill": SKILL_ID,
           "adapter_used": "video.ffmpeg", "final": rec.rel_path(final), "cover": rec.rel_path(cover),
           "duration_s": info_video.get("duration_s"), "size": [info_video.get("width"), info_video.get("height")],
           "artifact_ids": {"final": art_id, "cover": cover_id}, "stage": "publish",
           "next": f"准备发布信息：python3 .dsh/skills/title-cover-prep/run.py prepare --task-id {task['id']}"}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜成片 {out['final']}（{out['duration_s']}s）")
        print(f"封面帧：{out['cover']}")
        print("下一步：" + out["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="成片导出：定稿成片 + 抽封面帧")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="导出成片与封面")
    p_export.add_argument("--task-id", type=int, required=True)
    p_export.add_argument("--edited", default=None, help="剪辑版路径（默认取最近登记的 edited 产物）")
    p_export.add_argument("--cover-at", type=float, default=1.0, help="抽封面帧的时间点（秒）")
    p_export.add_argument("--out-dir", default=None, help="输出目录（默认 workspace/topic-<id>/video/final）")
    p_export.add_argument("--allow-paid", action="store_true", help="允许计费适配器（默认零付费，C-09）")
    p_export.add_argument("--step-no", type=int, default=None)
    p_export.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                          help="以 JSON 输出结果（也可写在子命令前）")
    p_export.set_defaults(func=cmd_export)

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
