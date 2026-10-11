#!/usr/bin/env python3
# 文件用途：hitl-gate 的实现入口 —— 三类人工关口（选定文案 / 剪辑干预 / 发布授权）的开启、决议与留痕。
# 对应需求：§8.3 三类 HITL 形态、R-L1-18（关口契约）、R-8-03（操作人字段）、C-08（未授权不发布）。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（关口①）、FLOW-VIDEO-20261012（关口②）、FLOW-PUBLISH-20261012（关口③）
# 维护提示：关口枚举改动请同步 db/schema.sql 的 hitl_events.gate、docs/skill-roster.md 与 docs/directory-and-files.md。
"""hitl-gate 命令行入口。

    open    --task-id N --gate G [--note 说明]                 开启关口（任务置 waiting_human）
    resolve --task-id N --gate G --action confirm|reject|adjust --actor 名字
            [--plan-no 1|2|3] [--snapshot-json J] [--diff-json J]  决议关口并写 hitl_events
    list    --task-id N                                         看该任务已发生的关口事件
    status  --task-id N                                         看任务是否正卡在关口上

通用参数：--db（缺省读 .env 的 DB_PATH）、--json（机器可读输出）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import db as dbm  # noqa: E402
import hitl  # noqa: E402
import recording as rec  # noqa: E402


def _json_arg(raw: str | None) -> object:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--json 参数不是合法 JSON：{exc}") from exc


def _emit(payload: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    info = hitl.open_gate(args.task_id, args.gate, note=args.note or "", path=args.db)
    info["提示"] = "已停在关口，等人处理；决议请用 resolve 子命令"
    return _emit(info, args.json)


def cmd_resolve(args: argparse.Namespace) -> int:
    event_id = hitl.resolve_gate(args.task_id, args.gate, args.action, args.actor,
                                 snapshot=_json_arg(args.snapshot_json), diff=_json_arg(args.diff_json),
                                 plan_no=args.plan_no, path=args.db)
    bundle = rec.task_bundle(args.task_id, args.db)
    return _emit({"event_id": event_id, "task_id": args.task_id, "action": args.action,
                  "task_status": bundle["task"]["status"],
                  "selected_plan": bundle["task"]["selected_plan"]}, args.json)


def cmd_list(args: argparse.Namespace) -> int:
    events = hitl.list_events(args.task_id, args.db)
    if args.json:
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return 0
    if not events:
        print(f"任务 {args.task_id} 还没有关口事件")
        return 0
    for e in events:
        print(f"[{e['created_at']}] {e['gate']} {e['action']} by {e['actor']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    task = dbm.query_one("SELECT id, status, selected_plan FROM tasks WHERE id = ?", (args.task_id,), args.db)
    if task is None:
        print(f"[错误] 任务不存在：{args.task_id}", file=sys.stderr)
        return 2
    return _emit({"task_id": task["id"], "status": task["status"],
                  "waiting_human": task["status"] == "waiting_human",
                  "selected_plan": task["selected_plan"]}, args.json)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="人工关口器：开启、决议并留痕三类 HITL 关口")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("open", help="开启关口（任务置 waiting_human）")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--gate", required=True, choices=[hitl.GATE1, hitl.GATE2, hitl.GATE3])
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_open)

    s = sub.add_parser("resolve", help="决议关口并写 hitl_events")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--gate", required=True, choices=[hitl.GATE1, hitl.GATE2, hitl.GATE3])
    s.add_argument("--action", required=True, choices=["confirm", "reject", "adjust"])
    s.add_argument("--actor", required=True, help="谁做的决定（R-8-03）")
    s.add_argument("--plan-no", type=int, default=None, help="关口① confirm 时必填：选定第几套")
    s.add_argument("--snapshot-json", default=None, help="当时待确认的内容快照")
    s.add_argument("--diff-json", default=None, help="调整前后差异（关口② 用）")
    s.set_defaults(func=cmd_resolve)

    s = sub.add_parser("list", help="看该任务的关口事件")
    s.add_argument("--task-id", type=int, required=True)
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("status", help="看任务是否卡在关口")
    s.add_argument("--task-id", type=int, required=True)
    s.set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (hitl.HitlError, rec.RecordingError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
