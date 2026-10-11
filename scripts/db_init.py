#!/usr/bin/env python3
# 文件用途：建库脚本 —— 按 db/schema.sql（或按 db/migrations/ 顺序）创建本地数据库，并灌入平台模板种子数据。
# 对应需求：R-L1-04（数据库二进制不入库，靠脚本可重建）、规格 §7（数据模型）、R-8-01（平台模板）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（本地数据库与日志留痕）
# 维护提示：新增迁移或种子文件后无需改本脚本（自动按目录扫描）；改了建库方式请同步 db/README.md 与 docs/directory-and-files.md。
"""建库脚本。

用法：
    python3 scripts/db_init.py                    # 用 db/schema.sql 建库（推荐：直接到最新结构），再灌种子
    python3 scripts/db_init.py --from-migrations  # 用 db/migrations/*.sql 顺序建库（验证迁移链）
    python3 scripts/db_init.py --db /tmp/x.db     # 指定数据库文件（默认读 .env 的 DB_PATH，兜底 db/app.db）
    python3 scripts/db_init.py --force            # 目标已存在时先删除（默认拒绝覆盖，防误删）

退出码：0 = 成功；1 = 失败。
"""

import argparse
import glob
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "db", "app.db")


def read_env_db_path():
    """从 .env 读 DB_PATH（没有就用默认值）。首版只做最简单的 KEY=VALUE 解析。"""
    env_file = os.path.join(ROOT, ".env")
    if not os.path.isfile(env_file):
        return DEFAULT_DB
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("DB_PATH="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val if os.path.isabs(val) else os.path.join(ROOT, val)
    return DEFAULT_DB


def run_sql_file(conn, path):
    """执行一个 .sql 文件（executescript 支持多语句）。"""
    with open(path, encoding="utf-8") as f:
        conn.executescript(f.read())


def main():
    ap = argparse.ArgumentParser(description="按 schema.sql 或 migrations 建库并灌种子")
    ap.add_argument("--db", default=None, help="数据库文件路径（默认 .env 的 DB_PATH 或 db/app.db）")
    ap.add_argument("--from-migrations", action="store_true", help="用 db/migrations/*.sql 顺序建库")
    ap.add_argument("--no-seed", action="store_true", help="不灌种子数据")
    ap.add_argument("--force", action="store_true", help="目标数据库已存在时先删除")
    args = ap.parse_args()

    db_path = args.db or read_env_db_path()
    if not os.path.isabs(db_path):
        db_path = os.path.join(ROOT, db_path)

    if os.path.exists(db_path):
        if not args.force:
            print(f"[跳过] 数据库已存在：{db_path}\n       如需重建请加 --force（注意会删除现有数据）")
            return 1
        os.remove(db_path)
        print(f"[清理] 已删除旧数据库：{db_path}")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if args.from_migrations:
            files = sorted(glob.glob(os.path.join(ROOT, "db", "migrations", "*.sql")))
            if not files:
                print("[失败] db/migrations/ 下没有迁移文件")
                return 1
            for path in files:
                run_sql_file(conn, path)
                print(f"[迁移] {os.path.relpath(path, ROOT)}")
        else:
            run_sql_file(conn, os.path.join(ROOT, "db", "schema.sql"))
            print("[建库] db/schema.sql")

        if not args.no_seed:
            for path in sorted(glob.glob(os.path.join(ROOT, "db", "seed", "*.sql"))):
                run_sql_file(conn, path)
                print(f"[种子] {os.path.relpath(path, ROOT)}")

        conn.commit()

        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        views = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
        print(f"[完成] {db_path}")
        print(f"       表 {len(tables)} 个：{', '.join(tables)}")
        print(f"       视图 {len(views)} 个：{', '.join(views)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
