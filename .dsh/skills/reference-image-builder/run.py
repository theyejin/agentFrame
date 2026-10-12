#!/usr/bin/env python3
# 文件用途：参考图生成师 —— 依据关口① 选定的文案生成 1–3 张风格参考图，作为整图（6×4）的视觉基准。
# 对应需求：R-L1-06（图文素材生成）、R-L1-19（下游 24 张图一致性的上游基准）、§6.5 交接契约、§8.3（风格确认属调整态人工关口）、C-09（零付费门禁）、R-L2-14（只认 kind，不写服务名）。
# 对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html（reference-image-builder → 人的风格确认）
# 维护提示：出图一律走 ar.invoke("image", …)；改提示词必须升 templates/prompts/image-reference.md 的 version 并补 templates/mock 样例。
"""参考图生成师（reference-image-builder）。

用法：
    python3 .dsh/skills/reference-image-builder/run.py build --task-id 1 [--count 2] [--style-hint "…"]
                                                          [--out DIR] [--cell-w 720] [--cell-h 1280]
                                                          [--attempts 3] [--allow-paid] [--json]

完成判据：
  ① 参考图数量等于 `--count`（1–3），每张真实非空、单边 ≥ 128 像素、竖屏（高 > 宽）；
  ② 每张都登记为 artifacts（带 model_version 与 prompt_version）；
  ③ step_runs 记一条 ok，产物落 workspace/topic-<id>/images/reference/。

退出码：0 = 成功；1 = 出图失败或自检不过（任务置 blocked）；2 = 输入校验不通过（上游没就绪）。
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

SKILL_ID = "reference-image-builder"
PROMPT_KEY = "image-reference"
DEFAULT_STYLE_HINT = "真实感、生活化、竖屏 9:16，光线自然，避免文字水印"
ASPECT_RATIO = "9:16 竖屏"
EXCERPT_CHARS = 120
MIN_SIDE = 128


class InputError(ValueError):
    """上游没就绪或参数不合法 —— 进场前就该挡住。"""


def validate_input(task_id: int, count: int, db: str | None) -> dict:
    """进场校验：必须已过关口①、必须已有 24 条连续分镜（R-L1-19）。"""
    if not 1 <= count <= 3:
        raise InputError(f"参考图数量只能是 1–3 张，收到 {count}")
    bundle = rec.task_bundle(task_id, db)
    task = bundle["task"]
    if not task.get("selected_plan"):
        raise InputError(f"任务 {task_id} 还没选定文案（selected_plan 为空）：请先过关口① gate1_select_copy")
    if rec.selected_copy(task_id, db) is None:
        raise InputError(f"任务 {task_id} 选定的第 {task['selected_plan']} 套文案不存在或已失效")
    shots = rec.current_storyboards(task_id, db)
    problems = tu.check_storyboard_shape(shots, expected=24)
    if problems:
        raise InputError("分镜未就绪：" + "；".join(problems))
    return bundle


def build_prompt(tpl, bundle: dict, style_hint: str, count: int) -> str:
    task, topic = bundle["task"], bundle["topic"]
    variant = rec.selected_copy(task["id"])
    body = (variant or {}).get("body", "")
    return tpl.render({
        "topic_title": topic.get("title", ""),
        "selected_copy_excerpt": body[:EXCERPT_CHARS] + ("…" if len(body) > EXCERPT_CHARS else ""),
        "platform": task.get("target_platform") or "未指定",
        "style_hint": style_hint,
        "count": count,
        "aspect_ratio": ASPECT_RATIO,
    })


def check_images(paths: list[Path], count: int) -> list[str]:
    """自检：数量、非空、单边、竖屏。"""
    problems: list[str] = []
    if len(paths) != count:
        problems.append(f"参考图数量应为 {count}，实际 {len(paths)}")
    for path in paths:
        if not path.is_file() or path.stat().st_size <= 0:
            problems.append(f"参考图不存在或为空：{path.name}")
            continue
        width, height = im.read_size(path)
        if min(width, height) < MIN_SIDE:
            problems.append(f"参考图过小（{width}×{height}）：{path.name}")
        if width >= height:
            problems.append(f"参考图不是竖屏（{width}×{height}）：{path.name}")
    return problems


def cmd_build(args: argparse.Namespace) -> int:
    try:
        bundle = validate_input(args.task_id, args.count, args.db)
    except (InputError, rec.RecordingError) as exc:
        try:  # 任务本身不存在时也要能优雅报错，不留半截流水
            rec.record_step(args.task_id, SKILL_ID, "failed", step_no=args.step_no,
                            error=f"输入校验不通过：{exc}", path=args.db)
        except rec.RecordingError as inner:
            print(f"[提示] 无法登记这次退回：{inner}", file=sys.stderr)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2

    task, topic = bundle["task"], bundle["topic"]
    style_hint = (args.style_hint or "").strip() or DEFAULT_STYLE_HINT
    tpl = pt.load(PROMPT_KEY)
    prompt = build_prompt(tpl, bundle, style_hint, args.count)

    out_dir = Path(args.out) if args.out else rec.workspace_dir(topic["id"], "images/reference", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = rec.timestamp_slug()
    n = 1
    while True:                      # 同秒重跑时整批一起避让，历史产物不能被覆盖
        stamp = base if n == 1 else f"{base}-{n}"
        paths = [out_dir / f"reference-{stamp}-{i:02d}.png" for i in range(1, args.count + 1)]
        if not any(p.exists() for p in paths):
            break
        n += 1

    payload = {
        "prompt": prompt, "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
        "count": args.count, "paths": [str(p) for p in paths],
        "cell_w": args.cell_w, "cell_h": args.cell_h,
        "topic_title": topic.get("title", ""), "style_hint": style_hint,
    }
    started = dbm.now_iso()
    problems: list[str] = []
    result = None
    for attempt in range(1, max(1, args.attempts) + 1):
        result = ar.invoke("image", payload, allow_paid=args.allow_paid)
        if not result.ok:
            problems = [f"第 {attempt} 次出图失败：{result.error}"]
            break
        problems = check_images(paths, args.count)
        if not problems:
            break
        problems = [f"第 {attempt} 次出图不合格：" + "；".join(problems)]
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

    step_id = rec.record_step(task["id"], SKILL_ID, "ok", step_no=args.step_no,
                              adapter_used=result.adapter_id,
                              input_json={"prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
                                          "count": args.count, "style_hint": style_hint},
                              output_json={"paths": [rec.rel_path(p) for p in paths],
                                           "model_version": result.model_version},
                              duration_ms=duration_ms, path=args.db)
    art_ids = []
    for i, path in enumerate(paths, start=1):
        art_ids.append(rec.record_artifact(task["id"], "image", rec.rel_path(path), step_run_id=step_id,
                                           model_version=result.model_version or "unknown",
                                           prompt_version=tpl.version,
                                           meta={"role": "reference", "index": i, "count": args.count,
                                                 "window": f"reference-{stamp}", "adapter_used": result.adapter_id},
                                           path=args.db))
    info = {
        "task_id": task["id"], "topic_id": topic["id"], "skill": SKILL_ID,
        "adapter_used": result.adapter_id, "model_version": result.model_version,
        "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
        "count": len(paths), "files": [rec.rel_path(p) for p in paths],
        "artifact_ids": art_ids, "step_run_id": step_id,
        "next": f"等风格确认：hitl-gate open --task-id {task['id']} --gate gate_visual_style",
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜适配器 {info['adapter_used']}｜{info['prompt_key']} {info['prompt_version']}")
        print(f"参考图 {info['count']} 张：" + "、".join(info["files"]))
        print("下一步：" + info["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="参考图生成师：文案 → 1–3 张风格参考图")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="生成参考图")
    p_build.add_argument("--task-id", type=int, required=True)
    p_build.add_argument("--count", type=int, default=2, help="参考图张数 1–3（默认 2）")
    p_build.add_argument("--style-hint", default="", help="风格提示（留空用默认基准）")
    p_build.add_argument("--out", default=None, help="产物目录（默认 workspace/topic-<id>/images/reference）")
    p_build.add_argument("--cell-w", type=int, default=720, help="单张宽（默认 720）")
    p_build.add_argument("--cell-h", type=int, default=1280, help="单张高（默认 1280，竖屏）")
    p_build.add_argument("--attempts", type=int, default=3, help="自检不过时的重试次数（默认 3）")
    p_build.add_argument("--step-no", type=int, default=None)
    p_build.add_argument("--allow-paid", action="store_true", help="允许调用计费适配器（C-09 默认禁止）")
    p_build.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                             help="以 JSON 输出结果（也可写在子命令前）")
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
