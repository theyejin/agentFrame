#!/usr/bin/env python3
# 文件用途：发布准备 —— 按平台模板（字数区间 / 标题写法 / 标签数量 / 封面比例）生成标题候选、标签与封面文案。
# 对应需求：R-8-01（平台预设模板）、R-L1-09（发布前信息准备）、Q-18、C-01（不得绝对化承诺）、C-09。
# 对应流程图：.archify/FLOW-VIDEO-20261012/video-line.html（video-exporter → publish-prep → 发布包）
#             .archify/FLOW-PUBLISH-20261012/publish-line.html（title-cover-prep → 发布包）
# 维护提示：平台模板取自数据库 platform_templates 表；改字段口径要同步 templates/prompts/publish-prep.md 与测试。
"""发布准备（title-cover-prep）。

用法：
    python3 .dsh/skills/title-cover-prep/run.py prepare --task-id 1 [--platform 抖音] [--out DIR]
                                                        [--attempts 3] [--allow-paid] [--step-no N] [--json]

完成判据：
  ① 任务已选出成片（role=final 产物存在），平台模板能在 platform_templates 里查到；
  ② 渲染 templates/prompts/publish-prep.md（v1）并至少 1 次产出可用结果；不足 3 条标题 / 标签数不符 /
     标题含绝对化用语（C-01）都要退回重试，最多 --attempts 次；
  ③ 产出 `workspace/topic-<选题号>/publish/prep-<时间戳>.json` 与同名 `.md`（给人在关口③ 核对）；
  ④ 登记 kind=manifest、role=publish-prep 的产物，任务 stage 保持 publish。

退出码：0 = 成功；1 = 生成失败或自检不过（任务置 blocked）；2 = 输入校验不通过。
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

SKILL_ID = "title-cover-prep"
LINE = "publish"
PROMPT_KEY = "publish-prep"
TITLE_COUNT = 3


class InputError(ValueError):
    """上游没就绪或参数不合法。"""


def platform_row(platform: str, db: str | None) -> dict:
    row = dbm.query_one("SELECT * FROM platform_templates WHERE platform = ?", (platform,), db)
    if row is None:
        known = [r["platform"] for r in dbm.query("SELECT platform FROM platform_templates ORDER BY id", (), db)]
        raise InputError(f"平台「{platform}」没有预设模板；已配置的平台：{'、'.join(known) or '（无）'}")
    return row


def cmd_prepare(args: argparse.Namespace) -> int:
    started = dbm.now_iso()
    try:
        bundle = rec.task_bundle(args.task_id, path=args.db)
        task, topic = bundle["task"], bundle["topic"]
        platform = args.platform or task["target_platform"]
        if not platform:
            raise InputError("任务没有 target_platform，也没有用 --platform 指定平台")
        row = platform_row(platform, args.db)
        final = rec.latest_artifact(task["id"], "video", role="final", path=args.db)
        if not final:
            raise InputError(f"任务 {task['id']} 还没有成片产物：请先跑 video-exporter export")
        copy = rec.selected_copy(task["id"], path=args.db) or {}
        copy_title = (copy.get("title") or topic.get("title") or "").strip()
        copy_excerpt = (copy.get("body") or task.get("prompt") or "").strip()[:120]
        if not copy_title:
            raise InputError("拿不到文案标题：请先跑 copy-writer 并在关口① 选定一套")
    except (InputError, rec.RecordingError) as exc:
        try:
            rec.record_step(args.task_id, SKILL_ID, "failed", step_no=args.step_no,
                            error=f"输入校验不通过：{exc}", path=args.db)
        except rec.RecordingError as inner:
            print(f"[提示] 无法登记这次退回：{inner}", file=sys.stderr)
        print(f"[错误] 输入校验不通过：{exc}", file=sys.stderr)
        return 2

    tpl = pt.load(PROMPT_KEY)
    values = {"platform": platform, "title_style": row["title_style"], "tag_count": row["tag_count"],
              "cover_ratio": row["cover_ratio"], "content_type": task["content_type"],
              "copy_title": copy_title, "copy_excerpt": copy_excerpt}
    prompt = tpl.render(values)
    payload = {"prompt": prompt, "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
               "platform": platform, "title_count": TITLE_COUNT, "tag_count": row["tag_count"],
               "topic_title": topic.get("title") or copy_title}

    problems: list[str] = []
    result = None
    prep: dict = {}
    for attempt in range(1, max(1, args.attempts) + 1):
        result = ar.invoke("llm", payload, allow_paid=args.allow_paid)
        if not result.ok:
            problems = [f"第 {attempt} 次调用失败：{result.error}"]
            break
        prep = tu.parse_publish_prep(result.output.get("text", ""))
        problems = tu.check_publish_prep(prep, tag_count=int(row["tag_count"]))
        if not problems:
            break

    if problems:
        error = "；".join(problems)
        rec.record_step(task["id"], SKILL_ID, "failed", step_no=args.step_no,
                        adapter_used=result.adapter_id if result else "",
                        error=error, input_json={"platform": platform, "attempts": args.attempts},
                        duration_ms=rec.elapsed_ms(started), path=args.db)
        rec.update_task(task["id"], status="blocked", path=args.db)
        print(f"[失败] {error}", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else rec.workspace_dir(task["topic_id"], f"{LINE}/prep", args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rec.timestamp_slug()
    data = {"task_id": task["id"], "topic_id": task["topic_id"], "platform": platform,
            "content_type": task["content_type"], "title_style": row["title_style"],
            "word_range": [row["word_min"], row["word_max"]], "tag_count": row["tag_count"],
            "cover_ratio": row["cover_ratio"], "titles": prep["titles"], "tags": prep["tags"],
            "cover": prep["cover"], "prompt_key": tpl.prompt_key, "prompt_version": tpl.version,
            "adapter_used": result.adapter_id, "model_version": result.model_version,
            "video_file": final["path"], "generated_at": dbm.now_iso()}
    json_path = out_dir / f"prep-{stamp}.json"
    md_path = out_dir / f"prep-{stamp}.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [f"# 发布准备 · {platform}", "",
                f"- 内容类型：{task['content_type']}｜建议字数：{row['word_min']}–{row['word_max']}",
                f"- 标签数量：{row['tag_count']}｜封面比例：{row['cover_ratio']}",
                f"- 成片：{final['path']}", "", "## 标题候选"]
    md_lines += [f"{i}. {title}" for i, title in enumerate(prep["titles"], 1)]
    md_lines += ["", "## 标签", "、".join(prep["tags"]), "", "## 封面文案", prep["cover"], "",
                 "## 下一步", "在关口③（发布授权）核对后由人工点击发布（C-08：自动流程只填不发）。"]
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    duration_ms = rec.elapsed_ms(started)
    step_id = rec.record_step(task["id"], SKILL_ID, "ok", step_no=args.step_no,
                              adapter_used=result.adapter_id,
                              input_json={"platform": platform, "tag_count": row["tag_count"]},
                              output_json={"json": rec.rel_path(json_path), "md": rec.rel_path(md_path),
                                           "titles": len(prep["titles"]), "tags": len(prep["tags"])},
                              duration_ms=duration_ms, path=args.db)
    art_id = rec.record_artifact(task["id"], "manifest", rec.rel_path(json_path), step_run_id=step_id,
                                 model_version=result.model_version or "mock-v1", prompt_version=tpl.version,
                                 meta={"role": "publish-prep", "platform": platform, "md": rec.rel_path(md_path),
                                       "cover_ratio": row["cover_ratio"], "tag_count": row["tag_count"]},
                                 path=args.db)
    rec.update_task(task["id"], stage="publish", path=args.db)

    out = {"task_id": task["id"], "topic_id": task["topic_id"], "skill": SKILL_ID, "platform": platform,
           "adapter_used": result.adapter_id, "prompt_version": tpl.version, "titles": prep["titles"],
           "tags": prep["tags"], "cover": prep["cover"], "json": rec.rel_path(json_path),
           "md": rec.rel_path(md_path), "artifact_id": art_id, "stage": "publish",
           "next": f"发布授权：python3 .dsh/skills/hitl-gate/run.py open --task-id {task['id']} "
                   f"--gate gate3_publish_auth"}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}｜平台 {platform}｜适配器 {out['adapter_used']}")
        for i, title in enumerate(out["titles"], 1):
            print(f"  标题{i}：{title}")
        print(f"  标签：{'、'.join(out['tags'])}｜封面：{out['cover']}")
        print("下一步：" + out["next"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发布准备：按平台模板生成标题、标签与封面文案")
    parser.add_argument("--db", default=None, help="数据库路径（默认 .env 的 DB_PATH）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare", help="生成发布准备信息")
    p_prepare.add_argument("--task-id", type=int, required=True)
    p_prepare.add_argument("--platform", default=None, help="平台名（默认取任务的 target_platform）")
    p_prepare.add_argument("--out", default=None, help="输出目录（默认 workspace/topic-<id>/publish/prep）")
    p_prepare.add_argument("--attempts", type=int, default=3, help="最多重试次数（自检不过就重来）")
    p_prepare.add_argument("--allow-paid", action="store_true", help="允许计费适配器（默认零付费，C-09）")
    p_prepare.add_argument("--step-no", type=int, default=None)
    p_prepare.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                           help="以 JSON 输出结果（也可写在子命令前）")
    p_prepare.set_defaults(func=cmd_prepare)

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
