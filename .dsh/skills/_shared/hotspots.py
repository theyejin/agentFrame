# 文件用途：热点批次与条目的落库、查询、分类汇总与表格渲染（FLOW-7）
# 对应需求：FLOW-7 热点采集与分类汇总、R-7-05 topic.source=hotspot、L3 控制台分类查询
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html
# 维护提示：分类枚举必须与 db/schema.sql 的 hotspot_items.category CHECK 一致
"""热点数据层：批次（hotspot_batches）与条目（hotspot_items）的唯一读写实现。

分类汇总与表格渲染也在这里，避免 hotspot-collector 与 table-builder 各写一套。
"""
from __future__ import annotations

import json
from pathlib import Path

import db as dbm

CATEGORIES = ("情绪冲突", "干货教程", "热点观点", "其他")
BATCH_SOURCES = ("manual", "browser", "fixture", "api", "export")

# 模型/浏览器返回的分类写法五花八门，这里做别名归一（归一到 CATEGORIES）
_CATEGORY_ALIASES = {
    "情绪": "情绪冲突", "冲突": "情绪冲突", "情绪冲突": "情绪冲突", "情感冲突": "情绪冲突",
    "干货": "干货教程", "教程": "干货教程", "干货教程": "干货教程", "方法": "干货教程",
    "观点": "热点观点", "热点": "热点观点", "热点观点": "热点观点", "评论": "热点观点",
    "其他": "其他", "其它": "其他", "": "其他",
}


class HotspotError(ValueError):
    """热点数据不合法（人话消息，直接给运营人员看）。"""


def normalize_category(text: str) -> str:
    """把任意分类写法归一到四个枚举值之一。"""
    key = (text or "").strip()
    if key in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[key]
    for name in CATEGORIES:                    # 含子串也算命中（例：「情绪冲突类」）
        if name in key:
            return name
    return "其他"


def parse_items(text: str) -> list[dict]:
    """解析模型返回的热点清单：每行 `标题 | 分类 | 热度 | 链接`（后两项可省）。"""
    items: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-*0123456789. 、)）")
        if not line or "|" not in raw:
            continue
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 2:
            continue
        title = parts[0].lstrip("-*0123456789. 、)）").strip()
        if not title:
            continue
        heat_raw = parts[2] if len(parts) > 2 else ""
        heat_text = "".join(ch for ch in heat_raw if ch.isdigit() or ch == ".")
        items.append({
            "title": title,
            "category": normalize_category(parts[1] if len(parts) > 1 else ""),
            "heat": float(heat_text) if heat_text else 0.0,
            "source_url": parts[3] if len(parts) > 3 else "",
        })
    return items


def check_items(items: list[dict], *, min_count: int = 1, max_count: int = 200) -> list[str]:
    """返回问题清单（空 = 通过）。判据：条数区间、标题非空、分类合法、热度非负。"""
    problems: list[str] = []
    if len(items) < min_count:
        problems.append(f"热点条数不足：至少 {min_count} 条，实际 {len(items)} 条")
    if len(items) > max_count:
        problems.append(f"热点条数过多：最多 {max_count} 条，实际 {len(items)} 条")
    seen: set[str] = set()
    for i, it in enumerate(items, start=1):
        title = (it.get("title") or "").strip()
        if not title:
            problems.append(f"第 {i} 条标题为空")
        elif title in seen:
            problems.append(f"第 {i} 条标题与前面重复：{title}")
        seen.add(title)
        if it.get("category") not in CATEGORIES:
            problems.append(f"第 {i} 条分类非法：{it.get('category')!r}（应为 {'/'.join(CATEGORIES)}）")
        if float(it.get("heat", 0) or 0) < 0:
            problems.append(f"第 {i} 条热度为负：{it.get('heat')}")
    return problems


