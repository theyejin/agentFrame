#!/usr/bin/env python3
# 文件用途：storyboard-builder 的实现入口 —— 把关口① 选定的文案拆成 24 条分镜场景内容（6×4）。
# 对应需求：R-L1-06（分镜拆解）、R-L1-19（24 条且编号连续）、R-L1-18（未选文案不得往下走）、R-7-03（记录模型与提示词版本）。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（storyboard-builder → storyboard.json）
# 维护提示：条数（24）与网格（6×4）是跨环节契约，改动要同步 db/schema.sql 的 storyboards.shot_no 上限、提示词与 docs/skill-roster.md。
"""storyboard-builder 命令行入口。

    build --task-id N [--out DIR] [--shot-seconds 3] [--style-hint "…"] [--attempts 3] [--allow-paid] [--json]

前置条件：任务必须已经过关口①（`tasks.selected_plan` 有值）。没有选定文案就直接拒绝，避免「拿一套没选的稿子去拍」。
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
import prompt_templates as pt  # noqa: E402
import recording as rec  # noqa: E402
import text_utils as tu  # noqa: E402

PROMPT_KEY = "storyboard-split"
SHOT_TOTAL = 24          # 分镜总数（跨环节契约：视觉线必须收到 24 条）
GRID = "6x4"
DEFAULT_SHOT_SECONDS = 3.0
DEFAULT_STYLE_HINT = "真实感、生活化、竖屏 9:16，光线自然，避免文字水印"
DEFAULT_ATTEMPTS = 3


class InputError(ValueError):
    """输入校验不通过（R-L1-18）。"""


def validate_input(bundle: dict) -> dict:
    task = bundle["task"]
    if task.get("selected_plan") not in (1, 2, 3):
        raise InputError(f"任务 {task['id']} 还没有选定文案：请先过关口①"
                         f"（hitl-gate resolve --task-id {task['id']} --gate gate1_select_copy --action confirm --actor 名字 --plan-no 1）")
    variant = dbm.query_one(
        "SELECT * FROM copy_variants WHERE task_id = ? AND plan_no = ? AND status = 'active'",
        (task["id"], task["selected_plan"]), bundle.get("_db"))
    if variant is None:
        raise InputError(f"任务 {task['id']} 选定的第 {task['selected_plan']} 套文案不存在或已失效（status 不是 active）")
    if not (variant["body"] or "").strip():
        raise InputError(f"第 {task['selected_plan']} 套文案正文为空：不能拆分镜")
    return dict(variant)


def check_shots(shots: list[dict], shot_seconds: float) -> list[str]:
    """自检 24 条分镜（R-L1-19）。返回问题清单，空列表=通过。"""
    problems = tu.check_storyboard_shape(shots, expected=SHOT_TOTAL)
    target = shot_seconds * SHOT_TOTAL
    total = sum(float(s.get("duration_s") or 0) for s in shots)
    if abs(total - target) > 0.01:
        problems.append(f"总时长 {total:g} 秒与目标 {target:g} 秒不一致（{SHOT_TOTAL} 条 × {shot_seconds:g} 秒）")
    return problems


def render_files(out_dir: Path, bundle: dict, variant: dict, shots: list[dict], meta: dict) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    task, topic = bundle["task"], bundle["topic"]
    payload = {
        "task_id": task["id"], "topic_id": topic["id"], "topic_title": topic["title"],
        "plan_no": variant["plan_no"], "focus": variant["focus"],
        "grid": GRID, "shot_total": SHOT_TOTAL, "shot_seconds": meta["shot_seconds"],
        "style_hint": meta["style_hint"],
        "prompt_key": meta["prompt_key"], "prompt_version": meta["prompt_version"],
        "model_version": meta["model_version"], "adapter_used": meta["adapter_used"],
        "generated_at": dbm.now_iso(), "stamp": meta["stamp"],
        "shots": [{"shot_no": s["shot_no"], "scene_text": s["scene_text"],
                   "camera_note": s["camera_note"], "duration_s": s["duration_s"]} for s in shots],
    }
    json_path = out_dir / f"storyboard-{meta['stamp']}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [f"# {topic['title']} · 分镜脚本（{SHOT_TOTAL} 条 / {GRID}）", "",
                f"- 选定方案：方案 {variant['plan_no']}（侧重 {variant['focus']}）　每条 {meta['shot_seconds']:g} 秒　总时长 {meta['shot_seconds'] * SHOT_TOTAL:g} 秒",
                f"- 提示词：{meta['prompt_key']} {meta['prompt_version']}　模型：{meta['model_version']}", ""]
    for s in shots:
        md_lines.append(f"{s['shot_no']:02d} | {s['scene_text']} | {s['camera_note']}")
    md_path = out_dir / "storyboard.md"
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
    return [json_path, md_path]


def persist(conn_path: str | None, bundle: dict, variant: dict, shots: list[dict], files: list[Path],
            meta: dict, step_no: int | None, duration_ms: int) -> dict:
    task = bundle["task"]
    step_run_id = rec.record_step(
        task["id"], "storyboard-builder", "ok", step_no=step_no, adapter_used=meta["adapter_used"],
        input_json={"plan_no": variant["plan_no"], "shot_total": SHOT_TOTAL, "grid": GRID,
                    "shot_seconds": meta["shot_seconds"], "prompt_version": meta["prompt_version"]},
        output_json={"shots": len(shots), "total_seconds": meta["shot_seconds"] * SHOT_TOTAL},
        duration_ms=duration_ms, path=conn_path)
    with dbm.transaction(conn_path) as conn:
        conn.execute("DELETE FROM storyboards WHERE task_id = ?", (task["id"],))
        for s in shots:
            conn.execute(
                """INSERT INTO storyboards (task_id, shot_no, scene_text, camera_note, duration_s, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task["id"], s["shot_no"], s["scene_text"], s["camera_note"],
                 float(s["duration_s"]), dbm.now_iso()))
    artifact_ids = [rec.record_artifact(task["id"], "storyboard", rec.rel_path(f), step_run_id=step_run_id,
                                        model_version=meta["model_version"], prompt_version=meta["prompt_version"],
                                        meta={"shot_total": len(shots), "grid": GRID}, path=conn_path)
                    for f in files]
    rec.update_task(task["id"], stage="visual", path=conn_path)
    return {"step_run_id": step_run_id, "artifact_ids": artifact_ids}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="把选定文案拆成 24 条分镜（文案线 FLOW-1 收尾）")
    p.add_argument("--db", default=None)
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build", help="生成 24 条分镜并入库")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--out", default=None, help="产出目录（缺省 workspace/topic-<选题号>/storyboard）")
    s.add_argument("--shot-seconds", type=float, default=DEFAULT_SHOT_SECONDS, help=f"每条分镜时长（秒），默认 {DEFAULT_SHOT_SECONDS:g}")
    s.add_argument("--style-hint", default=DEFAULT_STYLE_HINT, help="画面风格提示")
    s.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    s.add_argument("--step-no", type=int, default=None)
    s.add_argument("--allow-paid", action="store_true")
    s.set_defaults(func=cmd_build)
    return p


