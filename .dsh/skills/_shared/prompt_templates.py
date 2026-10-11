#!/usr/bin/env python3
# 文件用途：共享库 —— 提示词文件（templates/prompts/*.md）的解析、渲染与自检，供 prompt-registry 与各生成类 skill 共用。
# 对应需求：R-7-03（提示词入仓为文件、不许写死在代码里，且版本可追溯）、R-L1-20（模板与实现分离）。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（prompt-registry）、.archify/FLOW-OVERALL-20261012/overall-operations.html
# 维护提示：模板必须带 frontmatter 且声明全部变量；新增模板后跑 python3 .dsh/skills/prompt-registry/run.py check。
"""提示词模板库。

模板文件格式（templates/prompts/<prompt_key>.md）：

    ---
    prompt_key: copy-generate        # 必须与文件名一致
    version: v1                      # 版本号（改了正文就要升版本，保证可追溯）
    purpose: 一句话说明用途
    used_by: 使用它的 skill 名
    variables: [topic_title, ...]    # 声明全部变量，改正文必须同步改这里
    ---
    正文里用 {{变量名}} 占位

设计取舍：变量清单显式声明（而不是从正文里猜），这样「模板要什么」与「调用方给什么」可以对账，
少给一个变量在渲染时就报错，而不是生成一段带 {{占位符}} 的垃圾文案。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from env_file import REPO_ROOT

PROMPTS_DIR = REPO_ROOT / "templates" / "prompts"
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


class PromptError(RuntimeError):
    """模板本身有问题（缺字段、变量对不上）。"""


class MissingVariable(PromptError):
    """渲染时调用方漏给了变量。"""

    def __init__(self, prompt_key: str, names: list[str]) -> None:
        self.prompt_key = prompt_key
        self.names = sorted(names)
        super().__init__(f"模板 {prompt_key} 缺少变量：{', '.join(self.names)}")


@dataclass
class PromptTemplate:
    """一份提示词模板。"""

    prompt_key: str
    version: str
    body: str
    path: Path
    purpose: str = ""
    used_by: str = ""
    variables: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def rel_path(self) -> str:
        """仓库内相对路径（登记进 prompt_versions.file_path 用）。"""
        return str(self.path.relative_to(REPO_ROOT))

    def placeholders(self) -> set[str]:
        """正文里实际出现的占位符。"""
        return set(PLACEHOLDER_RE.findall(self.body))

    def render(self, variables: dict[str, Any]) -> str:
        """填充变量；漏给或多给都报错（多给只提示，不算致命）。"""
        missing = [v for v in self.variables if v not in variables]
        missing += [p for p in self.placeholders() if p not in variables and p not in missing]
        if missing:
            raise MissingVariable(self.prompt_key, missing)
        rendered = PLACEHOLDER_RE.sub(lambda m: str(variables[m.group(1)]), self.body)
        return rendered.strip() + "\n"


def parse_template(path: Path) -> PromptTemplate:
    """解析单个模板文件。"""
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        raise PromptError(f"{path.name} 缺少 frontmatter（--- 头）")
    meta = yaml.safe_load(match.group(1)) or {}
    for key in ("prompt_key", "version"):
        if not meta.get(key):
            raise PromptError(f"{path.name} 的 frontmatter 缺少 {key}")
    if meta["prompt_key"] != path.stem:
        raise PromptError(f"{path.name} 的 prompt_key（{meta['prompt_key']}）必须与文件名一致")
    return PromptTemplate(
        prompt_key=meta["prompt_key"],
        version=str(meta["version"]),
        body=match.group(2).strip(),
        path=path,
        purpose=str(meta.get("purpose", "")),
        used_by=str(meta.get("used_by", "")),
        variables=[str(v) for v in (meta.get("variables") or [])],
        meta=meta,
    )


def load_all(prompts_dir: Path | None = None) -> list[PromptTemplate]:
    """按文件名排序加载全部模板。"""
    directory = prompts_dir or PROMPTS_DIR
    return [parse_template(p) for p in sorted(directory.glob("*.md"))]


def load(prompt_key: str, prompts_dir: Path | None = None) -> PromptTemplate:
    """按 prompt_key 取一份模板。"""
    directory = prompts_dir or PROMPTS_DIR
    path = directory / f"{prompt_key}.md"
    if not path.is_file():
        raise PromptError(f"找不到提示词模板：{path.relative_to(REPO_ROOT)}")
    return parse_template(path)


def check(prompts_dir: Path | None = None) -> list[str]:
    """自检：声明变量与正文占位符必须一致，且模板可被解析。返回问题清单（空=通过）。"""
    problems: list[str] = []
    for path in sorted((prompts_dir or PROMPTS_DIR).glob("*.md")):
        try:
            tpl = parse_template(path)
        except PromptError as exc:
            problems.append(str(exc))
            continue
        declared, used = set(tpl.variables), tpl.placeholders()
        for name in sorted(declared - used):
            problems.append(f"{tpl.rel_path}：声明了变量 {name}，但正文里没有 {{{{{name}}}}} 占位符")
        for name in sorted(used - declared):
            problems.append(f"{tpl.rel_path}：正文用了 {{{{{name}}}}}，但 variables 里没声明")
        if not tpl.purpose:
            problems.append(f"{tpl.rel_path}：缺少 purpose")
        if not tpl.used_by:
            problems.append(f"{tpl.rel_path}：缺少 used_by")
    return problems
