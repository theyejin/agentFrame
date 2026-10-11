#!/usr/bin/env python3
# 文件用途：copy-writer 的实现入口 —— 一条选题输入生成 3 套不同侧重点的候选文案，供关口① 选择。
# 对应需求：R-L1-05（文案生成）、F-01（对话框 Prompt）、F-02（字数范围）、F-03（类型）、R-L1-19（3 套且侧重点互不重复）、R-7-03（记录模型与提示词版本）。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（copy-writer 与 3 套候选文案）
# 维护提示：侧重枚举（hook/emotion/cta）改动要同步 db/schema.sql 的 copy_variants.focus、templates/prompts/copy-generate.md 与 docs/skill-roster.md。
"""copy-writer 命令行入口。

    generate --task-id N [--out DIR] [--attempts 3] [--allow-paid] [--json]

做四件事：① 取任务与选题并校验输入；② 按版本取提示词、经 llm-adapter 生成 3 套文案；
③ 自检（3 套、侧重互不重复、字数落在 F-02 区间）；④ 登记产物与步骤流水，等关口① 选择。
生成不满 3 次就失败：把步骤记为 failed、任务置 blocked 并写明原因（由编排者决定重试或转人工）。
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
import prompt_templates as pt  # noqa: E402
import recording as rec  # noqa: E402
import text_utils as tu  # noqa: E402

PROMPT_KEY = "copy-generate"
# 三套文案的侧重（与 db/schema.sql 的 copy_variants.focus 枚举一致）
FOCUSES = [("hook", "开头钩子"), ("emotion", "情绪强度"), ("cta", "行动号召")]
CONTENT_TYPES = ("情绪冲突", "干货教程", "热点观点", "其他")
DEFAULT_ATTEMPTS = 3


class InputError(ValueError):
    """输入校验不通过（R-L1-18：校验失败必须退回，不能带病往下走）。"""


def validate_input(bundle: dict) -> None:
    task, topic = bundle["task"], bundle["topic"]
    if not (topic.get("title") or "").strip():
        raise InputError("选题标题为空：请先在 topics 里写明选题（title 不能为空）")
    if task.get("content_type") not in CONTENT_TYPES:
        raise InputError(f"内容类型必须是 {CONTENT_TYPES} 之一，当前为 {task.get('content_type')!r}")
    low, high = int(task.get("word_min") or 0), int(task.get("word_max") or 0)
    if low <= 0 or high <= 0 or low > high:
        raise InputError(f"字数区间不合法：word_min={low} word_max={high}（需满足 0 < 下限 ≤ 上限）")
    if not ((task.get("prompt") or "").strip() or (topic.get("summary") or "").strip()):
        raise InputError("对话框 Prompt（F-01）与选题简述都为空：至少要给一个，否则无法生成文案")


def check_plans(plans: list[dict], task: dict) -> list[str]:
    """自检 3 套文案（R-L1-19）。返回问题清单，空列表=通过。"""
    problems: list[str] = []
    if len(plans) != 3:
        problems.append(f"文案套数为 {len(plans)}，要求正好 3 套")
    numbers = [p["plan_no"] for p in plans]
    if sorted(numbers) != [1, 2, 3]:
        problems.append(f"套号必须是 1/2/3，实际为 {numbers}")
    got = [p["focus"] for p in plans]
    expected = [key for key, _ in FOCUSES]
    if sorted(got) != sorted(expected):
        problems.append(f"三套侧重必须正好是 {expected}（互不重复），实际为 {got}")
    low, high = int(task["word_min"]), int(task["word_max"])
    for plan in plans:
        n = tu.count_words(plan["body"])
        plan["word_count"] = n
        if not plan["body"]:
            problems.append(f"第 {plan['plan_no']} 套正文为空")
        elif not (low <= n <= high):
            problems.append(f"第 {plan['plan_no']} 套正文 {n} 字，超出 {low}–{high} 区间")
    return problems


def _title_of(body: str) -> str:
    for line in body.splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:30]
    return ""


def render_files(out_dir: Path, bundle: dict, plans: list[dict], meta: dict) -> list[Path]:
    """写出 variants.json（机器用）与 variants.md（人看）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    task, topic = bundle["task"], bundle["topic"]
    payload = {
        "task_id": task["id"], "topic_id": topic["id"], "topic_title": topic["title"],
        "content_type": task["content_type"], "platform": task["target_platform"] or "",
        "word_range": [task["word_min"], task["word_max"]],
        "prompt_key": meta["prompt_key"], "prompt_version": meta["prompt_version"],
        "model_version": meta["model_version"], "adapter_used": meta["adapter_used"],
        "generated_at": dbm.now_iso(), "stamp": meta["stamp"],
        "plans": [{"plan_no": p["plan_no"], "focus": p["focus"], "focus_note": p["focus_note"],
                   "word_count": p.get("word_count", 0), "title": _title_of(p["body"]),
                   "body": p["body"]} for p in plans],
    }
    json_path = out_dir / f"variants-{meta['stamp']}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [f"# {topic['title']} · 候选文案（3 套）", "",
                f"- 内容类型：{task['content_type']}　目标平台：{task['target_platform'] or '未指定'}",
                f"- 字数区间：{task['word_min']}–{task['word_max']} 字　模型：{meta['model_version']}　提示词：{meta['prompt_key']} {meta['prompt_version']}", ""]
    for p in plans:
        note = f"（{p['focus_note']}）" if p["focus_note"] else ""
        md_lines += [f"## 方案 {p['plan_no']} · 侧重 {p['focus']}{note}　{p.get('word_count', 0)} 字", "", p["body"], ""]
    md_path = out_dir / "variants.md"
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
    return [json_path, md_path]