def cmd_build(args: argparse.Namespace) -> int:
    bundle = rec.task_bundle(args.task_id, args.db)
    bundle["_db"] = args.db
    task, topic = bundle["task"], bundle["topic"]
    if task["stage"] not in ("copy", "visual"):
        print(f"[错误] 任务 {task['id']} 当前环节是 {task['stage']}：分镜拆解只接 copy/visual", file=sys.stderr)
        return 2
    try:
        variant = validate_input(bundle)
    except InputError as exc:
        rec.update_task(task["id"], status="blocked", path=args.db)
        rec.record_step(task["id"], "storyboard-builder", "failed", step_no=args.step_no,
                        error=f"输入校验不通过：{exc}", path=args.db)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2

    tpl = pt.load(PROMPT_KEY)
    prompt = tpl.render({
        "topic_title": topic["title"], "selected_copy": variant["body"],
        "platform": task["target_platform"] or "未指定", "shot_total": SHOT_TOTAL,
        "grid": GRID, "shot_seconds": f"{args.shot_seconds:g}", "style_hint": args.style_hint,
    })
    payload = {"prompt": prompt, "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
               "topic_title": topic["title"], "shot_total": SHOT_TOTAL}

    started = dbm.now_iso()
    problems: list[str] = []
    result = None
    for attempt in range(1, max(1, args.attempts) + 1):
        result = ar.invoke("llm", payload, allow_paid=args.allow_paid)
        if not result.ok:
            problems = [f"第 {attempt} 次调用失败：{result.error}"]
            break
        shots = tu.parse_storyboard(result.output.get("text", ""), shot_seconds=args.shot_seconds)
        problems = check_shots(shots, args.shot_seconds)
        if not problems:
            break
        problems = [f"第 {attempt} 次生成不合格：" + "；".join(problems)]
    duration_ms = rec.elapsed_ms(started)

    if problems:
        error = "；".join(problems)
        rec.record_step(task["id"], "storyboard-builder", "failed", step_no=args.step_no,
                        adapter_used=(result.adapter_id if result else ""), error=error, path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {error}", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else rec.workspace_dir(topic["id"], "storyboard", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
            "model_version": result.model_version or "unknown", "adapter_used": result.adapter_id,
            "shot_seconds": args.shot_seconds, "style_hint": args.style_hint,
            "stamp": rec.unique_stamp(out_dir, "storyboard")}
    files = render_files(out_dir, bundle, variant, shots, meta)
    info = persist(args.db, bundle, variant, shots, files, meta, args.step_no, duration_ms)
    info.update({"task_id": task["id"], "plan_no": variant["plan_no"], "shots": len(shots),
                 "total_seconds": args.shot_seconds * SHOT_TOTAL, "adapter_used": meta["adapter_used"],
                 "model_version": meta["model_version"], "prompt_version": meta["prompt_version"],
                 "files": [rec.rel_path(f) for f in files],
                 "next": "视觉线：把 24 条分镜交给 reference-image-builder / grid-image-builder"})
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜方案 {variant['plan_no']}（{variant['focus']}）｜{len(shots)} 条分镜"
              f"｜总时长 {args.shot_seconds * SHOT_TOTAL:g} 秒")
        print(f"适配器 {meta['adapter_used']}｜提示词 {meta['prompt_key']} {meta['prompt_version']}")
        print("产出：" + "、".join(info["files"]))
        print("下一步：" + info["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    for _action in parser._actions:  # 子命令也认 --json（写在子命令前后都行）
        if isinstance(_action, argparse._SubParsersAction):
            for _child in _action.choices.values():
                if not any("--json" in _a.option_strings for _a in _child._actions):
                    _child.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                                        help="以 JSON 输出结果（也可写在子命令前）")
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except pt.MissingVariable as exc:
        print(f"[错误] 提示词变量缺失（模板与调用方对不上）：{exc}", file=sys.stderr)
        return 2
    except (rec.RecordingError, InputError, ar.MissingKey) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
