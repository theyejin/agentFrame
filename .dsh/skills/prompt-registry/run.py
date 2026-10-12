#!/usr/bin/env python3
# 文件用途：prompt-registry 的实现入口 —— 提示词模板的列出/取值/渲染/自检/版本登记（templates/prompts/*.md）。
# 对应需求：R-7-03（提示词入仓为文件、版本可追溯）、R-L1-20（skill 三件套）、R-L1-15（文件头注释）。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（prompt-registry 提供提示词版本）
# 维护提示：模板目录或 frontmatter 字段有变化，请同步 README.md、docs/skill-readme-contract.md 与模板自身。
"""prompt-registry 命令行入口。

    list    [--json]                       列出全部提示词模板
    get     --key K [--version V] [--json] 取一份模板（含正文）
    render  --key K --var k=v ... [--out P] 渲染模板（漏变量会报错）
    check   [--json]                       自检：声明变量与正文占位符是否一致
    sync    [--db PATH] [--json]           把模板版本登记进 prompt_versions 表
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import prompt_templates as pt  # noqa: E402
from env_file import REPO_ROOT, get  # noqa: E402

DEFAULT_DB = REPO_ROOT / "db" / "app.db"


def _parse_vars(pairs: list[str]) -> dict[str, str]:
    """把 --var k=v 解析成字典。"""
    out: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"--var 需要 k=v 形式，收到：{item}")
        key, _, value = item.partition("=")
        out[key.strip()] = value
    return out


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def cmd_list(args: argparse.Namespace) -> int:
    rows = [
        {"prompt_key": t.prompt_key, "version": t.version, "used_by": t.used_by,
         "variables": t.variables, "path": t.rel_path, "purpose": t.purpose}
        for t in pt.load_all()
    ]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"共 {len(rows)} 份提示词模板：")
    for r in rows:
        print(f"  {r['prompt_key']:<20} {r['version']:<5} 用于 {r['used_by']:<18} {len(r['variables'])} 个变量  {r['path']}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    tpl = pt.load(args.key)
    if args.version and args.version != tpl.version:
        print(f"[错误] 文件里的版本是 {tpl.version}，与请求的 {args.version} 不一致", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"prompt_key": tpl.prompt_key, "version": tpl.version, "purpose": tpl.purpose,
                          "used_by": tpl.used_by, "variables": tpl.variables, "path": tpl.rel_path,
                          "body": tpl.body}, ensure_ascii=False, indent=2))
    else:
        print(f"# {tpl.prompt_key} {tpl.version}（{tpl.purpose}）")
        print(f"# 变量：{', '.join(tpl.variables)}")
        print(tpl.body)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    tpl = pt.load(args.key)
    values = _parse_vars(args.var)
    try:
        rendered = tpl.render(values)
    except pt.MissingVariable as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    extra = sorted(set(values) - set(tpl.variables))
    if extra:
        print(f"[提示] 多给了未声明的变量（已忽略）：{', '.join(extra)}", file=sys.stderr)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"[完成] 已写出 {target}（{len(rendered)} 字符）")
    else:
        print(rendered)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    problems = pt.check()
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems}, ensure_ascii=False, indent=2))
        return 1 if problems else 0
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("提示词模板自检通过 ✅")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    db = Path(args.db or get("DB_PATH", str(DEFAULT_DB)))
    if not db.is_file():
        print(f"[错误] 数据库不存在：{db}（先跑 python3 scripts/db_init.py）", file=sys.stderr)
        return 2
    templates = pt.load_all()
    conn = sqlite3.connect(db)
    try:
        for tpl in templates:
            conn.execute(
                """INSERT INTO prompt_versions (prompt_key, version, file_path, note, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(prompt_key, version) DO UPDATE SET
                     file_path = excluded.file_path, note = excluded.note, created_at = excluded.created_at""",
                (tpl.prompt_key, tpl.version, tpl.rel_path, tpl.purpose, _now()),
            )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0]
    finally:
        conn.close()
    if args.json:
        print(json.dumps({"ok": True, "synced": len(templates), "total_rows": total}, ensure_ascii=False))
    else:
        print(f"[完成] 已登记 {len(templates)} 份模板到 {db}（表内共 {total} 行）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="提示词注册表：列出/取值/渲染/自检/登记版本")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="列出全部提示词模板")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("get", help="取一份模板")
    p.add_argument("--key", required=True)
    p.add_argument("--version")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("render", help="渲染模板")
    p.add_argument("--key", required=True)
    p.add_argument("--var", action="append", default=[], help="k=v，可重复")
    p.add_argument("--out")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("check", help="自检模板变量一致性")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("sync", help="把模板版本登记进数据库")
    p.add_argument("--db")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_sync)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    for _action in parser._actions:  # 子命令也认 --json（写在子命令前后都行）
        if isinstance(_action, argparse._SubParsersAction):
            for _child in _action.choices.values():
                if not any("--json" in _a.option_strings for _a in _child._actions):
                    _child.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                                        help="以 JSON 输出结果（也可写在子命令前）")
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