def persist(conn_path: str | None, bundle: dict, plans: list[dict], files: list[Path], meta: dict,
            step_no: int | None, duration_ms: int) -> dict:
    task, topic = bundle["task"], bundle["topic"]
    step_run_id = rec.record_step(
        task["id"], "copy-writer", "ok", step_no=step_no, adapter_used=meta["adapter_used"],
        input_json={"prompt_key": meta["prompt_key"], "prompt_version": meta["prompt_version"],
                    "word_range": [task["word_min"], task["word_max"]], "content_type": task["content_type"]},
        output_json={"plans": [{"plan_no": p["plan_no"], "focus": p["focus"], "word_count": p.get("word_count", 0)} for p in plans]},
        duration_ms=duration_ms, path=conn_path)
    # copy_variants 上是 UNIQUE(task_id, plan_no)：库里只存「当前 3 套候选」，重生成就覆盖同一套号；
    # 每一代的完整正文留在带时间戳的产物文件与 artifacts 表里（可追溯靠产物，不靠堆行）。
    with dbm.transaction(conn_path) as conn:
        for p in plans:
            conn.execute(
                """INSERT INTO copy_variants (task_id, plan_no, focus, focus_note, title, body, word_count,
                                              status, model_version, prompt_version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                   ON CONFLICT(task_id, plan_no) DO UPDATE SET
                       focus = excluded.focus, focus_note = excluded.focus_note, title = excluded.title,
                       body = excluded.body, word_count = excluded.word_count, status = 'active',
                       model_version = excluded.model_version, prompt_version = excluded.prompt_version,
                       created_at = excluded.created_at""",
                (task["id"], p["plan_no"], p["focus"], p["focus_note"], _title_of(p["body"]), p["body"],
                 p.get("word_count", 0), meta["model_version"], meta["prompt_version"], dbm.now_iso()))
    artifact_ids = [rec.record_artifact(task["id"], "copy", rec.rel_path(f), step_run_id=step_run_id,
                                        model_version=meta["model_version"], prompt_version=meta["prompt_version"],
                                        meta={"plan_count": len(plans), "topic_id": topic["id"]}, path=conn_path)
                    for f in files]
    return {"step_run_id": step_run_id, "artifact_ids": artifact_ids}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="生成 3 套不同侧重点的候选文案（文案线 FLOW-1）")
    p.add_argument("--db", default=None)
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("generate", help="按任务生成 3 套文案并入库")
    s.add_argument("--task-id", type=int, required=True)
    s.add_argument("--out", default=None, help="产出目录（缺省 workspace/topic-<选题号>/copy）")
    s.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS, help=f"生成失败重试次数，默认 {DEFAULT_ATTEMPTS}")
    s.add_argument("--step-no", type=int, default=None, help="步骤号（缺省在任务内自增）")
    s.add_argument("--allow-paid", action="store_true", help="显式批准计费模型（C-09，默认不批）")
    s.set_defaults(func=cmd_generate)
    return p


