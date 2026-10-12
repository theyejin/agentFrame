#!/usr/bin/env python3
# 文件用途：素材打包 —— 把选定文案 + 24 张独立图 + 24 条分镜按顺序打包成视频线工程文件夹（含 manifest.json）。
# 对应需求：R-L1-07（文案与图片打包成文件夹）、R-L1-19（24 张图与 24 条分镜一一对应）、§6.5、C-09（纯本地，不调外部服务）。
# 对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html（图文包 → asset-packager → 打包文件夹）
# 维护提示：打包清单是下游 image-to-video / auto-editor 的唯一输入契约，改字段必须同步这两个 skill 与测试。
"""素材打包（asset-packager）。

用法：
    python3 .dsh/skills/asset-packager/run.py pack --task-id 1 [--out DIR] [--shot-seconds 3]
                                                    [--step-no N] [--json]

完成判据：
  ① 关口① 已选定文案、24 条分镜与 24 张独立图都在（缺一个就退回，不许先打包再补）；
  ② 产出 `workspace/topic-<选题号>/video/package/<时间戳>/`：`images/shot-NN.png` + `copy.md` + `manifest.json`；
  ③ manifest 每镜都有 shot_no / 图片路径 / 场景描述 / 时长，总时长可算（下游据此排片）；
  ④ 登记 kind=manifest、role=package 的产物（本地派生产物：model_version=local、prompt_version=none）。

退出码：0 = 成功；1 = 打包失败（任务置 blocked）；2 = 输入校验不通过。
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
import images as im  # noqa: E402
import recording as rec  # noqa: E402

SKILL_ID = "asset-packager"
SHOT_TOTAL = 24
LINE = "video"
DEFAULT_SHOT_SECONDS = 3.0


class InputError(ValueError):
    """上游没就绪或参数不合法。"""


def unique_dir(root: Path, name: str) -> Path:
    """同一秒内重复打包时目录名加 -2 / -3，绝不覆盖上一代工程文件夹。"""
    cand, i = root / name, 2
    while cand.exists():
        cand = root / f"{name}-{i}"
        i += 1
    return cand


def validate_input(task_id: int, db: str | None) -> tuple[dict, dict, list[dict]]:
    """进场三件事：任务在不在、文案选没选、24 张图与 24 条分镜齐不齐。"""
    bundle = rec.task_bundle(task_id, path=db)
    topic, task = bundle["topic"], bundle["task"]
    if not rec.selected_copy(task_id, path=db):
        raise InputError(f"任务 {task_id} 还没过关口①（未选定文案）：请先 hitl-gate resolve，再打包")
    storyboards = rec.current_storyboards(task_id, path=db)
    if len(storyboards) != SHOT_TOTAL:
        raise InputError(f"分镜应为 {SHOT_TOTAL} 条，实际 {len(storyboards)} 条")
    shots = rec.latest_shots(task_id, path=db)
    if len(shots) != SHOT_TOTAL:
        raise InputError(f"独立图应为 {SHOT_TOTAL} 张（最近一代切图），实际 {len(shots)} 张：请先跑 image-splitter split")
    missing = [s["file"] for s in shots if not (dbm.REPO_ROOT / s["file"]).is_file()]
    if missing:
        raise InputError(f"这些独立图文件已不在：{'、'.join(missing[:3])}{'…' if len(missing) > 3 else ''}")
    return task, topic, shots


def cmd_pack(args: argparse.Namespace) -> int:
    started = dbm.now_iso()
    try:
        task, topic, shots = validate_input(args.task_id, args.db)
    except (InputError, rec.RecordingError) as exc:
        try:
            rec.record_step(args.task_id, SKILL_ID, "failed", step_no=args.step_no,
                            error=f"输入校验不通过：{exc}", path=args.db)
        except rec.RecordingError as inner:
            print(f"[提示] 无法登记这次退回：{inner}", file=sys.stderr)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2
    if args.shot_seconds <= 0:
        print("[错误] 输入校验不通过：--shot-seconds 必须大于 0", file=sys.stderr)
        return 2

    copy = rec.selected_copy(task["id"], path=args.db) or {}
    base = Path(args.out) if args.out else rec.workspace_dir(topic["id"], f"{LINE}/package", args.db)
    pkg = unique_dir(base, rec.timestamp_slug()) if not args.out else Path(args.out)
    images_dir = pkg / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    scene_by_no = {int(s["shot_no"]): s.get("scene_text", "") for s in shots}
    packed: list[dict] = []
    for shot in shots:
        no = int(shot["shot_no"])
        src = dbm.REPO_ROOT / shot["file"]
        dst = images_dir / f"shot-{no:02d}{src.suffix.lower() or '.png'}"
        shutil.copy2(src, dst)
        packed.append({
            "shot_no": no,
            "image": rec.rel_path(dst),
            "source_image": shot["file"],
            "scene_text": scene_by_no.get(no, shot.get("scene_text", "")),
            "duration_s": float(args.shot_seconds),
        })

    copy_md = pkg / "copy.md"
    copy_md.write_text(
        f"# 选定文案（第 {copy.get('plan_no', '?')} 套 · 侧重 {copy.get('focus', '?')}）\n\n"
        f"{copy.get('title', '')}\n\n{copy.get('body', '')}\n",
        encoding="utf-8")

    manifest = {
        "task_id": task["id"], "topic_id": topic["id"], "skill": SKILL_ID,
        "platform": task["target_platform"], "content_type": task["content_type"],
        "plan_no": copy.get("plan_no"), "focus": copy.get("focus", ""),
        "copy_file": rec.rel_path(copy_md), "count": len(packed),
        "shot_seconds": float(args.shot_seconds),
        "total_seconds": round(len(packed) * float(args.shot_seconds), 3),
        "generated_at": dbm.now_iso(), "shots": packed,
    }
    manifest_path = pkg / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    duration_ms = rec.elapsed_ms(started)
    step_id = rec.record_step(task["id"], SKILL_ID, "ok", step_no=args.step_no,
                              input_json={"shots": len(shots), "plan_no": copy.get("plan_no")},
                              output_json={"package": rec.rel_path(pkg), "count": len(packed),
                                           "total_seconds": manifest["total_seconds"]},
                              duration_ms=duration_ms, path=args.db)
    art_id = rec.record_artifact(task["id"], "manifest", rec.rel_path(manifest_path), step_run_id=step_id,
                                 model_version="local", prompt_version="none",
                                 meta={"role": "package", "count": len(packed),
                                       "total_seconds": manifest["total_seconds"], "window": pkg.name},
                                 path=args.db)

    info = {"task_id": task["id"], "topic_id": topic["id"], "skill": SKILL_ID,
            "package": rec.rel_path(pkg), "manifest": rec.rel_path(manifest_path),
            "copy_file": rec.rel_path(copy_md), "count": len(packed),
            "total_seconds": manifest["total_seconds"], "artifact_id": art_id, "step_run_id": step_id,
            "next": f"图生视频：python3 .dsh/skills/image-to-video/run.py build --task-id {task['id']}"}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜已打包 {info['count']} 镜｜总时长 {info['total_seconds']}s")
        print(f"工程文件夹：{info['package']}（清单 {info['manifest']}）")
        print("下一步：" + info["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="素材打包：选定文案 + 24 张图 → 视频线工程文件夹")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pack = sub.add_parser("pack", help="按分镜顺序打包图文")
    p_pack.add_argument("--task-id", type=int, required=True)
    p_pack.add_argument("--out", default=None, help="输出目录（默认 workspace/topic-<id>/video/package/<时间戳>）")
    p_pack.add_argument("--shot-seconds", type=float, default=DEFAULT_SHOT_SECONDS, help="每镜默认时长（秒）")
    p_pack.add_argument("--step-no", type=int, default=None)
    p_pack.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="以 JSON 输出结果（也可写在子命令前）")
    p_pack.set_defaults(func=cmd_pack)

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
