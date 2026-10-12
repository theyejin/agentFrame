#!/usr/bin/env python3
# 文件用途：本地图片共享层 —— 占位整图绘制、6×4 网格切分、图片体检（尺寸/编号/非空），全部离线可跑。
# 对应需求：R-L1-06（分镜 → 图片）、R-L1-19（24 张一致）、§6.5 交接契约（24 张且分辨率一致）、C-09（零付费门禁下的离线终点）。
# 对应流程图：.archify/FLOW-VISUAL-20261012/visual-line.html（整图 6×4 → 切 24 张 → 抽查）
# 维护提示：只在这里实现图片读写与切分；skill 里不要直接 import PIL。Pillow 缺失时必须给出人话报错，不许静默失败。
"""本地图片共享层。

职责边界：
  * 画「占位整图」（本地 fallback，不是可发布素材，只用来打通流程与测试）；
  * 把一张整图按行列等分成独立图（`split.grid-slicer` 适配器的真实实现）；
  * 体检一批切好的图：数量、编号连续、尺寸一致、文件非空。

依赖：Pillow（本机已装 12.1.1）。若缺失，`require_pillow()` 会抛出带安装提示的 ImageError。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

try:  # 延迟到调用点报错，保证 import 本模块不会因为缺 Pillow 而整体失败
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - 只在没装 Pillow 的机器上走到
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
# 常见中文字体候选（macOS 优先），找不到就退回只画 ASCII 的内置位图字体
FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
CELL_BG = (24, 28, 38)
CELL_BORDER = (90, 110, 140)
LABEL_FG = (235, 240, 250)
SHOT_NAME_RE = re.compile(r"^(?P<prefix>.+)-(?P<no>\d{2,3})$")


class ImageError(ValueError):
    """图片处理不合法或环境缺依赖。"""


def require_pillow() -> None:
    """确认本地具备图片处理能力（离线终点不允许「没装库就静默跳过」）。"""
    if Image is None:
        raise ImageError("缺少 Pillow：请先 `python3 -m pip install Pillow`（本地切图是离线终点，不能跳过）")


def load_font(size: int):
    """找一个能画中文的字体；找不到返回 None（调用方退回 ASCII 标签）。"""
    require_pillow()
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # 字体文件损坏 / 索引不对 → 试下一个
                continue
    return None


def _ascii_only(text: str) -> str:
    """把中文等非 ASCII 字符替换掉，供没有中文字体时使用。"""
    return "".join(ch if ord(ch) < 128 else "." for ch in text)


def make_grid_image(cols: int, rows: int, cell_w: int, cell_h: int,
                    labels: Iterable[str] = (), title: str = "") -> "Image.Image":
    """画一张 cols×rows 的占位整图：每格标出分镜号，并尽量写上分镜前几个字。"""
    require_pillow()
    if cols < 1 or rows < 1:
        raise ImageError(f"行列数必须为正：cols={cols} rows={rows}")
    if cell_w < 16 or cell_h < 16:
        raise ImageError(f"单格尺寸太小（至少 16×16）：{cell_w}×{cell_h}")
    labels = list(labels)
    canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), CELL_BG)
    draw = ImageDraw.Draw(canvas)
    big = load_font(max(14, cell_w // 10))
    small = load_font(max(11, cell_w // 18))
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * cell_w, r * cell_h
            x1, y1 = x0 + cell_w - 1, y0 + cell_h - 1
            draw.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], outline=CELL_BORDER, width=2)
            no = r * cols + c + 1
            tag = f"#{no:02d}"
            if big is not None:
                draw.text((x0 + 10, y0 + 10), tag, fill=LABEL_FG, font=big)
            else:
                draw.text((x0 + 10, y0 + 10), tag, fill=LABEL_FG)
            note = labels[no - 1] if no <= len(labels) else ""
            if note:
                text = note if small is not None else _ascii_only(note)
                text = text[: max(4, cell_w // (16 if small is not None else 8))]
                if small is not None:
                    draw.text((x0 + 10, y0 + 10 + max(14, cell_w // 10) + 6), text, fill=LABEL_FG, font=small)
                else:
                    draw.text((x0 + 10, y0 + 10 + max(14, cell_w // 10) + 6), text, fill=LABEL_FG)
    if title:  # 顶部一行说明，方便人一眼看出这是哪条任务
        cap = title if load_font(12) is not None else _ascii_only(title)
        draw.text((10, 8), cap[:120], fill=LABEL_FG)
    return canvas


def save_image(image: "Image.Image", out_path: str | Path) -> Path:
    """把图片存到指定路径（自动建父目录，按扩展名决定格式）。"""
    require_pillow()
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target


def make_placeholder_grid(out_path: str | Path, cols: int, rows: int, cell_w: int, cell_h: int,
                          labels: Iterable[str] = (), title: str = "") -> dict[str, Any]:
    """一步到位：画占位整图并落盘，返回尺寸与路径。"""
    image = make_grid_image(cols, rows, cell_w, cell_h, labels, title)
    target = save_image(image, out_path)
    return {"path": str(target), "width": image.width, "height": image.height,
            "cols": cols, "rows": rows, "cells": cols * rows}


def read_size(path: str | Path) -> tuple[int, int]:
    """读出图片尺寸；文件不存在或不是图片都抛 ImageError。"""
    require_pillow()
    target = Path(path)
    if not target.is_file():
        raise ImageError(f"图片不存在：{target}")
    try:
        with Image.open(target) as im:
            return int(im.width), int(im.height)
    except Exception as exc:  # 不是图片 / 解码失败
        raise ImageError(f"读不出图片尺寸（{target}）：{exc}") from exc


def slice_grid(src: str | Path, cols: int, rows: int, out_dir: str | Path,
               prefix: str = "shot", ext: str = ".png", start_no: int = 1) -> list[dict[str, Any]]:
    """把整图按 cols×rows 等分成独立图，命名 `<prefix>-01.png` 起。

    返回每张图的 shot_no / 路径 / 尺寸。行优先（从左到右、从上到下）。
    """
    require_pillow()
    if ext not in IMAGE_EXTS:
        raise ImageError(f"扩展名不在允许集合 {IMAGE_EXTS}：{ext}")
    source = Path(src)
    if not source.is_file():
        raise ImageError(f"整图不存在：{source}")
    if cols < 1 or rows < 1:
        raise ImageError(f"行列数必须为正：cols={cols} rows={rows}")
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    shots: list[dict[str, Any]] = []
    with Image.open(source) as im:
        width, height = im.width, im.height
        cell_w, cell_h = width // cols, height // rows
        if cell_w < 8 or cell_h < 8:
            raise ImageError(f"整图 {width}×{height} 切 {cols}×{rows} 后单格过小（{cell_w}×{cell_h}）")
        for r in range(rows):
            for c in range(cols):
                no = start_no + r * cols + c
                box = (c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h)
                name = f"{prefix}-{no:02d}{ext}"
                target = out_root / name
                im.crop(box).save(target)
                shots.append({"shot_no": no, "path": str(target), "width": cell_w, "height": cell_h,
                              "bytes": target.stat().st_size})
    return shots


def check_images(paths: Iterable[str | Path], *, expected: int = 24, prefix: str = "shot",
                 min_side: int = 64) -> dict[str, Any]:
    """体检一批图：数量、编号 1..N 连续、文件非空、尺寸一致、单边不小于 min_side。"""
    require_pillow()
    items = [Path(p) for p in paths]
    problems: list[str] = []
    warnings: list[str] = []
    if not items:
        return {"ok": False, "count": 0, "sizes": [], "problems": ["没有传入任何图片"], "warnings": []}
    if len(items) != expected:
        problems.append(f"图片数量应为 {expected}，实际 {len(items)}")
    no_seq: list[int] = []
    sizes: list[tuple[int, int]] = []
    for item in sorted(items):
        if not item.is_file():
            problems.append(f"图片不存在：{item}")
            continue
        if item.stat().st_size <= 0:
            problems.append(f"图片是空文件：{item}")
            continue
        try:
            size = read_size(item)
        except ImageError as exc:
            problems.append(str(exc))
            continue
        sizes.append(size)
        if min(size) < min_side:
            problems.append(f"图片过小（{size[0]}×{size[1]}，单边至少 {min_side}）：{item.name}")
        match = SHOT_NAME_RE.match(item.stem)
        if match and match.group("prefix") == prefix:
            no_seq.append(int(match.group("no")))
        else:
            warnings.append(f"文件名不符合 `<{prefix}>-NN` 规范：{item.name}")
    if expected and len(items) != expected:
        problems.append(f"图片数量应为 {expected}，实际 {len(items)}")
    if no_seq:
        no_seq.sort()
        if no_seq != list(range(1, len(items) + 1)):
            problems.append(f"编号不连续或不从 01 起：{[f'{n:02d}' for n in no_seq]}")
    if sizes and len(set(sizes)) > 1:
        problems.append(f"尺寸不一致：{sorted(set(sizes))}")
    return {"ok": not problems, "count": len(items), "sizes": [f"{w}x{h}" for w, h in sizes],
            "problems": problems, "warnings": warnings}
