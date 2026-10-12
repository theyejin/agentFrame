/* 文件用途：控制台前端公共库 —— 调本地服务接口、渲染通用组件、调用白名单脚本（R-L3-04）。 */
/* 对应需求：R-L3-01~05（页面只通过 /api/* 与本地服务交互，不越过服务直连数据库或外部平台）、R-L2-08（页面代码区块注释）、AC-3。 */
/* 维护提示：所有写动作都走 run()；它只把参数转给 /api/run，白名单与红线由本地服务把关（scripts/serve_dashboard.py）。
   顶栏栏目在 topbar() 的 pages 里登记（键 = 页面文件名，页面调 shell(active) 传同一个键），新增栏目要同时给 index.html 加入口。 */

/* 区块：基础选择器与状态 */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const LOG_MAX = 6; // 页面底部最近动作保留条数
const state = { snapshot: null, health: null, actions: [] };

/* 区块：HTTP 小工具（同源，无第三方依赖） */
async function get(path) {
  const resp = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await resp.json().catch(() => ({ error: `响应不是 JSON（HTTP ${resp.status}）` }));
  if (!resp.ok) throw new Error(body.error || `HTTP ${resp.status}`);
  return body;
}

async function post(path, payload) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await resp.json().catch(() => ({ error: `响应不是 JSON（HTTP ${resp.status}）` }));
  return { ok: resp.ok, status: resp.status, body }; // 400 也是有效业务结果（脚本自检没过），交给页面展示
}

/* 区块：调用白名单脚本（R-L3-04） */
async function run(skill, action, args = []) {
  pushLog(`${skill} ${action} ${args.join(" ")}`.trim(), "");
  const out = await post("/api/run", { skill, action, args });
  const ok = out.ok && out.body && out.body.returncode === 0;
  pushLog(`${skill} ${action}`, ok ? "ok" : "failed");
  toast(ok ? `已执行：${skill} ${action}` : `失败：${(out.body && (out.body.error || out.body.stderr)) || out.status}`, !ok);
  return out.body || {};
}

/* 区块：通用渲染组件 */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value === null || value === undefined) continue;
    if (key === "class") node.className = value;
    else if (key === "html") node.innerHTML = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "disabled" && value) node.disabled = true;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function tag(text, cls = "") {
  return el("span", { class: `tag ${cls}`.trim(), text });
}

function stat(n, k) {
  return el("div", { class: "stat" }, el("div", { class: "n", text: String(n) }), el("div", { class: "k", text: k }));
}

/** 渲染一张表：headers = [表头…]，rows = [[单元格…]…]（单元格可以是 Node 或字符串） */
function table(headers, rows, empty = "（暂无数据）") {
  if (!rows.length) return el("div", { class: "muted", text: empty });
  return el("table", {},
    el("thead", {}, el("tr", {}, ...headers.map((h) => el("th", { text: h })))),
    el("tbody", {}, ...rows.map((row) => el("tr", {}, ...row.map((cell) =>
      el("td", {}, cell instanceof Node ? cell : String(cell ?? "—")))))));
}

function toast(message, bad = false) {
  const node = el("div", { class: `toast${bad ? " bad" : ""}`, text: message });
  document.body.append(node);
  setTimeout(() => node.remove(), bad ? 6000 : 3200);
}

/* 区块：页面底部的动作日志 */
function pushLog(label, result) {
  state.actions.unshift({ at: new Date().toLocaleTimeString("zh-CN", { hour12: false }), label, result });
  state.actions = state.actions.slice(0, LOG_MAX);
  const box = $("#action-log");
  if (!box) return;
  box.replaceChildren(...state.actions.map((item) => el("div", { class: "mono" },
    `[${item.at}] ${item.label}${item.result ? " → " + item.result : " …"}`)));
}

function skillResultBox(body) {
  if (!body) return el("span", { class: "muted", text: "（没有返回）" });
  if (body.error) return el("pre", { class: "out", text: `错误：${body.error}` });
  const text = body.json ? JSON.stringify(body.json, null, 2) : (body.stdout || body.stderr || "（脚本没有输出）");
  return el("pre", { class: "out", text });
}

