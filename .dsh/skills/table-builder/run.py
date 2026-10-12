#!/usr/bin/env python3
# 文件用途：table-builder 的实现入口 —— 把一批热点按分类汇总成表格（Markdown + CSV）。
# 对应需求：FLOW-7 分类汇总成表格 / R-7-03（汇总表可读可传）/ Q-5（表格是同步文档的内容源）。
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
# 维护提示：分类枚举改动要同步 db/schema.sql 的 hotspot_items.category 与 _shared/hotspots.py 的 CATEGORIES。
"""table-builder 命令行入口。

    build [--batch 批次号] [--latest] [--kw 关键词] [--category 分类] [--out-dir DIR]
          [--fmt both|md|csv] [--json]

把热点条目按分类汇成一张表，落 workspace/hotspots/<批次号>/hotspot-table-<时间戳>.md/.csv，
并把表格路径回填到 hotspot_batches.table_path，供 feishu-sync 同步。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import db as dbm  # noqa: E402
import hotspots as hs  # noqa: E402
import recording as rec  # noqa: E402


class InputError(ValueError):
    """输入校验不通过（没有批次、没有条目等）。"""


def _resolve_batch(args: argparse.Namespace) -> dict:
    if args.batch:
        batch = hs.get_batch(args.batch, path=args.db)
        if not batch:
            raise InputError(f"批次不存在：{args.batch}")
        return batch
    batch = hs.latest_batch(path=args.db)
    if not batch:
        raise InputError("还没有任何热点批次，先跑 hotspot-collector collect")
    return batch


def cmd_build(args: argparse.Namespace) -> int:
    batch = _resolve_batch(args)
    items = hs.items_of(batch["id"], category=args.category, path=args.db)
    if args.kw:
        needle = args.kw.strip()
        items = [i for i in items if needle in str(i.get("title", ""))]
    if not items:
        raise InputError(f"批次 {batch['batch_key']} 里没有符合条件的条目（分类={args.category or '全部'}）")

    out_dir = Path(args.out_dir) if args.out_dir else (rec.abs_path_of("workspace") / "hotspots" / batch["batch_key"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rec.unique_stamp(out_dir, "hotspot-table")
    summary = hs.aggregate(items)
    files: list[str] = []

    header = (f"# 热点分类汇总表 —— {batch['batch_key']}\n\n"
              f"- 关键词：{batch['keyword']}\n- 来源：{batch['source']}\n"
              f"- 周期：{batch.get('period_start') or '—'} ~ {batch.get('period_end') or '—'}\n"
              f"- 条数：{len(items)}\n\n")
    if args.fmt in ("both", "md"):
        md_path = out_dir / f"hotspot-table-{stamp}.md"
        md_path.write_text(header + hs.render_table(items, fmt="md") + "\n\n"
                           + hs.render_summary(summary) + "\n", encoding="utf-8")
        files.append(rec.rel_path(md_path))
    if args.fmt in ("both", "csv"):
        csv_path = out_dir / f"hotspot-table-{stamp}.csv"
        csv_path.write_text("分类,标题,热度,来源链接\n" + hs.render_table(items, fmt="csv") + "\n",
                            encoding="utf-8")
        files.append(rec.rel_path(csv_path))

    table_path = next((f for f in files if f.endswith(".md")), files[0] if files else "")
    hs.update_batch(batch["id"], table_path=table_path, path=args.db)
    info = {
        "batch_key": batch["batch_key"], "batch_id": batch["id"], "count": len(items),
        "categories": {k: v["count"] for k, v in summary.items() if k != "合计"},
        "files": files, "table_path": table_path,
        "next": f"python3 .dsh/skills/feishu-sync/run.py sync --batch {batch['batch_key']}",
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"[完成] 汇总表已生成：{batch['batch_key']}（{len(items)} 条）")
        for cat, cnt in info["categories"].items():
            print(f"  - {cat}：{cnt} 条")
        for f in files:
            print(f"  文件：{f}")
        print(f"  下一步：{info['next']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="table-builder", description="表格汇总员：把热点按分类汇成表格")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("build", help="生成分类汇总表")
    s.add_argument("--batch", default=None, help="批次号（缺省用最近一批）")
    s.add_argument("--latest", action="store_true", help="等价于不传 --batch（用最近一批）")
    s.add_argument("--kw", default="", help="按标题关键词过滤")
    s.add_argument("--category", default=None, choices=list(hs.CATEGORIES), help="只看某个分类")
    s.add_argument("--out-dir", default=None, help="输出目录（缺省 workspace/hotspots/<批次号>）")
    s.add_argument("--fmt", default="both", choices=["both", "md", "csv"], help="输出格式（默认 md+csv）")
    s.set_defaults(func=cmd_build)
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
    except (InputError, hs.HotspotError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
