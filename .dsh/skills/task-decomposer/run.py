#!/usr/bin/env python3
# 文件用途：task-decomposer 的实现入口 —— 把运营输入变成一条任务，并生成「派给谁、怎么起手、怎么算完」的派单书。
# 对应需求：R-L1-05（Agent 定义）/ R-L1-18（交接契约由运行时校验）/ §5.2.1（编排者不写文件，派单书由 Skill 落盘）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html
# 维护提示：派单契约的单一事实源是 agents/orchestrator/config.yml；本文件只读不写它。
"""task-decomposer 命令行入口。

    dispatch --title "选题" --platform 抖音 [--content-type 情绪冲突] [--word-min N --word-max N]
             [--topic-id N] [--source manual|hotspot] [--keywords 关键词] [--prompt 对话输入]
             [--priority 1|2|3] [--operator 姓名] [--out-dir DIR] [--json]
    plan     --task-id N [--json]          按任务当前环节给「下一步找谁 + 起手命令」（只读）
    agents   [--json]                      列出五个 Agent 与各自可派单 Skill（并检查目录是否存在）

派单书落 workspace/topic-<选题号>/plan/dispatch-<时间戳>.{json,md}，并登记 kind=manifest / meta.role=dispatch。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import db as dbm  # noqa: E402
import recording as rec  # noqa: E402
import yaml  # noqa: E402

CONFIG_PATH = dbm.REPO_ROOT / "agents" / "orchestrator" / "config.yml"
SKILLS_DIR = dbm.REPO_ROOT / ".dsh" / "skills"
CONTENT_TYPES = ("情绪冲突", "干货教程", "热点观点", "其他")
# 每个环节的起手 Skill 与子命令（config.yml 只声明 skill 白名单，入口固定在这里）
ENTRY = {
    "copy-agent": ("copy-writer", "generate"),
    "visual-agent": ("reference-image-builder", "build"),
    "video-agent": ("asset-packager", "pack"),
    "publish-agent": ("browser-publisher", "prepare"),
}


class InputError(ValueError):
    """输入校验不通过（没平台、字数区间反了、任务不存在等）。"""


# ---------------------------------------------------------------------------
# config.yml：读取与契约自检（R-L1-18）
# ---------------------------------------------------------------------------

def load_config(path: str | None = None) -> dict:
    cfg_path = Path(path) if path else CONFIG_PATH
    if not cfg_path.is_file():
        raise InputError(f"编排者配置不存在：{cfg_path}（agents/orchestrator/config.yml 是派单的单一事实源）")
    with cfg_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if not cfg.get("agents"):
        raise InputError(f"编排者配置里没有 agents 段：{cfg_path}")
    return cfg


def check_contract(cfg: dict) -> list[str]:
    """自检五个 Agent 的定义是否可用：交接契约三段齐、声明的 Skill 目录都在。"""
    problems: list[str] = []
    agents = cfg.get("agents") or []
    seen = {a.get("agent_id") for a in agents}
    for required in ("copy-agent", "visual-agent", "video-agent", "publish-agent"):
        if required not in seen:
            problems.append(f"config.yml 缺环节 Agent：{required}")
    for agent in agents:
        aid = agent.get("agent_id", "?")
        handoff = agent.get("handoff") or {}
        for key in ("input_check", "outputs", "done"):
            if not handoff.get(key):
                problems.append(f"{aid} 的交接契约缺 {key}（R-L1-18 要求三段齐）")
        for skill_id in agent.get("skills") or []:
            if not (SKILLS_DIR / str(skill_id)).is_dir():
                problems.append(f"{aid} 声明的 Skill 目录不存在：.dsh/skills/{skill_id}")
        if not agent.get("entry_stage") or not agent.get("exit_stage"):
            problems.append(f"{aid} 缺 entry_stage / exit_stage")
    routing = cfg.get("stage_routing") or {}
    for stage, aid in routing.items():
        if aid != "orchestrator" and aid not in seen:
            problems.append(f"stage_routing[{stage}] 指向未定义的 Agent：{aid}")
    return problems


def find_agent(cfg: dict, agent_id: str) -> dict:
    for agent in cfg.get("agents") or []:
        if agent.get("agent_id") == agent_id:
            return agent
    raise InputError(f"config.yml 里没有 Agent：{agent_id}")


def route(cfg: dict, stage: str) -> str:
    routing = cfg.get("stage_routing") or {}
    if stage not in routing:
        raise InputError(f"任务环节 {stage} 没有派单路由（config.yml 的 stage_routing）")
    return str(routing[stage])


def entry_command(agent_id: str, task_id: int) -> tuple[str, str]:
    if agent_id not in ENTRY:
        return ("", "(该环节由编排者收尾，不再派单)")
    skill_id, sub = ENTRY[agent_id]
    return (skill_id, f"python3 .dsh/skills/{skill_id}/run.py {sub} --task-id {task_id} --json")


def platforms(path: str | None = None) -> list[dict]:
    return dbm.query("SELECT * FROM platform_templates ORDER BY id", (), path)


# ---------------------------------------------------------------------------
# dispatch：建话题 + 建任务 + 出派单书
# ---------------------------------------------------------------------------

def cmd_dispatch(args: argparse.Namespace) -> int:
    cfg = load_config()
    problems = check_contract(cfg)
    if problems:
        raise InputError("派单前自检不通过：\n  - " + "\n  - ".join(problems))

    rows = platforms(args.db)
    if not rows:
        raise InputError("platform_templates 是空的，先跑 scripts/seed_platforms.py（或 db_init）")
    names = [r["platform"] for r in rows]
    if args.platform not in names:
        raise InputError(f"平台不存在：{args.platform}（已配置：{'、'.join(names)}）")
    tpl = next(r for r in rows if r["platform"] == args.platform)

    word_min = args.word_min if args.word_min is not None else int(tpl["word_min"])
    word_max = args.word_max if args.word_max is not None else int(tpl["word_max"])
    if not (100 <= word_min <= word_max <= 2000):
        raise InputError(f"字数区间不合法：{word_min}~{word_max}（要求 100 <= min <= max <= 2000）")

    if args.topic_id:
        topic = dbm.query_one("SELECT * FROM topics WHERE id = ?", (args.topic_id,), args.db)
        if not topic:
            raise InputError(f"话题不存在：topic_id={args.topic_id}")
        topic_id = int(topic["id"])
        topic_title = topic["title"]
    else:
        if not (args.title or "").strip():
            raise InputError("新建选题必须给 --title（或用 --topic-id 复用已有话题）")
        topic_id = rec.create_topic(args.title.strip(), source=args.source, keywords=args.keywords,
                                    summary=args.summary, created_by=args.created_by, path=args.db)
        topic_title = args.title.strip()

    task_id = rec.create_task(topic_id, stage=args.stage, content_type=args.content_type,
                              target_platform=args.platform, prompt=args.prompt,
                              word_min=word_min, word_max=word_max,
                              priority=args.priority, operator=args.operator, path=args.db)

    agent_id = route(cfg, args.stage)
    agent = find_agent(cfg, agent_id)
    skill_id, command = entry_command(agent_id, task_id)
    handoff = agent.get("handoff") or {}

    out_dir = Path(args.out_dir) if args.out_dir else rec.workspace_dir(topic_id, "plan", path=args.db)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = rec.unique_stamp(out_dir, "dispatch")
    book = {
        "dispatch_id": stamp,
        "task_id": task_id, "topic_id": topic_id, "topic_title": topic_title,
        "platform": args.platform, "content_type": args.content_type,
        "word_range": [word_min, word_max], "priority": args.priority,
        "stage": args.stage, "status": "pending",
        "agent_id": agent_id, "agent_name": agent.get("name", agent_id),
        "entry_skill": skill_id, "entry_command": command,
        "gates": agent.get("gates") or [],
        "skills": agent.get("skills") or [],
        "contract": {"input_check": handoff.get("input_check") or [],
                     "outputs": handoff.get("outputs") or [],
                     "done": handoff.get("done") or []},
        "agent_flow": agent.get("flow", ""),
    }

    lines = [f"# 派单书 —— 任务 {task_id}（{topic_title}）", "",
             f"- 派单号：{stamp}", f"- 平台：{args.platform}　内容类型：{args.content_type}　"
             f"字数：{word_min}~{word_max}　优先级：{args.priority}",
             f"- 找谁：**{book['agent_name']}**（`{agent_id}`，{args.stage} → {agent.get('exit_stage')}）",
             f"- 起手命令：`{command}`", f"- 涉及的关口：{'、'.join(book['gates']) or '无'}（必须真人拍板）", ""]
    for title, key in (("进场校验（不通过退回编排者）", "input_check"),
                       ("产出物清单", "outputs"), ("完成判据", "done")):
        lines.append(f"## {title}")
        lines += [f"{i}. {item}" for i, item in enumerate(book["contract"][key], 1)]
        lines.append("")
    lines += ["## 该环节可派单的 Skill", "、".join(f"`{s}`" for s in book["skills"]), "",
              "## 改任务后怎么再要一份", f"`python3 .dsh/skills/task-decomposer/run.py plan --task-id {task_id}`", ""]

    json_path = out_dir / f"dispatch-{stamp}.json"
    md_path = out_dir / f"dispatch-{stamp}.md"
    json_path.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    files = [rec.rel_path(json_path), rec.rel_path(md_path)]

    step_id = rec.record_step(task_id, "task-decomposer", "ok", step_no=args.step_no,
                              input_json={"topic_id": topic_id, "platform": args.platform},
                              output_json={"agent_id": agent_id, "dispatch_id": stamp}, path=args.db)
    rec.record_artifact(task_id, "manifest", files[0], step_run_id=step_id, model_version="task-decomposer-v1",
                        prompt_version="none", meta={"role": "dispatch", "agent_id": agent_id, "dispatch_id": stamp,
                              "files": files, "md": files[1]}, path=args.db)

    info = dict(book, dispatch_json=files[0], dispatch_md=files[1],
                next=f"把派单书交给 {book['agent_name']}：{command}")
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"[完成] 任务 {task_id} 已派单给 {book['agent_name']}（派单号 {stamp}）")
        print(f"  话题：{topic_title}（topic_id={topic_id}）")
        print(f"  起手命令：{command}")
        print(f"  派单书：{files[1]}")
        print(f"  下一步：{info['next']}")
    return 0


# ---------------------------------------------------------------------------
# plan / agents：只读查询
# ---------------------------------------------------------------------------

def cmd_plan(args: argparse.Namespace) -> int:
    cfg = load_config()
    bundle = rec.task_bundle(args.task_id, path=args.db)
    task, topic = bundle["task"], bundle["topic"]
    agent_id = route(cfg, task["stage"])
    agent = find_agent(cfg, agent_id) if agent_id != "orchestrator" else {"name": "编排者", "skills": [], "gates": []}
    skill_id, command = entry_command(agent_id, task["id"])
    dispatch = rec.latest_artifact(task["id"], "manifest", role="dispatch", path=args.db)
    info = {
        "task_id": task["id"], "topic_id": task["topic_id"], "topic_title": topic.get("title", ""),
        "stage": task["stage"], "status": task["status"], "platform": task["target_platform"],
        "agent_id": agent_id, "agent_name": agent.get("name", agent_id),
        "entry_skill": skill_id, "entry_command": command,
        "contract": (agent.get("handoff") or {}), "gates": agent.get("gates") or [],
        "dispatch_book": (dispatch or {}).get("path", ""),
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"任务 {task['id']}（{topic.get('title', '')}）　环节：{task['stage']}　状态：{task['status']}")
        print(f"  找谁：{info['agent_name']}（{agent_id}）")
        print(f"  起手命令：{command or '（编排者收尾）'}")
        print(f"  关口：{'、'.join(info['gates']) or '无'}")
        print(f"  派单书：{info['dispatch_book'] or '（还没出过派单书）'}")
    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    cfg = load_config()
    listed = []
    for agent in cfg.get("agents") or []:
        skills = list(agent.get("skills") or [])
        listed.append({
            "agent_id": agent.get("agent_id"), "name": agent.get("name", ""),
            "entry_stage": agent.get("entry_stage"), "exit_stage": agent.get("exit_stage"),
            "gates": agent.get("gates") or [], "skills": skills,
            "skills_missing": [s for s in skills if not (SKILLS_DIR / s).is_dir()],
            "flow": agent.get("flow", ""),
        })
    orch = cfg.get("orchestrator") or {}
    info = {"orchestrator": {"agent_id": orch.get("agent_id", "orchestrator"),
                             "tools": orch.get("tools") or [], "max_parallel": orch.get("max_parallel")},
            "human_gates": cfg.get("human_gates") or [], "agents": listed,
            "config_path": rec.rel_path(CONFIG_PATH), "problems": check_contract(cfg)}
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"编排者：{info['orchestrator']['agent_id']}（工具：{'、'.join(info['orchestrator']['tools'])}）")
        print(f"人工关口（{len(info['human_gates'])} 个）：{'、'.join(info['human_gates'])}")
        for a in listed:
            mark = "✅" if not a["skills_missing"] else f"⚠️ 缺 {len(a['skills_missing'])}"
            print(f"  - {a['name']}（{a['agent_id']}）：{a['entry_stage']} → {a['exit_stage']}，"
                  f"{len(a['skills'])} 个 Skill {mark}")
        if info["problems"]:
            print("[自检问题]")
            for p in info["problems"]:
                print(f"  - {p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="task-decomposer", description="派单员：建任务并把任务派给对应环节 Agent")
    p.add_argument("--db", default=None, help="数据库路径（缺省读 .env 的 DB_PATH）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("dispatch", help="建话题 + 建任务 + 出派单书")
    s.add_argument("--title", default="", help="选题标题（新建话题时必填）")
    s.add_argument("--topic-id", type=int, default=None, help="复用已有话题（给了就不新建）")
    s.add_argument("--platform", required=True, help="目标平台（必须在 platform_templates 内）")
    s.add_argument("--content-type", default="情绪冲突", choices=list(CONTENT_TYPES), help="内容类型")
    s.add_argument("--source", default="manual", choices=["manual", "hotspot"], help="话题来源")
    s.add_argument("--keywords", default="", help="话题关键词")
    s.add_argument("--summary", default="", help="话题摘要")
    s.add_argument("--created-by", default="", help="话题创建人")
    s.add_argument("--prompt", default="", help="对话框里的原始输入（喂给 copy-writer）")
    s.add_argument("--word-min", type=int, default=None, help="字数下限（缺省用平台模板）")
    s.add_argument("--word-max", type=int, default=None, help="字数上限（缺省用平台模板）")
    s.add_argument("--priority", type=int, default=2, choices=[1, 2, 3], help="优先级（1 最高）")
    s.add_argument("--operator", default="", help="接单的运营人员")
    s.add_argument("--stage", default="copy", help="入口环节（缺省 copy）")
    s.add_argument("--step-no", type=int, default=None, help="步骤号（缺省自动递增）")
    s.add_argument("--out-dir", default=None, help="派单书输出目录（缺省 workspace/topic-<选题号>/plan）")
    s.set_defaults(func=cmd_dispatch)

    s = sub.add_parser("plan", help="按任务当前环节给下一步（只读）")
    s.add_argument("--task-id", type=int, required=True, help="任务号")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("agents", help="列出五个 Agent 与各自可派单 Skill（只读）")
    s.set_defaults(func=cmd_agents)
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
    except (InputError, rec.RecordingError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    except dbm.sqlite3.Error as exc:
        print(f"[数据库错误] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
