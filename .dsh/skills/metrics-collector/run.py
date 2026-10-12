#!/usr/bin/env python3
# 文件用途：metrics-collector 的实现入口 —— 采集三项指标（播放量/互动量/涨粉数）并落库留痕
# 对应需求：FLOW-8 数据采集 / R-7-04（三项口径）/ R-8-14（来源可追溯）/ Q-16（口径固定，不多不少）
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html（metrics-collector）
# 维护提示：口径改动要同步 db/schema.sql 的 metrics.metric_key、_shared/metrics.py 与 docs/requirements-spec.md。
"""metrics-collector 命令行入口。

    collect --task-id N [--platform P] [--values "播放量=1200,互动量=88,涨粉=12"] [--fixture PATH]
            [--period-start D] [--period-end D] [--source manual|browser|api|export]
            [--allow-partial] [--out DIR] [--json]

两种入口：① 运营人员直接给 `--values`（人工录入）；② 经 metrics 降级链采集（离线走 metrics.local-fixture）。
同期同键更新而不是堆行，避免复盘时把同一个数字加两遍。
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
import metrics as mt  # noqa: E402
import recording as rec  # noqa: E402


class InputError(ValueError):
    """输入校验不通过（任务不存在、口径不对、周期缺失等）。"""


def _records(args: argparse.Namespace, task: dict) -> tuple[list[dict], str, str]:
    """返回（待落库记录, 适配器, 模型版本）。"""
    if args.values:
        values = mt.parse_values(args.values)
        platform = args.platform or task["target_platform"] or ""
        if not platform:
            raise InputError("没有平台：任务没设 target_platform，请用 --platform 指定")
        return [{"platform": platform, "period_start": args.period_start, "period_end": args.period_end,
                 "values": values, "source": args.source or "manual"}], "human", "manual-entry-v1"

    fixture = args.fixture
    if not fixture:
        raise InputError("要么给 --values（人工录入），要么给 --fixture（离线夹具）；本版没有浏览器采集实现")
    path = Path(fixture)
    if not path.is_file():
        raise InputError(f"夹具文件不存在：{fixture}")
    result = ar.invoke("metrics", {"abs_fixture": str(path.resolve()), "fixture": fixture,
                                   "platform": args.platform, "task_id": task["id"]}, allow_paid=False)
    if not result.ok:
        raise InputError(f"指标采集失败：{result.error}")
    records = list((result.output or {}).get("metrics") or [])
    if not records:
        raise InputError("采集结果为空：夹具里没有指标记录")
    out = []
    for one in records:
        platform = one.get("platform") or args.platform or task["target_platform"] or ""
        if args.platform and platform and platform != args.platform:
            continue
        out.append({"platform": platform,
                    "period_start": one.get("period_start") or args.period_start,
                    "period_end": one.get("period_end") or args.period_end,
                    "values": one.get("values") or {},
                    "source": one.get("source") or args.source or "export"})
    if not out:
        raise InputError(f"夹具里没有平台「{args.platform}」的记录")
    return out, result.adapter_id, result.model_version or "unknown"


def cmd_collect(args: argparse.Namespace) -> int:
    bundle = rec.task_bundle(args.task_id, args.db)
    task, topic = bundle["task"], bundle["topic"]
    records, adapter, model_version = _records(args, task)

    problems: list[str] = []
    for one in records:
        if not one["platform"]:
            problems.append("有记录缺平台")
        if not one["period_start"] or not one["period_end"]:
            problems.append(f"平台「{one['platform'] or '未标'}」缺统计周期（--period-start/--period-end）")
        problems.extend(f"{one['platform']}：" + p for p in
                        mt.check_values(one["values"], require_all=not args.allow_partial))
    if problems:
        print("[错误] 指标自检不通过：" + "；".join(problems), file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else rec.workspace_dir(topic["id"], "metrics", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rec.unique_stamp(out_dir, "metrics")
    snapshots, written = [], 0
    for one in records:
        written += mt.upsert_metrics(task["id"], one["values"], platform=one["platform"],
                                     period_start=one["period_start"], period_end=one["period_end"],
                                     source=one["source"], path=args.db)
        snapshots.append(mt.snapshot(task["id"], platform=one["platform"], values=one["values"],
                                     period_start=one["period_start"], period_end=one["period_end"],
                                     source=one["source"]))
    json_path = out_dir / f"metrics-{stamp}.json"
    aggregate = mt.aggregate(task["id"], path=args.db)
    json_path.write_text(json.dumps({"task_id": task["id"], "topic_id": topic["id"],
                                     "collect_adapter": adapter, "model_version": model_version,
                                     "records": snapshots, "aggregate": aggregate},
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path = out_dir / f"metrics-{stamp}.md"
    md_path.write_text(f"# 指标采集 —— 任务 {task['id']}（{topic['title']}）\n\n"
                       + "\n".join(f"- {s['platform']}｜{s['period_start']} ~ {s['period_end']}｜来源 {s['source']}"
                                   f"｜" + "、".join(f"{k} {v:g}" for k, v in s["labels"].items())
                                   for s in snapshots)
                       + "\n\n" + mt.render_summary(aggregate) + "\n", encoding="utf-8")

    step_id = rec.record_step(task["id"], "metrics-collector", "ok", step_no=args.step_no,
                              adapter_used=adapter, input_json={"records": len(records), "source": records[0]["source"]},
                              path=args.db)
    rec.record_artifact(task["id"], "table", rec.rel_path(json_path), step_run_id=step_id,
                        model_version=model_version, prompt_version="none",
                        meta={"role": "metrics", "records": len(records),
                              "period_start": records[0]["period_start"], "period_end": records[0]["period_end"]},
                        path=args.db)
    if task["stage"] == "publish":
        rec.update_task(task["id"], stage="metrics", path=args.db)

    info = {"task_id": task["id"], "topic_id": topic["id"], "records": len(records), "rows_written": written,
            "adapter_used": adapter, "model_version": model_version,
            "files": [rec.rel_path(json_path), rec.rel_path(md_path)],
            "totals": aggregate["totals"], "by_platform": aggregate["by_platform"],
            "stage": "metrics" if task["stage"] == "publish" else task["stage"]}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"[完成] 指标已入库：任务 {task['id']}，{len(records)} 条记录、{written} 行（适配器 {adapter}）")
        print(mt.render_summary(aggregate))
        print(f"  文件：{info['files'][0]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="metrics-collector", description="指标采集员：采集播放量/互动量/涨粉数")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("collect", help="采集一期指标")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--platform", default="", help="平台（缺省用任务的目标平台）")
    s.add_argument("--values", default="", help='人工录入，例："播放量=1200,互动量=88,涨粉=12"')
    s.add_argument("--fixture", default=None, help="离线指标夹具 JSON（经 metrics 降级链采集）")
    s.add_argument("--period-start", default="", help="统计周期开始（如 2026-10-05）")
    s.add_argument("--period-end", default="", help="统计周期结束")
    s.add_argument("--source", default="", choices=["", "manual", "browser", "api", "export"], help="数据来源")
    s.add_argument("--allow-partial", action="store_true", help="允许只采部分指标（默认三项必须齐全）")
    s.add_argument("--out", default=None, help="输出目录（缺省 workspace/topic-<id>/metrics）")
    s.add_argument("--step-no", type=int, default=None)
    s.set_defaults(func=cmd_collect)
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
    except (InputError, mt.MetricsError, rec.RecordingError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
