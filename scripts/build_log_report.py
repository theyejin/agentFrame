#!/usr/bin/env python3
# 文件用途：扫描 logs/*.jsonl，生成仓库根目录的搭建过程报告页 build-log.html 与结构化数据 build-log.data.json（R-L2-06）。
# 对应需求：R-L2-05、R-L2-06（根目录 + 生成脚本 + 结构化数据文件，不手写 HTML）、AC-3、S10、Q-6。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
# 维护提示：每完成一个实施步骤，必须在同一次提交里追加一条 logs 记录并重跑本脚本；页面样式与交互在 _shared/console.py 里改。
"""build-log 报告页生成脚本。

用法：
    python3 scripts/build_log_report.py                 # 生成仓库根目录的 build-log.html 与 build-log.data.json
    python3 scripts/build_log_report.py --check         # 只看会生成多少条，不写文件
    python3 scripts/build_log_report.py --logs-dir tmp  # 指定日志目录（测试用）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".dsh" / "skills" / "_shared"))

import console as cs  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从 logs/*.jsonl 生成仓库根目录的 build-log 报告页")
    parser.add_argument("--logs-dir", default=None, help="日志目录（默认仓库 logs/）")
    parser.add_argument("--root", default=None, help="输出目录（默认仓库根目录）")
    parser.add_argument("--check", action="store_true", help="只统计，不写文件")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    entries = cs.logs_entries(args.logs_dir)
    if args.check:
        result = {"total": len(entries),
                  "dates": sorted({entry["date"] for entry in entries}, reverse=True),
                  "failed": sum(1 for entry in entries if entry["result"] == "failed"),
                  "written": False}
    else:
        outcome = cs.render_build_log(entries, root=args.root)
        result = {**outcome, "written": True,
                  "failed": sum(1 for entry in entries if entry["result"] == "failed")}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.check:
            print(f"日志共 {result['total']} 条，覆盖 {len(result['dates'])} 个日期，其中失败 {result['failed']} 条（未写文件）")
        else:
            print(f"已生成：{result['html']}")
            print(f"结构化数据：{result['data']}")
            print(f"共 {result['total']} 条记录、{result['dates']} 个日期，其中失败 {result['failed']} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
