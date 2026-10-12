"""本地视频能力（ffmpeg / ffprobe，离线、免费）。

用途：为视频线提供四件事的本地实现 —— ① 图片序列 → 视频草稿（图生视频兜底）；
      ② 按参数（顺序 / 每镜时长 / 素材）渲染成片；③ 抽封面帧；④ 成片体检。
      它是外部图生视频服务的兜底终点（Q-7：Remotion 为主、ffmpeg 兜底；首版 Remotion 未接，
      降级链自动落到本模块）。不联网、不计费，符合 C-09 零付费门禁。
对应需求：R-L2-14 R-L2-15（统一接口 + 适配器）、R-L2-17（降级链）、§11 Q-7。
对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html（`video.ffmpeg` 适配器节点）。
维护提示：ffmpeg 命令只在本文件出现；业务 skill 一律调用本模块，不要自己拼命令行。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

# 候选路径：先查 PATH，再查常见的本机安装位置（含本机 Python 框架自带的 ffmpeg）
FFMPEG_CANDIDATES = (
    "ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/ffmpeg",
)
FFPROBE_CANDIDATES = (
    "ffprobe",
    "/opt/homebrew/bin/ffprobe",
    "/usr/local/bin/ffprobe",
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/ffprobe",
)

# 成片体检的默认口径
MIN_SECONDS = 0.5
MAX_SECONDS = 1800.0
DEFAULT_FPS = 30
DEFAULT_SECONDS_PER_IMAGE = 3.0
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")


class VideoError(RuntimeError):
    """视频能力相关的统一错误（找不到 ffmpeg、参数不合法、编码失败…）。"""


def _first_existing(candidates) -> str | None:
    for item in candidates:
        found = shutil.which(item) if "/" not in item else (item if Path(item).is_file() else None)
        if found:
            return found
    return None


def find_ffmpeg() -> str | None:
    """找到可用的 ffmpeg；没有返回 None。"""
    return _first_existing(FFMPEG_CANDIDATES)


def find_ffprobe() -> str | None:
    """找到可用的 ffprobe；没有返回 None（此时体检退化为「只看文件大小」）。"""
    return _first_existing(FFPROBE_CANDIDATES)


def require_ffmpeg() -> str:
    """取 ffmpeg 路径；没有就抛可读的中文错误（模型版本记录要用到）。"""
    path = find_ffmpeg()
    if not path:
        raise VideoError(
            "未找到 ffmpeg：本机视频能力不可用。请先安装 ffmpeg（macOS 可 `brew install ffmpeg`），"
            "或把视频链降级到 video.manual（人工剪辑）。"
        )
    return path


def ffmpeg_version() -> str:
    """取 ffmpeg 版本号（例 '9.0.2'），失败返回 'unknown'。"""
    try:
        out = subprocess.run([require_ffmpeg(), "-version"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError, VideoError):
        return "unknown"
    for line in out.splitlines():
        if line.startswith("ffmpeg version"):
            return line.split()[2].split("-")[0]
    return "unknown"


def _run(cmd: list[str], timeout: float = 300.0) -> subprocess.CompletedProcess:
    """跑一条 ffmpeg/ffprobe 命令；非 0 退出就把 stderr 尾部带进异常，方便定位。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:  # pragma: no cover - 由 require_ffmpeg 提前拦住
        raise VideoError(f"命令不存在：{cmd[0]}（{exc}）") from exc
    except subprocess.TimeoutExpired as exc:
        raise VideoError(f"命令超时（>{timeout}s）：{' '.join(cmd[:4])} …") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-4:]
        raise VideoError(f"{Path(cmd[0]).name} 退出码 {proc.returncode}：{' / '.join(tail)}")
    return proc


def _even(value: int) -> int:
    """yuv420p 要求宽高为偶数，向下取偶。"""
    return int(value) - int(value) % 2


