#!/usr/bin/env python3
# 文件用途：目录与文件结构体检 —— 检查磁盘实际结构、各目录 README 注释、以及《目录及文件说明》三者是否一致。
# 对应需求：R-L1-13（基础环境：目录与文件）、R-L1-14（目录与文件名都要有注释）、R-L2-09（说明文档随增删改同步更新）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
# 维护提示：新增顶层目录或调整必需文件时，必须同步修改本文件的 EXPECTED_DIRS / EXPECTED_ROOT_FILES 与 docs/directory-and-files.md。
"""目录结构体检脚本。

用途：每一步搭建完成后跑一次（R-L2-02「每步模拟测试通过再下一步」），确认：
  1. 计划内的顶层目录都在，且每个目录都有非空 README.md，README.md 里有「用途：」这一行（中文名注释，R-L1-14）；
  2. 必需文件（.env.example、docs/directory-and-files.md 等）存在；
  3. 《目录及文件说明》docs/directory-and-files.md 里逐个提到了这些目录，没有漏记；
  4. 不该出现在仓库里的东西（.env、*.db、.tmp/）确实没被纳入。

退出码：0 = 全部通过；1 = 有问题（逐条打印）。
用法：
    python3 scripts/structure_check.py            # 人读报告
    python3 scripts/structure_check.py --json     # 机器可读（CI / agent 调用）
"""

import json
import os
import subprocess
import sys

# 仓库根 = 本文件所在目录的上一级（scripts/ 的父目录）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 计划内的顶层目录（与 docs/directory-structure-plan.md 第 2 节一致）
# 注意：docs/ 与 .archify/ 在 WP-05 之前就已存在，一并纳入检查。
EXPECTED_DIRS = [
    "docs",
    ".archify",
    "agents",
    ".dsh/skills",
    "db",
    "dashboard",
    "workflows",
    "templates",
    "scripts",
    "tests",
    "logs",
    "workspace",
]

# 必需文件（路径相对仓库根）
EXPECTED_ROOT_FILES = [
    "README.md",
    ".gitignore",
    ".env.example",
    "docs/directory-and-files.md",
    "docs/requirements-spec.md",
    "docs/discussion-record.md",
    "docs/skill-roster.md",
    "docs/skill-readme-contract.md",
    "docs/directory-structure-plan.md",
    "docs/decision-log.md",
    "scripts/structure_check.py",
]

# 绝不允许出现在仓库工作区的路径/后缀（C-05 密钥、R-L1-04 数据库二进制、本地临时目录）
FORBIDDEN = [".env", ".tmp"]
FORBIDDEN_SUFFIX = (".db", ".sqlite", ".sqlite3")


def check_dirs(problems, notes):
    """检查顶层目录与其 README.md。"""
    for rel in EXPECTED_DIRS:
        path = os.path.join(ROOT, rel)
        if not os.path.isdir(path):
            problems.append(f"缺少目录：{rel}/")
            continue
        readme = os.path.join(path, "README.md")
        if not os.path.isfile(readme):
            problems.append(f"目录缺 README.md（R-L1-14）：{rel}/README.md")
            continue
        with open(readme, encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            problems.append(f"README.md 为空：{rel}/README.md")
        elif "用途：" not in text:
            problems.append(f"README.md 缺「用途：」说明行：{rel}/README.md")
        else:
            notes.append(f"OK 目录 {rel}/ 有 README.md 且含用途说明")


def check_files(problems, notes):
    """检查必需文件。"""
    for rel in EXPECTED_ROOT_FILES:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            problems.append(f"缺少文件：{rel}")
        elif os.path.getsize(path) == 0:
            problems.append(f"文件为空：{rel}")
        else:
            notes.append(f"OK 文件 {rel}")


def check_doc_covers_dirs(problems, notes):
    """检查《目录及文件说明》是否逐个覆盖了顶层目录（R-L2-09）。"""
    doc = os.path.join(ROOT, "docs/directory-and-files.md")
    if not os.path.isfile(doc):
        problems.append("缺少《目录及文件说明》：docs/directory-and-files.md")
        return
    with open(doc, encoding="utf-8") as f:
        text = f.read()
    for rel in EXPECTED_DIRS:
        # 说明文档里以 `rel/` 形式记录目录
        if f"{rel}/" not in text:
            problems.append(f"《目录及文件说明》未收录目录：{rel}/（R-L2-09）")
    if not problems:
        notes.append("OK 《目录及文件说明》已覆盖全部顶层目录")


def _is_ignored(rel):
    """路径是否被 .gitignore 排除（排除 = 允许留在本地但不入库）。"""
    r = subprocess.run(
        ["git", "check-ignore", "-q", rel],
        cwd=ROOT, capture_output=True,
    )
    return r.returncode == 0


def check_forbidden(problems, notes):
    """检查不该入库的东西确实没被 git 跟踪（密钥 / 数据库 / 临时目录）。

    允许它们存在于本地开发目录（截图、Chrome 用户目录等），但必须被 .gitignore 排除；
    一旦会被提交就是问题（C-05 密钥、R-L1-04 数据库二进制）。
    """
    ignored_only = []
    for rel in FORBIDDEN:
        if os.path.exists(os.path.join(ROOT, rel)):
            if _is_ignored(rel):
                ignored_only.append(rel)
            else:
                problems.append(
                    f"{rel} 存在且未被 .gitignore 排除，会被提交（C-05 / R-L1-04）"
                )
    for entry in os.listdir(ROOT):
        p = os.path.join(ROOT, entry)
        if os.path.isfile(p) and entry.endswith(FORBIDDEN_SUFFIX):
            if _is_ignored(entry):
                ignored_only.append(entry)
            else:
                problems.append(
                    f"仓库根出现数据库二进制 {entry} 且未被忽略（R-L1-04：只入库结构与迁移脚本）"
                )
    if ignored_only:
        notes.append("OK 禁止项仅存在于本地且已被忽略：" + "、".join(ignored_only))
    else:
        notes.append("OK 未发现密钥 / 数据库 / 临时目录")


def main():
    as_json = "--json" in sys.argv
    problems, notes = [], []

    check_dirs(problems, notes)
    check_files(problems, notes)
    check_doc_covers_dirs(problems, notes)
    check_forbidden(problems, notes)

    result = {
        "script": "structure_check",
        "root": ROOT,
        "expected_dirs": len(EXPECTED_DIRS),
        "expected_files": len(EXPECTED_ROOT_FILES),
        "ok": not problems,
        "problems": problems,
        "notes": notes,
    }

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("目录结构体检报告")
        print(f"  仓库根：{ROOT}")
        print(f"  受检顶层目录：{len(EXPECTED_DIRS)} 个；必需文件：{len(EXPECTED_ROOT_FILES)} 个")
        print("-" * 60)
        for n in notes:
            print("  " + n)
        if problems:
            print("-" * 60)
            print(f"  发现问题 {len(problems)} 条：")
            for p in problems:
                print("  ✗ " + p)
        else:
            print("-" * 60)
            print("  全部通过：目录说明与磁盘一致 ✅")

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
