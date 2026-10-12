"""发布红线与发布留痕（C-01 不得自动发布 / C-08 只填不发 / C-10 人工授权、R-8-17~R-8-19）。

这个支撑件只做两件事：
1. 组装「发布包」并做发布前自检 —— 视频在不在、封面在不在、标题/标签/封面文案对不对平台模板、
   有没有绝对化用语、关口③ 有没有授权、有没有人试图让 Agent 自动提交；
2. 把发布记录写进 publish_records —— 状态只能走到 filled（已填好待人工发布）/pending（等授权）；
   published 只能由 `mark_published()`（要求填 operator，代表人工已发布）推进。

任何情况下都不打开浏览器、不调用发布接口：首版没有发布适配器，C-08 要求停在发布前。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import db as dbm
import text_utils as tu

REPO_ROOT = Path(__file__).resolve().parents[3]
STATUSES = ("filled", "pending", "published", "failed")


class PublishGuardError(ValueError):
    """发布包不合法或违反红线。"""


def load_template(platform: str, *, path: str | None = None) -> dict[str, Any] | None:
    """读平台预设模板（平台名未知返回 None，由调用方决定怎么提示）。"""
    return dbm.query_one(
        "SELECT platform, word_min, word_max, title_style, tag_count, cover_ratio, note "
        "FROM platform_templates WHERE platform=?", (platform,), path)


def list_platforms(*, path: str | None = None) -> list[str]:
    return [r["platform"] for r in dbm.query(
        "SELECT platform FROM platform_templates ORDER BY id", (), path)]


def build_package(*, task_id: int, platform: str, account_label: str = "", video_path: str = "",
                  cover_path: str = "", prep: dict[str, Any] | None = None, package_dir: str = "",
                  operator: str = "", submit: bool = False) -> dict[str, Any]:
    """组装发布包（纯数据，不落盘、不写库）。submit 永远为 False，传 True 会被自检拦下。"""
    template = load_template(platform)
    return {
        "task_id": task_id,
        "platform": platform,
        "account_label": account_label,
        "video_path": video_path,
        "cover_path": cover_path,
        "package_dir": package_dir,
        "operator": operator,
        "submit": bool(submit),
        "auto_publish": bool(submit),
        "template": template,
        "prep": prep or {},
        "url": (template or {}).get("note", ""),
    }


def check_package(pkg: dict[str, Any], *, gate3_authorized: bool = False, live: bool = False,
                  exists=Path.is_file) -> dict[str, Any]:
    """发布前自检。返回 {ok, problems, warnings, checked}；problems 非空即不可发布。"""
    problems: list[str] = []
    warnings: list[str] = []
    platform = str(pkg.get("platform") or "")
    template = pkg.get("template") or load_template(platform)

    if pkg.get("submit") or pkg.get("auto_publish"):
        problems.append("C-08 红线：Agent 不得自动提交发布（首版没有发布适配器，只能填好等人发）")
    if not platform:
        problems.append("发布包缺平台")
    elif not template:
        problems.append(f"平台「{platform}」没有预设模板；已配置：{'、'.join(list_platforms())}")
    if not str(pkg.get("video_path") or ""):
        problems.append("发布包缺成片路径")
    else:
        video = Path(str(pkg["video_path"]))
        if not video.is_absolute():
            video = REPO_ROOT / video
        if not exists(video):
            problems.append(f"成片文件不存在：{pkg['video_path']}")
    cover = str(pkg.get("cover_path") or "")
    if not cover:
        problems.append("发布包缺封面（成片与封面必须成对留痕）")
    else:
        cover_file = Path(cover)
        if not cover_file.is_absolute():
            cover_file = REPO_ROOT / cover
        if not exists(cover_file):
            problems.append(f"封面文件不存在：{cover}")
    if not str(pkg.get("account_label") or ""):
        warnings.append("未提供账号标识（account_label），发布记录里会留空")

    prep = pkg.get("prep") or {}
    if not prep:
        warnings.append("发布包没有发布准备（标题/标签/封面文案），建议先跑 title-cover-prep")
    else:
        tag_count = int(template["tag_count"]) if template else len(prep.get("tags") or [])
        problems.extend(tu.check_publish_prep(prep, tag_count=tag_count))

    if live and not gate3_authorized:
        problems.append("关口③ 未授权：发布授权必须由真人在关口③ 给出（C-10）")
    if gate3_authorized and str(pkg.get("status") or "") != "published":
        warnings.append("关口③ 已授权：请在浏览器里人工发布，发布后回填链接（mark-published）")

    return {"ok": not problems, "problems": problems, "warnings": warnings,
            "platform": platform, "task_id": pkg.get("task_id"), "live": bool(live)}


def render_check(result: dict[str, Any]) -> str:
    lines = [f"发布包自检：{'通过 ✅' if result['ok'] else '不通过 ❌'}"
             f"（任务 {result.get('task_id')} / 平台 {result.get('platform') or '未填'}）"]
    for item in result.get("problems", []):
        lines.append(f"  ✗ {item}")
    for item in result.get("warnings", []):
        lines.append(f"  ! {item}")
    return "\n".join(lines)


def record(task_id: int, *, platform: str, account_label: str = "", package_path: str = "",
           video_path: str = "", status: str = "filled", operator: str = "", note: str = "",
           path: str | None = None) -> int:
    """写一条发布记录。Agent 侧只允许 filled / pending / failed（published 走 mark_published）。"""
    if status not in STATUSES:
        raise PublishGuardError(f"状态必须是 {'/'.join(STATUSES)} 之一：{status}")
    if status == "published":
        raise PublishGuardError("published 只能由人工发布后回填（mark_published），Agent 不得直接写")
    stamp = dbm.now_iso()
    filled_at = stamp if status in ("filled", "pending") else None
    return dbm.execute(
        "INSERT INTO publish_records (task_id, platform, account_label, package_path, video_path,"
        " status, filled_at, published_at, publish_url, operator, note, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (task_id, platform, account_label, package_path, video_path, status, filled_at, None, "",
         operator, note, stamp), path)


def mark_published(task_id: int, *, actor: str, url: str = "", platform: str = "",
                   note: str = "", path: str | None = None) -> int:
    """人工发布后回填：只有填了 operator（真人标识）才允许把状态推到 published。"""
    if not str(actor or "").strip():
        raise PublishGuardError("回填发布结果必须写明 operator（谁发的），否则无法追溯")
    sql = "SELECT id FROM publish_records WHERE task_id=?"
    args: list[Any] = [task_id]
    if platform:
        sql += " AND platform=?"
        args.append(platform)
    sql += " ORDER BY id DESC LIMIT 1"
    row = dbm.query_one(sql, tuple(args), path)
    stamp = dbm.now_iso()
    if not row:
        return dbm.execute(
            "INSERT INTO publish_records (task_id, platform, account_label, package_path, video_path,"
            " status, filled_at, published_at, publish_url, operator, note, created_at)"
            " VALUES (?,?,?,?,?,'published',NULL,?,?,?,?,?)",
            (task_id, platform, "", "", "", stamp, url, actor, note, stamp), path)
    dbm.execute(
        "UPDATE publish_records SET status='published', published_at=?, publish_url=?, operator=?,"
        " note=CASE WHEN ?='' THEN note ELSE ? END WHERE id=?",
        (stamp, url, actor, note, note, row["id"]), path)
    return row["id"]


def latest_record(task_id: int, *, platform: str | None = None, path: str | None = None):
    sql = "SELECT * FROM publish_records WHERE task_id=?"
    args: list[Any] = [task_id]
    if platform:
        sql += " AND platform=?"
        args.append(platform)
    sql += " ORDER BY id DESC LIMIT 1"
    return dbm.query_one(sql, tuple(args), path)


def records_of(task_id: int, *, path: str | None = None) -> list[dict[str, Any]]:
    return dbm.query("SELECT * FROM publish_records WHERE task_id=? ORDER BY id", (task_id,), path)
