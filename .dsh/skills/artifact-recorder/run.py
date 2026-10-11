#!/usr/bin/env python3
# 文件用途：artifact-recorder 的实现入口 —— 话题/任务/步骤流水/产物的唯一命令行写入与查询入口。
# 对应需求：§7 数据模型、R-7-01~05（产物与版本字段）、R-L2-05（执行过程留痕）、R-8-03（操作人字段）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（本地数据库与日志留痕）
# 维护提示：写入口径集中在 _shared/recording.py；新增字段请同步 db/README.md 与本目录 README.md。
"""artifact-recorder 命令行入口。

    topic-create  --title T [--source manual|hotspot] [--keywords K] [--summary S] [--operator OP]
    task-create   --topic-id N [--stage copy] [--type 情绪冲突] [--platform 抖音] [--prompt P]
                  [--words 300-500] [--priority 2] [--operator OP]
    task-update   --task-id N [--status S] [--stage S] [--selected-plan 1|2|3] [--operator OP]
    task-show     --task-id N
    step-run      --task-id N --skill S --status ok|running|failed|skipped [--step-no N]
                  [--adapter A] [--input-json J] [--output-json J] [--error E] [--duration-ms N]
    artifact      --task-id N --kind copy|storyboard|image|video|... --path P [--step-run-id N]
                  [--model-version V] [--prompt-version V] [--meta-json J]
    list          --task-id N [--what steps|artifacts|events|progress|all]

通用参数：--db PATH（默认读 .env 的 DB_PATH）、--json。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import db as dbm  # noqa: E402
import hitl as hitlmod  # noqa: E402
import recording as rec  # noqa: E402


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--*-json 不是合法 JSON：{exc}") from exc


def _words(spec: str) -> tuple[int, int]:
    lo, _, hi = spec.partition("-")
    return int(lo), int(hi)


def _out(payload, as_json: bool, human: str) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2) if as_json else human)
    return 0


def cmd_topic_create(args):
    w = _words(args.words) if args.words else (300, 500)
    topic_id = rec.create_topic(args.title, source=args.source, keywords=args.keywords,
                                summary=args.summary, created_by=args.operator, path=args.db)
    if args.task:
        task_id = rec.create_task(topic_id, content_type=args.type, target_platform=args.platform,
                                  prompt=args.prompt, word_min=w[0], word_max=w[1],
                                  operator=args.operator, path=args.db)
        return _out({"topic_id": topic_id, "task_id": task_id}, args.json,
                    f"已建话题 #{topic_id} 与任务 #{task_id}（{args.type}，{w[0]}-{w[1]} 字）")
    return _out({"topic_id": topic_id}, args.json, f"已建话题 #{topic_id}")


def cmd_task_create(args):
    w = _words(args.words)
    task_id = rec.create_task(args.topic_id, stage=args.stage, content_type=args.type,
                              target_platform=args.platform, prompt=args.prompt,
                              word_min=w[0], word_max=w[1], priority=args.priority,
                              operator=args.operator, path=args.db)
    return _out({"task_id": task_id}, args.json, f"已建任务 #{task_id}（{args.type}，{w[0]}-{w[1]} 字，{args.platform or '平台未定'}）")


def cmd_task_update(args):
    rec.update_task(args.task_id, status=args.status, stage=args.stage,
                    selected_plan=args.selected_plan, operator=args.operator, path=args.db)
    return _out({"task_id": args.task_id, "updated": True}, args.json,
                f"任务 #{args.task_id} 已更新（status={args.status or '-'} stage={args.stage or '-'} plan={args.selected_plan or '-'}）")


def cmd_task_show(args):
    bundle = rec.task_bundle(args.task_id, args.db)
    if args.json:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0
    t, topic, prog = bundle["task"], bundle["topic"], bundle["progress"]
    print(f"任务 #{t['id']}｜话题：{topic.get('title', '')}")
    print(f"  阶段={t['stage']} 状态={t['status']} 类型={t['content_type']} 平台={t['target_platform'] or '未定'}"
          f" 字数={t['word_min']}-{t['word_max']}")
    print(f"  选定套号={t['selected_plan'] or '未选定'} 处理人={t['operator'] or '-'}")
    print(f"  进度：已执行 {prog.get('done_steps', 0)} 步成功 / {prog.get('failed_steps', 0)} 步失败"
          f"（最近一步 #{prog.get('last_step_no') or 0}）")
    return 0


def cmd_step_run(args):
    step_id = rec.record_step(args.task_id, args.skill, args.status, step_no=args.step_no,
                              adapter_used=args.adapter, input_json=_loads(args.input_json),
                              output_json=_loads(args.output_json), error=args.error,
                              duration_ms=args.duration_ms, path=args.db)
    return _out({"step_run_id": step_id}, args.json, f"已登记步骤流水 #{step_id}（{args.skill} → {args.status}）")


def cmd_artifact(args):
    art_id = rec.record_artifact(args.task_id, args.kind, args.path, step_run_id=args.step_run_id,
                                 model_version=args.model_version, prompt_version=args.prompt_version,
                                 meta=_loads(args.meta_json), path=args.db)
    return _out({"artifact_id": art_id}, args.json, f"已登记产物 #{art_id}（{args.kind} → {args.path}）")


def cmd_list(args):
    payload = {}
    if args.what in ("steps", "all"):
        payload["steps"] = rec.list_steps(args.task_id, args.db)
    if args.what in ("artifacts", "all"):
        payload["artifacts"] = rec.list_artifacts(args.task_id, args.db)
    if args.what in ("events", "all"):
        payload["events"] = hitlmod.list_events(args.task_id, args.db)
    if args.what in ("progress", "all"):
        payload["progress"] = rec.task_progress(args.task_id, args.db)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for key, rows in payload.items():
        if isinstance(rows, list):
            print(f"{key}：{len(rows)} 条")
            for r in rows:
                label = r.get("skill_id") or r.get("kind") or r.get("gate") or r.get("task_id")
                detail = r.get("status") or r.get("path") or r.get("action") or ""
                print(f"  - {label}｜{detail}")
        else:
            print(f"{key}：{rows}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="留痕登记：话题 / 任务 / 步骤流水 / 产物")
    p.add_argument("--db", help="数据库路径（默认读 .env 的 DB_PATH，兜底 db/app.db）")
    p.add_argument("--json", action="store_true", help="机器可读输出")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("topic-create", help="新建话题")
    s.add_argument("--title", required=True)
    s.add_argument("--source", default="manual", choices=["manual", "hotspot"])
    s.add_argument("--keywords", default="")
    s.add_argument("--summary", default="")
    s.add_argument("--operator", default="")
    s.add_argument("--task", action="store_true", help="同时建一个任务")
    s.add_argument("--type", default="情绪冲突")
    s.add_argument("--platform", default="")
    s.add_argument("--prompt", default="")
    s.add_argument("--words", default="300-500")
    s.set_defaults(func=cmd_topic_create)

    s = sub.add_parser("task-create", help="新建任务")
    s.add_argument("--topic-id", type=int, required=True)
    s.add_argument("--stage", default="copy")
    s.add_argument("--type", default="情绪冲突")
    s.add_argument("--platform", default="")
    s.add_argument("--prompt", default="")
    s.add_argument("--words", default="300-500")
    s.add_argument("--priority", type=int, default=2)
    s.add_argument("--operator", default="")
    s.set_defaults(func=cmd_task_create)

    s = sub.add_parser("task-update", help="更新任务状态/阶段/选定套号")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--status")
    s.add_argument("--stage")
    s.add_argument("--selected-plan", type=int)
    s.add_argument("--operator")
    s.set_defaults(func=cmd_task_update)

    s = sub.add_parser("task-show", help="看任务全貌与进度")
    s.add_argument("--task-id", type=int, required=True)
    s.set_defaults(func=cmd_task_show)

    s = sub.add_parser("step-run", help="登记一步执行流水")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--skill", required=True)
    s.add_argument("--status", required=True, choices=["pending", "running", "ok", "failed", "skipped"])
    s.add_argument("--step-no", type=int)
    s.add_argument("--adapter", default="")
    s.add_argument("--input-json")
    s.add_argument("--output-json")
    s.add_argument("--error", default="")
    s.add_argument("--duration-ms", type=int, default=0)
    s.set_defaults(func=cmd_step_run)

    s = sub.add_parser("artifact", help="登记产物")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--kind", required=True)
    s.add_argument("--path", required=True)
    s.add_argument("--step-run-id", type=int)
    s.add_argument("--model-version", default="")
    s.add_argument("--prompt-version", default="")
    s.add_argument("--meta-json")
    s.set_defaults(func=cmd_artifact)

    s = sub.add_parser("list", help="列出流水/产物/关口/进度")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--what", default="all", choices=["steps", "artifacts", "events", "progress", "all"])
    s.set_defaults(func=cmd_list)
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (rec.RecordingError, dbm.sqlite3.Error) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
