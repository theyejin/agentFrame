#!/usr/bin/env python3
# 文件用途：运营控制台的本地服务 —— 只读展示快照 + 调用白名单本地脚本（R-L3-01~05）；不代持任何平台账号凭据，不做自动发布。
# 对应需求：R-L3-01（本地可访问）、R-L3-04（文案生成/选择/流转/发布/数据五类操作）、R-L3-05（只读库 + 调本地脚本、不持有凭据）、R-L3-06（框架图库栏目：按登记表开图与文档）、C-08（不自动发布）、C-09（付费调用不在控制台开口子）、AC-3。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（FLOW-9 运营人员操作面）
# 维护提示：新增页面或新增可调用脚本时，改 _shared/console.py 的 RUN_WHITELIST / DIAGRAMS 与 dashboard/README.md；本服务只监听 127.0.0.1，/diagrams/<key> 与 /docs/<key> 只认登记表里的 key，不接受路径。
"""运营控制台本地服务。

用法：
    python3 scripts/serve_dashboard.py                # 起服务，浏览器打开 http://127.0.0.1:8787/
    python3 scripts/serve_dashboard.py --port 9000
    python3 scripts/serve_dashboard.py --check        # 只生成一次快照并打印摘要（不监听端口，测试用）

接口：
    GET  /                    控制台首页（dashboard/index.html）
    GET  /pages/… /assets/…   各功能页与静态资源
    GET  /build-log.html      搭建过程报告页（仓库根目录，由 scripts/build_log_report.py 生成）
    GET  /api/health          服务与库状态
    GET  /api/snapshot        整包数据（任务 / 关口待办 / 发布队列 / 指标 / 热点 / 最近日志）
    GET  /api/diagrams        框架图库（图的登记表 + 磁盘事实：是否存在 / 大小 / 节点与连线计数 + 框架文档清单）
    GET  /diagrams/<key>      一张框架图的交付 HTML（key 取 _shared/console.py 的 DIAGRAMS，页面传不进路径）
    GET  /docs/<key>          一份框架文档的原文（纯文本，key 取 FRAMEWORK_DOCS）
    GET  /api/task?id=N       一条任务的完整轨迹
    GET  /api/copy?id=N       三套候选文案与选定套号（关口① 对比卡）
    GET  /api/artifacts?id=N&kind=…&role=…   一条任务的文字产物正文（文案对比卡 / 填写清单 / 复盘报告）
    POST /api/run             调用白名单里的本地脚本（页面按钮走这里；参数按列表传递，无 shell）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".dsh" / "skills" / "_shared"))

import console as cs  # noqa: E402
import db as dbm  # noqa: E402

DEFAULT_PORT = 8787
CST = timezone(timedelta(hours=8))
LOGS_DIR = ROOT / "logs"  # 控制台动作留痕目录（测试可改成临时目录，避免污染仓库日志）
# 控制台调用脚本时必须自己注入的参数：页面不许覆盖，避免把页面变成「换个库/换个人」的后门
FORBIDDEN_ARGS = ("--db", "--allow-paid")


def _now() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def check_skill(skill: str, action: str) -> tuple[bool, str]:
    """白名单校验：只允许 RUN_WHITELIST 里的 skill + 子命令。"""
    actions = cs.RUN_WHITELIST.get(skill)
    if actions is None:
        return False, f"控制台不允许调用 {skill}（白名单外的脚本请走命令行）"
    if action not in actions:
        return False, f"{skill} 不支持子命令 {action}（可用：{'、'.join(actions)}）"
    return True, ""


def build_command(skill: str, action: str, args: list[str], db: str | None) -> list[str]:
    """拼出真正执行的命令行：固定 python3 + 脚本绝对路径 + --db + 子命令 + 页面参数（列表形式，绝不过 shell）。"""
    for item in args:
        if any(item == bad or item.startswith(bad + "=") for bad in FORBIDDEN_ARGS):
            raise cs.ConsoleError(f"参数 {item} 不允许由页面传入（服务端自己决定库与付费开关）")
    script = ROOT / ".dsh" / "skills" / skill / "run.py"
    command = [sys.executable, str(script)]
    if db:
        command += ["--db", db]
    command += [action, *args, "--json"]
    return command


def run_skill(skill: str, action: str, args: list[str], *, db: str | None = None,
              timeout: float = 300.0) -> dict:
    """调用一个本地脚本并落一条日志（控制台的所有写动作都经这里，可追溯）。"""
    ok, why = check_skill(skill, action)
    if not ok:
        raise cs.ConsoleError(why)
    command = build_command(skill, action, args, db)
    proc = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT), timeout=timeout)
    result = "ok" if proc.returncode == 0 else "failed"
    _append_log(skill=skill, action=f"控制台调用 {skill} {action}", result=result,
                note=(proc.stdout or proc.stderr or "").strip()[:300])
    payload = None
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        payload = None
    return {"returncode": proc.returncode, "result": result,
            "stdout": proc.stdout, "stderr": proc.stderr, "json": payload}


def _append_log(*, skill: str, action: str, result: str, note: str, actor: str = "运营（控制台）") -> None:
    """把控制台触发的动作追加进当天日志（R-L2-05：过程可追溯）。"""
    day = datetime.now(CST).strftime("%Y-%m-%d")
    path = LOGS_DIR / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now(), "step": "L3-console", "actor": actor, "skill": skill,
           "action": action, "result": result, "note": note}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


PAGE_ALIASES = {  # 只写页面名时的顺手跳转（人手输 URL 常忘 pages/ 前缀）
    "/tasks.html": "/pages/tasks.html",
    "/copy.html": "/pages/copy.html",
    "/publish.html": "/pages/publish.html",
    "/metrics.html": "/pages/metrics.html",
    "/index.html": "/",
}


def _static_file(url_path: str) -> Path | None:
    """把 URL 映射到仓库内的静态文件；越界（../）直接拒绝。"""
    rel = url_path.lstrip("/") or "index.html"
    if rel in ("build-log.html", "build-log.data.json"):
        target = ROOT / rel
    elif rel.startswith("pages/") or rel.startswith("assets/"):
        target = ROOT / "dashboard" / rel
    else:
        target = ROOT / "dashboard" / rel
    resolved = target.resolve()
    if not str(resolved).startswith(str(ROOT.resolve())):
        return None
    return resolved if resolved.is_file() else None


class Handler(BaseHTTPRequestHandler):
    """极简本地服务：GET 静态与数据、POST 调脚本。故意不支持目录列表与写文件。"""

    server_version = "agentFrame-console/1.1"
    db: str | None = None

    # ---- 小工具 ----
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def log_message(self, fmt, *args):  # 控制台自己的日志走 logs/*.jsonl，这里只留一行访问记录
        sys.stderr.write("[console] " + fmt % args + "\n")

    # ---- GET ----
    def do_GET(self) -> None:  # noqa: N802（http.server 的约定名）
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)
        try:
            if route in PAGE_ALIASES:  # /tasks.html → /pages/tasks.html
                self.send_response(302)
                self.send_header("Location", PAGE_ALIASES[route])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if route == "/favicon.ico":  # 浏览器自动请求，回空内容免得刷 404
                return self._send(204, b"", "image/x-icon")
            if route == "/api/health":
                return self._json(200, {"ok": True, "db": str(dbm.db_path(self.db)), "time": _now(),
                                        "whitelist": {k: list(v) for k, v in cs.RUN_WHITELIST.items()}})
            if route == "/api/snapshot":
                return self._json(200, cs.snapshot(db=self.db))
            if route == "/api/diagrams":
                return self._json(200, cs.diagrams())
            if route.startswith("/diagrams/"):
                # 只认登记表里的 key：页面拼不出任意路径，也开不到 .archify/ 以外的文件
                return self._send(200, cs.diagram_file(route[len("/diagrams/"):]).read_bytes(),
                                  "text/html; charset=utf-8")
            if route.startswith("/docs/"):
                return self._send(200, cs.framework_doc(route[len("/docs/"):]).read_bytes(),
                                  "text/plain; charset=utf-8")
            if route == "/api/task":
                task_id = int(query.get("id", ["0"])[0])
                return self._json(200, cs.task_trace(task_id, db=self.db))
            if route == "/api/copy":
                task_id = int(query.get("id", ["0"])[0])
                return self._json(200, cs.copy_plans(task_id, db=self.db))
            if route == "/api/artifacts":
                task_id = int(query.get("id", ["0"])[0])
                return self._json(200, cs.artifact_texts(
                    task_id, kind=query.get("kind", [""])[0], role=query.get("role", [""])[0], db=self.db))
            target = _static_file(route)
            if target is None:
                return self._json(404, {"error": f"没有这个路径：{route}"})
            ctype = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
                     ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
                     ".svg": "image/svg+xml", ".png": "image/png"}.get(target.suffix, "text/plain; charset=utf-8")
            return self._send(200, target.read_bytes(), ctype)
        except cs.ConsoleError as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:  # 不静默失败（C-03）：把原因回给页面
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    # ---- POST ----
    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw or "{}")
        except ValueError:
            return self._json(400, {"error": "请求体不是合法 JSON"})
        try:
            if parsed.path == "/api/run":
                skill = str(payload.get("skill", ""))
                action = str(payload.get("action", ""))
                args = [str(item) for item in payload.get("args", [])]
                outcome = run_skill(skill, action, args, db=self.db)
                return self._json(200 if outcome["returncode"] == 0 else 400, outcome)
            return self._json(404, {"error": f"没有这个接口：{parsed.path}"})
        except cs.ConsoleError as exc:
            return self._json(400, {"error": str(exc)})
        except subprocess.TimeoutExpired:
            return self._json(504, {"error": "脚本执行超时（300 秒），已在日志里留痕，请到命令行重试"})
        except Exception as exc:
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运营控制台本地服务（只监听 127.0.0.1）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（只允许本机）")
    parser.add_argument("--db", default=None, help="数据库路径（默认 db/app.db）")
    parser.add_argument("--check", action="store_true", help="只生成一次快照并打印摘要，不监听端口")
    parser.add_argument("--json", action="store_true", help="--check 时以 JSON 输出")
    args = parser.parse_args(argv)

    Handler.db = args.db
    if args.check:
        snap = cs.snapshot(db=args.db)
        gallery = cs.diagrams()
        summary = {"ok": True, "db": snap["db"], "tasks": len(snap["tasks"]),
                   "gate_todos": len(snap["gate_todos"]), "publish_queue": len(snap["publish_queue"]),
                   "logs": snap["logs"]["count"], "diagrams": gallery["available"],
                   "diagrams_missing": gallery["missing"], "generated_at": snap["generated_at"]}
        print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json
              else f"控制台数据自检通过：任务 {summary['tasks']} 条、待办关口 {summary['gate_todos']} 个、"
                   f"发布队列 {summary['publish_queue']} 条、日志 {summary['logs']} 条、"
                   f"框架图 {summary['diagrams']}/{gallery['count']} 张可打开（库：{summary['db']}）")
        return 0
    if args.host != "127.0.0.1":
        print("控制台只允许监听 127.0.0.1（R-L3-05：不对外暴露）", file=sys.stderr)
        return 2
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"运营控制台已启动：http://{args.host}:{args.port}/   （Ctrl+C 退出）")
    print(f"框架图库：http://{args.host}:{args.port}/pages/diagrams.html")
    print(f"搭建过程报告页：http://{args.host}:{args.port}/build-log.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
