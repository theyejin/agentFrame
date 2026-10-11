#!/usr/bin/env python3
# 文件用途：WP-05 步骤 3 的模拟测试 —— 验证适配器登记表、降级链、零付费门禁、人工兜底与提示词模板（全部离线，不调用真实服务）。
# 对应需求：R-L2-14/15/16/17（统一接口与降级链）、C-09（零付费门禁）、R-7-03（提示词入仓与版本）、R-L2-02（每步模拟测试）。
# 对应流程图：.archify/FLOW-OVERALL-20261012/overall-operations.html（外部服务适配层）
# 维护提示：新增适配器或新增 kind 后，本测试会自动覆盖；若新增了运行时实现，请补一条对应的调用断言。
"""适配器层与提示词层模拟测试。

运行：python3 tests/test_adapters.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED = REPO_ROOT / ".dsh" / "skills" / "_shared"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import adapter_runtime as ar  # noqa: E402
import env_file  # noqa: E402
import prompt_templates as pt  # noqa: E402
import seed_adapters  # noqa: E402

KINDS = {"llm", "image", "split", "video", "browser", "doc", "metrics"}
ENV_KEYS = ("LLM_API_KEY", "LLM_COST_LIMIT", "COST_LIMIT", "LLM_BASE_URL", "LLM_MODEL")


@contextmanager
def env(**values: str):
    """临时设置环境变量，并清掉其它相关键（.env 不存在时行为等价于真实环境）。"""
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    for k in ENV_KEYS:
        os.environ.pop(k, None)
    os.environ.update({k: str(v) for k, v in values.items()})
    try:
        yield
    finally:
        for k in ENV_KEYS:
            os.environ.pop(k, None)
            if saved[k] is not None:
                os.environ[k] = saved[k]


class RegistryTests(unittest.TestCase):
    """登记表本身要自洽 —— 它是降级链的唯一事实来源。"""

    @classmethod
    def setUpClass(cls):
        cls.registry = ar.load_registry()
        cls.adapters = cls.registry["adapters"]

    def test_required_fields_present(self):
        required = {"adapter_id", "kind", "provider", "capabilities", "needs_key",
                    "billable", "failure_signals", "fallback_order", "enabled", "implemented"}
        for a in self.adapters:
            self.assertTrue(required <= set(a), f"{a.get('adapter_id')} 缺字段：{required - set(a)}")

    def test_kind_values_are_legal(self):
        for a in self.adapters:
            self.assertIn(a["kind"], KINDS, a["adapter_id"])

    def test_adapter_ids_unique(self):
        ids = [a["adapter_id"] for a in self.adapters]
        self.assertEqual(len(ids), len(set(ids)), "adapter_id 有重复")

    def test_fallback_order_strictly_increasing_per_kind(self):
        for kind in KINDS:
            orders = [a["fallback_order"] for a in ar.chain(kind, self.registry)]
            self.assertGreaterEqual(len(orders), 1, f"{kind} 没有任何适配器")
            self.assertEqual(orders, sorted(orders), f"{kind} 的 fallback_order 不是升序")
            self.assertEqual(len(orders), len(set(orders)), f"{kind} 的 fallback_order 有重复")

    def test_every_kind_has_an_implemented_adapter(self):
        """每条链都必须能走通（否则整条流程会卡死）。"""
        for kind in KINDS:
            impl = [a["adapter_id"] for a in ar.chain(kind, self.registry) if a.get("implemented")]
            self.assertTrue(impl, f"{kind} 链上没有任何「已接入」的适配器")

    def test_implemented_flag_matches_runtime(self):
        """implemented 标记与代码里的运行时实现必须一一对应，防止「说已接入其实没代码」。"""
        for a in self.adapters:
            with self.subTest(adapter=a["adapter_id"]):
                self.assertEqual(bool(a.get("implemented")), ar.runtime_of(a) is not None)

    def test_every_kind_ends_with_offline_fallback(self):
        """设计原则：链尾必须是不依赖外部服务、且已接入的兜底（人工兜底或本地导出），保证断网也能收尾。

        doc 链的链尾是「本地导出」而不是「人工」：把表格写成 Markdown/CSV 交给运营人员，本身就是它的兜底形态。
        """
        for kind in KINDS:
            last = ar.chain(kind, self.registry)[-1]
            with self.subTest(kind=kind):
                self.assertTrue(last["implemented"], f"{kind} 链尾未接入：{last['adapter_id']}")
                self.assertFalse(last["needs_key"], f"{kind} 链尾需要密钥：{last['adapter_id']}")
                self.assertFalse(last["billable"], f"{kind} 链尾要花钱：{last['adapter_id']}")

    def test_billable_adapters_are_declared_with_cost(self):
        for a in self.adapters:
            if a.get("billable"):
                self.assertGreater(float(a.get("cost_per_call", 0)), 0, a["adapter_id"])


class FallbackTests(unittest.TestCase):
    """降级链行为：成功、失败换下一个、未接入跳过、最终转人工。"""

    def test_mock_llm_succeeds_offline(self):
        with env():
            result = ar.invoke("llm", {"prompt": "写 3 套文案", "topic_title": "测试"})
        self.assertTrue(result.ok)
        self.assertEqual(result.adapter_id, "llm.mock")
        self.assertTrue(result.model_version)
        self.assertIn("方案1", result.output["text"])
        self.assertEqual(result.attempts[0]["status"], ar.STATUS_OK)

    def test_failure_falls_through_paid_skipped_then_human(self):
        """mock 失败 → 计费适配器未被批准（跳过）→ 人工兜底，尝试记录要说明每一步。"""
        with env():
            result = ar.invoke("llm", {"prompt": "MOCK_FAIL 触发模拟故障"})
        statuses = [(a["adapter_id"], a["status"]) for a in result.attempts]
        self.assertIn(("llm.mock", ar.STATUS_FAILED), statuses)
        self.assertIn(("llm.deepseek", ar.STATUS_BILLABLE_SKIPPED), statuses)
        self.assertEqual(result.adapter_id, "llm.manual")
        self.assertTrue(result.ok)
        self.assertTrue(result.needs_human)

    def test_all_chains_failed_reports_every_attempt(self):
        """链上没有任何可用适配器时，错误信息必须逐条列出 adapter=status，方便定位该动哪一环。"""
        registry = {"adapters": [{**ar.find("llm.mock"), "implemented": False}]}
        with env():
            result = ar.invoke("llm", {"prompt": "x"}, registry=registry)
        self.assertFalse(result.ok)
        self.assertIn("llm.mock=not_implemented", result.error)

    def test_paid_requires_key(self):
        """批准了计费但没有密钥：应报 missing_key，而不是直接崩。"""
        registry = {"adapters": [ar.find("llm.deepseek")]}
        with env(LLM_COST_LIMIT="1.0"):
            result = ar.invoke("llm", {"prompt": "hi"}, registry=registry, allow_paid=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.attempts[0]["status"], ar.STATUS_MISSING_KEY)

    def test_cost_limit_blocks_paid_call(self):
        """成本上限低于单次预估 → 停止计费尝试（C-09 超限暂停）。"""
        registry = {"adapters": [ar.find("llm.deepseek")]}
        with env(LLM_API_KEY="sk-fake", LLM_COST_LIMIT="0.005"):
            result = ar.invoke("llm", {"prompt": "hi"}, registry=registry, allow_paid=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.attempts[0]["status"], ar.STATUS_COST_LIMIT)
        self.assertIn("C-09", result.attempts[0]["detail"])

    def test_not_implemented_is_skipped_and_chain_continues(self):
        with env():
            result = ar.invoke("image", {"prompt": "参考图", "count": 3})
        statuses = [a["status"] for a in result.attempts]
        self.assertEqual(statuses.count(ar.STATUS_NOT_IMPLEMENTED), 3)
        self.assertTrue(result.ok)
        self.assertEqual(result.adapter_id, "image.manual")
        self.assertTrue(result.needs_human)

    def test_chain_order_follows_fallback_order(self):
        mock_first = {"adapters": [ar.find("llm.mock"), ar.find("llm.deepseek")]}
        self.assertEqual([a["adapter_id"] for a in ar.chain("llm", mock_first)], ["llm.mock", "llm.deepseek"])
        flipped = {"adapters": [{**ar.find("llm.deepseek"), "fallback_order": 1},
                                {**ar.find("llm.mock"), "fallback_order": 2}]}
        self.assertEqual([a["adapter_id"] for a in ar.chain("llm", flipped)], ["llm.deepseek", "llm.mock"])

    def test_disabled_adapter_is_not_in_chain(self):
        registry = {"adapters": [{**ar.find("llm.mock"), "enabled": False}]}
        self.assertEqual(ar.chain("llm", registry), [])

    def test_local_export_writes_real_file(self):
        """doc 链的兜底是「本地导出」：真的把内容写成文件，且不污染仓库根（用绝对路径落点）。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "exports" / "out.md"
            registry = {"adapters": [ar.find("doc.local-export")]}
            result = ar.invoke("doc", {"abs_path": str(target), "content": "# 热点表\n"}, registry=registry)
            self.assertTrue(result.ok)
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_text(encoding="utf-8"), "# 热点表\n")
            self.assertGreater(result.output["bytes"], 0)

    def test_local_export_defaults_under_workspace(self):
        """不给落点时默认写到 workspace/exports/ 下（相对仓库根，供运营人员直接拿文件）。"""
        with tempfile.TemporaryDirectory() as tmp:
            registry = {"adapters": [ar.find("doc.local-export")]}
            with mock.patch.object(ar, "REPO_ROOT", Path(tmp)):
                result = ar.invoke("doc", {"content": "x"}, registry=registry)
            self.assertTrue(result.ok)
            self.assertEqual(result.output["path"], "workspace/exports/export.md")
            self.assertTrue((Path(tmp) / "workspace/exports/export.md").is_file())

    def test_describe_chain_is_sorted_and_complete(self):
        rows = ar.describe_chain("video")
        self.assertEqual([r["order"] for r in rows], sorted(r["order"] for r in rows))
        self.assertEqual(rows[-1]["adapter_id"], "video.manual")
        for row in rows:
            self.assertIn("capabilities", row)
            self.assertIn("failure_signals", row)

    def test_unknown_kind_returns_readable_error(self):
        with env():
            result = ar.invoke("nope", {})
        self.assertFalse(result.ok)
        self.assertIn("nope", result.error)


