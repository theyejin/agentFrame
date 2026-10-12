#!/usr/bin/env python3
# 文件用途：留痕共享层 —— 话题/任务/步骤流水/产物/人工关口的唯一写入实现，保证「一处写、处处一致」。
# 对应需求：§7 数据模型、R-7-01~05、R-L2-05（执行过程留痕）、R-L1-18（交接契约）、R-8-03（操作人字段）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（本地数据库与日志留痕）
# 维护提示：新增字段或改变写入口径时，必须同步 db/README.md 与 docs/directory-and-files.md；各 skill 只调用本层，不自己拼 SQL。
"""留痕共享层（唯一写入实现）。

设计理由（N008）：执行流程要求「每个 skill 结束都要登记产物与流水」。如果让每个 skill 自己写 SQL，
迟早出现某条线漏记 `model_version` 或漏记失败原因。所以把写入集中到本层：
  * `artifact-recorder` skill 是本层的命令行外壳（给人用、给运维补录用）；
  * 其它 skill 直接 import 本层函数 —— 这是「复用代码」而不是「skill 调 skill」（D-09）。

所有写入自动带 `created_at` / `updated_at`（ISO-8601 本地时区），口径与 db/README.md 第 5 节一致。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import db as dbm

# 需要计大小的产物类型（图片/视频缺大小会被触发器拦下，提前给出人话错误）
MEDIA_KINDS = {"image", "video", "audio"}
ARTIFACT_KINDS = {"copy", "storyboard", "image", "video", "audio", "manifest", "table", "report", "publish_package"}
GATES = {"gate1_select_copy", "gate2_edit_video", "gate3_publish_auth",
         "gate_visual_style", "gate_visual_fix"}   # 后两个是视觉线的人工关口（迁移 0002 加入）


class RecordingError(ValueError):
    """留痕参数不合法（提前拦下，避免撞数据库触发器）。"""


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def rel_path(path: str | Path) -> str:
    """把文件路径规范成「相对仓库根」的 POSIX 路径（artifacts.path 的存法）。"""
    p = Path(path)
    if not p.is_absolute():
        return p.as_posix()
    try:
        return p.resolve().relative_to(dbm.REPO_ROOT).as_posix()
    except ValueError:
        return p.resolve().as_posix()


def workspace_dir(topic_id: int, line: str, path: str | None = None) -> Path:
    """该选题某条线的产出目录：workspace/topic-<选题号>/<线名>（不存在则建）。"""
    p = dbm.REPO_ROOT / "workspace" / f"topic-{int(topic_id)}" / line
    p.mkdir(parents=True, exist_ok=True)
    return p


def timestamp_slug() -> str:
    """本次动作的时间戳（文件名用，形如 20261012T030707）。"""
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")


def unique_stamp(directory: Path, stem: str, ext: str = ".json") -> str:
    """同一秒内重复生成也不会互相覆盖：撞名就加 -2、-3 …（历史留痕不能丢）。"""
    base = timestamp_slug()
    slug, n = base, 1
    while (Path(directory) / f"{stem}-{slug}{ext}").exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def elapsed_ms(started_iso: str) -> int:
    """从 started_iso 到现在的毫秒数（步骤流水用）。"""
    try:
        started = datetime.fromisoformat(started_iso)
    except ValueError:
        return 0
    return max(0, int((datetime.now().astimezone() - started).total_seconds() * 1000))


def sha256_of(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def abs_path_of(rel: str) -> Path:
    """相对路径按仓库根解析；绝对路径原样返回。"""
    p = Path(rel)
    return p if p.is_absolute() else (dbm.REPO_ROOT / p)


# ---------------------------------------------------------------------------
# 话题与任务
# ---------------------------------------------------------------------------
def create_topic(title: str, *, source: str = "manual", keywords: str = "", summary: str = "",
                 created_by: str = "", path: str | None = None) -> int:
    if not title.strip():
        raise RecordingError("选题标题不能为空")
    if source not in {"manual", "hotspot"}:
        raise RecordingError(f"source 只能是 manual / hotspot，收到 {source}")
    now = dbm.now_iso()
    return dbm.execute(
        """INSERT INTO topics (title, source, keywords, summary, created_by, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'new', ?, ?)""",
        (title.strip(), source, keywords, summary, created_by, now, now), path,
    )


def create_task(topic_id: int, *, stage: str = "copy", content_type: str = "情绪冲突",
                target_platform: str = "", prompt: str = "", word_min: int = 300, word_max: int = 500,
                priority: int = 2, operator: str = "", path: str | None = None) -> int:
    if dbm.query_one("SELECT id FROM topics WHERE id = ?", (topic_id,), path) is None:
        raise RecordingError(f"话题不存在：topic_id={topic_id}")
    if word_min <= 0 or word_max <= 0:
        raise RecordingError("字数区间必须为正整数")
    if word_min > word_max:
        raise RecordingError(f"字数下限 {word_min} 不得大于上限 {word_max}（F-02）")
    now = dbm.now_iso()
    return dbm.execute(
        """INSERT INTO tasks (topic_id, stage, status, priority, target_platform, content_type, prompt,
                              word_min, word_max, operator, created_at, updated_at)
           VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (topic_id, stage, priority, target_platform, content_type, prompt, word_min, word_max,
         operator, now, now), path,
    )


