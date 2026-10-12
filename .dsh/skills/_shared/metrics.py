"""指标口径与聚合（FLOW-8 / Q-16 / R-8-14~R-8-16）。

三张口径固定，不多不少：播放量 views、互动量 engagements（赞+藏+评+转）、涨粉数 follower_gain。
来源只能是 manual / browser / api / export（与 metrics 表的 CHECK 一致）。

设计约束：
- 中文别名在入口归一（运营人员给的是「播放量」这种词，库里只存英文键）；
- 同一任务 + 平台 + 周期 + 指标重复采集时「更新而不是堆行」，避免复盘时把同一个数字加两遍；
- 聚合只做「加总 + 互动率」，不做加权评分（评分口径没有需求依据，R-8-16 只要求看趋势）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import db as dbm

METRIC_KEYS = ("views", "engagements", "follower_gain")
METRIC_LABELS = {"views": "播放量", "engagements": "互动量", "follower_gain": "涨粉数"}
SOURCES = ("manual", "browser", "api", "export")

_ALIASES = {
    "views": "views", "view": "views", "播放": "views", "播放量": "views", "播放数": "views",
    "engagements": "engagements", "engagement": "engagements", "互动": "engagements",
    "互动量": "engagements", "互动数": "engagements", "赞藏评": "engagements", "点赞": "engagements",
    "follower_gain": "follower_gain", "followergain": "follower_gain", "涨粉": "follower_gain",
    "涨粉数": "follower_gain", "涨粉量": "follower_gain", "新增粉丝": "follower_gain",
}


class MetricsError(ValueError):
    """指标口径不合法（键名不认识、数值为负、周期缺失等）。"""


def normalize_key(text: str) -> str:
    """把中文/英文指标名归一到三键之一，未知的抛错（不猜）。"""
    key = str(text or "").strip().lower().replace(" ", "")
    if key in _ALIASES:
        return _ALIASES[key]
    raise MetricsError(f"不认识的指标名「{text}」；只支持：{'、'.join(METRIC_LABELS.values())}")


def parse_values(text: str) -> dict[str, float]:
    """解析 `播放量=1200,互动量=88,涨粉=12` 或 JSON `{"views": 1200}`。"""
    raw = str(text or "").strip()
    if not raw:
        raise MetricsError("指标值不能为空，例：--values \"播放量=1200,互动量=88,涨粉=12\"")
    pairs: list[tuple[str, Any]] = []
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MetricsError(f"指标值不是合法 JSON：{exc}") from exc
        if not isinstance(data, dict):
            raise MetricsError("指标值 JSON 必须是对象，例：{\"views\": 1200}")
        pairs = list(data.items())
    else:
        for chunk in raw.replace("，", ",").replace(";", ",").replace("；", ",").split(","):
            if not chunk.strip():
                continue
            if "=" not in chunk and ":" not in chunk:
                raise MetricsError(f"指标值片段「{chunk.strip()}」缺分隔符，例：播放量=1200")
            sep = "=" if "=" in chunk else ":"
            name, value = chunk.split(sep, 1)
            pairs.append((name, value))
    out: dict[str, float] = {}
    for name, value in pairs:
        key = normalize_key(name)
        try:
            num = float(str(value).strip())
        except ValueError as exc:
            raise MetricsError(f"指标「{name}」的值不是数字：{value!r}") from exc
        if num < 0:
            raise MetricsError(f"指标「{name}」不能为负：{num}")
        out[key] = num
    return out


def check_values(values: dict[str, float], *, require_all: bool = True) -> list[str]:
    """返回问题清单（空 = 通过）。require_all=True 要求三项齐全。"""
    problems: list[str] = []
    if not values:
        problems.append("一个指标都没有")
        return problems
    unknown = [k for k in values if k not in METRIC_KEYS]
    if unknown:
        problems.append(f"指标键不在口径内：{', '.join(unknown)}")
    if require_all:
        missing = [METRIC_LABELS[k] for k in METRIC_KEYS if k not in values]
        if missing:
            problems.append(f"缺指标：{'、'.join(missing)}（--allow-partial 可只采部分）")
    for k, v in values.items():
        if v < 0:
            problems.append(f"{METRIC_LABELS.get(k, k)} 为负：{v}")
    return problems


def load_fixture(path: str | Path) -> list[dict[str, Any]]:
    """读离线指标夹具：单条 `{platform, period_start, period_end, values}` 或 `{records: [...]}`。"""
    p = Path(path)
    if not p.is_file():
        raise MetricsError(f"指标夹具不存在：{p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "records" in data:
        records = data["records"]
    elif isinstance(data, list):
        records = data
    else:
        records = [data]
    out: list[dict[str, Any]] = []
    for one in records:
        if not isinstance(one, dict):
            raise MetricsError("指标夹具的每条记录必须是对象")
        values = parse_values(json.dumps(one.get("values") or {}, ensure_ascii=False))
        out.append({
            "platform": str(one.get("platform") or ""),
            "period_start": str(one.get("period_start") or ""),
            "period_end": str(one.get("period_end") or ""),
            "values": values,
            "source": str(one.get("source") or "export"),
        })
    if not out:
        raise MetricsError("指标夹具里没有任何记录")
    return out


def upsert_metrics(task_id: int, values: dict[str, float], *, platform: str, period_start: str = "",
                   period_end: str = "", collected_at: str | None = None, source: str = "manual",
                   path: str | None = None) -> int:
    """同期同键更新、否则插入；返回写过的行数。"""
    if source not in SOURCES:
        raise MetricsError(f"来源必须是 {'/'.join(SOURCES)} 之一：{source}")
    problems = check_values(values, require_all=False)
    if problems:
        raise MetricsError("；".join(problems))
    stamp = collected_at or dbm.now_iso()
    written = 0
    for key in METRIC_KEYS:
        if key not in values:
            continue
        row = dbm.query_one(
            "SELECT id FROM metrics WHERE task_id=? AND platform=? AND metric_key=? "
            "AND period_start=? AND period_end=?",
            (task_id, platform, key, period_start, period_end), path)
        if row:
            dbm.execute(
                "UPDATE metrics SET value=?, collected_at=?, source=? WHERE id=?",
                (float(values[key]), stamp, source, row["id"]), path)
        else:
            dbm.execute(
                "INSERT INTO metrics (task_id, platform, metric_key, value, period_start, period_end,"
                " collected_at, source, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (task_id, platform, key, float(values[key]), period_start, period_end, stamp, source, stamp),
                path)
        written += 1
    return written


def snapshot(task_id: int, *, platform: str, values: dict[str, float], period_start: str = "",
             period_end: str = "", source: str = "manual", collected_at: str = "") -> dict[str, Any]:
    """一次采集的快照（落盘用），字段名与表格/报告对齐。"""
    return {
        "task_id": task_id,
        "platform": platform,
        "period_start": period_start,
        "period_end": period_end,
        "source": source,
        "collected_at": collected_at or dbm.now_iso(),
        "values": {k: values[k] for k in METRIC_KEYS if k in values},
        "labels": {METRIC_LABELS[k]: values[k] for k in METRIC_KEYS if k in values},
    }


def aggregate(task_id: int | None = None, *, platform: str | None = None,
              period_start: str | None = None, path: str | None = None) -> dict[str, Any]:
    """按平台汇总：三项总数 + 互动率；task_id 为空则汇总全库。"""
    sql = "SELECT task_id, platform, metric_key, value, period_start, period_end FROM metrics WHERE 1=1"
    args: list[Any] = []
    if task_id is not None:
        sql += " AND task_id=?"
        args.append(task_id)
    if platform:
        sql += " AND platform=?"
        args.append(platform)
    if period_start:
        sql += " AND period_start>=?"
        args.append(period_start)
    rows = dbm.query(sql, tuple(args), path)
    by_platform: dict[str, dict[str, Any]] = {}
    totals = {k: 0.0 for k in METRIC_KEYS}
    periods: set[str] = set()
    for row in rows:
        key = row["metric_key"]
        if key not in METRIC_KEYS:
            continue
        slot = by_platform.setdefault(row["platform"], {k: 0.0 for k in METRIC_KEYS})
        slot[key] += float(row["value"] or 0)
        totals[key] += float(row["value"] or 0)
        if row["period_start"]:
            periods.add(f"{row['period_start']}~{row['period_end']}")
    for slot in by_platform.values():
        views = slot.get("views") or 0.0
        slot["engagement_rate"] = round(slot.get("engagements", 0.0) / views, 4) if views else 0.0
    totals["engagement_rate"] = round(totals["engagements"] / totals["views"], 4) if totals["views"] else 0.0
    return {
        "task_id": task_id,
        "rows": len(rows),
        "periods": sorted(periods),
        "period_start": period_start or (sorted(periods)[0].split("~")[0] if periods else ""),
        "period_end": sorted(periods)[-1].split("~")[-1] if periods else "",
        "totals": totals,
        "by_platform": by_platform,
    }


def render_summary(report: dict[str, Any]) -> str:
    """把 aggregate 的结果渲染成人读表格。"""
    lines = ["| 平台 | 播放量 | 互动量 | 涨粉数 | 互动率 |", "| --- | --- | --- | --- | --- |"]
    for platform, slot in sorted(report.get("by_platform", {}).items()):
        lines.append("| {p} | {v:g} | {e:g} | {f:g} | {r:.2%} |".format(
            p=platform or "（未标注）", v=slot.get("views", 0.0), e=slot.get("engagements", 0.0),
            f=slot.get("follower_gain", 0.0), r=slot.get("engagement_rate", 0.0)))
    if not report.get("by_platform"):
        lines.append("| （无数据） | 0 | 0 | 0 | 0.00% |")
    t = report.get("totals", {})
    lines.append(f"\n合计：播放 {t.get('views', 0):g}、互动 {t.get('engagements', 0):g}、"
                 f"涨粉 {t.get('follower_gain', 0):g}，互动率 {t.get('engagement_rate', 0):.2%}")
    if report.get("period_start"):
        lines.append(f"周期：{report['period_start']} ~ {report['period_end']}")
    return "\n".join(lines)
