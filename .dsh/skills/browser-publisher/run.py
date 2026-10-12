#!/usr/bin/env python3
# 文件用途：browser-publisher 的实现入口 —— 组装发布包、生成填写清单，停在发布前等人工（C-08）
# 对应需求：FLOW-6 发布准备与填写 / R-L1-09（发布留痕）/ R-8-17（发布红线）/ C-08（Agent 只填不发）/ C-10（关口③ 人工授权）
# 对应流程图：.archify/FLOW-PUBLISH-20261012/publish-line.html（browser-publisher 与关口③）
# 维护提示：发布适配器改动只改 templates/adapters/registry.json 的 browser 链；本文件不得出现任何提交发布的调用。
"""browser-publisher 命令行入口。

    prepare        --task-id N [--platform P] [--account-label X] [--live] [--json]
    mark-published --task-id N --actor 名字 [--url U] [--platform P] [--note 说明] [--json]
    status         --task-id N [--platform P] [--live] [--json]

prepare 做四件事：① 校验任务在发布环节、成片与封面齐备、发布准备就绪；② 经 browser 降级链拿填写清单
（离线走 browser.fill-plan）；③ 写发布包与 publish_records（status=filled/pending，**绝不写 published**）；
④ 开启关口③ 等人工发布。mark-published 只做人工发布后的回填（必须写 operator）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import adapter_runtime as ar  # noqa: E402
import db as dbm  # noqa: E402
import hitl  # noqa: E402
import publish_guard as pg  # noqa: E402
import recording as rec  # noqa: E402


class InputError(ValueError):
    """输入校验不通过（环节不对、缺成片/封面/发布准备等）。"""


def _load_prep(task_id: int, db: str | None) -> tuple[dict, str]:
    """取发布准备（title-cover-prep 的产物）：返回（prep 字典, 提示词版本）。"""
    row = rec.latest_artifact(task_id, "manifest", role="publish-prep", path_like="publish/prep", path=db)
    if not row:
        raise InputError("没有发布准备产物：先跑 title-cover-prep prepare 生成标题/标签/封面文案")
    path = rec.abs_path_of(row["path"])
    if not path.is_file():
        raise InputError(f"发布准备文件不存在：{row['path']}")
    try:
        prep = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"发布准备不是合法 JSON：{row['path']}（{exc}）") from exc
    return prep, (row.get("prompt_version") or "none")


def _gate3_authorized(task_id: int, db: str | None) -> bool:
    row = dbm.query_one(
        "SELECT id FROM hitl_events WHERE task_id=? AND gate=? AND action='confirm' ORDER BY id DESC LIMIT 1",
        (task_id, hitl.GATE3), db)
    return row is not None


def cmd_prepare(args: argparse.Namespace) -> int:
    bundle = rec.task_bundle(args.task_id, args.db)
    task, topic = bundle["task"], bundle["topic"]
    if task["stage"] != "publish":
        print(f"[错误] 任务 {task['id']} 当前环节是 {task['stage']}，不是 publish：发布线不接这一单", file=sys.stderr)
        return 2
    platform = args.platform or task["target_platform"] or ""
    if not platform:
        raise InputError("没有平台：任务没设 target_platform，请用 --platform 指定")
    if platform not in pg.list_platforms(path=args.db):
        raise InputError(f"平台「{platform}」没有预设模板；已配置：{'、'.join(pg.list_platforms(path=args.db))}")

    video_row = rec.latest_artifact(task["id"], "video", role="final", path=args.db)
    cover_row = rec.latest_artifact(task["id"], "image", role="cover", path=args.db)
    if not video_row:
        raise InputError("没有最终成片产物（role=final）：先跑 video-exporter export")
    if not cover_row:
        raise InputError("没有封面产物（role=cover）：成片与封面必须成对，先跑 video-exporter export")
    video_path = rec.abs_path_of(video_row["path"])
    if not video_path.is_file():
        raise InputError(f"成片文件不存在：{video_row['path']}")

    prep, prep_version = _load_prep(task["id"], args.db)
    authorized = _gate3_authorized(task["id"], args.db)

    pkg = pg.build_package(task_id=task["id"], platform=platform, account_label=args.account_label,
                           video_path=video_row["path"], cover_path=cover_row["path"], prep=prep,
                           operator=task.get("operator") or "", submit=False)
    check = pg.check_package(pkg, gate3_authorized=authorized, live=args.live)

    out_dir = rec.workspace_dir(topic["id"], "publish", args.db)
    stamp = rec.unique_stamp(out_dir, "package")
    package_dir = out_dir / f"package-{stamp}"
    package_dir.mkdir(parents=True, exist_ok=True)

    # 经 browser 降级链拿「填写清单」：离线走 browser.fill-plan，永远 submitted=false（C-08）
    fields = {
        "标题候选": prep.get("titles") or [],
        "正文": prep.get("body") or prep.get("copy") or "",
        "标签": prep.get("tags") or [],
        "封面文案": prep.get("cover") or "",
    }
    fill_payload = {"platform": platform, "account_label": args.account_label, "video": video_row["path"],
                    "cover": cover_row["path"], "fields": fields, "url": (pkg.get("template") or {}).get("note", ""),
                    "rel_out": rec.rel_path(package_dir / "fill-plan.json")}
    filled = ar.invoke("browser", fill_payload, allow_paid=False)
    if not filled.ok:
        rec.record_step(task["id"], "browser-publisher", "failed", step_no=args.step_no,
                        error=f"填写清单生成失败：{filled.error}", path=args.db)
        print(f"[失败] 填写清单生成失败：{filled.error}", file=sys.stderr)
        return 1
    plan = filled.output or {}
    if plan.get("submitted") or plan.get("auto_publish"):
        rec.record_step(task["id"], "browser-publisher", "failed", step_no=args.step_no,
                        error="C-08 红线：适配器返回了 submitted=true（自动发布），已拒绝继续", path=args.db)
        print("[失败] C-08 红线：适配器声称已自动提交，流程中止（发布必须由人完成）", file=sys.stderr)
        return 1

    package_path = package_dir / "package.json"
    package_path.write_text(json.dumps({
        "task_id": task["id"], "topic_id": topic["id"], "platform": platform,
        "account_label": args.account_label, "video_path": video_row["path"], "cover_path": cover_row["path"],
        "prep": prep, "prompt_version": prep_version, "fill_plan": plan.get("plan_path", ""),
        "check": {"ok": check["ok"], "problems": check["problems"], "warnings": check["warnings"]},
        "submitted": False, "note": "首版不自动提交：运营人员核对后手动发布（C-08）",
        "created_at": dbm.now_iso(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    step_id = rec.record_step(task["id"], "browser-publisher", "ok" if check["ok"] else "failed",
                              step_no=args.step_no, adapter_used=filled.adapter_id,
                              input_json={"platform": platform, "live": bool(args.live)},
                              error="" if check["ok"] else "；".join(check["problems"]), path=args.db)
    rec.record_artifact(task["id"], "publish_package", rec.rel_path(package_path), step_run_id=step_id,
                        model_version=filled.model_version or "fill-plan-v1", prompt_version=prep_version,
                        meta={"role": "package", "platform": platform, "fill_plan": plan.get("plan_path", ""),
                              "submitted": False}, path=args.db)
    status = "pending" if authorized else "filled"
    record_id = pg.record(task["id"], platform=platform, account_label=args.account_label,
                          package_path=rec.rel_path(package_dir), video_path=video_row["path"],
                          status=status, operator=task.get("operator") or "", note="等待人工发布", path=args.db)

    gate_event = None
    if check["ok"]:
        gate_event = hitl.open_gate(task["id"], hitl.GATE3,
                                    note=f"发布包已就绪：{rec.rel_path(package_dir)}（人工核对后点击发布）",
                                    path=args.db)
    else:
        rec.update_task(task["id"], status="blocked", path=args.db)

    info = {
        "task_id": task["id"], "platform": platform, "package_dir": rec.rel_path(package_dir),
        "package_json": rec.rel_path(package_path), "fill_plan": plan.get("plan_path", ""),
        "adapter_used": filled.adapter_id, "model_version": filled.model_version,
        "publish_record_id": record_id, "publish_status": status, "gate3_event": gate_event,
        "check": check, "submitted": False,
        "message": "发布包已备好，且**没有**提交发布：请人工核对填写清单后在浏览器里发布（C-08）" if check["ok"]
                   else "发布包自检不通过：已把任务置 blocked，修好后再跑一次",
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(pg.render_check(check))
        print(f"[{'完成' if check['ok'] else '失败'}] {info['message']}")
        print(f"  发布包：{info['package_dir']}")
        print(f"  填写清单：{info['fill_plan']}（适配器 {info['adapter_used']}）")
        if check["ok"]:
            print(f"  关口③ 已开启（事件 {gate_event}）：等人工发布后跑 mark-published 回填")
    return 0 if check["ok"] else 1


def cmd_mark_published(args: argparse.Namespace) -> int:
    bundle = rec.task_bundle(args.task_id, args.db)
    task = bundle["task"]
    platform = args.platform or task["target_platform"] or ""
    record = pg.latest_record(task["id"], platform=platform or None, path=args.db)
    resolved = None
    if task["status"] == "waiting_human":
        resolved = hitl.resolve_gate(task["id"], hitl.GATE3, "confirm", args.actor,
                                     snapshot={"url": args.url, "platform": platform},
                                     path=args.db)
    record_id = pg.mark_published(task["id"], actor=args.actor, url=args.url, platform=platform,
                                 note=args.note or "人工发布完成", path=args.db)
    rec.update_task(task["id"], stage="metrics", status="running", operator=args.actor, path=args.db)
    rec.record_step(task["id"], "browser-publisher", "ok", step_no=args.step_no,
                    adapter_used="human", input_json={"action": "mark-published", "url": args.url},
                    path=args.db)
    info = {"task_id": task["id"], "platform": platform, "publish_record_id": record_id,
            "gate3_event": resolved, "url": args.url, "operator": args.actor,
            "stage": "metrics", "had_record": record is not None}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"[完成] 已回填人工发布结果：{platform or '（未标平台）'} {args.url or '（未填链接）'}"
              f"（记录 {record_id}，操作人 {args.actor}），任务推进到 metrics")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    bundle = rec.task_bundle(args.task_id, args.db)
    task, topic = bundle["task"], bundle["topic"]
    platform = args.platform or task["target_platform"] or ""
    record = pg.latest_record(task["id"], platform=platform or None, path=args.db)
    authorized = _gate3_authorized(task["id"], args.db)
    video_row = rec.latest_artifact(task["id"], "video", role="final", path=args.db)
    cover_row = rec.latest_artifact(task["id"], "image", role="cover", path=args.db)
    prep_row = rec.latest_artifact(task["id"], "manifest", role="publish-prep", path=args.db)
    prep = {}
    if prep_row and rec.abs_path_of(prep_row["path"]).is_file():
        try:
            prep = json.loads(rec.abs_path_of(prep_row["path"]).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prep = {}
    pkg = pg.build_package(task_id=task["id"], platform=platform,
                           account_label=(record or {}).get("account_label", ""),
                           video_path=(video_row or {}).get("path", ""),
                           cover_path=(cover_row or {}).get("path", ""), prep=prep)
    check = pg.check_package(pkg, gate3_authorized=authorized, live=args.live)
    info = {"task_id": task["id"], "stage": task["stage"], "status": task["status"], "platform": platform,
            "gate3_authorized": authorized, "record": record, "check": check}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}：环节 {task['stage']}、状态 {task['status']}、平台 {platform or '（未定）'}")
        print(f"关口③：{'已授权' if authorized else '未授权'}")
        if record:
            print(f"发布记录：{record['status']}（{record.get('filled_at') or ''}）"
                  f"{' 链接 ' + record['publish_url'] if record.get('publish_url') else ''}")
        print(pg.render_check(check))
    return 0 if check["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="browser-publisher", description="浏览器发布员：只填不发，停在发布前（C-08）")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("prepare", help="组装发布包并生成填写清单（不发布）")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--platform", default="", help="平台（缺省用任务的目标平台）")
    s.add_argument("--account-label", default="", help="账号标识（只记标签，不存密码）")
    s.add_argument("--live", action="store_true", help="按「要真正发布」的标准自检：检查关口③ 是否已授权")
    s.add_argument("--step-no", type=int, default=None, help="步骤号（缺省按已记录步骤自增）")
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser("mark-published", help="人工发布后回填结果（必须写操作人）")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--actor", required=True, help="谁发布的（真人标识，R-8-03）")
    s.add_argument("--url", default="", help="发布后的作品链接")
    s.add_argument("--platform", default="", help="平台（缺省用任务的目标平台）")
    s.add_argument("--note", default="", help="备注")
    s.add_argument("--step-no", type=int, default=None)
    s.set_defaults(func=cmd_mark_published)

    s = sub.add_parser("status", help="看发布准备到哪一步了")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--platform", default="", help="平台（缺省用任务的目标平台）")
    s.add_argument("--live", action="store_true", help="按「要真正发布」的标准自检")
    s.set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    for _action in parser._actions:  # 子命令也认 --json（写在子命令前后都行）
        if isinstance(_action, argparse._SubParsersAction):
            for _child in _action.choices.values():
                if not any("--json" in _a.option_strings for _a in _child._actions):
                    _child.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                                        help="以 JSON 输出结果（也可写在子命令前）")
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (InputError, pg.PublishGuardError, hitl.HitlError, rec.RecordingError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