# ---------------------------------------------------------------------------
# 落库
# ---------------------------------------------------------------------------
def create_batch(batch_key: str, keyword: str, *, source: str = "manual", period_start: str = "",
                 period_end: str = "", adapter_used: str = "", collected_at: str = "",
                 path: str | None = None) -> int:
    """新建一个采集批次，返回 hotspot_batches.id。"""
    if not batch_key.strip():
        raise HotspotError("批次号不能为空")
    if not keyword.strip():
        raise HotspotError("采集关键词不能为空")
    if source not in BATCH_SOURCES:
        raise HotspotError(f"采集来源只能是 {'/'.join(BATCH_SOURCES)}，收到 {source}")
    if dbm.query_one("SELECT id FROM hotspot_batches WHERE batch_key = ?", (batch_key.strip(),), path):
        raise HotspotError(f"批次号已存在：{batch_key.strip()}（换一个 --batch-key，或让它按时间戳自动生成）")
    now = dbm.now_iso()
    return dbm.execute(
        """INSERT INTO hotspot_batches (batch_key, keyword, source, period_start, period_end,
                                        items_count, table_path, export_path, adapter_used,
                                        collected_at, created_at)
           VALUES (?, ?, ?, ?, ?, 0, '', '', ?, ?, ?)""",
        (batch_key.strip(), keyword.strip(), source, period_start, period_end,
         adapter_used, collected_at or now, now), path,
    )


