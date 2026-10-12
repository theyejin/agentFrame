#!/usr/bin/env python3
# 文件用途：自动剪辑 —— 按人工在关口② 给的参数（镜头顺序 / 每镜时长 / 单张素材替换）渲染剪辑版成片。
# 对应需求：R-L1-08（视频自动剪辑可人工干预）、§8.3（关口② 调整态）、R-L2-17（降级链）、Q-7、C-09。
# 对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html（关口② 剪辑干预 → auto-editor → 成片）
# 维护提示：参数口径（order / durations / replacements）必须与 hitl-events 的 diff_json 字段一致，改要同步测试。
"""自动剪辑（auto-editor）。

用法：
    python3 .dsh/skills/auto-editor/run.py edit --task-id 1 [--draft FILE] [--from-hitl]
                                                  [--order "1,2,3,…"] [--durations "1:3,5:2"]
                                                  [--replace "7=workspace/…/shot-07.png"] [--out FILE]
                                                  [--fps 30] [--size 720x1280] [--allow-paid] [--step-no N] [--json]

参数来源（二选一，同时给以命令行优先）：
  ① `--from-hitl`：读该任务最近一次已决议的关口② 事件（confirm 表示按草稿原样，adjust 表示带 diff_json 调整）；
  ② 命令行直给：`--order` 决定播放顺序、`--durations` 覆盖个别镜头时长、`--replace` 指定某镜换素材。

完成判据：
  ① 镜头顺序是 1–24 的一个排列（不重不漏）、每镜时长都大于 0、替换素材必须存在；
  ② 产出 `workspace/topic-<选题号>/video/edited/edited-<时间戳>.mp4`，时长与参数计划一致（±15%）；
  ③ 登记 kind=video、role=edited 的产物 + 一份 `edit-params` 参数留痕（人工改了什么要能查）。

退出码：0 = 成功；1 = 渲染失败或自检不过（任务置 blocked）；2 = 输入校验不通过。
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
import recording as rec  # noqa: E402
import video as vd  # noqa: E402

SKILL_ID = "auto-editor"
LINE = "video"
SHOT_TOTAL = 24
DEFAULT_FPS = 30
DEFAULT_SIZE = (720, 1280)
DURATION_TOLERANCE = 0.15


class InputError(ValueError):
    """上游没就绪或参数不合法。"""


def parse_size(text: str) -> tuple[int, int]:
    parts = text.lower().replace("*", "x").split("x")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise InputError(f"--size 需形如 720x1280，收到：{text}")
    return int(parts[0]), int(parts[1])


def parse_order(text: str) -> list[int]:
    if not text.strip():
        raise InputError("--order 不能为空（要么给 1,2,3… 的顺序，要么用 --from-hitl 读关口② 的参数）")
    try:
        order = [int(x.strip()) for x in text.replace("，", ",").split(",") if x.strip()]
    except ValueError:
        raise InputError(f"--order 只能是逗号分隔的镜号，收到：{text}")
    if sorted(order) != list(range(1, SHOT_TOTAL + 1)):
        raise InputError(f"--order 必须是 1–{SHOT_TOTAL} 的一个排列（不重不漏），收到 {len(order)} 个")
    return order


def parse_durations(text: str) -> dict[int, float]:
    """`--durations "1:3,5:2.5"` → {1: 3.0, 5: 2.5}。"""
    out: dict[int, float] = {}
    for chunk in (text or "").replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise InputError(f"--durations 需形如 镜号:秒数（如 1:3），收到：{chunk}")
        no, secs = chunk.split(":", 1)
        try:
            no_i, secs_f = int(no.strip()), float(secs.strip())
        except ValueError:
            raise InputError(f"--durations 解析失败：{chunk}")
        if not 1 <= no_i <= SHOT_TOTAL:
            raise InputError(f"--durations 镜号越界：{no_i}（应在 1–{SHOT_TOTAL}）")
        if secs_f <= 0:
            raise InputError(f"--durations 秒数必须大于 0：{chunk}")
        out[no_i] = secs_f
    return out


def parse_replace(text: str) -> dict[int, str]:
    """`--replace "7=workspace/…/shot-07.png"` → {7: 'workspace/…/shot-07.png'}。"""
    out: dict[int, str] = {}
    for chunk in (text or "").replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise InputError(f"--replace 需形如 镜号=图片路径，收到：{chunk}")
        no, path = chunk.split("=", 1)
        try:
            no_i = int(no.strip())
        except ValueError:
            raise InputError(f"--replace 镜号不是数字：{chunk}")
        if not 1 <= no_i <= SHOT_TOTAL:
            raise InputError(f"--replace 镜号越界：{no_i}（应在 1–{SHOT_TOTAL}）")
        out[no_i] = path.strip()
    return out


def params_from_hitl(task_id: int, db: str | None) -> tuple[dict, dict]:
    """读最近一次已决议的关口② 事件；confirm=原样、adjust=按 diff_json 调整。"""
    events = [e for e in hitl.list_events(task_id, path=db) if e["gate"] == hitl.GATE2]
    if not events:
        raise InputError(f"任务 {task_id} 没有关口②（剪辑干预）记录：请先 hitl-gate open --gate {hitl.GATE2} 并 resolve")
    event = sorted(events, key=lambda e: e["id"])[-1]
    diff = json.loads(event.get("diff_json") or "{}")
    return ({"action": event["action"], "actor": event.get("actor", ""), "event_id": event["id"]}, diff)


def cmd_edit(args: argparse.Namespace) -> int:
    started = dbm.now_iso()
    try:
        task = rec.task_bundle(args.task_id, path=args.db)["task"]
        shots = rec.latest_shots(args.task_id, path=args.db)
        if len(shots) != SHOT_TOTAL:
            raise InputError(f"独立图应为 {SHOT_TOTAL} 张，实际 {len(shots)} 张：请先跑 image-splitter split")
        size = parse_size(args.size) if args.size else DEFAULT_SIZE

        hitl_info: dict = {}
        order_arg, durations_arg, replace_arg = args.order, args.durations, args.replace
        if args.from_hitl:
            hitl_info, diff = params_from_hitl(args.task_id, args.db)
            order_arg = order_arg or ",".join(str(x) for x in (diff.get("order") or []))
            if not durations_arg and diff.get("durations"):
                pairs = diff["durations"]
                durations_arg = ",".join(f"{k}:{v}" for k, v in pairs.items()) if isinstance(pairs, dict) \
                    else ",".join(f"{i + 1}:{v}" for i, v in enumerate(pairs))
            if not replace_arg and diff.get("replacements"):
                replace_arg = ",".join(f"{k}={v}" for k, v in diff["replacements"].items())

        order = parse_order(order_arg or ",".join(str(i) for i in range(1, SHOT_TOTAL + 1)))
        overrides = parse_durations(durations_arg or "")
        replacements = parse_replace(replace_arg or "")
        draft = None
        if args.draft:
            draft = Path(args.draft)
            if not draft.is_absolute():
                draft = dbm.REPO_ROOT / draft
        else:
            art = rec.latest_artifact(args.task_id, "video", role="draft", path=args.db)
            draft = (dbm.REPO_ROOT / art["path"]) if art else None

        image_by_no = {int(s["shot_no"]): (dbm.REPO_ROOT / s["file"]) for s in shots}
        for no, path in replacements.items():
            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = dbm.REPO_ROOT / candidate
            if not candidate.is_file():
                raise InputError(f"--replace 第 {no} 镜给的图片不存在：{path}")
            image_by_no[no] = candidate
        plan = [{"shot_no": no, "image": image_by_no[no], "duration_s": float(overrides.get(no, args.shot_seconds))}
                for no in order]
    except (InputError, rec.RecordingError, hitl.HitlError) as exc:
        try:
            rec.record_step(args.task_id, SKILL_ID, "failed", step_no=args.step_no,
                            error=f"输入校验不通过：{exc}", path=args.db)
        except rec.RecordingError as inner:
            print(f"[提示] 无法登记这次退回：{inner}", file=sys.stderr)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out).parent if args.out else rec.workspace_dir(task["topic_id"], f"{LINE}/edited", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    edited = Path(args.out) if args.out else out_dir / f"edited-{rec.timestamp_slug()}.mp4"
    planned = round(sum(item["duration_s"] for item in plan), 3)

    payload = {"images": [str(item["image"]) for item in plan], "abs_out": str(edited),
               "durations": [item["duration_s"] for item in plan], "fps": int(args.fps),
               "size": [size[0], size[1]], "task_id": task["id"]}
    result = ar.invoke("video", payload, allow_paid=args.allow_paid)
    problems: list[str] = []
    if not result.ok:
        problems.append(f"渲染失败：{result.error}")
    else:
        produced = Path(result.output.get("path") or edited)
        report = vd.check_video(produced, min_seconds=0.5, expect_size=size)
        problems = list(report["problems"])
        actual = float(report["info"].get("duration_s") or 0.0)
        if planned > 0 and abs(actual - planned) / planned > DURATION_TOLERANCE:
            problems.append(f"成片时长 {actual}s 与参数计划 {planned}s 偏差超过 {int(DURATION_TOLERANCE * 100)}%")

    if problems:
        error = "；".join(problems)
        rec.record_step(task["id"], SKILL_ID, "failed", step_no=args.step_no,
                        adapter_used=result.adapter_id, error=error,
                        input_json={"order": order, "source": "hitl" if args.from_hitl else "cli"},
                        output_json=result.to_dict(), duration_ms=rec.elapsed_ms(started), path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {error}", file=sys.stderr)
        return 1

    produced = Path(result.output["path"])
    params = {"order": order, "durations": {str(item["shot_no"]): item["duration_s"] for item in plan},
              "replacements": {str(k): rec.rel_path(Path(v)) for k, v in replacements.items()},
              "shot_seconds": args.shot_seconds, "fps": args.fps, "size": f"{size[0]}x{size[1]}",
              "draft": rec.rel_path(draft) if draft else "", "hitl": hitl_info}
    params_path = out_dir / f"edit-params-{rec.timestamp_slug()}.json"
    params_path.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")

    duration_ms = rec.elapsed_ms(started)
    step_id = rec.record_step(task["id"], SKILL_ID, "ok", step_no=args.step_no,
                              adapter_used=result.adapter_id,
                              input_json={"source": "hitl" if args.from_hitl else "cli", "order": order,
                                          "durations_override": overrides, "replacements": list(replacements)},
                              output_json={"edited": rec.rel_path(produced), "params": rec.rel_path(params_path),
                                           "planned_duration_s": planned},
                              duration_ms=duration_ms, path=args.db)
    art_id = rec.record_artifact(task["id"], "video", rec.rel_path(produced), step_run_id=step_id,
                                 model_version=result.model_version or "ffmpeg-render-v1", prompt_version="none",
                                 meta={"role": "edited", "planned_duration_s": planned, "order": order,
                                       "adapter_used": result.adapter_id},
                                 path=args.db)
    rec.record_artifact(task["id"], "manifest", rec.rel_path(params_path), step_run_id=step_id,
                        model_version="human" if args.from_hitl else "local", prompt_version="none",
                        meta={"role": "edit-params", "source": "hitl" if args.from_hitl else "cli"},
                        path=args.db)

    info = {"task_id": task["id"], "topic_id": task["topic_id"], "skill": SKILL_ID,
            "adapter_used": result.adapter_id, "edited": rec.rel_path(produced),
            "duration_s": float(result.output.get("duration_s") or 0.0), "planned_duration_s": planned,
            "order": order, "replacements": list(replacements), "params": rec.rel_path(params_path),
            "artifact_id": art_id, "step_run_id": step_id,
            "next": f"导出成片与封面：python3 .dsh/skills/video-exporter/run.py export --task-id {task['id']}"}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜适配器 {info['adapter_used']}｜剪辑版 {info['duration_s']}s（计划 {info['planned_duration_s']}s）")
        print(f"参数留痕：{info['params']}")
        print("下一步：" + info["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="自动剪辑：按关口② 的参数渲染剪辑版成片")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_edit = sub.add_parser("edit", help="渲染剪辑版")
    p_edit.add_argument("--task-id", type=int, required=True)
    p_edit.add_argument("--draft", default=None, help="草稿视频路径（默认取最近登记的 draft 产物）")
    p_edit.add_argument("--from-hitl", action="store_true", help="读关口② 最近一次决议的参数")
    p_edit.add_argument("--order", default=None, help="镜头顺序，如 1,2,3…24")
    p_edit.add_argument("--durations", default=None, help="个别镜头时长覆盖，如 1:3,5:2.5")
    p_edit.add_argument("--replace", default=None, help="单张素材替换，如 7=workspace/…/shot-07.png")
    p_edit.add_argument("--shot-seconds", type=float, default=3.0, help="未覆盖镜头的默认时长（秒）")
    p_edit.add_argument("--fps", type=int, default=DEFAULT_FPS)
    p_edit.add_argument("--size", default="720x1280", help="输出分辨率，形如 720x1280")
    p_edit.add_argument("--out", default=None, help="输出文件（默认 workspace/topic-<id>/video/edited/edited-<时间戳>.mp4）")
    p_edit.add_argument("--allow-paid", action="store_true", help="允许计费适配器（默认零付费，C-09）")
    p_edit.add_argument("--step-no", type=int, default=None)
    p_edit.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="以 JSON 输出结果（也可写在子命令前）")
    p_edit.set_defaults(func=cmd_edit)

    for _action in parser._actions:  # 子命令也认 --json（写在子命令前后都行）
        if isinstance(_action, argparse._SubParsersAction):
            for _child in _action.choices.values():
                if not any("--json" in _a.option_strings for _a in _child._actions):
                    _child.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                                        help="以 JSON 输出结果（也可写在子命令前）")
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
