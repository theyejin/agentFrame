#!/usr/bin/env python3
# 文件用途：切图师 —— 把 6×4 整图等分成 24 张独立图片（shot-01…shot-24），并写出清单 latest.json。
# 对应需求：R-L1-06（整图 → 独立图片）、R-L1-19（24 张与 24 条分镜一一对应）、Q-11（先出整图再切、保留逐张重生成）、§6.5、C-09、R-L2-14（切分能力也可换适配器）。
# 对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html（grid-image-builder → image-splitter → 独立图 ×24）
# 维护提示：切分默认走 split 链（当前 split.grid-slicer 离线可跑）；行列数默认必须 6×4，改了要同步 storyboard-builder。
"""切图师（image-splitter）。

用法：
    python3 .dsh/skills/image-splitter/run.py split --task-id 1 [--grid PATH] [--cols 6] [--rows 4]
                                                   [--out DIR] [--prefix shot] [--start-no 1]
                                                   [--step-no N] [--allow-paid] [--json]

完成判据：
  ① 切出正好 cols×rows 张图（默认 24），命名连续 `shot-01.png …`；
  ② 尺寸一致、非空、单边 ≥ 64 像素；
  ③ 写出清单 `workspace/topic-<id>/images/shots/<时间戳>/latest.json`，并把 24 张登记为 artifacts；
  ④ 任务阶段推进到 `video`（图生视频的入口）。

退出码：0 = 成功；1 = 切分失败或自检不过（任务置 blocked）；2 = 输入校验不通过。
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
import images as im  # noqa: E402
import recording as rec  # noqa: E402
import text_utils as tu  # noqa: E402

SKILL_ID = "image-splitter"
DEFAULT_COLS, DEFAULT_ROWS = 6, 4
MIN_SIDE = 64


class InputError(ValueError):
    """上游没就绪或参数不合法。"""


def unique_dir(root: Path, name: str) -> Path:
    """同一秒内重复切分时，目录名依次加 -2 / -3，不覆盖上一代产物。"""
    cand, i = root / name, 2
    while cand.exists():
        cand = root / f"{name}-{i}"
        i += 1
    return cand


def resolve_grid(task_id: int, grid: str | None, db: str | None) -> Path:
    """整图来源：显式 --grid 优先，否则取最近一次登记的 grid 产物。"""
    if grid:
        path = Path(grid)
        if not path.is_absolute():
            path = dbm.REPO_ROOT / path
        if not path.is_file():
            raise InputError(f"--grid 指向的整图不存在：{grid}")
        return path
    art = rec.latest_artifact(task_id, "image", role="grid", path=db) or \
        rec.latest_artifact(task_id, "image", path_like="images/grid", path=db)
    if not art:
        raise InputError(f"任务 {task_id} 还没有整图产物：请先跑 grid-image-builder build")
    path = dbm.REPO_ROOT / art["path"]
    if not path.is_file():
        raise InputError(f"登记的整图文件已不在：{art['path']}")
    return path


def validate_input(task_id: int, cols: int, rows: int, grid: str | None,
                   db: str | None) -> tuple[dict, Path]:
    if cols < 1 or rows < 1:
        raise InputError(f"行列数必须为正：cols={cols} rows={rows}")
    bundle = rec.task_bundle(task_id, db)
    shots = rec.current_storyboards(task_id, db)
    problems = tu.check_storyboard_shape(shots, expected=cols * rows)
    if problems:
        raise InputError("分镜未就绪：" + "；".join(problems))
    return bundle, resolve_grid(task_id, grid, db)


def cmd_split(args: argparse.Namespace) -> int:
    try:
        bundle, grid_path = validate_input(args.task_id, args.cols, args.rows, args.grid, args.db)
        width, height = im.read_size(grid_path)
        if width % args.cols or height % args.rows:
            raise InputError(f"整图尺寸 {width}×{height} 不能被 {args.cols}×{args.rows} 整除，无法等分")
    except (InputError, rec.RecordingError, im.ImageError) as exc:
        try:  # 任务本身不存在时也要能优雅报错，不留半截流水
            rec.record_step(args.task_id, SKILL_ID, "failed", step_no=args.step_no,
                            error=f"输入校验不通过：{exc}", path=args.db)
        except rec.RecordingError as inner:
            print(f"[提示] 无法登记这次退回：{inner}", file=sys.stderr)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2

    task, topic = bundle["task"], bundle["topic"]
    shots = rec.current_storyboards(task["id"], args.db)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        root = rec.workspace_dir(topic["id"], "images/shots", args.db)
        out_dir = unique_dir(root, rec.timestamp_slug())
        out_dir.mkdir(parents=True, exist_ok=True)

    payload = {"abs_src": str(grid_path), "cols": args.cols, "rows": args.rows,
               "prefix": args.prefix, "ext": ".png", "start_no": args.start_no,
               "out_dir": str(out_dir)}
    started = dbm.now_iso()
    result = ar.invoke("split", payload, allow_paid=args.allow_paid)
    duration_ms = rec.elapsed_ms(started)

    problems: list[str] = []
    paths: list[Path] = []
    if not result.ok:
        problems = [f"切分失败：{result.error}"]
    else:
        items = result.output.get("shots") or result.output.get("images") or []
        paths = [Path(item["path"]) if Path(item["path"]).is_absolute() else dbm.REPO_ROOT / item["path"]
                 for item in items]
        report = im.check_images(paths, expected=args.cols * args.rows, prefix=args.prefix, min_side=MIN_SIDE)
        problems = list(report["problems"])

    if problems:
        error = "；".join(problems)
        rec.record_step(task["id"], SKILL_ID, "failed", step_no=args.step_no,
                        adapter_used=result.adapter_id, error=error,
                        input_json={"grid": rec.rel_path(grid_path), "cols": args.cols, "rows": args.rows},
                        output_json=result.to_dict(), duration_ms=duration_ms, path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {error}", file=sys.stderr)
        return 1

    scene_by_no = {int(s["shot_no"]): s["scene_text"] for s in shots}
    manifest = {
        "task_id": task["id"], "topic_id": topic["id"], "grid": rec.rel_path(grid_path),
        "cols": args.cols, "rows": args.rows, "prefix": args.prefix,
        "generated_at": dbm.now_iso(), "count": len(paths),
        "shots": [{"shot_no": args.start_no + i,
                   "file": rec.rel_path(path),
                   "width": im.read_size(path)[0], "height": im.read_size(path)[1],
                   "bytes": path.stat().st_size,
                   "scene_text": scene_by_no.get(args.start_no + i, "")}
                  for i, path in enumerate(paths)],
    }
    manifest_path = out_dir / "latest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    step_id = rec.record_step(task["id"], SKILL_ID, "ok", step_no=args.step_no,
                              adapter_used=result.adapter_id,
                              input_json={"grid": rec.rel_path(grid_path), "cols": args.cols, "rows": args.rows,
                                          "prefix": args.prefix, "start_no": args.start_no},
                              output_json={"count": len(paths), "manifest": rec.rel_path(manifest_path)},
                              duration_ms=duration_ms, path=args.db)
    # 切出来的图是本地派生产物：prompt_version 记 none（R-7-03 约定：非模型产物填 none/human）
    art_ids = [rec.record_artifact(task["id"], "image", rec.rel_path(path), step_run_id=step_id,
                                   model_version=result.model_version or "grid-slicer-v1",
                                   prompt_version="none",
                                   meta={"role": "shot", "shot_no": args.start_no + i,
                                         "window": out_dir.name, "grid": rec.rel_path(grid_path),
                                         "adapter_used": result.adapter_id},
                                   path=args.db)
               for i, path in enumerate(paths)]
    rec.record_artifact(task["id"], "manifest", rec.rel_path(manifest_path), step_run_id=step_id,
                        model_version="local", prompt_version="none",
                        meta={"role": "shots-manifest", "count": len(paths), "window": out_dir.name},
                        path=args.db)
    rec.update_task(task["id"], stage="video", path=args.db)

    info = {
        "task_id": task["id"], "topic_id": topic["id"], "skill": SKILL_ID,
        "adapter_used": result.adapter_id, "cols": args.cols, "rows": args.rows,
        "count": len(paths), "dir": rec.rel_path(out_dir), "manifest": rec.rel_path(manifest_path),
        "files": [rec.rel_path(p) for p in paths], "artifact_ids": art_ids, "step_run_id": step_id,
        "next": f"体检：image-consistency-checker check --task-id {task['id']}；或进入视频线：asset-packager pack --task-id {task['id']}",
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜适配器 {info['adapter_used']}｜切分 {info['cols']}×{info['rows']} = {info['count']} 张")
        print(f"目录：{info['dir']}（清单 {info['manifest']}）")
        print("下一步：" + info["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="切图师：6×4 整图 → 24 张独立图片")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_split = sub.add_parser("split", help="等分整图")
    p_split.add_argument("--task-id", type=int, required=True)
    p_split.add_argument("--grid", default=None, help="整图路径（默认取最近登记的 grid 产物）")
    p_split.add_argument("--cols", type=int, default=DEFAULT_COLS)
    p_split.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    p_split.add_argument("--out", default=None, help="输出目录（默认 workspace/topic-<id>/images/shots/<时间戳>）")
    p_split.add_argument("--prefix", default="shot", help="文件名前缀（默认 shot → shot-01.png）")
    p_split.add_argument("--start-no", type=int, default=1, help="起始编号（默认 1）")
    p_split.add_argument("--step-no", type=int, default=None)
    p_split.add_argument("--allow-paid", action="store_true")
    p_split.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                             help="以 JSON 输出结果（也可写在子命令前）")
    p_split.set_defaults(func=cmd_split)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
