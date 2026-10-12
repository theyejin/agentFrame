#!/usr/bin/env python3
# 文件用途：运营控制台（dashboard/）与搭建过程报告页（build-log）的共享数据层 —— 只读数据库聚合 + 日志聚合 + 页面生成。
# 对应需求：R-L2-05（按日期记录执行过程并生成报告页）、R-L2-06（build-log 生成在仓库根目录，数据来源可追溯：生成脚本 + 结构化数据文件）、R-L3-01~05（本地可访问、页面只读库与调本地脚本、不持有账号凭据）、AC-3、Q-6（控制台与 build-log 是两个独立页面）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（FLOW-9 运营人员操作面）
# 维护提示：控制台任何页面字段改动的口径都在本文件（STAGE_LABELS / STATUS_LABELS / GATE_LABELS）；改完必须同步 tests/test_dashboard.py 与 dashboard/README.md。
"""控制台与 build-log 的数据层。

三层职责：
1. 只读聚合：`tasks_overview` / `gate_todos` / `publish_queue` / `metrics_summary` / `hotspots_overview` / `task_trace`；
2. 日志聚合：`logs_entries` 把 `logs/YYYY-MM-DD.jsonl` 读成「按日期倒序 + 每条一个标题与详情」；
3. 页面生成：`render_build_log` 写出仓库根目录的 `build-log.data.json`（结构化数据，可追溯）与 `build-log.html`（由数据生成，不手写）。

本文件不建立任何数据库写操作：控制台只读库；要动数据一律走 skill（页面通过本地服务调用白名单脚本）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import db as dbm
import metrics as mt

ROOT = Path(__file__).resolve().parents[3]

# 环节与状态的中文口径（页面上只出现中文，库里只存英文）
STAGE_LABELS = {
    "copy": "文案",
    "visual": "视觉",
    "video": "视频",
    "publish": "发布",
    "metrics": "指标",
    "review": "复盘",
    "closed": "收尾",
}
STATUS_LABELS = {
    "pending": "待开始",
    "running": "进行中",
    "waiting_human": "等人工",
    "blocked": "受阻",
    "done": "完成",
    "failed": "失败",
    "cancelled": "已取消",
}
GATE_LABELS = {
    "gate1_select_copy": "关口① 选定文案",
    "gate2_edit_video": "关口② 剪辑干预",
    "gate3_publish_auth": "关口③ 发布授权",
    "gate_visual_style": "风格确认",
    "gate_visual_fix": "单张返工",
}
# 每个环节「挂在哪个关口上等人工」——只为页面提示用，真正的关口决议仍由 hitl-gate 负责
STAGE_GATE = {
    "copy": "gate1_select_copy",
    "video": "gate2_edit_video",
    "publish": "gate3_publish_auth",
}
# 控制台允许调用的本地脚本白名单（R-L3-05：页面只调本地脚本，不持有任何账号凭据）
RUN_WHITELIST = {
    "copy-writer": ("generate",),
    "storyboard-builder": ("build",),
    "storyboard-validator": ("check",),
    "reference-image-builder": ("build",),
    "grid-image-builder": ("build",),
    "image-splitter": ("split",),
    "image-consistency-checker": ("check",),
    "asset-packager": ("pack",),
    "image-to-video": ("build",),
    "auto-editor": ("edit",),
    "video-exporter": ("export",),
    "title-cover-prep": ("prepare",),
    "hitl-gate": ("open", "resolve", "status"),
    "browser-publisher": ("prepare", "mark-published", "status"),
    "publish-guard": ("check",),
    "metrics-collector": ("collect",),
    "review-reporter": ("report",),
    "hotspot-collector": ("collect",),
    "table-builder": ("build",),
    "feishu-sync": ("sync",),
    "task-decomposer": ("dispatch", "plan"),
    "summary-writer": ("summarize",),
    "artifact-recorder": ("topic-create", "task-create", "task-update", "task-show", "list"),
}


class ConsoleError(ValueError):
    """控制台数据层的可读错误（页面直接展示这句话，不展示堆栈）。"""


# ---------------------------------------------------------------------------
# 1. 只读聚合
# ---------------------------------------------------------------------------

def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def label_of(stage: str | None, status: str | None = None) -> str:
    """把环节 / 状态翻成中文；给页面用，空值返回「—」。"""
    if status:
        return STATUS_LABELS.get(status, status)
    return STAGE_LABELS.get(stage or "", stage or "—")


def tasks_overview(*, stage: str = "", status: str = "", keyword: str = "", db: str | None = None) -> list[dict]:
    """任务清单（页面上「任务流转」那张表）：话题 + 环节 + 状态 + 处理人 + 步骤与产物计数 + 关口提示。"""
    sql = [
        "SELECT t.id, t.topic_id, t.stage, t.status, t.priority, t.target_platform, t.content_type,",
        "       t.word_min, t.word_max, t.selected_plan, t.operator, t.locked_at, t.updated_at,",
        "       p.title AS topic_title, p.keywords AS topic_keywords,",
        "       (SELECT COUNT(*) FROM step_runs s WHERE s.task_id = t.id) AS step_count,",
        "       (SELECT COUNT(*) FROM step_runs s WHERE s.task_id = t.id AND s.status = 'failed') AS failed_steps,",
        "       (SELECT COUNT(*) FROM artifacts a WHERE a.task_id = t.id) AS artifact_count,",
        "       (SELECT s.skill_id FROM step_runs s WHERE s.task_id = t.id ORDER BY s.step_no DESC, s.id DESC LIMIT 1) AS last_skill",
        "  FROM tasks t LEFT JOIN topics p ON p.id = t.topic_id",
    ]
    where, params = [], []
    if stage:
        where.append("t.stage = ?")
        params.append(stage)
    if status:
        where.append("t.status = ?")
        params.append(status)
    if keyword:
        where.append("(p.title LIKE ? OR p.keywords LIKE ? OR t.prompt LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)
    if where:
        sql.append(" WHERE " + " AND ".join(where))
    sql.append(" ORDER BY t.updated_at DESC, t.id DESC")
    rows = dbm.query(" ".join(sql), params, db)
    for row in rows:
        row["stage_label"] = label_of(row["stage"])
        row["status_label"] = label_of(None, row["status"])
        row["gate"] = STAGE_GATE.get(row["stage"] or "", "")
        row["gate_label"] = GATE_LABELS.get(row["gate"], "")
        row["failed_steps"] = _safe_int(row["failed_steps"])
    return rows


def stage_board(*, db: str | None = None) -> list[dict]:
    """按环节统计（首页看板的泳道计数），空环节也返回 0，方便页面固定顺序渲染。"""
    counts = {stage: {"stage": stage, "label": label_of(stage), "total": 0, "waiting_human": 0, "running": 0}
              for stage in STAGE_LABELS}
    for row in dbm.query("SELECT stage, status, COUNT(*) AS n FROM tasks GROUP BY stage, status", (), db):
        bucket = counts.get(row["stage"])
        if bucket is None:
            continue
        bucket["total"] += row["n"]
        if row["status"] == "waiting_human":
            bucket["waiting_human"] += row["n"]
        if row["status"] == "running":
            bucket["running"] += row["n"]
    return list(counts.values())


def gate_todos(*, db: str | None = None) -> list[dict]:
    """挂在人工关口上的待办：任务处于 `waiting_human`，且最近一条 hitl_events 没有决议。"""
    rows = dbm.query(
        "SELECT t.id AS task_id, t.stage, t.status, t.operator, p.title AS topic_title,"
        "       (SELECT e.gate FROM hitl_events e WHERE e.task_id = t.id ORDER BY e.id DESC LIMIT 1) AS last_gate,"
        "       (SELECT e.action FROM hitl_events e WHERE e.task_id = t.id ORDER BY e.id DESC LIMIT 1) AS last_action,"
        "       (SELECT e.actor FROM hitl_events e WHERE e.task_id = t.id ORDER BY e.id DESC LIMIT 1) AS last_actor,"
        "       (SELECT e.created_at FROM hitl_events e WHERE e.task_id = t.id ORDER BY e.id DESC LIMIT 1) AS last_at"
        "  FROM tasks t LEFT JOIN topics p ON p.id = t.topic_id"
        " WHERE t.status = 'waiting_human' ORDER BY t.updated_at DESC, t.id DESC",
        (), db,
    )
    todos = []
    for row in rows:
        # 有决议就不算待办：关口已过（hitl-gate resolve 过），只是任务还没被下一步推走
        if row["last_action"] in ("confirm", "reject"):
            continue
        gate = row["last_gate"] or STAGE_GATE.get(row["stage"] or "", "")
        todos.append({
            **row,
            "gate": gate,
            "gate_label": GATE_LABELS.get(gate, "人工待办"),
            "stage_label": label_of(row["stage"]),
        })
    return todos


def publish_queue(*, db: str | None = None) -> list[dict]:
    """发布队列：视图 `v_pending_publish`（成片齐、等授权/等发布）+ 每条任务最近的发布记录与红线自检结论。"""
    rows = dbm.query(
        "SELECT v.task_id, v.title, v.target_platform, v.shots, v.videos, v.last_auth_at,"
        "       r.status AS record_status, r.account_label, r.package_path, r.publish_url, r.operator,"
        "       (SELECT t.status FROM tasks t WHERE t.id = v.task_id) AS task_status"
        "  FROM v_pending_publish v"
        "  LEFT JOIN publish_records r ON r.id ="
        "       (SELECT r2.id FROM publish_records r2 WHERE r2.task_id = v.task_id ORDER BY r2.id DESC LIMIT 1)"
        " ORDER BY v.task_id DESC",
        (), db,
    )
    for row in rows:
        row["record_label"] = {"filled": "已填写（等授权）", "pending": "已填写（已授权）",
                               "published": "已发布", "failed": "填写失败", None: "还没填写"}.get(
            row["record_status"], row["record_status"] or "还没填写")
        row["can_auto_publish"] = False  # C-08：任何情况下都不允许系统自动发布
    return rows


def metrics_summary(*, db: str | None = None, platform: str = "", period_start: str = "") -> dict:
    """指标汇总（「数据查看」页顶部）：直接复用 `_shared/metrics.aggregate`，不另造口径。

    返回里 `totals` 是三项合计与互动率，`rows` 是明细行（周期 × 平台 × 口径），空库时是空列表。
    """
    try:
        summary = dict(mt.aggregate(None, platform=platform or None, period_start=period_start or None, path=db))
    except Exception as exc:  # 空库或口径不对时给可读结论，不让页面白屏
        return {"rows": [], "row_count": 0, "periods": [], "period_start": "", "period_end": "",
                "totals": {"views": 0, "engagements": 0, "follower_gain": 0, "engagement_rate": 0.0},
                "by_platform": {}, "note": f"指标暂不可用：{exc}"}
    conditions, params = [], []
    if platform:
        conditions.append("platform = ?")
        params.append(platform)
    if period_start:
        conditions.append("period_start = ?")
        params.append(period_start)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    detail = dbm.query(
        "SELECT period_start, period_end, platform, metric_key, SUM(value) AS value, COUNT(*) AS n"
        f"  FROM metrics{where}"
        " GROUP BY period_start, period_end, platform, metric_key"
        " ORDER BY period_start, period_end, platform, metric_key",
        tuple(params), db,
    )
    # 口径统一：`_shared/metrics.py` 里 engagement_rate 是比值（0.0167），页面一律按百分比展示（1.67）
    totals = summary.get("totals") or {}
    if "engagement_rate" in totals:
        totals["engagement_rate"] = round(float(totals.get("engagement_rate") or 0) * 100, 2)
    for slot in (summary.get("by_platform") or {}).values():
        if isinstance(slot, dict) and "engagement_rate" in slot:
            slot["engagement_rate"] = round(float(slot.get("engagement_rate") or 0) * 100, 2)
    summary["rows"] = [dict(row) for row in detail]
    summary["row_count"] = len(detail)
    return summary


def metrics_trend(*, db: str | None = None) -> list[dict]:
    """按周期聚合的走势（页面画折线用）：每期一行，含三项指标与互动率。"""
    rows = dbm.query(
        "SELECT period_start, period_end, platform, metric_key, SUM(value) AS value"
        "  FROM metrics GROUP BY period_start, period_end, platform, metric_key"
        " ORDER BY period_start, platform, metric_key",
        (), db,
    )
    periods: dict[tuple, dict] = {}
    for row in rows:
        key = (row["period_start"], row["period_end"])
        bucket = periods.setdefault(key, {"period_start": key[0], "period_end": key[1],
                                          "views": 0.0, "engagements": 0.0, "follower_gain": 0.0,
                                          "platforms": []})
        if row["metric_key"] in ("views", "engagements", "follower_gain"):
            bucket[row["metric_key"]] += float(row["value"] or 0)
        if row["platform"] not in bucket["platforms"]:
            bucket["platforms"].append(row["platform"])
    trend = sorted(periods.values(), key=lambda item: item["period_start"])
    for bucket in trend:
        views = bucket["views"] or 0.0
        bucket["engagement_rate"] = round(bucket["engagements"] / views * 100, 2) if views else 0.0
    return trend


def hotspots_overview(*, db: str | None = None) -> dict:
    """热点批次与分类分布（「数据查看」页下半部分，选题来源一目了然）。"""
    batches = dbm.query(
        "SELECT b.id, b.batch_key, b.keyword, b.source, b.items_count, b.table_path, b.export_path,"
        "       b.adapter_used, b.collected_at FROM hotspot_batches b ORDER BY b.id DESC LIMIT 20",
        (), db,
    )
    categories = dbm.query(
        "SELECT i.category, COUNT(*) AS n, SUM(i.heat) AS heat FROM hotspot_items i"
        " GROUP BY i.category ORDER BY n DESC",
        (), db,
    )
    return {"batches": batches, "categories": categories}


def task_trace(task_id: int, *, db: str | None = None) -> dict:
    """一条任务的完整轨迹（build-log / 控制台「看轨迹」都用它）：任务 / 步骤 / 产物 / 关口 / 指标 / 发布。"""
    task = dbm.query_one(
        "SELECT t.*, p.title AS topic_title, p.keywords AS topic_keywords, p.summary AS topic_summary"
        "  FROM tasks t LEFT JOIN topics p ON p.id = t.topic_id WHERE t.id = ?",
        (task_id,), db,
    )
    if task is None:
        raise ConsoleError(f"任务不存在：#{task_id}")
    task["stage_label"] = label_of(task["stage"])
    task["status_label"] = label_of(None, task["status"])
    steps = dbm.query(
        "SELECT id, step_no, skill_id, status, adapter_used, error, started_at, ended_at, duration_ms"
        "  FROM step_runs WHERE task_id = ? ORDER BY step_no, id", (task_id,), db)
    artifacts = dbm.query(
        "SELECT id, kind, path, size_bytes, model_version, prompt_version, meta_json, created_at"
        "  FROM artifacts WHERE task_id = ? ORDER BY id", (task_id,), db)
    for art in artifacts:
        try:
            art["role"] = json.loads(art["meta_json"] or "{}").get("role", "")
        except (TypeError, ValueError):
            art["role"] = ""
    gates = dbm.query(
        "SELECT id, gate, actor, action, diff_json, created_at FROM hitl_events"
        " WHERE task_id = ? ORDER BY id", (task_id,), db)
    for event in gates:
        event["gate_label"] = GATE_LABELS.get(event["gate"], event["gate"])
    metrics_rows = dbm.query(
        "SELECT platform, metric_key, value, period_start, period_end, source, collected_at"
        "  FROM metrics WHERE task_id = ? ORDER BY period_start, platform, metric_key", (task_id,), db)
    publishes = dbm.query(
        "SELECT platform, account_label, package_path, video_path, status, publish_url, operator, note, created_at"
        "  FROM publish_records WHERE task_id = ? ORDER BY id", (task_id,), db)
    return {"task": task, "steps": steps, "artifacts": artifacts, "gates": gates,
            "metrics": metrics_rows, "publishes": publishes}


FOCUS_LABELS = {"hook": "开头钩子", "emotion": "情绪强度", "cta": "行动号召"}


def copy_plans(task_id: int, *, db: str | None = None) -> dict:
    """某个任务的三套候选文案（「文案生成」页的对比卡）：读 copy_variants + 任务的选定套号。"""
    rows = dbm.query(
        "SELECT plan_no, focus, title, body, word_count, created_at FROM copy_variants"
        " WHERE task_id = ? ORDER BY plan_no", (task_id,), db)
    for row in rows:
        row["focus_label"] = FOCUS_LABELS.get(row["focus"], row["focus"])
    task = dbm.query_one("SELECT selected_plan, stage, status FROM tasks WHERE id = ?", (task_id,), db)
    if task is None:
        raise ConsoleError(f"任务不存在：#{task_id}")
    return {"task_id": task_id, "selected_plan": task["selected_plan"], "stage": task["stage"],
            "status": task["status"], "stage_label": label_of(task["stage"]),
            "status_label": label_of(None, task["status"]), "plans": rows}


TEXT_SUFFIXES = (".md", ".txt", ".json", ".csv", ".jsonl")
TEXT_MAX_BYTES = 200_000


def artifact_texts(task_id: int, *, kind: str = "", role: str = "", db: str | None = None) -> dict:
    """把一条任务的文字类产物读成页面能直接显示的内容（文案对比卡 / 填写清单 / 复盘报告都用它）。

    只读：不写库、不改文件；二进制产物（图片/视频）只回路径与大小，不回正文。
    """
    sql = ["SELECT id, kind, path, size_bytes, model_version, prompt_version, meta_json, created_at",
           "  FROM artifacts WHERE task_id = ?"]
    params: list = [task_id]
    if kind:
        sql.append(" AND kind = ?")
        params.append(kind)
    sql.append(" ORDER BY id")
    rows = dbm.query(" ".join(sql), params, db)
    out = []
    for row in rows:
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except (TypeError, ValueError):
            meta = {}
        item = {"id": row["id"], "kind": row["kind"], "path": row["path"], "role": meta.get("role", ""),
                "size_bytes": row["size_bytes"], "model_version": row["model_version"],
                "prompt_version": row["prompt_version"], "created_at": row["created_at"],
                "text": "", "truncated": False, "binary": False}
        if role and item["role"] != role:
            continue
        suffix = Path(row["path"] or "").suffix.lower()
        if suffix not in TEXT_SUFFIXES:
            item["binary"] = True
        else:
            target = Path(row["path"])
            if not target.is_absolute():
                target = ROOT / target
            try:
                data = target.read_bytes()
            except OSError as exc:
                item["text"] = f"（读不到文件：{exc}）"
            else:
                item["truncated"] = len(data) > TEXT_MAX_BYTES
                item["text"] = data[:TEXT_MAX_BYTES].decode("utf-8", errors="replace")
        out.append(item)
    return {"task_id": task_id, "artifacts": out}


def snapshot(*, db: str | None = None, logs_dir: str | Path | None = None) -> dict:
    """控制台首页与各功能页共用的整包数据（本地服务 `/api/snapshot` 直接返回它）。"""
    entries = logs_entries(logs_dir)
    return {
        "generated_at": dbm.now_iso(),
        "db": str(dbm.db_path(db)),
        "tasks": tasks_overview(db=db),
        "stage_board": stage_board(db=db),
        "gate_todos": gate_todos(db=db),
        "publish_queue": publish_queue(db=db),
        "metrics": metrics_summary(db=db),
        "metrics_trend": metrics_trend(db=db),
        "hotspots": hotspots_overview(db=db),
        "logs": {"count": len(entries), "latest": entries[:20]},
    }


# ---------------------------------------------------------------------------
# 2. 日志聚合（build-log 的数据源）
# ---------------------------------------------------------------------------

def logs_entries(logs_dir: str | Path | None = None) -> list[dict]:
    """把 `logs/YYYY-MM-DD.jsonl` 读成条目列表：按日期倒序、同一日期内按时间倒序。

    每条条目带上页面用得到的字段：`date` / `step` / `category` / `title` / `detail` / `result`。
    """
    directory = Path(logs_dir) if logs_dir else ROOT / "logs"
    entries: list[dict] = []
    for path in sorted(directory.glob("*.jsonl")):
        date = path.stem
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                # 坏行不致命：日志是「追加写」的，写一半断电也会留半行；跳过它，其余记录照常展示。
                continue
            entries.append({
                "id": f"{date}-{lineno}",
                "date": date,
                "ts": row.get("ts", ""),
                "step": row.get("step", "") or "未分步",
                "category": "-".join((row.get("step", "") or "未分步").split("-")[:2]),
                "title": row.get("action", "") or "（无标题）",
                "detail": row.get("note", ""),
                "result": row.get("result", ""),
                "skill": row.get("skill", ""),
                "actor": row.get("actor", ""),
            })
    entries.sort(key=lambda item: (item["date"], item["ts"], item["id"]), reverse=True)
    return entries


# ---------------------------------------------------------------------------
# 3. build-log 页面生成（R-L2-06：仓库根目录 + 生成脚本 + 结构化数据文件）
# ---------------------------------------------------------------------------

BUILD_LOG_HTML = "build-log.html"
BUILD_LOG_DATA = "build-log.data.json"


def render_build_log(entries: list[dict], *, root: str | Path | None = None,
                     title: str = "搭建过程记录（build-log）") -> dict:
    """生成仓库根目录的 build-log 页面与结构化数据文件。

    页面是「数据驱动」的：`build-log.data.json` 是可追溯的数据源，HTML 里同时内联同一份数据，
    这样双击 HTML（file://）也能打开交互，不依赖本地服务。
    """
    root_dir = Path(root) if root else ROOT
    dates: list[dict] = []
    index: dict[str, dict] = {}
    for entry in entries:
        bucket = index.get(entry["date"])
        if bucket is None:
            bucket = {"date": entry["date"], "count": 0, "titles": []}
            index[entry["date"]] = bucket
            dates.append(bucket)
        bucket["count"] += 1
        bucket["titles"].append({"id": entry["id"], "title": entry["title"],
                                 "step": entry["step"], "result": entry["result"]})
    payload = {
        "generated_at": dbm.now_iso(),
        "generator": "scripts/build_log_report.py",
        "title": title,
        "total": len(entries),
        "dates": dates,
        "entries": entries,
    }
    data_path = root_dir / BUILD_LOG_DATA
    html_path = root_dir / BUILD_LOG_HTML
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_build_log_html(payload), encoding="utf-8")
    return {"html": str(html_path), "data": str(data_path), "total": len(entries), "dates": len(dates)}


def _build_log_html(payload: dict) -> str:
    """把数据渲染成左右分栏页面（搜索 + 分类查询 + 点击切换），页面代码按区块加注释（R-L2-08）。"""
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<!-- 文件用途：搭建过程报告页（build-log）—— 由 scripts/build_log_report.py 从 logs/*.jsonl 生成，不要手改本文件（R-L2-06）。
     页面结构：左侧日期与标题列表（按日期倒序）| 右侧所选条目的实现轨迹 | 顶部搜索与分类查询。
     数据来源：本目录 build-log.data.json（同一份数据也内联在下方，便于 file:// 直接打开）。 -->
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{payload["title"]}</title>
<style>
  /* 区块：全局与排版 */
  :root {{ color-scheme: light dark; --line: #d8dee9; --bg: #f7f8fa; --fg: #1f2430; --accent: #2f6fed; --muted: #6b7280; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 14px/1.6 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--fg); }}
  header {{ padding: 18px 22px 12px; background: #fff; border-bottom: 1px solid var(--line); }}
  h1 {{ margin: 0 0 4px; font-size: 19px; }}
  .sub {{ color: var(--muted); font-size: 12.5px; }}
  /* 区块：搜索与分类查询 */
  .tools {{ display: flex; gap: 10px; flex-wrap: wrap; padding: 12px 22px; background: #fff; border-bottom: 1px solid var(--line); }}
  .tools input, .tools select {{ padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--fg); min-width: 180px; }}
  .tools .count {{ margin-left: auto; color: var(--muted); align-self: center; }}
  /* 区块：左右分栏 */
  main {{ display: grid; grid-template-columns: minmax(260px, 30%) 1fr; gap: 0; height: calc(100vh - 132px); }}
  .left {{ overflow: auto; border-right: 1px solid var(--line); background: #fff; }}
  .right {{ overflow: auto; padding: 18px 24px; }}
  .date {{ padding: 10px 16px 4px; font-weight: 600; color: var(--muted); font-size: 12.5px; letter-spacing: .04em; }}
  .item {{ display: block; width: 100%; text-align: left; padding: 8px 16px; border: 0; background: none; cursor: pointer; color: inherit; font: inherit; border-left: 3px solid transparent; }}
  .item:hover {{ background: #f0f4ff; }}
  .item.active {{ background: #e8f0ff; border-left-color: var(--accent); }}
  .item .step {{ color: var(--accent); font-size: 12px; margin-right: 6px; }}
  .item.bad .step {{ color: #c0392b; }}
  /* 区块：右侧详情 */
  .detail h2 {{ margin: 0 0 6px; font-size: 17px; }}
  .meta {{ color: var(--muted); font-size: 12.5px; margin-bottom: 14px; }}
  .card {{ background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }}
  .card h3 {{ margin: 0 0 6px; font-size: 14px; }}
  .empty {{ color: var(--muted); }}
  pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }}
  mark {{ background: #ffe58f; }}
</style>
</head>
<body>
<!-- 区块：页头 -->
<header>
  <h1>{payload["title"]}</h1>
  <div class="sub">共 <b id="total">{payload["total"]}</b> 条记录 · <span id="dates">{len(payload["dates"])}</span> 个日期 ·
    数据文件 <code>build-log.data.json</code> · 生成器 <code>scripts/build_log_report.py</code> ·
    <a href="dashboard/index.html">回运营控制台</a></div>
</header>
<!-- 区块：搜索与分类查询 -->
<div class="tools">
  <input id="q" type="search" placeholder="搜索标题 / 详情 / Skill / 编号">
  <select id="cat"><option value="">全部环节分类</option></select>
  <select id="res">
    <option value="">全部结果</option>
    <option value="ok">仅成功（ok）</option>
    <option value="failed">仅失败（failed）</option>
  </select>
  <span class="count" id="count"></span>
</div>
<!-- 区块：左栏日期与标题 / 右栏详情 -->
<main>
  <div class="left" id="left"></div>
  <div class="right" id="right"><p class="empty">从左侧点一条记录看它的实现轨迹。</p></div>
</main>
<script>
// 区块：数据（由生成脚本内联，便于 file:// 直接打开；同一份数据另有 build-log.data.json）
window.BUILD_LOG = {blob};

// 区块：状态与工具函数
const state = {{ q: "", cat: "", res: "", active: null }};
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }}[c]));
const hit = (entry) => {{
  const q = state.q.trim().toLowerCase();
  if (state.cat && entry.category !== state.cat) return false;
  if (state.res && entry.result !== state.res) return false;
  if (!q) return true;
  return [entry.title, entry.detail, entry.skill, entry.step, entry.id, entry.date].join(" ").toLowerCase().includes(q);
}};

// 区块：渲染左栏（日期倒序，日期下挂标题条目）
function renderLeft() {{
  const rows = window.BUILD_LOG.entries.filter(hit);
  const byDate = new Map();
  rows.forEach((entry) => {{
    if (!byDate.has(entry.date)) byDate.set(entry.date, []);
    byDate.get(entry.date).push(entry);
  }});
  const left = document.getElementById("left");
  left.innerHTML = "";
  [...byDate.keys()].sort().reverse().forEach((date) => {{
    const head = document.createElement("div");
    head.className = "date";
    head.textContent = date + "（" + byDate.get(date).length + " 条）";
    left.appendChild(head);
    byDate.get(date).forEach((entry) => {{
      const button = document.createElement("button");
      button.className = "item" + (entry.result === "failed" ? " bad" : "") + (state.active === entry.id ? " active" : "");
      button.innerHTML = '<span class="step">' + esc(entry.step) + '</span>' + esc(entry.title);
      button.onclick = () => {{ state.active = entry.id; renderLeft(); renderRight(entry); }};
      left.appendChild(button);
    }});
  }});
  document.getElementById("count").textContent = "筛出 " + rows.length + " / " + window.BUILD_LOG.total + " 条";
  if (!rows.length) left.innerHTML = '<p class="empty" style="padding:16px">没有匹配的记录。</p>';
}}

// 区块：渲染右栏（所选条目的实现轨迹）
function renderRight(entry) {{
  const box = document.getElementById("right");
  box.innerHTML = "";
  const h2 = document.createElement("h2");
  h2.textContent = entry.title;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = [entry.date, entry.ts, entry.step, entry.skill ? "skill=" + entry.skill : "", "actor=" + entry.actor, "结果=" + entry.result].filter(Boolean).join(" · ");
  box.append(h2, meta);
  [["做了什么（note）", entry.detail], ["原始记录（JSON）", JSON.stringify(entry, null, 2)]].forEach(([name, body]) => {{
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = "<h3>" + esc(name) + "</h3><pre>" + esc(body) + "</pre>";
    box.appendChild(card);
  }});
}}

// 区块：初始化（分类下拉、搜索联动、默认选中最新一条）
function init() {{
  const cats = [...new Set(window.BUILD_LOG.entries.map((entry) => entry.category))].sort();
  const cat = document.getElementById("cat");
  cats.forEach((name) => {{ const option = document.createElement("option"); option.value = name; option.textContent = name; cat.appendChild(option); }});
  document.getElementById("q").oninput = (event) => {{ state.q = event.target.value; renderLeft(); }};
  cat.onchange = (event) => {{ state.cat = event.target.value; renderLeft(); }};
  document.getElementById("res").onchange = (event) => {{ state.res = event.target.value; renderLeft(); }};
  renderLeft();
  const first = window.BUILD_LOG.entries.find(hit);
  if (first) {{ state.active = first.id; renderLeft(); renderRight(first); }}
}}
init();
</script>
</body>
</html>
"""