def add_items(batch_id: int, items: list[dict], *, path: str | None = None) -> int:
    """写入热点条目并回填批次的条数，返回写入行数。"""
    now = dbm.now_iso()
    for it in items:
        dbm.execute(
            """INSERT INTO hotspot_items (batch_id, title, category, heat, source_url, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (batch_id, it["title"], normalize_category(it.get("category", "")),
             float(it.get("heat", 0) or 0), it.get("source_url", ""), it.get("note", ""), now), path,
        )
    dbm.execute("UPDATE hotspot_batches SET items_count = ? WHERE id = ?", (len(items), batch_id), path)
    return len(items)


def update_batch(batch_id: int, *, table_path: str | None = None, export_path: str | None = None,
                 items_count: int | None = None, path: str | None = None) -> None:
    """回填批次的条数 / 表格文件路径 / 文档导出路径（hotspot-collector、table-builder、feishu-sync 调用）。"""
    if table_path is not None:
        dbm.execute("UPDATE hotspot_batches SET table_path = ? WHERE id = ?", (table_path, batch_id), path)
    if export_path is not None:
        dbm.execute("UPDATE hotspot_batches SET export_path = ? WHERE id = ?", (export_path, batch_id), path)
    if items_count is not None:
        dbm.execute("UPDATE hotspot_batches SET items_count = ? WHERE id = ?", (int(items_count), batch_id), path)


def get_batch(batch_key: str, *, path: str | None = None):
    return dbm.query_one("SELECT * FROM hotspot_batches WHERE batch_key = ?", (batch_key,), path)


def latest_batch(*, path: str | None = None):
    return dbm.query_one("SELECT * FROM hotspot_batches ORDER BY id DESC LIMIT 1", (), path)


def items_of(batch_id: int, *, category: str | None = None, path: str | None = None) -> list[dict]:
    """按批次取条目，可按分类过滤（L3 控制台的分类查询入口）。"""
    if category:
        return dbm.query(
            "SELECT * FROM hotspot_items WHERE batch_id = ? AND category = ? ORDER BY heat DESC, id",
            (batch_id, normalize_category(category)), path)
    return dbm.query(
        "SELECT * FROM hotspot_items WHERE batch_id = ? ORDER BY category, heat DESC, id",
        (batch_id,), path)


def search_items(keyword: str = "", *, category: str | None = None, limit: int = 200,
                 path: str | None = None) -> list[dict]:
    """跨批次搜索热点（关键词模糊匹配标题或采集词，可按分类过滤）。"""
    sql = ("SELECT i.*, b.batch_key, b.keyword, b.collected_at FROM hotspot_items i "
           "JOIN hotspot_batches b ON b.id = i.batch_id WHERE 1=1")
    args: list = []
    if keyword.strip():
        sql += " AND (i.title LIKE ? OR b.keyword LIKE ?)"
        like = f"%{keyword.strip()}%"
        args += [like, like]
    if category:
        sql += " AND i.category = ?"
        args.append(normalize_category(category))
    sql += " ORDER BY i.heat DESC, i.id LIMIT ?"
    args.append(int(limit))
    return dbm.query(sql, tuple(args), path)


# ---------------------------------------------------------------------------
# 夹具（离线演练的公开源替身）与汇总
# ---------------------------------------------------------------------------
def load_fixture(path: str | Path) -> list[dict]:
    """读本地夹具 JSON：`{"items": [{title, category?, heat?, source_url?}, ...]}` 或直接数组。"""
    target = Path(path)
    if not target.is_file():
        raise HotspotError(f"热点夹具不存在：{target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HotspotError(f"热点夹具不是合法 JSON：{target}（{exc}）") from exc
    rows = data.get("items") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise HotspotError("热点夹具格式应为数组，或含 items 数组的对象")
    items = []
    for row in rows:
        if not isinstance(row, dict) or not (row.get("title") or "").strip():
            continue
        items.append({
            "title": str(row["title"]).strip(),
            "category": normalize_category(str(row.get("category", ""))),
            "heat": float(row.get("heat", 0) or 0),
            "source_url": str(row.get("source_url", "")),
        })
    if not items:
        raise HotspotError(f"热点夹具里没有可用条目：{target}")
    return items


def aggregate(items: list[dict], *, top: int = 3) -> dict:
    """按分类汇总：每类条数、热度合计与均值、热度最高的前 top 条。"""
    summary: dict[str, dict] = {}
    for cat in CATEGORIES:
        rows = [it for it in items if normalize_category(it.get("category", "")) == cat]
        heats = [float(it.get("heat", 0) or 0) for it in rows]
        summary[cat] = {
            "count": len(rows),
            "heat_total": round(sum(heats), 2),
            "heat_avg": round(sum(heats) / len(heats), 2) if heats else 0.0,
            "top": [it["title"] for it in sorted(rows, key=lambda r: -float(r.get("heat", 0) or 0))[:top]],
        }
    summary["合计"] = {"count": len(items),
                     "heat_total": round(sum(float(it.get("heat", 0) or 0) for it in items), 2)}
    return summary


def render_table(items: list[dict], *, fmt: str = "md") -> str:
    """把热点条目渲染成表格：md=Markdown 表格（给人看 / 进文档），csv=逗号分隔（给表格软件）。"""
    ordered = sorted(items, key=lambda r: (normalize_category(r.get("category", "")),
                                           -float(r.get("heat", 0) or 0)))
    header = ["分类", "热度", "标题", "来源链接"]
    if fmt == "csv":
        def cell(v) -> str:
            text = str(v).replace('"', '""')
            return f'"{text}"' if any(ch in text for ch in ',"\n') else text
        lines = [",".join(header)]
        lines += [",".join(cell(r.get(k, "")) for k in ("category", "heat", "title", "source_url"))
                  for r in ordered]
        return "\n".join(lines) + "\n"
    if fmt != "md":
        raise HotspotError(f"表格格式只支持 md / csv，收到 {fmt}")
    out = ["| " + " | ".join(header) + " |", "| --- | --- | --- | --- |"]
    for r in ordered:
        out.append(f"| {normalize_category(r.get('category',''))} | {r.get('heat', 0)} | "
                   f"{r.get('title','')} | {r.get('source_url','')} |")
    return "\n".join(out) + "\n"


def render_summary(summary: dict) -> str:
    """把 aggregate 的结果渲染成一段人读汇总（表格前的一段话）。"""
    lines = ["| 分类 | 条数 | 热度合计 | 热度均值 | 代表标题 |", "| --- | --- | --- | --- | --- |"]
    for cat, row in summary.items():
        if cat == "合计":
            continue
        top = "；".join(row.get("top", [])) or "—"
        lines.append(f"| {cat} | {row['count']} | {row['heat_total']} | {row['heat_avg']} | {top} |")
    total = summary.get("合计", {})
    lines.append(f"\n合计 {total.get('count', 0)} 条，热度总计 {total.get('heat_total', 0)}。")
    return "\n".join(lines) + "\n"
