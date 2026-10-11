#!/usr/bin/env python3
# 文件用途：把 templates/adapters/registry.json 的适配器声明同步进数据库 adapter_registry 表（登记表是源头，数据库是查询副本）。
# 对应需求：R-L2-16（适配器声明包含能力/密钥/计费/失败特征/降级顺序）、R-L2-17（运行时按降级顺序调用）、§7（adapter_registry 表）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（外部服务适配层）
# 维护提示：registry.json 的字段改名时同步本脚本的映射；本脚本只写「进数据库的列」，运行时专用字段（implemented/cost_per_call/settings）有意跳过。
"""适配器声明同步脚本。

    python3 scripts/seed_adapters.py            # 同步（新增或更新，按 adapter_id 对齐）
    python3 scripts/seed_adapters.py --check    # 只比对不写库，打印差异（测试与 CI 用）
    python3 scripts/seed_adapters.py --db /tmp/x.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "templates" / "adapters" / "registry.json"
DEFAULT_DB = REPO_ROOT / "db" / "app.db"

# registry.json 字段 → adapter_registry 列（只含进库的列；implemented/cost_per_call/settings 是运行时专用，不入库）
COLUMNS = ["adapter_id", "kind", "provider", "capabilities", "needs_key",
           "billable", "failure_signals", "fallback_order", "enabled", "note"]


def load_rows(path: Path = REGISTRY) -> list[dict]:
    """读登记表并规整成数据库行（布尔转 0/1）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for a in data["adapters"]:
        row = {c: a.get(c, "") for c in COLUMNS}
        row["needs_key"] = 1 if a.get("needs_key") else 0
        row["billable"] = 1 if a.get("billable") else 0
        row["enabled"] = 1 if a.get("enabled", True) else 0
        rows.append(row)
    return rows


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def compare(db: Path) -> list[str]:
    """比对登记表与数据库，返回差异描述（空=一致）。"""
    if not db.is_file():
        return [f"数据库不存在：{db}"]
    rows = {r["adapter_id"]: r for r in load_rows()}
    conn = sqlite3.connect(db)
    try:
        existing = {r[0]: r for r in conn.execute(f"SELECT {', '.join(COLUMNS)} FROM adapter_registry")}
    finally:
        conn.close()
    diffs: list[str] = []
    for aid, row in rows.items():
        if aid not in existing:
            diffs.append(f"数据库缺少适配器：{aid}")
            continue
        for i, col in enumerate(COLUMNS):
            if existing[aid][i] != row[col]:
                diffs.append(f"{aid}.{col}：数据库={existing[aid][i]!r} 登记表={row[col]!r}")
    for aid in existing:
        if aid not in rows:
            diffs.append(f"数据库多出适配器（登记表已删）：{aid}")
    return diffs


def sync(db: Path) -> int:
    """写入数据库（按 adapter_id 覆盖更新）。返回写入条数。"""
    rows = load_rows()
    conn = sqlite3.connect(db)
    try:
        for row in rows:
            values = [row[c] for c in COLUMNS] + [_now()]
            placeholders = ", ".join(["?"] * (len(COLUMNS) + 1))
            conn.execute(
                f"""INSERT INTO adapter_registry ({', '.join(COLUMNS)}, updated_at)
                    VALUES ({placeholders})
                    ON CONFLICT(adapter_id) DO UPDATE SET
                      {', '.join(f'{c} = excluded.{c}' for c in COLUMNS[1:])},
                      updated_at = excluded.updated_at""",
                values,
            )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把适配器登记表同步进数据库")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="数据库路径（默认 db/app.db）")
    parser.add_argument("--check", action="store_true", help="只比对不写库")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    db = Path(args.db)

    if args.check:
        diffs = compare(db)
        if args.json:
            print(json.dumps({"ok": not diffs, "diffs": diffs}, ensure_ascii=False, indent=2))
        elif diffs:
            print(f"发现 {len(diffs)} 处不一致：")
            for d in diffs:
                print(f"  - {d}")
        else:
            print("适配器登记表与数据库一致 ✅")
        return 1 if diffs else 0

    if not db.is_file():
        print(f"[错误] 数据库不存在：{db}（先跑 python3 scripts/db_init.py）", file=sys.stderr)
        return 2
    n = sync(db)
    print(f"[完成] 已同步 {n} 条适配器声明 → {db}（adapter_registry 表）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