def update_task(task_id: int, *, status: str | None = None, stage: str | None = None,
                selected_plan: int | None = None, operator: str | None = None,
                path: str | None = None) -> None:
    fields, values = [], []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if stage is not None:
        fields.append("stage = ?")
        values.append(stage)
    if selected_plan is not None:
        if selected_plan not in (1, 2, 3):
            raise RecordingError(f"选定套号只能是 1/2/3，收到 {selected_plan}")
        fields += ["selected_plan = ?", "selected_at = ?"]
        values += [selected_plan, dbm.now_iso()]
    if operator is not None:
        fields.append("operator = ?")
        values.append(operator)
    if not fields:
        return
    fields.append("updated_at = ?")
    values += [dbm.now_iso(), task_id]
    dbm.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values, path)


def task_bundle(task_id: int, path: str | None = None) -> dict[str, Any]:
    """任务 + 所属话题 + 进度视图，一次取全（各 skill 的「取任务」都用它）。"""
    task = dbm.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,), path)
    if task is None:
        raise RecordingError(f"任务不存在：task_id={task_id}")
    topic = dbm.query_one("SELECT * FROM topics WHERE id = ?", (task["topic_id"],), path) or {}
    progress = dbm.query_one("SELECT * FROM v_task_progress WHERE task_id = ?", (task_id,), path) or {}
    return {"task": task, "topic": topic, "progress": progress}


def current_storyboards(task_id: int, path: str | None = None) -> list[dict[str, Any]]:
    """取某任务当前的分镜列表（按 shot_no 升序）—— 视觉线的硬输入。"""
    return dbm.query("SELECT * FROM storyboards WHERE task_id = ? ORDER BY shot_no", (task_id,), path)


def selected_copy(task_id: int, path: str | None = None) -> dict[str, Any] | None:
    """取关口① 已选定的那套文案；没选定返回 None（视觉线必须靠它把关）。"""
    return dbm.query_one(
        """SELECT c.* FROM copy_variants c
             JOIN tasks t ON t.id = c.task_id AND t.selected_plan = c.plan_no
            WHERE c.task_id = ? AND c.status = 'active'""",
        (task_id,), path)


def _meta_of(row: dict[str, Any]) -> dict[str, Any]:
    """artifacts.meta_json 的安全解析（坏 JSON 当成空对象，不让留痕数据拖垮流水线）。"""
    try:
        return json.loads(row.get("meta_json") or "{}")
    except ValueError:
        return {}


