#!/usr/bin/env python3
# 文件用途：人工关口（HITL）共享层 —— 三类关口（选定文案 / 剪辑干预 / 发布授权）的统一开启与决议落库。
# 对应需求：§8.3 三类 HITL 形态（选择 / 调整 / 授权）、R-L1-18（契约校验）、R-8-03（操作人字段）、C-08（发布红线）。
# 对应流程图：.archify/FLOW-COPY-20261012/copy-line.html（关口①）、FLOW-VIDEO-20261012（关口②）、FLOW-PUBLISH-20261012（关口③）
# 维护提示：新增关口形态请同步 docs/skill-roster.md 的 hitl-gate 条目与 db/README.md 的 hitl_events 枚举表。
"""人工关口共享层。

三类形态（与 §8.3 一致）：
  * 选择态  gate1_select_copy    —— 三套文案里挑一套（confirm 时必须给 plan_no）
  * 调整态  gate2_edit_video     —— 改顺序/时长/素材（用 action=adjust + diff_json）
  * 授权态  gate3_publish_auth   —— 停在发布前，人工点击发布（confirm 即授权已登录会话发出去）

硬规则：
  1. 未开启关口就不能决议（`tasks.status` 必须是 waiting_human），防止「没有等人确认就往下走」；
  2. 决议一律写入 hitl_events，带 snapshot_json（当时的待执行内容）与 diff_json（参数前后差异）；
  3. 关口不实现任何「自动通过」，任何 actor 为空都不允许（要能回答「谁点的」）。
"""

from __future__ import annotations

import json
from typing import Any

import db as dbm
import recording as rec

GATE1 = "gate1_select_copy"
GATE2 = "gate2_edit_video"
GATE3 = "gate3_publish_auth"
ACTIONS = {"confirm", "reject", "adjust"}


class HitlError(ValueError):
    """关口操作不合法。"""


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def open_gate(task_id: int, gate: str, *, note: str = "", path: str | None = None) -> dict[str, Any]:
    """开启关口：把任务置为 waiting_human（等人来处理），并把待确认内容写进日志备注。"""
    if gate not in rec.GATES:
        raise HitlError(f"未知关口：{gate}")
    rec.task_bundle(task_id, path)  # 任务必须存在
    rec.update_task(task_id, status="waiting_human", path=path)
    return {"task_id": task_id, "gate": gate, "status": "waiting_human", "note": note}


def resolve_gate(task_id: int, gate: str, action: str, actor: str, *, snapshot: Any = None,
                 diff: Any = None, plan_no: int | None = None, path: str | None = None) -> int:
    """决议关口：写 hitl_events 并按结果推进任务状态。返回事件 id。"""
    if gate not in rec.GATES:
        raise HitlError(f"未知关口：{gate}")
    if action not in ACTIONS:
        raise HitlError(f"action 只能是 {sorted(ACTIONS)}，收到 {action}")
    if not actor.strip():
        raise HitlError("必须写明 actor（谁做的决定，R-8-03）")
    bundle = rec.task_bundle(task_id, path)
    if bundle["task"]["status"] != "waiting_human":
        raise HitlError(f"任务当前状态是 {bundle['task']['status']}，不是 waiting_human：不能决议（先开启关口）")
    if gate == GATE1 and action == "confirm":
        if plan_no not in (1, 2, 3):
            raise HitlError("关口① 确认时必须给出 plan_no（1/2/3）")
        variant = dbm.query_one(
            "SELECT id FROM copy_variants WHERE task_id = ? AND plan_no = ? AND status = 'active'",
            (task_id, plan_no), path)
        if variant is None:
            raise HitlError(f"第 {plan_no} 套文案不存在或已失效：不能选定")
    event_id = dbm.execute(
        """INSERT INTO hitl_events (task_id, gate, actor, action, snapshot_json, diff_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task_id, gate, actor.strip(), action, _json(snapshot), _json(diff), dbm.now_iso()), path)
    if gate == GATE1 and action == "confirm":
        rec.update_task(task_id, selected_plan=plan_no, status="running", operator=actor.strip(), path=path)
    else:
        # 拒绝 / 调整：回到执行中，由编排者决定重生成还是继续
        rec.update_task(task_id, status="running", operator=actor.strip(), path=path)
    return event_id


def list_events(task_id: int, path: str | None = None) -> list[dict[str, Any]]:
    return dbm.query("SELECT * FROM hitl_events WHERE task_id = ? ORDER BY id", (task_id,), path)


def is_waiting(task_id: int, path: str | None = None) -> bool:
    task = dbm.query_one("SELECT status FROM tasks WHERE id = ?", (task_id,), path)
    return bool(task and task["status"] == "waiting_human")
