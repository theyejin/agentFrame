#!/usr/bin/env python3
# 文件用途：llm-adapter 的实现入口 —— 文本生成与任意 kind 的统一调用，含降级链演练、计费门禁与调用记录。
# 对应需求：R-L2-14/15/16/17（统一接口 + 适配器声明 + 失败自动降级并记录实际适配器）、C-09（零付费门禁）、R-7-03（记录模型版本）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（外部服务适配层）、.archify/FLOW-COPY-20261012/copy-line.html（llm-adapter）
# 维护提示：新增适配器改 templates/adapters/registry.json；本文件的命令行参数变化请同步 README.md 与 docs/directory-and-files.md。
"""llm-adapter 命令行入口。

    chains   [--kind K] [--json]                     看降级链（省略 kind 则看全部）
    adapters [--kind K] [--json]                     看适配器登记明细
    generate --prompt-key K --var k=v ... [--out P]  渲染提示词并生成文本
    call     --kind K [--payload-json J] [--out P]   以统一接口调用任意 kind（演练用）

通用参数：--allow-paid（显式批准计费调用，C-09）、--json（机器可读输出）、--dry-run（只看会走哪条链，不真调用）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "_shared"
sys.path.insert(0, str(SHARED))

import adapter_runtime as ar  # noqa: E402
import prompt_templates as pt  # noqa: E402


def _parse_vars(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise SystemExit(f"--var 需要 k=v 形式，收到：{item}")
        key, _, value = item.partition("=")
        out[key.strip()] = value
    return out


def cmd_chains(args: argparse.Namespace) -> int:
    kinds = [args.kind] if args.kind else sorted({a["kind"] for a in ar.adapters()})
    payload = {k: ar.describe_chain(k) for k in kinds}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for kind in kinds:
        print(f"[{kind}] 降级链（数字小的先试）：")
        for row in payload[kind]:
            flags = []
            flags.append("需密钥" if row["needs_key"] else "免密钥")
            flags.append("计费" if row["billable"] else "免费")
            flags.append("已接入" if row["implemented"] else "未接入")
            print(f"  {row['order']}. {row['adapter_id']:<22} {row['provider']:<24} {' / '.join(flags)}")
            print(f"      能力：{row['capabilities']}")
            if row["failure_signals"]:
                print(f"      换它的情况：{row['failure_signals']}")
    return 0


def cmd_adapters(args: argparse.Namespace) -> int:
    rows = [a for a in ar.adapters() if not args.kind or a["kind"] == args.kind]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"共 {len(rows)} 条适配器声明（templates/adapters/registry.json）：")
    for a in rows:
        print(f"  {a['adapter_id']:<22} kind={a['kind']:<8} order={a['fallback_order']} "
              f"billable={'Y' if a['billable'] else 'N'} implemented={'Y' if a['implemented'] else 'N'}  {a['provider']}")
    print(f"\n成本上限（LLM_COST_LIMIT）：{ar.cost_limit()} 元/次；默认零付费（C-09）")
    return 0


def _finish(result: "ar.InvocationResult", out: str | None, as_json: bool) -> int:
    if out and result.ok and not result.needs_human:
        text = result.output.get("text") or json.dumps(result.output, ensure_ascii=False, indent=2)
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        result.output["saved_to"] = str(target)
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"[适配器] {result.adapter_id or '（无）'}  模型版本={result.model_version or '（无）'}")
        for attempt in result.attempts:
            print(f"  - 尝试 {attempt['adapter_id']}：{attempt['status']}（{attempt['detail']}）")
        if result.needs_human:
            print(f"[转人工] {result.output.get('handoff', '需要人工处理')}")
        elif result.ok:
            text = result.output.get("text", "")
            print("[输出]" + ("（已落盘）" if out else "："))
            if not out:
                print(text)
        else:
            print(f"[失败] {result.error}", file=sys.stderr)
    return 0 if result.ok else 1


def cmd_generate(args: argparse.Namespace) -> int:
    tpl = pt.load(args.prompt_key)
    values = _parse_vars(args.var)
    try:
        prompt = tpl.render(values)
    except pt.MissingVariable as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    payload = {
        "prompt": prompt,
        "prompt_key": tpl.prompt_key,
        "prompt_version": tpl.version,
        "topic_title": values.get("topic_title", ""),
        "plan_count": int(values.get("plan_count", args.plan_count)),
        "focuses": (values.get("focus_list") or args.focus or "").split("、") if (values.get("focus_list") or args.focus) else None,
    }
    if args.dry_run:
        chain = ar.chain("llm")
        print("[演练] 会按此顺序尝试：" + " → ".join(a["adapter_id"] for a in chain))
        return 0
    result = ar.invoke("llm", payload, allow_paid=args.allow_paid)
    result.output.setdefault("prompt_key", tpl.prompt_key)
    result.output.setdefault("prompt_version", tpl.version)
    return _finish(result, args.out, args.json)


def cmd_call(args: argparse.Namespace) -> int:
    payload = json.loads(args.payload_json) if args.payload_json else {}
    if args.dry_run:
        chain = ar.chain(args.kind)
        print("[演练] 会按此顺序尝试：" + " → ".join(a["adapter_id"] for a in chain))
        return 0
    result = ar.invoke(args.kind, payload, allow_paid=args.allow_paid)
    return _finish(result, args.out, args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="外部服务统一入口：降级链、计费门禁、调用记录")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func, help_text in (("chains", cmd_chains, "查看降级链（别名 chain）"),
                                  ("chain", cmd_chains, "chains 的别名"),
                                  ("adapters", cmd_adapters, "查看适配器登记明细")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--kind")
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=func)

    p = sub.add_parser("generate", help="渲染提示词并生成文本")
    p.add_argument("--prompt-key", required=True)
    p.add_argument("--var", action="append", default=[])
    p.add_argument("--out")
    p.add_argument("--plan-count", type=int, default=3)
    p.add_argument("--focus")
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("call", help="以统一接口调用任意 kind")
    p.add_argument("--kind", required=True)
    p.add_argument("--payload-json", default="")
    p.add_argument("--out")
    p.add_argument("--allow-paid", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_call)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