def latest_artifact(task_id: int, kind: str, *, role: str = "", path_like: str = "",
                    path: str | None = None) -> dict[str, Any] | None:
    """取某任务最近一条某类产物。

    两种过滤方式：`role` 按 meta.role 判（推荐 —— 产物目录会被 `--out` 改掉，角色不会）；
    `path_like` 按路径关键字判（例如只要 images/grid 目录里的图）。
    """
    sql = "SELECT * FROM artifacts WHERE task_id = ? AND kind = ?"
    params: list[Any] = [task_id, kind]
    if path_like:
        sql += " AND path LIKE ?"
        params.append(f"%{path_like}%")
    sql += " ORDER BY id DESC"
    rows = dbm.query(sql, tuple(params), path)
    if role:
        for row in rows:
            if _meta_of(row).get("role") == role:
                return row
        return None
    return rows[0] if rows else None


def task_progress(task_id: int, path: str | None = None) -> dict[str, Any]:
    return dbm.query_one("SELECT * FROM v_task_progress WHERE task_id = ?", (task_id,), path) or {}


# ---------------------------------------------------------------------------
# 步骤流水与产物
# ---------------------------------------------------------------------------
def record_step(task_id: int, skill_id: str, status: str, *, step_no: int | None = None,
                adapter_used: str = "", input_json: Any = None, output_json: Any = None,
                error: str = "", duration_ms: int = 0, path: str | None = None) -> int:
    """登记一步执行流水。status=failed 必须给 error（与数据库触发器一致，提前报人话错误）。"""
    if status not in {"pending", "running", "ok", "failed", "skipped"}:
        raise RecordingError(f"step_runs.status 非法：{status}")
    if status == "failed" and not error.strip():
        raise RecordingError("status=failed 必须写明 error（否则无法回答「为什么失败」）")
    if step_no is None:
        last = dbm.query_one("SELECT COALESCE(MAX(step_no), 0) AS n FROM step_runs WHERE task_id = ?", (task_id,), path)
        step_no = int(last["n"]) + 1
    now = dbm.now_iso()
    return dbm.execute(
        """INSERT INTO step_runs (task_id, step_no, skill_id, status, adapter_used, input_json, output_json,
                                  error, started_at, ended_at, duration_ms, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, step_no, skill_id, status, adapter_used, _json(input_json), _json(output_json),
         error, now, now, duration_ms, now), path,
    )


def record_artifact(task_id: int, kind: str, artifact_path: str, *, step_run_id: int | None = None,
                    model_version: str = "", prompt_version: str = "", meta: Any = None,
                    path: str | None = None) -> int:
    """登记产物。路径相对仓库根；大文件只记路径 + 大小 + 指纹（R-7-01）。"""
    if kind not in ARTIFACT_KINDS:
        raise RecordingError(f"artifacts.kind 非法：{kind}")
    if not model_version:
        raise RecordingError("产物必须记 model_version（R-7-03；人工产物填 human）")
    if not prompt_version:
        raise RecordingError("产物必须记 prompt_version（R-7-03；人工产物填 none）")
    target = abs_path_of(artifact_path)
    size = target.stat().st_size if target.is_file() else 0
    if kind in MEDIA_KINDS and size <= 0:
        raise RecordingError(f"{kind} 产物必须真实存在且非空：{artifact_path}")
    return dbm.execute(
        """INSERT INTO artifacts (task_id, step_run_id, kind, path, size_bytes, sha256,
                                  model_version, prompt_version, meta_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, step_run_id, kind, artifact_path, size, sha256_of(target),
         model_version, prompt_version, _json(meta), dbm.now_iso()), path,
    )


def list_artifacts(task_id: int, path: str | None = None) -> list[dict[str, Any]]:
    return dbm.query("SELECT * FROM artifacts WHERE task_id = ? ORDER BY id", (task_id,), path)


def list_steps(task_id: int, path: str | None = None) -> list[dict[str, Any]]:
    return dbm.query("SELECT * FROM step_runs WHERE task_id = ? ORDER BY step_no", (task_id,), path)
