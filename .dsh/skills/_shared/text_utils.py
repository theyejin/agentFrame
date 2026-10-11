#!/usr/bin/env python3
# 文件用途：文本解析共享层 —— 把提示词产出的文本解析成结构化数据（3 套文案、24 条分镜），并统一字数口径。
# 对应需求：R-L1-05（文案生成）、R-L1-06（分镜拆解）、R-L1-19（24 条分镜与一致性校验）、F-02（字数区间）。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html
# 维护提示：解析格式必须与 templates/prompts/*.md 的「输出格式」段保持一致；改格式要同时改提示词版本与本文件。
"""文本解析共享层。

为什么单独放一层：文案与分镜的解析规则既要被生成方（copy-writer / storyboard-builder）用，
也要被校验方（storyboard-validator）与测试用；放一处才不会出现「生成按 A 格式、校验按 B 格式」。
"""

from __future__ import annotations

import re
from typing import Any

# 方案头：方案1（侧重：hook | 开头钩子）
PLAN_HEAD_RE = re.compile(r"^方案\s*(\d)\s*[（(]\s*侧重\s*[:：]\s*([A-Za-z_]+)\s*(?:\|\s*(.*?))?\s*[)）]\s*$")
# 分镜行：01 | 画面描述 | 镜头提示
SHOT_LINE_RE = re.compile(r"^\s*(\d{1,2})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*$")


def count_words(text: str) -> int:
    """字数口径（全项目统一）：去掉所有空白字符后的字符数，标点计入。

    中文场景下这是最接近「读者感知字数」的口径；英文按字符计，首版不做分词。
    """
    return len(re.sub(r"\s+", "", text or ""))


def parse_copy_plans(text: str) -> list[dict[str, Any]]:
    """解析文案模型输出 → [{plan_no, focus, focus_note, body}]。

    容错：正文可跨多行；空行不计；缺少「侧重」键的行会让该方案 focus 为空字符串（由调用方判定为不合格）。
    """
    plans: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        m = PLAN_HEAD_RE.match(line.strip())
        if m:
            if current:
                current["body"] = "\n".join(current.pop("_lines")).strip()
                plans.append(current)
            current = {
                "plan_no": int(m.group(1)),
                "focus": (m.group(2) or "").strip().lower(),
                "focus_note": (m.group(3) or "").strip(),
                "_lines": [],
            }
            continue
        if current is not None:
            current["_lines"].append(line)
    if current:
        current["body"] = "\n".join(current.pop("_lines")).strip()
        plans.append(current)
    return plans


def parse_storyboard(text: str, shot_seconds: float = 0.0) -> list[dict[str, Any]]:
    """解析分镜模型输出 → [{shot_no, scene_text, camera_note, duration_s}]（按出现顺序）。

    文本格式里没有时长字段：每条时长统一取 `shot_seconds`（由调用方给；0 表示未知）。
    """
    shots: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        m = SHOT_LINE_RE.match(raw)
        if not m:
            continue
        shots.append({
            "shot_no": int(m.group(1)),
            "scene_text": m.group(2).strip(),
            "camera_note": m.group(3).strip(),
            "duration_s": float(shot_seconds),
        })
    return shots


def check_storyboard_shape(shots: list[dict[str, Any]], expected: int = 24) -> list[str]:
    """分镜结构自检（R-L1-19）：条数、编号连续、字段非空、场景不重复。返回问题清单（空=通过）。"""
    problems: list[str] = []
    if len(shots) != expected:
        problems.append(f"分镜条数为 {len(shots)}，要求正好 {expected} 条")
    numbers = [s["shot_no"] for s in shots]
    if numbers != list(range(1, expected + 1)):
        problems.append(f"分镜编号必须从 1 连续到 {expected}，实际为 {numbers[:8]}{'…' if len(numbers) > 8 else ''}")
    for s in shots:
        if not s["scene_text"]:
            problems.append(f"第 {s['shot_no']} 条缺画面描述")
    seen: dict[str, int] = {}
    for s in shots:
        key = s["scene_text"][:20]
        if key and key in seen:
            problems.append(f"第 {s['shot_no']} 条与第 {seen[key]} 条画面描述重复")
        seen.setdefault(key, s["shot_no"])
    return problems
