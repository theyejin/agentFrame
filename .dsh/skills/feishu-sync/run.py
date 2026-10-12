#!/usr/bin/env python3
# 文件用途：feishu-sync 的实现入口 —— 把汇总表同步到飞书文档；飞书不可用时导出本地文件（Q-5 降级）
# 对应需求：FLOW-7 汇总表存飞书文档 / R-7-03（文档同步）/ Q-5（飞书 API 失败就导出文件）/ C-09（离线优先、不擅自付费）。
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
# 维护提示：新增文档服务时改 templates/adapters/registry.json 的 doc 链，不要在本文件里写死服务名。
"""feishu-sync 命令行入口。

    sync [--batch 批次号] [--file 表格文件] [--title 标题] [--folder-token TOKEN]
         [--out-dir DIR] [--json]

只做同步这一件事：经 doc 降级链（doc.feishu-api → doc.local-export）把表格内容送出去。
本版飞书 API 未接，链会落到本地导出，命令会明确说明「导出到了哪个文件」，不假装同步成功。
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
import recording as rec  # noqa: E402


class InputError(ValueError):
    """输入校验不通过（没有内容可同步等）。"""


def _resolve_source(args: argparse.Namespace) -> tuple[str, Path, dict | None]:
    """返回（标题, 内容文件, 批次行）。"""
    batch = None
    if args.batch:
        batch = hs.get_batch(args.batch, path=args.db)
        if not batch:
            raise InputError(f"批次不存在：{args.batch}")
    else:
        batch = hs.latest_batch(path=args.db)   # 不带批次号就用最近一批
    raw = args.file or (batch or {}).get("table_path") or ""
    if not raw:
        raise InputError("没有可同步的文件：传 --file，或先跑 table-builder build 生成汇总表")
    path = Path(raw)
    if not path.is_absolute():
        path = rec.abs_path_of(raw)
    if not path.is_file():
        raise InputError(f"文件不存在：{raw}")
    title = args.title or (f"热点汇总表 {batch['batch_key']}" if batch else path.stem)
    return title, path, batch


def cmd_sync(args: argparse.Namespace) -> int:
    title, src, batch = _resolve_source(args)
    content = src.read_text(encoding="utf-8")
    stamp = rec.timestamp_slug()
    out_dir = Path(args.out_dir) if args.out_dir else (rec.abs_path_of("workspace") / "exports" / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{src.stem}.md"

    payload = {
        "title": title,
        "content": content,
        "rel_path": rec.rel_path(target),
        "abs_path": str(target),
        "folder_token": args.folder_token,
        "source_file": rec.rel_path(src),
    }
    result = ar.invoke("doc", payload, allow_paid=False)
    if not result.ok:
        print(f"[错误] 文档同步失败：{result.error}", file=sys.stderr)
        return 1

    out = result.output or {}
    synced_path = out.get("path") or rec.rel_path(target)
    degraded = str(result.adapter_id) != "doc.feishu-api"
    if batch:
        hs.update_batch(batch["id"], export_path=synced_path, path=args.db)

    info = {
        "title": title, "batch_key": (batch or {}).get("batch_key", ""), "source_file": rec.rel_path(src),
        "adapter_used": result.adapter_id, "model_version": result.model_version,
        "export_path": synced_path, "bytes": out.get("bytes", 0), "degraded": degraded,
        "note": ("飞书 API 本版未接：已导出本地文件（Q-5 降级路径），需要人工上传到飞书文档"
                 if degraded else "已通过飞书 API 同步"),
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"[完成] {info['note']}")
        print(f"  内容源：{info['source_file']}")
        print(f"  落点：{info['export_path']}（{info['bytes']} 字节，适配器 {info['adapter_used']}）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="feishu-sync", description="文档同步员：把汇总表同步到飞书文档（不可用则导出文件）")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sync", help="同步一份表格到文档")
    s.add_argument("--batch", default=None, help="批次号（缺省时用 --file）")
    s.add_argument("--file", default=None, help="要同步的表格文件")
    s.add_argument("--title", default="", help="文档标题（缺省按批次号生成）")
    s.add_argument("--folder-token", default="", help="飞书文件夹 token（本版仅记录，不调用 API）")
    s.add_argument("--out-dir", default=None, help="导出目录（缺省 workspace/exports/<时间戳>）")
    s.set_defaults(func=cmd_sync)
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
    except (InputError, hs.HotspotError, RuntimeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
