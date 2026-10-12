#!/usr/bin/env python3
# 文件用途：图片一致性体检员 —— 检查 24 张独立图是否合规（数量、编号连续、非空、尺寸一致、与分镜一一对应），输出问题与提示。
# 对应需求：R-L1-19（图片必须 24 张且分辨率一致）、§6.5 交接契约（交接前挡住不合格产物）、R-L2-16（失败特征）。
# 对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html（image-splitter → 人工修图关口前的体检）
# 维护提示：本 skill 是「体检」不是「生产」——它不修改产物、也不把任务置为 blocked，只把结论写进 step_runs 供编排者判断。
"""图片一致性体检员（image-consistency-checker）。

用法：
    python3 .dsh/skills/image-consistency-checker/run.py check --task-id 1
                                                              [--dir DIR] [--expect 24] [--min-side 64]
                                                              [--step-no N] [--json]

判据：
  通过 = 数量正好 expect、编号 1..expect 连续、每张非空且单边 ≥ min-side、所有图尺寸一致、且与数据库里的分镜条数一致；
  提示（不影响退出码）= 图片文件名与分镜编号对不上、画面描述缺失等。

退出码：0 = 通过（可能带提示）；1 = 有问题；2 = 连产物都找不到（输入问题）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import db as dbm  # noqa: E402
import images as im  # noqa: E402
import recording as rec  # noqa: E402

SKILL_ID = "image-consistency-checker"
DEFAULT_EXPECT = 24
MIN_SIDE = 64


class InputError(ValueError):
    """找不到要体检的产物目录或清单。"""


def resolve_dir(task_id: int, directory: str | None, db: str | None) -> tuple[Path, dict | None]:
    """定位要体检的「一代」图：显式 --dir 优先，否则用最近登记的产物/清单定位。"""
    if directory:
        path = Path(directory)
        if not path.is_absolute():
            path = dbm.REPO_ROOT / path
        if not path.is_dir():
            raise InputError(f"--dir 目录不存在：{directory}")
        manifest = path / "latest.json"
        return path, (json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else None)
    art = rec.latest_artifact(task_id, "manifest", role="shots-manifest", path=db) or \
        rec.latest_artifact(task_id, "image", role="shot", path=db) or \
        rec.latest_artifact(task_id, "manifest", path_like="images/shots", path=db)
    if not art:
        raise InputError(f"任务 {task_id} 还没有切图产物：请先跑 image-splitter split")
    path = (dbm.REPO_ROOT / art["path"]).parent
    if not path.is_dir():
        raise InputError(f"登记的产物目录已不在：{art['path']}")
    manifest = path / "latest.json"
    return path, (json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else None)


def cmd_check(args: argparse.Namespace) -> int:
    try:
        out_dir, manifest = resolve_dir(args.task_id, args.dir, args.db)
    except (InputError, rec.RecordingError, json.JSONDecodeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    if manifest and manifest.get("shots"):
        paths = [dbm.REPO_ROOT / item["file"] if not Path(item["file"]).is_absolute() else Path(item["file"])
                 for item in manifest["shots"]]
        prefix = manifest.get("prefix", "shot")
    else:
        prefix = "shot"
        paths = sorted(p for p in out_dir.iterdir() if p.suffix.lower() in im.IMAGE_EXTS and p.name.startswith(prefix))

    report = im.check_images(paths, expected=args.expect, prefix=prefix, min_side=args.min_side)
    problems = list(report["problems"])
    warnings = list(report["warnings"])

    shots_db = rec.current_storyboards(args.task_id, args.db)
    if shots_db and len(shots_db) != len(paths):
        problems.append(f"图片 {len(paths)} 张与数据库分镜 {len(shots_db)} 条不一致")
    missing = [int(s["shot_no"]) for s in shots_db if not (s.get("scene_text") or "").strip()]
    if missing:
        warnings.append("分镜缺少画面描述：" + "、".join(f"{n:02d}" for n in missing))

    status = "ok" if not problems else "failed"
    rec.record_step(args.task_id, SKILL_ID, status, step_no=args.step_no,
                    adapter_used="local", error="；".join(problems),
                    input_json={"dir": rec.rel_path(out_dir), "expect": args.expect, "min_side": args.min_side},
                    output_json={"count": report["count"], "problems": problems, "warnings": warnings},
                    path=args.db)

    info = {
        "task_id": args.task_id, "skill": SKILL_ID, "dir": rec.rel_path(out_dir),
        "ok": not problems, "count": report["count"], "expect": args.expect,
        "sizes": report["sizes"], "problems": problems, "warnings": warnings,
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        flag = "✅ 通过" if info["ok"] else "❌ 不通过"
        print(f"{flag}｜任务 {args.task_id}｜{info['dir']}｜{info['count']} 张（期望 {args.expect}）")
        print(f"尺寸：{info['sizes']}")
        for item in info["problems"]:
            print(f"  问题：{item}")
        for item in info["warnings"]:
            print(f"  提示：{item}")
    return 0 if info["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="图片一致性体检员：24 张独立图是否合规")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="体检一代独立的图")
    p_check.add_argument("--task-id", type=int, required=True)
    p_check.add_argument("--dir", default=None, help="要体检的目录（默认取最近登记的产物）")
    p_check.add_argument("--expect", type=int, default=DEFAULT_EXPECT, help="期望张数（默认 24）")
    p_check.add_argument("--min-side", type=int, default=MIN_SIDE, help="单边最小像素（默认 64）")
    p_check.add_argument("--step-no", type=int, default=None)
    p_check.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                             help="以 JSON 输出结果（也可写在子命令前）")
    p_check.set_defaults(func=cmd_check)

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