def cmd_generate(args: argparse.Namespace) -> int:
    bundle = rec.task_bundle(args.task_id, args.db)
    task, topic = bundle["task"], bundle["topic"]
    if task["stage"] != "copy":
        print(f"[错误] 任务 {task['id']} 当前环节是 {task['stage']}，不是 copy：文案线不接这一单", file=sys.stderr)
        return 2
    try:
        validate_input(bundle)
    except InputError as exc:
        rec.update_task(task["id"], status="blocked", operator=task.get("operator") or "", path=args.db)
        rec.record_step(task["id"], "copy-writer", "failed", step_no=args.step_no,
                        error=f"输入校验不通过：{exc}", path=args.db)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2

    tpl = pt.load(PROMPT_KEY)
    values = {
        "topic_title": topic["title"],
        "topic_brief": (topic.get("summary") or topic.get("keywords") or "").strip(),
        "content_type": task["content_type"],
        "platform": task["target_platform"] or "未指定",
        "word_min": task["word_min"], "word_max": task["word_max"],
        "focus_list": "、".join(name for _, name in FOCUSES),
        "extra_requirements": (task.get("prompt") or "").strip() or "无",
    }
    prompt = tpl.render(values)
    payload = {"prompt": prompt, "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
               "topic_title": topic["title"], "plan_count": 3, "focuses": [name for _, name in FOCUSES]}

    started = dbm.now_iso()
    problems: list[str] = []
    result = None
    for attempt in range(1, max(1, args.attempts) + 1):
        result = ar.invoke("llm", payload, allow_paid=args.allow_paid)
        if not result.ok:
            problems = [f"第 {attempt} 次调用失败：{result.error}"]
            break
        plans = tu.parse_copy_plans(result.output.get("text", ""))
        problems = check_plans(plans, task)
        if not problems:
            break
        problems = [f"第 {attempt} 次生成不合格：" + "；".join(problems)]
    duration_ms = rec.elapsed_ms(started)

    if problems:
        error = "；".join(problems)
        rec.record_step(task["id"], "copy-writer", "failed", step_no=args.step_no,
                        adapter_used=(result.adapter_id if result else ""), error=error,
                        input_json={"prompt_key": tpl.prompt_key, "prompt_version": tpl.version},
                        duration_ms=duration_ms, path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {error}", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else rec.workspace_dir(topic["id"], "copy", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
            "model_version": result.model_version or "unknown", "adapter_used": result.adapter_id,
            "stamp": rec.unique_stamp(out_dir, "variants")}
    files = render_files(out_dir, bundle, plans, meta)
    info = persist(args.db, bundle, plans, files, meta, args.step_no, duration_ms)
    info.update({"task_id": task["id"], "topic_id": topic["id"], "adapter_used": meta["adapter_used"],
                 "model_version": meta["model_version"], "prompt_version": meta["prompt_version"],
                 "files": [rec.rel_path(f) for f in files],
                 "plans": [{"plan_no": p["plan_no"], "focus": p["focus"],
                            "word_count": p.get("word_count", 0), "title": _title_of(p["body"])} for p in plans],
                 "next": "等关口①：hitl-gate open --task-id %d --gate gate1_select_copy" % task["id"]})
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜适配器 {meta['adapter_used']}｜提示词 {meta['prompt_key']} {meta['prompt_version']}")
        for p in info["plans"]:
            print(f"  方案{p['plan_no']}  侧重 {p['focus']}　{p['word_count']} 字　{p['title']}")
        print("产出：" + "、".join(info["files"]))
        print("下一步：" + info["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except pt.MissingVariable as exc:
        print(f"[错误] 提示词变量缺失（模板与调用方对不上）：{exc}", file=sys.stderr)
        return 2
    except (rec.RecordingError, InputError, ar.MissingKey) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