class PromptTemplateTests(unittest.TestCase):
    """提示词模板：可解析、变量对得上、渲染可控报错。"""

    def test_check_is_clean(self):
        self.assertEqual(pt.check(), [])

    def test_all_templates_parse_with_metadata(self):
        templates = pt.load_all()
        self.assertGreaterEqual(len(templates), 3)
        for tpl in templates:
            self.assertTrue(tpl.version)
            self.assertTrue(tpl.purpose)
            self.assertTrue(tpl.used_by)
            self.assertTrue(tpl.rel_path.startswith("templates/prompts/"))

    def test_render_replaces_all_placeholders(self):
        tpl = pt.load("copy-generate")
        values = {v: f"<{v}>" for v in tpl.variables}
        text = tpl.render(values)
        self.assertNotIn("{{", text)
        for v in tpl.variables:
            self.assertIn(f"<{v}>", text)

    def test_render_lists_every_missing_variable(self):
        tpl = pt.load("storyboard-split")
        with self.assertRaises(pt.MissingVariable) as ctx:
            tpl.render({"topic_title": "只有这一个"})
        self.assertGreaterEqual(len(ctx.exception.names), 5)
        self.assertIn("selected_copy", ctx.exception.names)

    def test_unknown_prompt_key_raises(self):
        with self.assertRaises(pt.PromptError):
            pt.load("no-such-prompt")

    def test_frontmatter_key_must_match_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "wrong-name.md"
            bad.write_text("---\nprompt_key: other\nversion: v1\n---\n正文", encoding="utf-8")
            with self.assertRaises(pt.PromptError):
                pt.parse_template(bad)


