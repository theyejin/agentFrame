#!/usr/bin/env python3
# 文件用途：一键跑完全部模拟测试（九套），打印每套结果与合计项数，供「每步先过测试」这条完成门使用。
# 对应需求：R-L2-02（每一步完成前必须有模拟测试并通过）、AC-5、C-01（零付费：全部离线运行）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
# 维护提示：新增测试文件后不必改本脚本（按 tests/test_*.py 自动发现）；改测试文件名请同步 docs/directory-and-files.md。

"""跑完全部模拟测试。

用法：
    python3 scripts/run_tests.py              # 跑全部
    python3 scripts/run_tests.py --only copy  # 只跑名字里带 copy 的
    python3 scripts/run_tests.py --json       # 机器可读结果
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


def suites(only: str = "") -> list[Path]:
    found = sorted(p for p in TESTS_DIR.glob("test_*.py") if p.is_file())
    if only:
        found = [p for p in found if only in p.name]
    return found


def run_one(path: Path) -> dict:
    proc = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, cwd=str(ROOT))
    output = (proc.stdout or "") + (proc.stderr or "")
    match = RAN_RE.search(output)
    tail = [line for line in output.strip().splitlines() if line.startswith(("OK", "FAILED"))]
    return {
        "file": str(path.relative_to(ROOT)),
        "returncode": proc.returncode,
        "tests": int(match.group(1)) if match else 0,
        "verdict": tail[-1] if tail else ("ok" if proc.returncode == 0 else "failed"),
        "output": output,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="跑完全部模拟测试（离线）")
    parser.add_argument("--only", default="", help="只跑文件名里含该片段的测试")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    results = [run_one(path) for path in suites(args.only)]
    if not results:
        print("[错误] tests/ 下没有找到测试文件", file=sys.stderr)
        return 2

    total = sum(r["tests"] for r in results)
    failed = [r for r in results if r["returncode"] != 0]

    if args.json:
        print(json.dumps({"ok": not failed, "total": total, "suites": results,
                          "failed": [r["file"] for r in failed]}, ensure_ascii=False, indent=1))
        return 0 if not failed else 1

    for r in results:
        mark = "✅" if r["returncode"] == 0 else "❌"
        print(f"{mark} {r['file']:<32} {r['tests']:>3} 项  {r['verdict']}")
    print(f"\n合计 {len(results)} 套 / {total} 项 —— {'全部通过' if not failed else '有失败'}")
    if failed:
        for r in failed:
            print(f"\n--- {r['file']} ---\n{r['output'][-4000:]}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
