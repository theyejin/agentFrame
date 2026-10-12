#!/usr/bin/env python3
# 文件用途：publish-guard 的实现入口 —— 发布前红线自检（C-08 不自动发布 / C-10 关口③ 授权 / 信息齐备）
# 对应需求：R-7-05（发布前必须过红线）/ C-08（Agent 不得自动发布）/ C-10（发布授权必须真人给）/ Q-5（首版只准备不发布）
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html（publish-guard 支撑件）
# 维护提示：红线规则改动要同步 docs/decision-log.md（发一条 D 记录）与浏览器发布员的 SKILL.md 自检清单。
"""publish-guard 命令行入口。

    check --task-id N [--package PATH] [--platform P] [--live] [--json]

退出码：0 = 可以进入人工发布（可能有提示项）；1 = 有阻断项，不得发布；2 = 用法或数据问题。
本工具只做检查，不改任务状态、不写发布记录（人工发布后由 browser-publisher mark-published 回填）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import db as dbm  # noqa: E402
import publish_guard as pg  # noqa: E402
import recording as rec  # noqa: E402

GATE3 = "gate3_publish_auth"


class InputError(ValueError):
    """输入校验不通过（任务不存在、没有发布包等）。"""


def gate3_authorized(task_id: int, path: str | None, *, status: str = "") -> tuple[bool, str]:
    """读关口③ 最近一次决议：confirm 即已授权。

    注意：`hitl.open_gate` 只把任务置 waiting_human、不写 hitl_events，
    所以「待办已挂但还没决议」表现为「没有事件 + 任务 waiting_human」。
    """
    row = dbm.query_one("SELECT action, actor, created_at FROM hitl_events WHERE task_id=? AND gate=?"
                        " ORDER BY id DESC LIMIT 1", (task_id, GATE3), path)
    if not row:
        if status == "waiting_human":
            return False, "关口③ 待人工授权（待办已挂，还没有决议）"
        return False, "关口③ 还没有挂在待办上（先跑 browser-publisher prepare）"
    if row["action"] == "confirm":
        return True, f"关口③ 已由 {row['actor']} 于 {row['created_at']} 授权"
    if row["action"] == "reject":
        return False, f"关口③ 已被 {row['actor']} 退回（{row['created_at']}）：先改完再重新挂待办"
    return False, f"关口③ 最近一次是 {row['action']}（{row['actor']}），需要真人 confirm 才算授权"


def load_package(task_id: int, args: argparse.Namespace) -> dict:
    """优先用 --package 指定的清单，否则取该任务最近一份 publish_package 产物。"""
    if args.package:
        path = Path(args.package)
        if not path.is_file():
            raise InputError(f"发布包不存在：{args.package}")
        return json.loads(path.read_text(encoding="utf-8"))
    row = rec.latest_artifact(task_id, "publish_package", path=args.db)
    if not row:
        raise InputError("这个任务还没有填写清单：先跑 browser-publisher prepare（它会停在发布前）")
    file_path = rec.abs_path_of(row["path"])
    if not file_path.is_file():
        raise InputError(f"填写清单文件已不在：{row['path']}")
    return json.loads(file_path.read_text(encoding="utf-8"))


def cmd_check(args: argparse.Namespace) -> int:
    bundle = rec.task_bundle(args.task_id, args.db)  # 任务不存在就在这里报错
    pkg = load_package(args.task_id, args)
    if args.platform:
        pkg["platform"] = args.platform
    authorized, note = gate3_authorized(args.task_id, args.db, status=bundle["task"]["status"])
    result = pg.check_package(pkg, gate3_authorized=authorized, live=args.live)
    lines = pg.render_check(result)
    if not result["ok"]:
        lines += "\n  → 不得发布：先按上面 ✗ 项修好，再重新 prepare（C-08/C-10）"
    elif authorized:
        lines += "\n  → 可以在浏览器里人工发布；发布后回填：browser-publisher mark-published"
    else:
        lines += f"\n  → 还不能发布（{note}）：先挂关口③ 待办并等真人授权（hitl-gate open --gate {GATE3}）"

    info = {"task_id": args.task_id, "platform": result["platform"], "ok": result["ok"],
            "blocked": not result["ok"], "gate3_authorized": authorized, "gate3_note": note,
            "problems": result["problems"], "warnings": result["warnings"], "live": args.live}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(lines)
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="publish-guard", description="发布红线守卫：发布前自检，不做任何发布动作")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("check", help="检查一份发布包能不能进入人工发布")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--package", default=None, help="发布包 JSON 路径（缺省取最近一份 publish_package 产物）")
    s.add_argument("--platform", default="", help="覆盖发布包里的平台")
    s.add_argument("--live", action="store_true", help="按「真的要发布」的标准检查（会因关口③ 未授权而阻断）")
    s.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_check)
    return p


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
    except (InputError, pg.PublishGuardError, rec.RecordingError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