class SeedAndCliTests(unittest.TestCase):
    """登记表 → 数据库同步，以及两个 skill 的命令行真的能跑。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "app.db"
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "db_init.py"),
                        "--db", str(self.db), "--force"], check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_syncs_every_declared_adapter(self):
        n = seed_adapters.sync(self.db)
        self.assertEqual(n, len(ar.adapters()))
        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute("SELECT adapter_id, needs_key, billable FROM adapter_registry").fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), n)
        by_id = {r[0]: (r[1], r[2]) for r in rows}
        self.assertEqual(by_id["llm.deepseek"], (1, 1))
        self.assertEqual(by_id["llm.mock"], (0, 0))

    def test_seed_sync_is_idempotent_and_compare_passes(self):
        seed_adapters.sync(self.db)
        seed_adapters.sync(self.db)
        conn = sqlite3.connect(self.db)
        try:
            count = conn.execute("SELECT COUNT(*) FROM adapter_registry").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, len(ar.adapters()))
        self.assertEqual(seed_adapters.compare(self.db), [])

    def test_compare_detects_drift(self):
        seed_adapters.sync(self.db)
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("UPDATE adapter_registry SET capabilities = '被人改坏了' WHERE adapter_id = 'llm.mock'")
            conn.commit()
        finally:
            conn.close()
        diffs = seed_adapters.compare(self.db)
        self.assertTrue(any("llm.mock.capabilities" in d for d in diffs))

    def test_prompt_registry_cli_list_and_check(self):
        out = subprocess.run([sys.executable, str(REPO_ROOT / ".dsh/skills/prompt-registry/run.py"),
                              "list", "--json"], capture_output=True, text=True, check=True)
        rows = json.loads(out.stdout)
        self.assertEqual({r["prompt_key"] for r in rows}, {"copy-generate", "storyboard-split", "review-report"})
        check = subprocess.run([sys.executable, str(REPO_ROOT / ".dsh/skills/prompt-registry/run.py"), "check"],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_prompt_registry_sync_writes_rows(self):
        subprocess.run([sys.executable, str(REPO_ROOT / ".dsh/skills/prompt-registry/run.py"),
                        "sync", "--db", str(self.db)], check=True, capture_output=True)
        conn = sqlite3.connect(self.db)
        try:
            keys = [r[0] for r in conn.execute("SELECT prompt_key FROM prompt_versions ORDER BY prompt_key")]
        finally:
            conn.close()
        self.assertEqual(keys, ["copy-generate", "review-report", "storyboard-split"])

    def test_llm_adapter_cli_generate_offline(self):
        target = Path(self.tmp.name) / "copy" / "plan.txt"
        out = subprocess.run(
            [sys.executable, str(REPO_ROOT / ".dsh/skills/llm-adapter/run.py"), "generate",
             "--prompt-key", "copy-generate",
             "--var", "topic_title=离线演练", "--var", "topic_brief=一句话", "--var", "content_type=情绪冲突",
             "--var", "platform=抖音", "--var", "word_min=200", "--var", "word_max=400",
             "--var", "focus_list=开头钩子、情绪强度、行动号召", "--var", "extra_requirements=口语化",
             "--out", str(target), "--json"],
            capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        payload = json.loads(out.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["adapter_id"], "llm.mock")
        self.assertTrue(target.is_file() and target.stat().st_size > 0)

    def test_llm_adapter_chain_alias_works(self):
        for name in ("chain", "chains"):
            out = subprocess.run([sys.executable, str(REPO_ROOT / ".dsh/skills/llm-adapter/run.py"),
                                  name, "--kind", "llm", "--json"], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, f"{name}: {out.stderr}")
            self.assertEqual([r["adapter_id"] for r in json.loads(out.stdout)["llm"]],
                             ["llm.mock", "llm.deepseek", "llm.manual"])

    def test_c05_env_file_is_not_committed(self):
        """C-05：真实密钥只放 .env，且 .env 必须被 gitignore 忽略。"""
        ignore = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT)
        self.assertEqual(ignore.returncode, 0, ".env 没有被 .gitignore 忽略")


if __name__ == "__main__":
    unittest.main(verbosity=2)
