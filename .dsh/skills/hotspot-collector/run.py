#!/usr/bin/env python3
# 文件用途：hotspot-collector 的实现入口 —— 采集热点、归类去重，落库并产出批次文件。
# 对应需求：FLOW-7 热点采集与分类汇总 / R-7-01（关键词采集）/ R-7-02（分类）/ R-L2-17（经适配器，不在业务代码里写死服务）。
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
# 维护提示：分类枚举改动要同步 db/schema.sql 的 hotspot_items.category、templates/prompts/hotspot-summarize.md 与 _shared/hotspots.py。
"""hotspot-collector 命令行入口。

    collect --keyword 关键词 [--keywords "a,b"] [--limit 20] [--fixture PATH] [--out DIR]
            [--period-start D] [--period-end D] [--attempts 3] [--allow-paid] [--json]

三步：① 经 browser 降级链采集原始条目（离线走 browser.local-fixture 读夹具）；
② 经 llm 降级链渲染 hotspot-summarize 提示词做归类去重；③ 落 hotspot_batches + hotspot_items 并写出批次文件。
热点是话题级产物、先于选题立项，所以不进 artifacts（那张表的 task_id 非空），批次留痕在 hotspot_batches。
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
import hotspots as hs  # noqa: E402
import prompt_templates as pt  # noqa: E402
import recording as rec  # noqa: E402

PROMPT_KEY = "hotspot-summarize"
DEFAULT_ATTEMPTS = 3
DEFAULT_LIMIT = 20


class InputError(ValueError):
    """输入校验不通过（R-L1-18：校验失败必须退回，不能带病往下走）。"""


def _raw_items_text(items: list[dict]) -> str:
    """把原始采集条目渲染成提示词里的清单（带序号与来源，方便模型保留可追溯性）。"""
    lines = []
    for i, item in enumerate(items, start=1):
        url = item.get("source_url") or ""
        rank = item.get("rank")
        head = f"{i}. {item.get('title', '')}"
        if rank:
            head += f"（榜位 {rank}）"
        if url:
            head += f"｜来源 {url}"
        lines.append(head)
    return "\n".join(lines)


def _abs_or_none(raw: str | None) -> str | None:
    if not raw:
        return None
    path = Path(raw)
    return str(path.resolve()) if path.is_file() else None


def cmd_collect(args: argparse.Namespace) -> int:
    keyword = (args.keyword or args.keywords or "").strip()
    if not keyword:
        print("[错误] 必须给关键词：--keyword 或 --keywords", file=sys.stderr)
        return 2
    fixture = _abs_or_none(args.fixture)
    if args.fixture and not fixture:
        print(f"[错误] 夹具文件不存在：{args.fixture}", file=sys.stderr)
        return 2

    batch_key = args.batch_key or f"hotspot-{rec.timestamp_slug()}"
    out_dir = Path(args.out) if args.out else (rec.abs_path_of("workspace") / "hotspots" / batch_key)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ① 采集原始条目：只写「要什么」，具体谁去抓由降级链决定（R-L2-17）
    collect_payload: dict = {"keyword": keyword, "limit": args.limit,
                             "period_start": args.period_start, "period_end": args.period_end}
    if fixture:
        collect_payload.update({"abs_fixture": fixture, "fixture": rec.rel_path(args.fixture)})
    collected = ar.invoke("browser", collect_payload, allow_paid=False)
    if not collected.ok:
        print(f"[错误] 采集失败：{collected.error}", file=sys.stderr)
        return 2
    raw_items = list((collected.output or {}).get("items") or [])
    if not raw_items:
        print("[错误] 采集结果为空：夹具里没有条目，或页面结构变了", file=sys.stderr)
        return 2
    source = "fixture" if str(collected.adapter_id).startswith("browser.local-fixture") else "browser"

    # ② 归类去重：提示词按版本取，模型只负责分类与热度估计
    tpl = pt.load(PROMPT_KEY)
    period = f"{args.period_start} ~ {args.period_end}" if args.period_start or args.period_end else "最近一期"
    prompt = tpl.render({
        "keyword": keyword,
        "period": period,
        "raw_items": _raw_items_text(raw_items),
        "limit": args.limit,
    })
    payload = {"prompt": prompt, "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
               "keyword": keyword, "limit": args.limit}

    problems: list[str] = []
    result = None
    items: list[dict] = []
    for attempt in range(1, max(1, args.attempts) + 1):
        result = ar.invoke("llm", payload, allow_paid=args.allow_paid)
        if not result.ok:
            problems = [f"第 {attempt} 次调用失败：{result.error}"]
            break
        items = hs.parse_items(result.output.get("text", ""))
        problems = hs.check_items(items, min_count=1, max_count=max(1, args.limit) * 3)
        if not problems:
            break
        problems = [f"第 {attempt} 次分类不合格：" + "；".join(problems)]

    if problems:
        print(f"[失败] {'；'.join(problems)}", file=sys.stderr)
        return 1

    # ③ 落库 + 写文件
    collected_at = dbm.now_iso()
    batch_id = hs.create_batch(batch_key, keyword, source=source, period_start=args.period_start,
                               period_end=args.period_end, adapter_used=collected.adapter_id,
                               collected_at=collected_at, path=args.db)
    hs.add_items(batch_id, items, path=args.db)
    hs.update_batch(batch_id, items_count=len(items), path=args.db)

    stamp = rec.unique_stamp(out_dir, "hotspots")
    json_path = out_dir / f"hotspots-{stamp}.json"
    md_path = out_dir / f"hotspots-{stamp}.md"
    summary = hs.aggregate(items)
    json_path.write_text(json.dumps({
        "batch_key": batch_key, "keyword": keyword, "source": source,
        "collect_adapter": collected.adapter_id, "classify_adapter": result.adapter_id,
        "prompt_version": tpl.version, "period": period, "collected_at": collected_at,
        "count": len(items), "items": items,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        f"# 热点批次 {batch_key}\n\n- 关键词：{keyword}\n- 来源：{source}（{collected.adapter_id}）\n"
        f"- 周期：{period}\n- 采集时间：{collected_at}\n- 条数：{len(items)}\n\n"
        + hs.render_table(items, fmt="md") + "\n\n" + hs.render_summary(summary) + "\n",
        encoding="utf-8")

    info = {
        "batch_key": batch_key, "batch_id": batch_id, "keyword": keyword, "source": source,
        "count": len(items), "categories": {k: v["count"] for k, v in summary.items() if k != "合计"},
        "collect_adapter": collected.adapter_id, "classify_adapter": result.adapter_id,
        "model_version": result.model_version, "prompt_version": tpl.version,
        "files": [rec.rel_path(json_path), rec.rel_path(md_path)],
        "next": f"python3 .dsh/skills/table-builder/run.py build --batch {batch_key}",
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"[完成] 热点批次 {batch_key}：{len(items)} 条（{source} / {collected.adapter_id}）")
        for cat, cnt in info["categories"].items():
            print(f"  - {cat}：{cnt} 条")
        print(f"  文件：{info['files'][0]}")
        print(f"  下一步：{info['next']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hotspot-collector", description="热点采集员：采集热点并归类去重")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("collect", help="采集一批热点并归类")
    s.add_argument("--keyword", default="", help="采集关键词")
    s.add_argument("--keywords", default="", help="多个关键词（逗号分隔，与 --keyword 等价）")
    s.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"最多保留条数（默认 {DEFAULT_LIMIT}）")
    s.add_argument("--fixture", default=None, help="离线夹具 JSON（缺省时由 browser 链决定谁能采）")
    s.add_argument("--out", default=None, help="输出目录（缺省 workspace/hotspots/<批次号>）")
    s.add_argument("--batch-key", default=None, help="指定批次号（缺省按时间戳生成）")
    s.add_argument("--period-start", default="", help="统计周期开始")
    s.add_argument("--period-end", default="", help="统计周期结束")
    s.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS, help=f"最多尝试次数（默认 {DEFAULT_ATTEMPTS}）")
    s.add_argument("--allow-paid", action="store_true", help="允许调用计费适配器（默认只走免费链）")
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
    except (hs.HotspotError, InputError, RuntimeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
