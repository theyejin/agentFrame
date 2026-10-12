#!/usr/bin/env python3
# 文件用途：review-reporter 的实现入口 —— 依据当期指标生成数据复盘与下一轮优化建议
# 对应需求：FLOW-9 数据复盘与优化 / R-8-15（复盘报告）/ R-8-16（不给评分、只给可执行建议）/ Q-19（只回写仓库内的提示词版本建议）
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html（review-reporter）
# 维护提示：报告结构改动要升 templates/prompts/review-report.md 的 version，并同步 templates/mock/review-report.v1.txt。
"""review-reporter 命令行入口。

    report --task-id N [--period-start D] [--period-end D] [--attempts 3] [--allow-paid]
           [--out DIR] [--json]

读 metrics 表聚合 → 渲染 review-report 提示词 → 经 llm 降级链出报告 → 落 report-<时间戳>.{md,json}
并把任务推进到 review。报告里的优化建议只作为「下一轮提示词版本改动」的输入，不自动改提示词（Q-19）。
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
import prompt_templates as pt  # noqa: E402
import recording as rec  # noqa: E402

PROMPT_KEY = "review-report"
DEFAULT_ATTEMPTS = 3
MIN_REPORT_CHARS = 200


class InputError(ValueError):
    """输入校验不通过（没有指标、没有发布记录等）。"""


def _period_of(task_id: int, args: argparse.Namespace) -> tuple[str, str]:
    """确定复盘周期：显式优先，否则取该任务指标里最近的一个周期。"""
    if args.period_start:
        return args.period_start, args.period_end or args.period_start
    row = dbm.query_one(
        "SELECT period_start, period_end FROM metrics WHERE task_id=? ORDER BY period_start DESC, id DESC LIMIT 1",
        (task_id,), args.db)
    if not row:
        raise InputError("这个任务还没有任何指标：先跑 metrics-collector collect（--values 或 --fixture）")
    return row["period_start"], row["period_end"]


def _rank_topics(period_start: str, path: str | None) -> tuple[list[str], list[str], int]:
    """同一期内按播放量排出选题表现，返回（前列, 后列, 本期条数）。"""
    rows = dbm.query(
        "SELECT t.id AS task_id, tp.title AS title, SUM(m.value) AS views, COUNT(DISTINCT m.platform) AS platforms "
        "FROM metrics m JOIN tasks t ON t.id = m.task_id JOIN topics tp ON tp.id = t.topic_id "
        "WHERE m.metric_key = 'views' AND m.period_start = ? GROUP BY t.id ORDER BY views DESC",
        (period_start,), path)
    if not rows:
        return [], [], 0
    lines = [f"{r['title']}（播放 {int(r['views'] or 0)}，{r['platforms']} 个平台）" for r in rows]
    top = lines[:2]
    bottom = lines[-2:] if len(lines) > 2 else lines[-1:]
    return top, bottom, len(rows)


def _published_count(task_id: int, path: str | None) -> int:
    row = dbm.query_one("SELECT COUNT(*) AS n FROM publish_records WHERE task_id=? AND status='published'",
                        (task_id,), path)
    return int((row or {}).get("n") or 0)


def _check_report(text: str) -> list[str]:
    problems: list[str] = []
    if len(text.strip()) < MIN_REPORT_CHARS:
        problems.append(f"报告太短（{len(text.strip())} 字，至少要 {MIN_REPORT_CHARS} 字）")
    if "建议" not in text:
        problems.append("报告里没有「优化建议」部分")
    if not any(ch.isdigit() for ch in text):
        problems.append("报告里没有任何数字，无法作为复盘依据")
    return problems


def cmd_report(args: argparse.Namespace) -> int:
    bundle = rec.task_bundle(args.task_id, args.db)
    task, topic = bundle["task"], bundle["topic"]
    period_start, period_end = _period_of(task["id"], args)
    aggregate = mt.aggregate(task["id"], period_start=period_start, path=args.db)
    if not aggregate["rows"]:
        raise InputError(f"任务 {task['id']} 在周期 {period_start} 没有指标：先跑 metrics-collector")

    top, bottom, published_tasks = _rank_topics(period_start, args.db)
    published_count = _published_count(task["id"], args.db) or published_tasks
    tpl = pt.load(PROMPT_KEY)
    prompt = tpl.render({
        "period": f"{period_start} ~ {period_end}",
        "metrics_table": mt.render_summary(aggregate),
        "top_topics": "\n".join(top) or "（本期只有这一条）",
        "bottom_topics": "\n".join(bottom) or "（本期只有这一条）",
        "published_count": published_count,
    })
    payload = {"prompt": prompt, "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
               "period_start": period_start, "period_end": period_end, "task_id": task["id"]}

    problems: list[str] = []
    result = None
    report = ""
    for attempt in range(1, max(1, args.attempts) + 1):
        result = ar.invoke("llm", payload, allow_paid=args.allow_paid)
        if not result.ok:
            problems = [f"第 {attempt} 次调用失败：{result.error}"]
            break
        report = str((result.output or {}).get("text") or "")
        problems = _check_report(report)
        if not problems:
            break
        problems = [f"第 {attempt} 次报告不合格：" + "；".join(problems)]

    out_dir = Path(args.out) if args.out else rec.workspace_dir(topic["id"], "review", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rec.unique_stamp(out_dir, "report")
    md_path = out_dir / f"report-{stamp}.md"
    json_path = out_dir / f"report-{stamp}.json"

    if problems:
        md_path.write_text(f"# 复盘报告（生成失败） —— 任务 {task['id']} {topic['title']}\n\n"
                           f"周期：{period_start} ~ {period_end}\n\n" + "；".join(problems) + "\n",
                           encoding="utf-8")
        rec.record_step(task["id"], "review-reporter", "failed", step_no=args.step_no,
                        adapter_used=(result.adapter_id if result else ""), error="；".join(problems),
                        input_json={"prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
                                    "period_start": period_start},
                        path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {'；'.join(problems)}", file=sys.stderr)
        return 1

    md_path.write_text(f"# 数据复盘 —— 任务 {task['id']}｜{topic['title']}\n\n"
                       f"- 周期：{period_start} ~ {period_end}\n- 本期发布条数：{published_count}\n"
                       f"- 提示词版本：{tpl.prompt_key} {tpl.version}｜模型：{result.model_version}\n\n"
                       f"## 指标明细\n\n{mt.render_summary(aggregate)}\n\n## 复盘与建议\n\n{report}\n",
                       encoding="utf-8")
    json_path.write_text(json.dumps({
        "task_id": task["id"], "topic_id": topic["id"], "period_start": period_start,
        "period_end": period_end, "published_count": published_count,
        "aggregate": aggregate, "top_topics": top, "bottom_topics": bottom,
        "report": report, "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
        "model_version": result.model_version, "adapter_used": result.adapter_id,
        "note": "建议只用于下一轮提示词版本改动，不自动改提示词（Q-19）",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    step_id = rec.record_step(task["id"], "review-reporter", "ok", step_no=args.step_no,
                              adapter_used=result.adapter_id,
                              input_json={"prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
                                          "period_start": period_start}, path=args.db)
    rec.record_artifact(task["id"], "report", rec.rel_path(md_path), step_run_id=step_id,
                        model_version=result.model_version or "unknown", prompt_version=tpl.version,
                        meta={"role": "review", "period_start": period_start, "period_end": period_end,
                              "json": rec.rel_path(json_path)}, path=args.db)
    if task["stage"] in ("metrics", "publish"):
        rec.update_task(task["id"], stage="review", path=args.db)

    info = {"task_id": task["id"], "topic_id": topic["id"], "period_start": period_start,
            "period_end": period_end, "published_count": published_count,
            "adapter_used": result.adapter_id, "model_version": result.model_version,
            "prompt_version": tpl.version, "files": [rec.rel_path(md_path), rec.rel_path(json_path)],
            "totals": aggregate["totals"], "report_chars": len(report)}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"[完成] 复盘报告已生成：任务 {task['id']}（周期 {period_start} ~ {period_end}）")
        print(mt.render_summary(aggregate))
        print(f"  报告：{info['files'][0]}（{info['report_chars']} 字，模型 {info['model_version']}）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="review-reporter", description="复盘报告员：按指标出复盘与优化建议")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("report", help="生成一期复盘报告")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--period-start", default="", help="复盘周期开始（缺省取最近一期指标）")
    s.add_argument("--period-end", default="", help="复盘周期结束")
    s.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS, help=f"最多尝试次数（默认 {DEFAULT_ATTEMPTS}）")
    s.add_argument("--allow-paid", action="store_true", help="允许调用计费适配器（默认只走免费链）")
    s.add_argument("--out", default=None, help="输出目录（缺省 workspace/topic-<id>/review）")
    s.add_argument("--step-no", type=int, default=None)
    s.set_defaults(func=cmd_report)
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
    except (InputError, pt.PromptError, rec.RecordingError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
