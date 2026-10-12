#!/usr/bin/env python3
# 文件用途：summary-writer 的实现入口 —— 把一条任务的留痕汇总成一段给运营人员看的回报（只读、不改状态、不调模型）。
# 对应需求：R-L1-05（编排者汇总对外汇报）/ §5.2.1（编排者不写文件，回报由 Skill 落盘）/ R-L1-18（回报五项齐备）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
# 维护提示：回报只汇总已留痕的事实；缺数据就写缺口，不得推算或编造数字（C-09 / Q-19）。
"""summary-writer 命令行入口。

    summarize --task-id N [--period-start 2026-10-05] [--period-end 2026-10-11]
              [--out-dir DIR] [--min-chars 120] [--json]

回报五项：当前环节 / 已完成步骤数 / 待办关口 / 关键产物 / 下一步找谁（缺一项即不合格）。
产物落 workspace/topic-<选题号>/reports/summary-<时间戳>.{md,json}，登记 kind=report / meta.role=summary。
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
import metrics as mets  # noqa: E402
import recording as rec  # noqa: E402

LABELS = ("当前环节", "已完成步骤", "待办关口", "关键产物", "下一步找谁")
SKILL_DIR = dbm.REPO_ROOT / ".dsh" / "skills"
ENTRY = {
    "copy": ("copy-agent", "copy-writer", "generate"),
    "visual": ("visual-agent", "reference-image-builder", "build"),
    "video": ("video-agent", "asset-packager", "pack"),
    "publish": ("publish-agent", "browser-publisher", "prepare"),
    "metrics": ("publish-agent", "metrics-collector", "collect"),
    "review": ("publish-agent", "review-reporter", "report"),
}


class InputError(ValueError):
    """输入校验不通过（任务不存在、回报不合格等）。"""


def _roles(artifact: dict) -> list[str]:
    try:
        meta = json.loads(artifact.get("meta_json") or "{}")
    except (TypeError, ValueError):
        meta = {}
    out = [str(meta.get("role") or "")]
    if meta.get("files"):
        out.append("files")
    return [r for r in out if r]


def collect_facts(task_id: int, args: argparse.Namespace) -> dict:
    bundle = rec.task_bundle(task_id, path=args.db)
    task, topic = bundle["task"], bundle["topic"]
    steps = rec.list_steps(task_id, path=args.db)
    artifacts = rec.list_artifacts(task_id, path=args.db)
    events = hitl.list_events(task_id, path=args.db)
    waiting = hitl.is_waiting(task_id, path=args.db)
    report = mets.aggregate(task_id=task_id, period_start=args.period_start, path=args.db)
    review = rec.latest_artifact(task_id, "report", role="review", path=args.db)
    dispatch = rec.latest_artifact(task_id, "manifest", role="dispatch", path=args.db)

    kinds: dict[str, int] = {}
    for a in artifacts:
        roles = _roles(a)
        if "dispatch" in roles:      # 派单书本身不算内容产物，单列
            continue
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1

    return {
        "task": task, "topic": topic, "progress": bundle["progress"],
        "steps_ok": [s for s in steps if s["status"] == "ok"],
        "steps_failed": [s for s in steps if s["status"] == "failed"],
        "steps_total": len(steps), "artifacts": artifacts, "kinds": kinds,
        "events": events, "waiting": waiting, "metrics": report,
        "review": review, "dispatch": dispatch,
    }


def route_of(stage: str) -> tuple[str, str, str]:
    return ENTRY.get(stage, ("orchestrator", "", ""))


def render(facts: dict, task_id: int) -> tuple[str, dict]:
    task, topic = facts["task"], facts["topic"]
    agent_id, skill_id, sub = route_of(task["stage"])
    command = (f"python3 .dsh/skills/{skill_id}/run.py {sub} --task-id {task_id} --json"
               if skill_id else "（该任务已到编排者收尾，不再派单）")
    gate_line = ("有 1 个关口待人工决议（`python3 .dsh/skills/hitl-gate/run.py status --task-id "
                 f"{task_id}` 看是哪个人在等）") if facts["waiting"] else "无待办关口"
    resolved = [e["gate"] for e in facts["events"] if e.get("action") == "confirm"]
    kinds = facts["kinds"]
    kinds_line = "、".join(f"{k} {v}" for k, v in sorted(kinds.items())) or "还没有内容产物"
    totals = (facts["metrics"] or {}).get("totals") or {}
    period = (facts["metrics"] or {}).get("period_start") or "—"
    period_end = (facts["metrics"] or {}).get("period_end") or "—"
    rows = (facts["metrics"] or {}).get("rows") or []
    if rows:
        metrics_line = (f"播放 {int(totals.get('views', 0))} / 互动 {int(totals.get('engagements', 0))} / "
                        f"涨粉 {int(totals.get('follower_gain', 0))}（{period} ~ {period_end}）")
    else:
        metrics_line = "本期还没有指标（先跑 metrics-collector collect）"
    review_line = f"已有（{review_line_path(facts['review'])}）" if facts["review"] else "还没有复盘报告"

    lines = [
        f"# 任务 {task_id} 汇总回报 —— {topic.get('title', '')}",
        "",
        f"- 当前环节：{task['stage']}（状态 {task['status']}，平台 {task['target_platform'] or '—'}）",
        f"- 已完成步骤：{len(facts['steps_ok'])} 步（失败 {len(facts['steps_failed'])} 步，"
        f"共留痕 {facts['steps_total']} 步）",
        f"- 待办关口：{gate_line}",
        f"- 关键产物：{kinds_line}",
        f"- 下一步找谁：{agent_id}（`{command}`）",
        "",
        "## 数据与复盘",
        f"- 指标：{metrics_line}",
        f"- 复盘：{review_line}",
        f"- 已确认关口：{'、'.join(resolved) if resolved else '还没有关口决议'}",
        "",
        "## 派单书",
        f"- {(facts['dispatch'] or {}).get('path', '（还没出过派单书）')}",
        "",
        "> 本回报只汇总已留痕的事实；缺口照实写，不推算、不代答关口、不改任何状态。",
        "",
    ]
    info = {
        "task_id": task_id, "topic_id": task["topic_id"], "topic_title": topic.get("title", ""),
        "stage": task["stage"], "status": task["status"],
        "steps_ok": len(facts["steps_ok"]), "steps_failed": len(facts["steps_failed"]),
        "waiting_human": facts["waiting"], "gates_resolved": resolved,
        "artifacts_by_kind": kinds, "metrics": totals,
        "has_review": bool(facts["review"]),
        "agent_id": agent_id, "next_command": command,
    }
    return "\n".join(lines), info


def review_line_path(review: dict | None) -> str:
    return (review or {}).get("path", "") or "（路径未登记）"


def check_report(text: str, *, min_chars: int) -> list[str]:
    problems = []
    if len(text) < min_chars:
        problems.append(f"回报太短：{len(text)} 字 < {min_chars} 字")
    for label in LABELS:
        if label not in text:
            problems.append(f"回报缺少「{label}」一项")
    if not any(ch.isdigit() for ch in text):
        problems.append("回报里一个数字都没有（回报必须基于留痕事实）")
    return problems


def cmd_summarize(args: argparse.Namespace) -> int:
    facts = collect_facts(args.task_id, args)
    text, info = render(facts, args.task_id)
    problems = check_report(text, min_chars=args.min_chars)
    if problems:
        raise InputError("回报自检不通过：\n  - " + "\n  - ".join(problems))

    task, topic = facts["task"], facts["topic"]
    out_dir = Path(args.out_dir) if args.out_dir else rec.workspace_dir(task["topic_id"], "reports", path=args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rec.unique_stamp(out_dir, "summary")
    md_path = out_dir / f"summary-{stamp}.md"
    json_path = out_dir / f"summary-{stamp}.json"
    md_path.write_text(text, encoding="utf-8")
    json_path.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = [rec.rel_path(md_path), rec.rel_path(json_path)]

    step_id = rec.record_step(args.task_id, "summary-writer", "ok", step_no=args.step_no,
                              input_json={"task_id": args.task_id, "stage": task["stage"]},
                              output_json={"agent_id": info["agent_id"], "chars": len(text)}, path=args.db)
    rec.record_artifact(args.task_id, "report", files[0], step_run_id=step_id, model_version="summary-writer-v1",
                        prompt_version="none", meta={"role": "summary", "files": files, "stage": task["stage"],
                              "agent_id": info["agent_id"], "chars": len(text)}, path=args.db)

    out = dict(info, files=files, chars=len(text), topic_title=topic.get("title", ""))
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(text)
        print(f"[完成] 回报已落盘：{files[0]}（{len(text)} 字）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="summary-writer", description="汇总回报员：把一条任务的留痕汇总成一段回报")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("summarize", help="生成任务汇总回报（只读）")
    s.add_argument("--task-id", type=int, required=True, help="任务号")
    s.add_argument("--period-start", default=None, help="指标周期起（缺省取最近一期）")
    s.add_argument("--period-end", default=None, help="指标周期止（缺省取最近一期）")
    s.add_argument("--min-chars", type=int, default=120, help="回报最短字数（默认 120）")
    s.add_argument("--step-no", type=int, default=None, help="步骤号（缺省自动递增）")
    s.add_argument("--out-dir", default=None, help="输出目录（缺省 workspace/topic-<选题号>/reports）")
    s.set_defaults(func=cmd_summarize)
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
    except (InputError, rec.RecordingError, mets.MetricsError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
