#!/usr/bin/env python3
# 文件用途：storyboard-validator 的实现入口 —— 分镜脚本的结构体检（条数、编号连续性、重复、时长口径）。
# 对应需求：R-L1-19（典型校验例：分镜必须 24 条且编号连续）、§5.2.2 完成判据。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（storyboard-builder 的自检环节）
# 维护提示：判定口径变化（条数、编号、时长容差）请同步 docs/skill-roster.md 与本目录 README.md。
"""storyboard-validator 命令行入口。

    check --file F [--expect 24] [--target-seconds 72] [--json]

输入可以是 storyboard-builder 产出的 JSON（读其中的 shots 数组），也可以是「NN | 画面描述 | 镜头提示」纯文本。
退出码：0 = 结构通过（可能有提示级警告）；1 = 有结构问题；2 = 文件读不了 / 参数不对。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import text_utils as tu  # noqa: E402

DEFAULT_EXPECT = 24
DURATION_TOLERANCE = 0.10   # 总时长允许 ±10%
SCENE_CHAR_WARN = 60        # 单条画面描述超过这个字数只提示、不判失败


def load_shots(path: Path, shot_seconds: float = 0.0) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        shots = data.get("shots") if isinstance(data, dict) else data
        if not isinstance(shots, list):
            raise ValueError("JSON 里没有 shots 数组")
        out = []
        for item in shots:
            out.append({
                "shot_no": int(item.get("shot_no") or item.get("no") or 0),
                "scene_text": str(item.get("scene_text") or item.get("desc") or "").strip(),
                "camera_note": str(item.get("camera_note") or "").strip(),
                "duration_s": float(item.get("duration_s") or 0),
            })
        return out
    return tu.parse_storyboard(raw, shot_seconds=shot_seconds)


def check(shots: list[dict], expect: int, target_seconds: float | None) -> tuple[list[str], list[str]]:
    problems = tu.check_storyboard_shape(shots, expected=expect)
    warnings: list[str] = []
    for shot in shots:
        if len(shot.get("scene_text", "")) > SCENE_CHAR_WARN:
            warnings.append(f"第 {shot['shot_no']} 条画面描述 {len(shot['scene_text'])} 字，超过建议的 {SCENE_CHAR_WARN} 字")
    total = sum(float(s.get("duration_s") or 0) for s in shots)
    if target_seconds:
        low, high = target_seconds * (1 - DURATION_TOLERANCE), target_seconds * (1 + DURATION_TOLERANCE)
        if not (low <= total <= high):
            problems.append(f"总时长 {total:g} 秒超出目标 {target_seconds:g} 秒的 ±{int(DURATION_TOLERANCE * 100)}% 区间（{low:g}–{high:g} 秒）")
    return problems, warnings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="分镜脚本结构体检")
    p.add_argument("check", nargs="?", help="（默认动作）")
    p.add_argument("--file", required=True, help="分镜 JSON 或纯文本路径")
    p.add_argument("--expect", type=int, default=DEFAULT_EXPECT, help=f"期望条数，默认 {DEFAULT_EXPECT}")
    p.add_argument("--target-seconds", type=float, default=None, help="目标总时长（秒），给了就校验 ±10%")
    p.add_argument("--shot-seconds", type=float, default=0.0, help="纯文本输入时每条分镜的时长（秒）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.file)
    if not path.exists():
        print(f"[错误] 找不到文件：{path}", file=sys.stderr)
        return 2
    try:
        shots = load_shots(path, shot_seconds=args.shot_seconds)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"[错误] 分镜文件解析失败：{exc}", file=sys.stderr)
        return 2
    problems, warnings = check(shots, args.expect, args.target_seconds)
    total = sum(float(s.get("duration_s") or 0) for s in shots)
    payload = {"file": str(path), "shots": len(shots), "total_seconds": round(total, 2),
               "ok": not problems, "problems": problems, "warnings": warnings}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"文件：{path}\n条数：{len(shots)}（期望 {args.expect}）  总时长：{total:g} 秒")
        for item in problems:
            print(f"  [问题] {item}")
        for item in warnings:
            print(f"  [提示] {item}")
        print("结论：" + ("结构通过 ✅" if not problems else "结构不通过 ❌"))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