/* 区块：样式与环节基础数据 */
const STAGE_LABEL = { copy: "文案", visual: "视觉", video: "视频", publish: "发布", metrics: "指标", review: "复盘", closed: "已归档" };
const STATUS_LABEL = { pending: "待开始", running: "进行中", waiting_human: "待人工", blocked: "被挡住", done: "已完成", failed: "失败", cancelled: "已取消" };
const STATUS_CLASS = { running: "accent", waiting_human: "warn", blocked: "bad", failed: "bad", done: "ok" };

function stageTag(stage) { return tag(STAGE_LABEL[stage] || stage || "—", "accent"); }
function statusTag(status) { return tag(STATUS_LABEL[status] || status || "—", STATUS_CLASS[status] || ""); }
function timeText(iso) { return iso ? String(iso).replace("T", " ").slice(0, 19) : "—"; }

/* 区块：启动引导 —— 检查本地服务是否在跑，并拿到白名单 */
async function boot(render) {
  try {
    state.health = await get("/api/health");
  } catch (err) {
    document.body.prepend(el("div", { class: "card" },
      el("h2", { text: "控制台连不上本地服务" }),
      el("p", { class: "muted", text: "页面必须由本地服务打开（直接双击 HTML 只能看静态外壳）。请在仓库根目录执行：" }),
      el("pre", { class: "out", text: "python3 scripts/serve_dashboard.py\n# 然后浏览器打开 http://127.0.0.1:8787/" }),
      el("p", { class: "muted", text: `原因：${err.message}` })));
    return;
  }
  try {
    state.snapshot = await get("/api/snapshot");
  } catch (err) {
    state.snapshot = null;
    toast(`取数据失败：${err.message}`, true);
  }
  try { await render(); } catch (err) { toast(`页面渲染失败：${err.message}`, true); }
}

/* 区块：顶栏（各页面共用；active 传当前文件名） */
function topbar(active) {
  // 首页挂在 /（或 dashboard/）下，功能页挂在 pages/ 下：href 按当前层级补前缀，
  // 否则从首页点「任务流转」会跳到 /tasks.html、从功能页点「总览」会跳到 /pages/index.html（都是 404）。
  const up = location.pathname.includes("/pages/") ? "../" : "";
  const pages = [["index.html", up + "index.html", "总览"],
                 ["tasks.html", up + "pages/tasks.html", "任务流转"],
                 ["copy.html", up + "pages/copy.html", "文案生成"],
                 ["diagrams.html", up + "pages/diagrams.html", "框架图库"],
                 ["publish.html", up + "pages/publish.html", "发布操作"],
                 ["metrics.html", up + "pages/metrics.html", "数据与复盘"],
                 ["build-log.html", up + "../build-log.html", "搭建过程报告"]];
  return el("header", { class: "topbar" },
    el("h1", { text: "agentFrame 运营控制台" }),
    el("nav", {}, ...pages.map(([key, href, label]) =>
      el("a", { href: active === key ? "#" : href, class: active === key ? "active" : "", text: label }))),
    el("div", { class: "right" },
      el("span", { id: "db-path", class: "mono", text: state.health ? state.health.db : "" }),
      el("button", { text: "刷新", onclick: () => location.reload() })));
}

/** 统一骨架：顶栏 + 主体 + 底部动作日志（页面按需在 main 里追加内容） */
function shell(active, main) {
  document.body.replaceChildren(
    topbar(active),
    main,
    el("div", { class: "card" }, el("h2", { text: "最近动作（本页）" }),
      el("div", { id: "action-log", class: "mono" }, el("span", { class: "muted", text: "还没有动作" }))));
}

/* 区块：按环节找任务（各页面共用过滤） */
function tasksIn(snapshot, stages) {
  return (snapshot.tasks || []).filter((task) => stages.includes(task.stage));
}

/** 生成一个 <option>：value 是提交值，label 是给人看的文字（缺省与 value 相同） */
function option(value, label) {
  return el("option", { value, text: label === undefined ? value : label });
}
