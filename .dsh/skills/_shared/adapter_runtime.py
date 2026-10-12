#!/usr/bin/env python3
# 文件用途：共享库 —— 适配器运行时：读 templates/adapters/registry.json，按 kind 组降级链并按顺序尝试，落实零付费门禁与失败降级。
# 对应需求：R-L2-14（业务代码不认服务名）/ R-L2-15（统一接口 generate_images / image_to_video 等）/ R-L2-16（能力·密钥·计费·失败特征·降级顺序）/ R-L2-17（失败自动降级并记录实际适配器）、C-09（零付费门禁）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（外部服务适配层：可替换 / 可降级）
# 维护提示：新增适配器只改 templates/adapters/registry.json 并跑 python3 scripts/seed_adapters.py；统一接口若有变化，必须同步 docs/skill-roster.md、docs/directory-and-files.md 与相关 skill 的 README。
"""适配器运行时。

统一接口（R-L2-15）：
    invoke("llm",   {"prompt": "...", ...})                 -> InvocationResult
    invoke("image", {"prompt": "...", "count": 3, "size": "..."} )
    invoke("split", {"grid_path": "...", "rows": 6, "cols": 4})
    invoke("video", {"images": [...], "audio": "..."} )
    invoke("browser", {"publish_package": {...}})
    invoke("doc",   {"title": "...", "table": [...]})
    invoke("metrics", {"platform": "...", "period": "..."})

调用方永远只传 kind 与业务参数，不出现具体服务名 —— 换服务只改 registry.json（R-L2-14）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from env_file import REPO_ROOT, get, load_env

REGISTRY_PATH = REPO_ROOT / "templates" / "adapters" / "registry.json"

# 每次尝试的结果状态
STATUS_OK = "ok"
STATUS_MISSING_KEY = "missing_key"                 # 缺密钥，换下一个
STATUS_BILLABLE_SKIPPED = "skipped_needs_approval"  # 计费适配器未被批准（C-09）
STATUS_COST_LIMIT = "cost_limit_exceeded"           # 超出成本上限（C-09）
STATUS_NOT_IMPLEMENTED = "not_implemented"          # 本版还没接（诚实登记，不假装成功）
STATUS_HUMAN_REQUIRED = "human_required"            # 降级到人工（流程终点，不是错误）
STATUS_FAILED = "failed"                            # 调用失败，按失败特征换下一个

# 哪些状态算「流程可以继续」：人工兜底也是合规终点
TERMINAL_OK = {STATUS_OK, STATUS_HUMAN_REQUIRED}


# ---------------------------------------------------------------------------
# 登记表读取
# ---------------------------------------------------------------------------
def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    """读 registry.json 原始字典。"""
    target = Path(path) if path else REGISTRY_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def adapters(registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """返回全部适配器声明（默认读仓库内 registry.json）。"""
    return list((registry or load_registry())["adapters"])


def chain(kind: str, registry: dict[str, Any] | None = None, only_enabled: bool = True) -> list[dict[str, Any]]:
    """按 fallback_order 升序返回某个 kind 的降级链（R-L2-17）。"""
    pool = [a for a in adapters(registry) if a["kind"] == kind]
    if only_enabled:
        pool = [a for a in pool if a.get("enabled", True)]
    return sorted(pool, key=lambda a: (a["fallback_order"], a["adapter_id"]))


def find(adapter_id: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """按 adapter_id 取一条声明。"""
    for a in adapters(registry):
        if a["adapter_id"] == adapter_id:
            return a
    raise KeyError(f"registry.json 中没有适配器：{adapter_id}")


# ---------------------------------------------------------------------------
# 已实现的具体调用（业务代码通过 kind 走这里，不直接引用）
# ---------------------------------------------------------------------------
MOCK_DIR = REPO_ROOT / "templates" / "mock"


def _mock_fixture(payload: dict[str, Any]) -> str | None:
    """取离线样例：templates/mock/<prompt_key>.<prompt_version>.txt。

    有样例文件时优先返回它 —— 这样模拟测试与演练拿到的结构与真实模型一致（文案 3 套、分镜 24 条）。
    """
    key = payload.get("prompt_key")
    version = payload.get("prompt_version")
    if not key or not version:
        return None
    path = MOCK_DIR / f"{key}.{version}.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _runtime_mock(adapter: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """离线假模型：不回网络，返回固定样例或按输入确定性地造一段可辨识的假文案。"""
    prompt = str(payload.get("prompt", ""))
    if "MOCK_FAIL" in prompt:  # 测试用的失败开关
        raise RuntimeError("MOCK_FAIL：模拟适配器故障")
    fixture = _mock_fixture(payload)
    if fixture is not None:
        return {
            "output": {"text": fixture, "fixture": f"{payload['prompt_key']}.{payload['prompt_version']}"},
            "model_version": adapter.get("settings", {}).get("model", "mock-v1"),
        }
    plan_count = int(payload.get("plan_count", 3))
    focuses = payload.get("focuses") or ["开头钩子", "情绪强度", "行动号召"]
    lines: list[str] = ["【模拟输出 · 未调用任何外部服务】"]
    for i in range(plan_count):
        focus = focuses[i % len(focuses)]
        lines += [f"方案{i + 1}（侧重：{focus}）", f"[模拟文案] 选题={payload.get('topic_title', '未命名')} 第{i + 1}套，侧重{focus}。"]
    return {
        "output": {"text": "\n".join(lines), "plan_count": plan_count},
        "model_version": adapter.get("settings", {}).get("model", "mock-v1"),
    }


def _runtime_openai_compatible(adapter: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """OpenAI 兼容接口（DeepSeek 等）。只在这里出现具体协议，业务代码看不到网址。"""
    settings = adapter.get("settings", {})
    base_url = get(settings.get("base_url_env", "LLM_BASE_URL"), settings.get("default_base_url", ""))
    model = get(settings.get("model_env", "LLM_MODEL"), settings.get("default_model", ""))
    api_key = get(settings.get("api_key_env", "LLM_API_KEY"))
    if not api_key:
        raise MissingKey("缺少密钥 LLM_API_KEY（C-05：密钥只放 .env）")
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": payload.get("system", "你是严谨的中文内容助手。")},
                {"role": "user", "content": payload.get("prompt", "")},
            ],
            "temperature": float(payload.get("temperature", 0.7)),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(payload.get("timeout", 60))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # 401/429 等：交给降级链
        raise RuntimeError(f"HTTP {exc.code}：{exc.read().decode('utf-8', 'ignore')[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络不可达：{exc.reason}") from exc
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})
    return {"output": {"text": text, "usage": usage}, "model_version": data.get("model", model)}


def _runtime_local_export(adapter: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """本地导出（飞书不可用时的兜底，Q-5）：把内容写成文件，返回路径。"""
    # 落点二选一：abs_path（绝对路径，测试与临时导出用）优先，否则按仓库根 + rel_path
    abs_path = payload.get("abs_path")
    rel = payload.get("rel_path") or "workspace/exports/export.md"
    target = Path(abs_path) if abs_path else (REPO_ROOT / rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(payload.get("content", "")), encoding="utf-8")
    shown = str(target) if abs_path else rel
    return {"output": {"path": shown, "bytes": target.stat().st_size}, "model_version": "local-export-v1"}


def _runtime_human(adapter: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """人工兜底：不是错误，而是把球交回运营人员（HITL）。"""
    return {
        "output": {"handoff": payload.get("handoff", "请运营人员人工完成此步")},
        "model_version": "human",
        "needs_human": True,
    }


def _runtime_image_placeholder(adapter: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """本地占位整图（离线终点，不是可发布素材）：按行列画格并标出分镜号。

    用途：① 让视觉线在没有任何外部生图服务时也能端到端跑通与测试；② 给运营人员一张
    「该放什么图」的版式参考。真实出图仍应优先走前面的 image.flow / image.doubao / image.comfyui。
    """
    import images as im

    cell_w = int(payload.get("cell_w", 320))
    cell_h = int(payload.get("cell_h", 320))
    labels = payload.get("labels") or []
    title = payload.get("title", "")
    paths = payload.get("paths") or []          # 多张（参考图）：每个路径一张单格图
    if paths:
        made = []
        for i, one in enumerate(paths, start=1):
            info = im.make_placeholder_grid(one, 1, 1, cell_w, cell_h,
                                            [labels[i - 1]] if i <= len(labels) else [],
                                            title if i == 1 else "")
            info["placeholder"] = True
            made.append(info)
        return {"output": {"images": made, "count": len(made)}, "model_version": "placeholder-v1"}
    out_path = payload.get("abs_path") or payload.get("out_path")
    if not out_path:
        rel = payload.get("rel_path") or "workspace/exports/placeholder-grid.png"
        out_path = REPO_ROOT / rel
    cols = int(payload.get("cols", 6))
    rows = int(payload.get("rows", 4))
    info = im.make_placeholder_grid(out_path, cols, rows, cell_w, cell_h, labels, title)
    info["placeholder"] = True
    return {"output": info, "model_version": "placeholder-v1"}


def _runtime_grid_slicer(adapter: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """本地网格切分：把一张整图按 6×4 等分成 24 张独立图（离线终点，无需任何外部服务）。"""
    import images as im

    src = payload.get("abs_src") or payload.get("grid_path") or payload.get("src")
    if not src:
        raise RuntimeError("grid_slicer 需要整图路径：abs_src / grid_path / src 三者任一")
    out_dir = payload.get("abs_out_dir") or payload.get("out_dir") or (REPO_ROOT / "workspace" / "exports" / "shots")
    shots = im.slice_grid(src, int(payload.get("cols", 6)), int(payload.get("rows", 4)), out_dir,
                          prefix=payload.get("prefix", "shot"), ext=payload.get("ext", ".png"),
                          start_no=int(payload.get("start_no", 1)))
    sizes = sorted({(s["width"], s["height"]) for s in shots})
    if len(sizes) != 1:
        raise RuntimeError(f"切分结果尺寸不一致：{sizes}")
    return {"output": {"shots": shots, "count": len(shots), "cell_size": {"w": sizes[0][0], "h": sizes[0][1]}},
            "model_version": "grid-slicer-v1"}


class MissingKey(RuntimeError):
    """缺密钥 —— 与「调用失败」区分开，便于运营人员快速定位。"""


RUNTIMES: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "mock": _runtime_mock,
    "openai_compatible": _runtime_openai_compatible,
    "local_export": _runtime_local_export,
    "human": _runtime_human,
    "image_placeholder": _runtime_image_placeholder,
    "grid_slicer": _runtime_grid_slicer,
}


def runtime_of(adapter: dict[str, Any]) -> Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None:
    """取某个适配器的运行时实现；没有实现返回 None（代表本版还没接）。"""
    name = adapter.get("settings", {}).get("runtime")
    return RUNTIMES.get(name) if name else None


# ---------------------------------------------------------------------------
# 调用入口
# ---------------------------------------------------------------------------
@dataclass
class InvocationResult:
    """一次调用（含降级尝试）的完整结果 —— 调用方据此登记 step_runs.adapter_used 与 artifacts。"""

    kind: str
    ok: bool
    adapter_id: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    model_version: str = ""
    needs_human: bool = False
    error: str = ""
    attempts: list[dict[str, Any]] = field(default_factory=list)
    billable_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "ok": self.ok,
            "adapter_id": self.adapter_id,
            "output": self.output,
            "model_version": self.model_version,
            "needs_human": self.needs_human,
            "error": self.error,
            "attempts": self.attempts,
            "billable_used": self.billable_used,
        }


def cost_limit() -> float:
    """成本上限（元）；未配置视为 0，即不允许任何计费调用（C-09 默认零付费）。"""
    raw = get("LLM_COST_LIMIT") or get("COST_LIMIT")
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def invoke(
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    registry: dict[str, Any] | None = None,
    allow_paid: bool = False,
) -> InvocationResult:
    """按降级链调用某个 kind 的服务。

    规则（顺序即优先级）：
      1. 未启用 → 跳过；
      2. 计费且未获批准 → skipped_needs_approval（C-09 默认零付费）；
      3. 计费且已批准但超出成本上限 → cost_limit_exceeded，并停止再尝试计费适配器；
      4. 需要密钥但没有 → missing_key，换下一个；
      5. 本版还没实现 → not_implemented，换下一个；
      6. 调用抛错 → failed（记录失败特征），换下一个；
      7. 成功 → ok；降到人工兜底 → human_required（也算流程可继续）。
    """
    load_env()
    payload = payload or {}
    result = InvocationResult(kind=kind, ok=False)
    limit = cost_limit()
    paid_blocked = False

    for adapter in chain(kind, registry):
        aid = adapter["adapter_id"]
        if adapter.get("billable"):
            if not allow_paid:
                result.attempts.append({"adapter_id": aid, "status": STATUS_BILLABLE_SKIPPED,
                                        "detail": "计费适配器需显式 --allow-paid 批准（C-09）"})
                continue
            if paid_blocked or float(adapter.get("cost_per_call", 0.0)) > limit:
                paid_blocked = True
                result.attempts.append({"adapter_id": aid, "status": STATUS_COST_LIMIT,
                                        "detail": f"单次预估 {adapter.get('cost_per_call', 0.0)} 元 > 上限 {limit} 元（C-09）"})
                continue
        impl = runtime_of(adapter) if adapter.get("implemented") else None
        if impl is None:
            result.attempts.append({"adapter_id": aid, "status": STATUS_NOT_IMPLEMENTED,
                                    "detail": "本版尚未接入，按降级链继续"})
            continue
        try:
            out = impl(adapter, payload)
        except MissingKey as exc:
            result.attempts.append({"adapter_id": aid, "status": STATUS_MISSING_KEY, "detail": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001 —— 失败一律降级，不让整条流程崩掉
            result.attempts.append({"adapter_id": aid, "status": STATUS_FAILED, "detail": f"{type(exc).__name__}: {exc}"})
            continue
        result.adapter_id = aid
        result.output = out.get("output", {})
        result.model_version = out.get("model_version", "")
        result.needs_human = bool(out.get("needs_human"))
        result.billable_used = bool(adapter.get("billable"))
        result.ok = True
        result.attempts.append({"adapter_id": aid, "status": STATUS_OK, "detail": "调用成功"})
        return result

    # 全部走完：给出可读原因，方便运营人员判断该动哪一环
    reasons = "；".join(f"{a['adapter_id']}={a['status']}" for a in result.attempts) or f"kind={kind} 没有任何可用适配器"
    result.error = f"降级链全部未成功：{reasons}"
    return result


def describe_chain(kind: str, registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """输出某 kind 的降级链说明（给运营人员与文档看）。"""
    rows = []
    for a in chain(kind, registry):
        rows.append({
            "order": a["fallback_order"],
            "adapter_id": a["adapter_id"],
            "provider": a["provider"],
            "needs_key": bool(a.get("needs_key")),
            "billable": bool(a.get("billable")),
            "implemented": bool(a.get("implemented")),
            "capabilities": a.get("capabilities", ""),
            "failure_signals": a.get("failure_signals", ""),
        })
    return rows
