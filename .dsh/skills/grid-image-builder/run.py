#!/usr/bin/env python3
# 文件用途：整图生成师 —— 把 24 条分镜按 6×4 画进**一张**整图，供 image-splitter 等分切成 24 张独立图。
# 对应需求：R-L1-06（分镜 → 图片）、R-L1-19（24 条分镜与 24 格一一对应）、§6.5 交接契约、C-09、R-L2-14。
# 对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html（grid-image-builder → 整图 6×4）
# 维护提示：网格行列来自参数而不是写死常量，但默认必须是 6×4（规格 Q-11：先出整图再切）；改提示词要升 version。
"""整图生成师（grid-image-builder）。

用法：
    python3 .dsh/skills/grid-image-builder/run.py build --task-id 1 [--cols 6] [--rows 4]
                                                       [--cell-w 320] [--cell-h 320] [--style-hint "…"]
                                                       [--out DIR] [--attempts 3] [--allow-paid] [--json]

完成判据：
  ① 整图真实存在且非空，尺寸正好等于 (cols×cell_w) × (rows×cell_h)；
  ② 分镜数量与格数一致（24 = 6×4），否则进场就退回；
  ③ 登记 artifacts（kind=image，meta 里带 cols/rows/cell/cells）与一条 ok 的 step_runs。

退出码：0 = 成功；1 = 出图失败或自检不过（任务置 blocked）；2 = 输入校验不通过。
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
import prompt_templates as pt  # noqa: E402
import recording as rec  # noqa: E402
import text_utils as tu  # noqa: E402

SKILL_ID = "grid-image-builder"
PROMPT_KEY = "image-grid"
DEFAULT_STYLE_HINT = "真实感、生活化、竖屏人物特写，光线自然，全图色调统一，避免文字水印"
DEFAULT_COLS, DEFAULT_ROWS = 6, 4
MIN_CELL_SIDE = 32


class InputError(ValueError):
    """上游没就绪或参数不合法。"""


def validate_input(task_id: int, cols: int, rows: int, cell_w: int, cell_h: int, db: str | None) -> dict:
    if cols < 1 or rows < 1:
        raise InputError(f"行列数必须为正：cols={cols} rows={rows}")
    if cell_w < MIN_CELL_SIDE or cell_h < MIN_CELL_SIDE:
        raise InputError(f"单格尺寸至少 {MIN_CELL_SIDE}×{MIN_CELL_SIDE}，收到 {cell_w}×{cell_h}")
    bundle = rec.task_bundle(task_id, db)
    task = bundle["task"]
    if not task.get("selected_plan"):
        raise InputError(f"任务 {task_id} 还没选定文案：请先过关口① gate1_select_copy")
    shots = rec.current_storyboards(task_id, db)
    problems = tu.check_storyboard_shape(shots, expected=cols * rows)
    if problems:
        raise InputError("分镜未就绪：" + "；".join(problems))
    return bundle


def shots_brief(shots: list[dict]) -> str:
    """把分镜压成「01 画面描述（镜头提示）」的 24 行清单喂给提示词。"""
    lines = []
    for shot in shots:
        note = (shot.get("camera_note") or "").strip()
        lines.append(f"{int(shot['shot_no']):02d} {shot['scene_text'].strip()}" + (f"（{note}）" if note else ""))
    return "\n".join(lines)


def cmd_build(args: argparse.Namespace) -> int:
    try:
        bundle = validate_input(args.task_id, args.cols, args.rows, args.cell_w, args.cell_h, args.db)
    except (InputError, rec.RecordingError) as exc:
        try:  # 任务本身不存在时也要能优雅报错，不留半截流水
            rec.record_step(args.task_id, SKILL_ID, "failed", step_no=args.step_no,
                            error=f"输入校验不通过：{exc}", path=args.db)
        except rec.RecordingError as inner:
            print(f"[提示] 无法登记这次退回：{inner}", file=sys.stderr)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2

    task, topic = bundle["task"], bundle["topic"]
    shots = rec.current_storyboards(task["id"], args.db)
    style_hint = (args.style_hint or "").strip() or DEFAULT_STYLE_HINT
    tpl = pt.load(PROMPT_KEY)
    prompt = tpl.render({
        "topic_title": topic.get("title", ""),
        "shots_brief": shots_brief(shots),
        "grid": f"{args.cols}×{args.rows}",
        "cell_size": f"{args.cell_w}×{args.cell_h} 像素",
        "platform": task.get("target_platform") or "未指定",
        "style_hint": style_hint,
    })

    out_dir = Path(args.out) if args.out else rec.workspace_dir(topic["id"], "images/grid", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rec.unique_stamp(out_dir, "grid", ".png")
    grid_path = out_dir / f"grid-{stamp}.png"
    expect = (args.cols * args.cell_w, args.rows * args.cell_h)

    payload = {
        "prompt": prompt, "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
        "abs_path": str(grid_path), "cols": args.cols, "rows": args.rows,
        "cell_w": args.cell_w, "cell_h": args.cell_h,
        "labels": [shot["scene_text"][:24] for shot in shots],
        "title": f"{topic.get('title', '')} · {args.cols}×{args.rows}",
    }
    started = dbm.now_iso()
    problems: list[str] = []
    result = None
    for attempt in range(1, max(1, args.attempts) + 1):
        result = ar.invoke("image", payload, allow_paid=args.allow_paid)
        if not result.ok:
            problems = [f"第 {attempt} 次出图失败：{result.error}"]
            break
        if not grid_path.is_file() or grid_path.stat().st_size <= 0:
            problems = [f"第 {attempt} 次出图后没有拿到整图文件：{grid_path.name}"]
            continue
        size = im.read_size(grid_path)
        if size != expect:
            problems = [f"第 {attempt} 次整图尺寸不符：应为 {expect[0]}×{expect[1]}，实际 {size[0]}×{size[1]}"]
            continue
        problems = []
        break
    duration_ms = rec.elapsed_ms(started)

    if problems:
        error = "；".join(problems)
        rec.record_step(task["id"], SKILL_ID, "failed", step_no=args.step_no,
                        adapter_used=(result.adapter_id if result else ""), error=error,
                        input_json={"prompt_key": tpl.prompt_key, "prompt_version": tpl.version},
                        output_json=result.to_dict() if result else {}, duration_ms=duration_ms, path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {error}", file=sys.stderr)
        return 1

    size = im.read_size(grid_path)
    step_id = rec.record_step(task["id"], SKILL_ID, "ok", step_no=args.step_no,
                              adapter_used=result.adapter_id,
                              input_json={"prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
                                          "cols": args.cols, "rows": args.rows,
                                          "cell": f"{args.cell_w}x{args.cell_h}"},
                              output_json={"path": rec.rel_path(grid_path), "size": f"{size[0]}x{size[1]}"},
                              duration_ms=duration_ms, path=args.db)
    art_id = rec.record_artifact(task["id"], "image", rec.rel_path(grid_path), step_run_id=step_id,
                                 model_version=result.model_version or "unknown", prompt_version=tpl.version,
                                 meta={"role": "grid", "cols": args.cols, "rows": args.rows,
                                       "cell_w": args.cell_w, "cell_h": args.cell_h, "cells": args.cols * args.rows,
                                       "width": size[0], "height": size[1],
                                       "window": f"grid-{stamp}", "adapter_used": result.adapter_id},
                                 path=args.db)
    info = {
        "task_id": task["id"], "topic_id": topic["id"], "skill": SKILL_ID,
        "adapter_used": result.adapter_id, "model_version": result.model_version,
        "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
        "grid": f"{args.cols}x{args.rows}", "cells": args.cols * args.rows,
        "size": f"{size[0]}x{size[1]}", "file": rec.rel_path(grid_path),
        "artifact_id": art_id, "step_run_id": step_id,
        "next": f"切分：image-splitter split --task-id {task['id']}",
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜适配器 {info['adapter_used']}｜{info['prompt_key']} {info['prompt_version']}")
        print(f"整图 {info['grid']}（{info['cells']} 格）{info['size']}：{info['file']}")
        print("下一步：" + info["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="整图生成师：24 条分镜 → 一张 6×4 整图")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="生成整图")
    p_build.add_argument("--task-id", type=int, required=True)
    p_build.add_argument("--cols", type=int, default=DEFAULT_COLS)
    p_build.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    p_build.add_argument("--cell-w", type=int, default=320)
    p_build.add_argument("--cell-h", type=int, default=320)
    p_build.add_argument("--style-hint", default="")
    p_build.add_argument("--out", default=None, help="产物目录（默认 workspace/topic-<id>/images/grid）")
    p_build.add_argument("--attempts", type=int, default=3)
    p_build.add_argument("--step-no", type=int, default=None)
    p_build.add_argument("--allow-paid", action="store_true")
    p_build.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                             help="以 JSON 输出结果（也可写在子命令前）")
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
