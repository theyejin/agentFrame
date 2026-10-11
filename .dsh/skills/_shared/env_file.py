#!/usr/bin/env python3
# 文件用途：共享库 —— 读取仓库根 .env（不依赖第三方库），供各 skill 取用密钥与路径配置。
# 对应需求：C-05（密钥只放 .env，不入库）、C-09（零付费门禁需要读成本上限）、R-L2-14。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（外部服务适配层）
# 维护提示：新增环境变量请同时补 .env.example；本文件不打印任何密钥值。
"""读取 .env 的最小实现（不引入 python-dotenv 依赖）。"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_env(path: str | os.PathLike | None = None, override: bool = False) -> dict[str, str]:
    """把 .env 的键值写进 os.environ（默认不覆盖已存在的真实环境变量）。

    返回本次解析到的键值字典（不包含值以外的任何输出，避免密钥进日志）。
    """
    env_path = Path(path) if path else REPO_ROOT / ".env"
    parsed: dict[str, str] = {}
    if not env_path.is_file():
        return parsed
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if not key:
            continue
        parsed[key] = value
        if override or key not in os.environ or os.environ.get(key) == "":
            os.environ[key] = value
    return parsed


def get(name: str, default: str = "") -> str:
    """取环境变量（先加载 .env），没有则返回 default。"""
    load_env()
    return os.environ.get(name, "") or default