def probe(path: str | os.PathLike) -> dict:
    """探测视频信息：宽 / 高 / 时长 / 字节数。缺 ffprobe 时退化为只读文件大小。"""
    src = Path(path)
    if not src.is_file():
        raise VideoError(f"视频文件不存在：{src}")
    info = {"path": str(src), "bytes": src.stat().st_size, "width": 0, "height": 0, "duration_s": 0.0}
    probe_bin = find_ffprobe()
    if not probe_bin:
        return info
    proc = _run([
        probe_bin, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration", "-of", "json", str(src),
    ])
    try:
        data = json.loads(proc.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        info["width"] = int(stream.get("width") or 0)
        info["height"] = int(stream.get("height") or 0)
        info["duration_s"] = round(float((data.get("format") or {}).get("duration") or 0.0), 3)
    except (ValueError, TypeError):
        raise VideoError(f"读不懂 ffprobe 输出：{(proc.stdout or '')[:120]}")
    return info


def make_slideshow(images: list, out_path: str | os.PathLike, *, seconds_per_image: float = DEFAULT_SECONDS_PER_IMAGE,
                   fps: int = DEFAULT_FPS, size: tuple[int, int] | None = None,
                   durations: list[float] | None = None) -> dict:
    """把一列图片按顺序合成 mp4（图生视频草稿 / 参数化渲染共用这一条实现）。

    - `images`：按播放顺序排好的图片路径（至少 1 张）
    - `durations`：可选的「每张播多久」，长度必须与 images 一致；不给就用 seconds_per_image
    - `size`：可选目标分辨率 (宽, 高)；给了就等比缩放并加黑边垫满（保持竖屏比例不被拉伸）
    """
    items = [Path(p) for p in images]
    if not items:
        raise VideoError("至少要有一张图片才能合成视频")
    missing = [str(p) for p in items if not p.is_file()]
    if missing:
        raise VideoError(f"这些图片不存在：{'、'.join(missing[:4])}{'…' if len(missing) > 4 else ''}")
    if durations is None:
        durations = [float(seconds_per_image)] * len(items)
    if len(durations) != len(items):
        raise VideoError(f"每镜时长个数（{len(durations)}）必须与图片张数（{len(items)}）一致")
    if any(float(d) <= 0 for d in durations):
        raise VideoError("每镜时长必须大于 0")
    fps = int(fps)
    if fps < 1 or fps > 120:
        raise VideoError(f"帧率必须在 1–120 之间，收到 {fps}")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = "format=yuv420p"
    if size:
        width, height = _even(size[0]), _even(size[1])
        if width < 16 or height < 16:
            raise VideoError(f"目标分辨率太小：{width}×{height}")
        vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
              f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")

    # 清单写在成片同目录（不用系统临时目录：ffmpeg 子进程在本机沙箱下读 /var/folders 可能被拒）
    listing = out.with_name(f"{out.stem}.files.txt")
    try:
        lines: list[str] = []
        for path, secs in zip(items, durations):
            # 必须写绝对路径：concat 解复用器会把相对路径按「清单文件所在目录」再拼一次
            lines.append(f"file '{path.resolve()}'")
            lines.append(f"duration {float(secs):.3f}")
        lines.append(f"file '{items[-1].resolve()}'")  # concat 约定：最后一张再列一次，否则末段时长丢失
        listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _run([
            require_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            # 注意：ffmpeg 9 已移除 -vsync（改用 -fps_mode）；这里直接用 -r 定帧率，
            # 每段时长由 concat 清单里的 duration 指令决定，兼容新旧版本。
            "-r", str(fps), "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            str(out),
        ])
    finally:
        listing.unlink(missing_ok=True)
    info = probe(out)
    info["count"] = len(items)
    info["fps"] = fps
    info["planned_duration_s"] = round(sum(float(d) for d in durations), 3)
    return info


def extract_cover(video: str | os.PathLike, out_path: str | os.PathLike, *, at_s: float = 1.0,
                  width: int = 0) -> dict:
    """从成片里抽一张封面帧（png）。`width` > 0 时按宽度缩放（高度等比取偶）。"""
    src = Path(video)
    if not src.is_file():
        raise VideoError(f"视频文件不存在：{src}")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [require_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
    if at_s > 0:
        cmd += ["-ss", f"{float(at_s):.3f}"]
    cmd += ["-i", str(src), "-frames:v", "1"]
    if width > 0:
        cmd += ["-vf", f"scale={_even(width)}:-2"]
    cmd += [str(out)]
    _run(cmd)
    if not out.is_file() or out.stat().st_size == 0:
        raise VideoError(f"封面帧抽取失败（{at_s}s 处可能超出片长）：{out}")
    from images import read_size  # 同目录共享库，复用尺寸读取
    size = read_size(out)
    return {"path": str(out), "bytes": out.stat().st_size, "width": size[0], "height": size[1], "at_s": float(at_s)}


def check_video(path: str | os.PathLike, *, min_seconds: float = MIN_SECONDS,
                max_seconds: float = MAX_SECONDS, expect_size: tuple[int, int] | None = None,
                cover: str | os.PathLike | None = None) -> dict:
    """成片体检：文件在不在、时长是否落在区间、分辨率对不对、封面能不能读。"""
    problems: list[str] = []
    warnings: list[str] = []
    src = Path(path)
    if src.suffix.lower() not in VIDEO_EXTS:
        warnings.append(f"扩展名 {src.suffix} 不是常见视频后缀（{'/'.join(VIDEO_EXTS)}）")
    if not src.is_file():
        return {"ok": False, "problems": [f"成片不存在：{src}"], "warnings": warnings, "info": {}}
    if src.stat().st_size == 0:
        return {"ok": False, "problems": [f"成片是空文件：{src}"], "warnings": warnings, "info": {}}
    info = probe(src)
    if not find_ffprobe():
        warnings.append("本机没有 ffprobe：只体检到文件大小，时长与分辨率未校验")
    else:
        duration = info["duration_s"]
        if duration < min_seconds:
            problems.append(f"成片时长 {duration}s 小于下限 {min_seconds}s")
        if duration > max_seconds:
            problems.append(f"成片时长 {duration}s 超过上限 {max_seconds}s")
        if expect_size:
            want = (_even(expect_size[0]), _even(expect_size[1]))
            got = (info["width"], info["height"])
            if got != want:
                problems.append(f"成片分辨率应为 {want[0]}×{want[1]}，实际 {got[0]}×{got[1]}")
    if cover is not None:
        cover_path = Path(cover)
        if not cover_path.is_file():
            problems.append(f"封面帧不存在：{cover_path}")
        elif cover_path.stat().st_size == 0:
            problems.append(f"封面帧是空文件：{cover_path}")
    return {"ok": not problems, "problems": problems, "warnings": warnings, "info": info}
