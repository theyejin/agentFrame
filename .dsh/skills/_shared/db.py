#!/usr/bin/env python3
# 文件用途：数据库访问共享层 —— 统一连接、时间格式与读写入口，供各 skill 直接复用。
# 对应需求：§7 数据模型、R-L1-04（数据库二进制不入库）、R-7-01~05（产物/指标/版本字段）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（本地留痕与外部文档）
# 维护提示：本文件只做「连接与读写」，不写业务规则；表结构变更请改 db/schema.sql 与 db/migrations/。
"""SQLite 访问共享层。

约定：
  * 库路径优先取 --db 参数，其次 .env 的 DB_PATH，最后 db/app.db；
  * 时间统一写 ISO-8601 本地时区文本（与 db/README.md 第 5 节一致）；
  * 行以 dict 返回（sqlite3.Row → dict），方便直接 json.dumps；
  * 默认开启外键约束（SQLite 默认关闭，必须显式打开，否则 REFERENCES 形同虚设）。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from env_file import get, load_env

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = "db/app.db"


def db_path(explicit: str | None = None) -> Path:
    """解析数据库路径：显式参数 > .env 的 DB_PATH > db/app.db。"""
    load_env()
    raw = explicit or get("DB_PATH") or DEFAULT_DB
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path)


def connect(path: str | None = None) -> sqlite3.Connection:
    """打开连接：行工厂为 Row、开启外键、自动提交关闭（由调用方决定提交）。"""
    target = db_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(path: str | None = None) -> Iterator[sqlite3.Connection]:
    """事务上下文：正常结束提交，异常回滚。"""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    """当前时间（ISO-8601，带本地时区偏移），与 logs/ 的时间格式一致。"""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def query(sql: str, params: Iterable[Any] = (), path: str | None = None) -> list[dict[str, Any]]:
    """只读查询，返回 dict 列表。"""
    with connect(path) as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = (), path: str | None = None) -> dict[str, Any] | None:
    """只读查询，返回第一行或 None。"""
    rows = query(sql, params, path)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = (), path: str | None = None) -> int:
    """写操作，返回 lastrowid（无自增主键时返回受影响行数）。"""
    with transaction(path) as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def executemany(sql: str, rows: Iterable[Iterable[Any]], path: str | None = None) -> int:
    """批量写操作，返回受影响行数。"""
    with transaction(path) as conn:
        cur = conn.executemany(sql, [tuple(r) for r in rows])
        return cur.rowcount
