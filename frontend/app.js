/* CQA UI — static HTML/CSS/JS, no build step, Dynamics 365 (Fluent) look. Talks to /api via fetch. */
const API = (window.CQA_CONFIG && window.CQA_CONFIG.apiBase) || "";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt2 = n => n == null ? "—" : (Math.round(n * 100) / 100).toFixed(2).replace(".", ",");
const dt = s => s ? new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z").toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
const state = { group: localStorage.getItem("cqa_group") || "DEV", role: localStorage.getItem("cqa_role") || "qc", user: localStorage.getItem("cqa_user") || "М. Ибраева", checklist: null, settings: null, lastJob: null };

async function api(path, opts = {}) {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (!r.ok) { let msg = r.statusText; try { msg = (await r.json()).detail || msg; } catch (_) {} throw new Error(msg); }
  return r.json();
}
function toast(msg, kind = "info", ms = 4000) { const t = $("#toast"); t.textContent = msg; t.className = `toast ${kind}`; t.hidden = false; clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), ms); }

/* ---------- icons (Fluent-like outlines) ---------- */
const P = {
  home: '<path d="M3 9.5 10 4l7 5.5V16a1 1 0 0 1-1 1h-3.5v-4h-5v4H4a1 1 0 0 1-1-1z"/>', inbox: '<path d="M3 11h4l1.5 2h3L13 11h4M4 4h12l1 7v5H3v-5z"/>', list: '<path d="M4 6h12M4 10h12M4 14h12"/>',
  flag: '<path d="M5 17V3h9l-1.5 3L14 9H5"/>', scale: '<path d="M10 3v14M4 7h12M4 7l-2 5h4zM16 7l-2 5h4zM6 17h8"/>', check: '<rect x="3" y="3" width="14" height="14" rx="2"/><path d="m6.5 10 2.5 2.5 4.5-5"/>',
  refresh: '<path d="M16 10a6 6 0 1 1-1.8-4.3M16 4v3h-3"/>', chart: '<path d="M3 17h14M6 14V8M10 14V5M14 14v-4"/>', gear: '<circle cx="10" cy="10" r="2.5"/><path d="M10 3v2M10 15v2M3 10h2M15 10h2M5 5l1.5 1.5M13.5 13.5 15 15M5 15l1.5-1.5M13.5 6.5 15 5"/>',
  upload: '<path d="M10 13V4m-3.5 3.5L10 4l3.5 3.5M4 13v3h12v-3"/>', search: '<circle cx="9" cy="9" r="5"/><path d="m13 13 4 4"/>', filter: '<path d="M3 5h14l-5.5 6v5l-3-1.5V11z"/>', columns: '<rect x="3" y="4" width="14" height="12" rx="1"/><path d="M8 4v12M13 4v12"/>',
  add: '<path d="M10 4v12M4 10h12"/>', save: '<path d="M4 3h10l3 3v11H4zM7 3v5h6V3M7 17v-5h6v5"/>', share: '<path d="M12 5a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM4 10a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM12 15a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM8 9l4-3M8 11l4 3"/>',
  more: '<circle cx="10" cy="5" r="1"/><circle cx="10" cy="10" r="1"/><circle cx="10" cy="15" r="1"/>', chev: '<path d="m6 8 4 4 4-4"/>', close: '<path d="m5 5 10 10M15 5 5 15"/>', bulb: '<path d="M7 14h6M8 17h4M10 3a5 5 0 0 1 3 9v2H7v-2a5 5 0 0 1 3-9z"/>',
  play: '<path d="M7 4v12l9-6z"/>', doc: '<path d="M5 3h7l3 3v11H5zM12 3v3h3"/>', phone: '<path d="M6 3h3l1.5 4-2 1.5a8 8 0 0 0 3 3L13 9.5 17 11v3a2 2 0 0 1-2 2A12 12 0 0 1 4 5a2 2 0 0 1 2-2z"/>', chat: '<path d="M4 5h12v8H9l-4 3v-3H4z"/>',
  export: '<path d="M10 3v9m-3.5-3.5L10 12l3.5-3.5M4 14v3h12v-3"/>', back: '<path d="m11 5-5 5 5 5M6 10h10"/>', edit: '<path d="M4 16h3l9-9-3-3-9 9zM11 6l3 3"/>', warn: '<path d="M10 3 2.5 17h15zM10 8v4M10 14.5v.5"/>', book: '<path d="M4 4h5a2 2 0 0 1 2 2v11a2 2 0 0 0-2-2H4zM16 4h-5a2 2 0 0 0-2 2v11a2 2 0 0 1 2-2h5z"/>',
  link: '<path d="M8 12a3 3 0 0 0 4 0l3-3a3 3 0 0 0-4-4l-1 1M12 8a3 3 0 0 0-4 0l-3 3a3 3 0 0 0 4 4l1-1"/>', help: '<circle cx="10" cy="10" r="7"/><path d="M8 8a2 2 0 1 1 3 1.7c-.7.4-1 .8-1 1.6M10 14v.5"/>', dash: '<rect x="3" y="3" width="6" height="6"/><rect x="11" y="3" width="6" height="6"/><rect x="3" y="11" width="6" height="6"/><rect x="11" y="11" width="6" height="6"/>',
};
const ic = (n, l) => `<svg class="i${l ? " l" : ""}" viewBox="0 0 20 20">${P[n] || ""}</svg>`;

/* ---------- shell ---------- */
const NAV = [["dialogs", "Диалоги", "chat"], ["violations", "Нарушения", "flag"], ["appeals", "Апелляции", "scale"], ["runs", "Запуски оценки", "refresh"], ["analytics", "Аналитика", "chart"]];
const NAV2 = [["checklists", "Чек-листы", "check"], ["settings", "Модели и данные", "gear"], ["export", "Сдача результатов", "export"]];
function shell(active, body, opts = {}) {
  const tabs = [["Главная", "home", false, "#/dialogs"], ["Апелляции", "inbox", false, "#/appeals"], ...(opts.tabs || [])];
  return `<div class="app ${opts.pane ? "pane" : ""}">
    <div class="appbar"><div class="waffle"><i></i></div><div class="brand">${window.CQA_LOGO}</div><div class="area">Контроль качества диалогов</div>
      <div class="gsearch">${ic("search")}<input id="gsearch" placeholder="Поиск по ID или тексту реплики" value="${esc(state.q || "")}" style="border:0;outline:0;flex:1;font:inherit;background:transparent"></div>
      <div class="icons"><span title="Набор данных" class="dd" style="height:28px;color:#fff;border-color:rgba(255,255,255,.3);background:transparent;min-width:0;max-width:none;width:auto;white-space:nowrap;overflow:visible" onclick="pickGroup()">${esc(state.group)} ${ic("chev")}</span>
        <span class="dd" style="height:28px;color:#fff;border-color:rgba(255,255,255,.3);background:transparent;min-width:0;max-width:none;width:auto;white-space:nowrap;overflow:visible" onclick="pickRole()">${{ op: "Оператор", qc: "Проверяющий", mgr: "Руководитель" }[state.role]} ${ic("chev")}</span>
        <span>${ic("help", 1)}</span><span class="avatar" title="${esc(state.user)}">${esc(state.user.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase())}</span></div></div>
    <div class="sessions"><span class="burger">${ic("list", 1)}</span>${tabs.map(([t, i, on, href]) => `<a class="stab ${on ? "on" : ""}" href="${href || "#"}">${ic(i)} ${esc(t)}${on ? `<span class="x">${ic("close")}</span>` : ""}</a>`).join("")}</div>
    <nav class="sitemap"><div class="grp lbl">Контроль качества</div>${NAV.map(([k, t, i]) => `<a href="#/${k}" class="${active === k ? "on" : ""}" title="${t}">${ic(i)}<span class="lbl">${t}</span></a>`).join("")}
      <div class="grp lbl">Настройка</div>${NAV2.map(([k, t, i]) => `<a href="#/${k}" class="${active === k ? "on" : ""}" title="${t}">${ic(i)}<span class="lbl">${t}</span></a>`).join("")}
      <div class="areasel"><span class="lbl">Контроль качества</span>${ic("chev")}</div></nav>
    <div class="work">${body}</div>
    ${opts.pane ? `<aside class="sidepane">${opts.pane}</aside>` : ""}
    <div class="strip"><span class="${opts.pane ? "on" : ""}" title="Помощник оценки">${ic("bulb", 1)}</span><a href="#/export" title="Сдача">${ic("export", 1)}</a><a href="${API}/api/docs" target="_blank" title="API">${ic("doc", 1)}</a></div></div>`;
}
window.pickGroup = async () => { const groups = await api("/api/datasets"); const g = prompt("Набор (group_id):\n" + groups.map(x => `${x.group_id} — ${x.dialogs} диалогов, оценено ${x.evaluated}`).join("\n"), state.group); if (g) { state.group = g.trim(); localStorage.setItem("cqa_group", state.group); render(); } };
window.pickRole = () => { const r = prompt("Роль: op (оператор), qc (проверяющий), mgr (руководитель)", state.role); if (r && ["op", "qc", "mgr"].includes(r.trim())) { state.role = r.trim(); localStorage.setItem("cqa_role", state.role); render(); } };
const cmd = (i, t, cls = "", on = "") => `<button class="cmd ${cls}" ${on ? `onclick="${on}"` : ""}>${ic(i)}${t}</button>`;
const lang = l => `<span class="lang">${esc(l)}</span>`;
const sbar = t => t == null ? `<span class="muted">—</span>` : `<span class="sbar num"><i style="--w:${t}%;--c:${t < 60 ? "var(--bad)" : t < 80 ? "#C19C00" : "var(--brand)"}"></i>${fmt2(t)}</span>`;
function ring(total, critical, size = 112) { const r = (size - 12) / 2, C = 2 * Math.PI * r, v = total ?? 0; const col = critical || v < 60 ? "var(--bad)" : v < 80 ? "#C19C00" : "var(--brand)"; return `<div class="ring" style="width:${size}px;height:${size}px"><svg width="${size}" height="${size}"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" stroke="var(--line2)" stroke-width="10" fill="none"/><circle cx="${size / 2}" cy="${size / 2}" r="${r}" stroke="${col}" stroke-width="10" fill="none" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - v / 100)}"/></svg><div class="v"><b>${fmt2(total)}</b><small>из 100</small></div></div>`; }
function critOf(id) { return (state.checklist?.criteria || []).find(c => c.id === id) || { id, code: "", title: id, type: "binary", weight: 0, scale: [] }; }
function bdg(c, v) {
  if (c.type === "flag") return v ? `<span class="bdg flag">Нарушение</span>` : `<span class="bdg ok">Нет</span>`;
  if (v === null || v === undefined) return `<span class="bdg na">N/A</span>`;
  if (c.type === "binary") return v ? `<span class="bdg yes">Да</span>` : `<span class="bdg no">Нет</span>`;
  const top = Math.max(...(c.scale || []).map(s => s[0]), 1); return `<span class="bdg ${v === top ? "yes" : v === 0 ? "no" : "step"}">${v} из ${top}</span>`;
}
async function ensureChecklist() { if (!state.checklist) { const all = await api("/api/checklists"); state.checklist = all.find(c => c.is_active) || all[0]; state.checklists = all; } return state.checklist; }

/* ---------- jobs (progress toast + polling) ---------- */
window.startJob = async (body) => {
  try { const j = await api("/api/jobs", { method: "POST", body: { group_id: state.group, ...body } }); state.lastJob = j.id; toast(`Запуск #${j.id}: 0 / ${j.total}`, "info", 60000); pollJob(j.id); }
  catch (e) { toast("Не удалось запустить оценку: " + e.message, "bad"); }
};
async function pollJob(id) {
  const j = await api(`/api/jobs/${id}`);
  if (j.status === "running" || j.status === "queued") { toast(`Запуск #${id}: ${j.done} / ${j.total} · $${j.cost_usd.toFixed(3)}${j.last ? " · " + j.last : ""}`, "info", 60000); setTimeout(() => pollJob(id), 1500); }
  else { toast(`Запуск #${id} ${j.status === "done" ? "завершён" : "завершился с ошибкой"}: ${j.done} диалогов, ошибок ${j.failed}, $${j.cost_usd.toFixed(3)}`, j.status === "done" ? "good" : "bad", 8000); render(); }
}
window.evalSelected = () => { const ids = [...document.querySelectorAll("input.sel:checked")].map(x => x.value); if (!ids.length) return toast("Отметьте диалоги в списке", "warn"); startJob({ conversation_ids: ids, parallel_dialogs: 3 }); };
window.evalAll = () => startJob({ only_unevaluated: true, parallel_dialogs: 3 });
window.reEval = (cid) => startJob({ conversation_ids: [cid], parallel_dialogs: 1 });
window.fetchGroup = async () => { const g = prompt("group_id набора у организаторов", state.group === "DEV" ? "DEV" : state.group); if (!g) return; try { const r = await api("/api/datasets/fetch", { method: "POST", body: { group_id: g.trim() } }); state.group = g.trim(); localStorage.setItem("cqa_group", state.group); toast(`Загружено ${r.records} диалогов (${g})`, "good"); render(); } catch (e) { toast("Ошибка загрузки: " + e.message, "bad", 8000); } };

/* ---------- dialogs ---------- */
async function pageDialogs() {
  await ensureChecklist();
  const q = state.q ? `&q=${encodeURIComponent(state.q)}` : "";
  const [rows, st] = await Promise.all([api(`/api/conversations?group_id=${encodeURIComponent(state.group)}${q}`), api(`/api/stats?group_id=${encodeURIComponent(state.group)}`)]);
  rows.sort((a, b) => ((a.evaluation?.final_score ?? 101) - (b.evaluation?.final_score ?? 101)));
  const body = `<div class="cmdbar">${cmd("play", "Оценить выбранные", "", "evalSelected()")}${cmd("upload", "Загрузить набор", "", "fetchGroup()")}${cmd("refresh", "Обновить", "", "render()")}<span class="cmdsep"></span><a class="cmd" href="${API}/api/export/preview?group_id=${esc(state.group)}" target="_blank">${ic("export")}Экспорт JSON</a>${cmd("columns", "Столбцы")}${cmd("filter", "Фильтры")}
      <button class="cmd primary" onclick="evalAll()">${ic("play")}Оценить все неоценённые</button></div>
    <div class="viewbar"><div class="viewsel">Все диалоги · набор ${esc(state.group)} <span class="chev">${ic("chev")}</span></div><div class="kw">${ic("search")}<input id="kw" placeholder="Фильтр по ключевому слову" value="${esc(state.q || "")}" style="border:0;outline:0;flex:1;font:inherit"></div></div>
    <div class="body" style="padding-top:0"><div class="cols c4">
      <div class="tile"><div class="l">Оценено диалогов</div><div class="v">${st.evaluated} <span class="muted" style="font-size:14px;font-weight:400">из ${st.dialogs}</span></div><div class="d">стоимость $${(st.cost_usd || 0).toFixed(2)}</div></div>
      <div class="tile"><div class="l">Средний итог</div><div class="v num">${fmt2(st.avg)}</div><div class="d">медиана ${fmt2(st.median)}</div></div>
      <div class="tile"><div class="l">Грубые нарушения</div><div class="v" style="color:${st.critical ? "var(--bad)" : "var(--ink)"}">${st.critical}</div><div class="d">по флагу критерия 08</div></div>
      <div class="tile"><div class="l">Апелляции</div><div class="v">${st.appeals_open} <span class="muted" style="font-size:14px;font-weight:400">открыто</span></div><div class="d">${st.appeals_decided} решено · изменено ${st.appeals_changed}</div></div></div>
    <div class="panel"><table class="grid"><tr><th class="ck"><input type="checkbox" onclick="document.querySelectorAll('input.sel').forEach(x=>x.checked=this.checked)"></th><th>Диалог</th><th>Канал</th><th>Язык</th><th>Оператор</th><th>Реплик</th><th>Итог</th><th>Грубая ошибка</th><th>Апелляции</th><th>Оценён</th><th>Модель</th></tr>
      ${rows.map(x => { const e = x.evaluation; return `<tr><td class="ck"><input type="checkbox" class="sel" value="${esc(x.conversation_id)}"></td><td><a href="#/dialog/${esc(x.conversation_id)}">${esc(x.conversation_id)}</a></td><td>${x.channel === "voice call" ? `${ic("phone")} Звонок` : `${ic("chat")} Чат`}</td><td>${lang(x.language)}</td><td>${esc(x.operator || "—")}</td><td class="num">${x.turns}</td>
        <td>${e ? (e.status === "ok" ? sbar(e.final_after_appeals?.final_score ?? e.final_score) : `<span class="bdg no" title="${esc(e.error)}">ошибка</span>`) : `<span class="muted">не оценён</span>`}</td><td>${e?.critical_flag ? `<span class="bdg flag">Да</span>` : `<span class="muted">${e ? "Нет" : "—"}</span>`}</td>
        <td>${x.appeals.length ? x.appeals.map(a => `<span class="bdg ${a.status === "open" ? "warn" : "neu"}">${a.status === "open" ? "Открыта" : "Решена"}</span>`).join(" ") : `<span class="muted">—</span>`}</td><td class="muted">${e ? dt(e.created_at) : "—"}</td><td class="muted">${e ? esc(e.model?.name || "") : ""}</td></tr>`; }).join("")}
      ${!rows.length ? `<tr><td colspan="11" class="muted" style="text-align:center;padding:40px">Нет диалогов. Нажмите «Загрузить набор» и введите group_id.</td></tr>` : ""}
    </table><div class="gfoot"><span>Строки: ${rows.length} · сортировка: сначала низкий итог</span><span>group_id ${esc(state.group)}</span></div></div></div>`;
  setTimeout(() => { const kw = $("#kw"); if (kw) kw.onchange = () => { state.q = kw.value.trim(); render(); }; const g = $("#gsearch"); if (g) g.onchange = () => { state.q = g.value.trim(); location.hash = "#/dialogs"; render(); }; }, 0);
  return shell("dialogs", body);
}

/* ---------- transcript ---------- */
function transcript(turns, ev, hl, compact) {
  const marks = {}, expected = {};
  for (const [cid, r] of Object.entries(ev?.criteria || {})) { for (const t of r.evidence_turns || []) (marks[t] ||= []).push(critOf(cid)); if (r.expected_turn) (expected[r.expected_turn] ||= []).push(critOf(cid)); }
  return `<div class="tl">${compact ? "" : `<div class="tlsearch">${ic("search")}Поиск по транскрипту</div>`}${turns.map(t => {
    const cls = t.speaker === "operator" ? "op" : t.speaker === "client" ? "cl" : t.speaker === "bot" ? "bot" : "sys"; const m = marks[t.n] || []; const on = m.length && (!hl || m.some(c => c.id === hl));
    const ts = t.timestamp.length > 8 ? t.timestamp.slice(11, 19) : t.timestamp; const who = { op: "Оператор", cl: "Клиент", bot: "Бот AIM", sys: "Система" }[cls]; const init = { op: "О", cl: "К", bot: "AI", sys: "⚙" }[cls];
    return `${(expected[t.n] || []).map(c => `<div class="expect">${ic("warn")}ожидалось здесь: ${c.code} ${esc(c.title)}<i></i></div>`).join("")}
      <div class="msg ${cls} ${on ? "ev" : ""}" id="t${t.n}"><div class="ic">${init}</div><div><div class="hd"><b>${who}</b><span class="t">${esc(ts)}</span><span class="n">#${t.n}</span></div><div class="tx">${esc(t.text)}</div>${m.length ? `<div class="tags">${m.map(c => `<span class="bdg ${c.type === "flag" ? "flag" : "out"}">${c.code} ${esc(c.title)}</span>`).join("")}</div>` : ""}</div></div>`;
  }).join("")}</div>`;
}

/* ---------- dialog record ---------- */
async function pageDialog(cid, openCrit) {
  await ensureChecklist();
  const d = await api(`/api/conversations/${encodeURIComponent(cid)}?group_id=${encodeURIComponent(state.group)}`).catch(() => api(`/api/conversations/${encodeURIComponent(cid)}`));
  const ev = d.evaluation, rec = d.dialog, isCall = rec.channel === "voice call";
  const cl = state.checklists?.find(c => c.id === ev?.checklist_version_id) || state.checklist;
  const defs = cl.criteria;
  const score = ev?.score, fin = ev?.final_after_appeals;
  const open = openCrit || (score?.critical_flag ? "critical" : defs.find(c => ev?.criteria?.[c.id]?.value === false)?.id || defs[defs.length - 2]?.id);
  const critRows = ev ? defs.map(c => { const r = ev.criteria[c.id]; if (!r) return ""; const row = (score?.rows || []).find(x => x.criterion_id === c.id); const ov = ev.overrides?.[c.id];
    const pts = c.type === "flag" ? "" : row?.applicable ? `${fmt2(row.points)} <small>/ ${c.weight}</small>` : `<small>N/A</small>`; const isOpen = c.id === open;
    return `<div class="crit ${isOpen ? "open" : ""}" onclick="location.hash='#/dialog/${esc(cid)}/c/${c.id}'"><span class="code">${c.code}</span><div class="tt"><div class="t">${esc(c.title)}</div><div class="s">${esc(c.section || "")}</div></div><span>${bdg(c, r.value)}${ov !== undefined ? ` → ${bdg(c, ov)}` : ""}</span><div class="pts">${pts}</div></div>
      ${isOpen ? `<div class="critbody"><div><span class="sb">Обоснование.</span> ${esc(r.rationale)}</div>
        ${(r.evidence_turns || []).map(t => { const tt = d.turns[t - 1]; return tt ? `<div class="quote"><div class="m">реплика #${t} · ${esc(tt.speaker)} · ${esc(tt.timestamp.length > 8 ? tt.timestamp.slice(11, 19) : tt.timestamp)}</div>«${esc(tt.text.slice(0, 200))}${tt.text.length > 200 ? "…" : ""}»</div>` : ""; }).join("")}
        ${r.expected_turn ? `<div class="msgbar bad">Пропущенное действие ожидалось в реплике #${r.expected_turn}.</div>` : ""}
        ${r.value === null ? `<div class="msgbar info">N/A: ${esc(r.na_reason || c.na_rule || "")} Критерий исключён, вес ${c.weight} перераспределён.</div>` : ""}
        ${ev.second_opinion?.[c.id] ? `<div class="small ${ev.second_opinion[c.id].agrees ? "muted" : ""}" style="${ev.second_opinion[c.id].agrees ? "" : "color:var(--warn)"}">Второе мнение (${esc(ev.second_opinion[c.id].model || "локальная модель")}): ${ev.second_opinion[c.id].agrees ? "совпадает" : "расходится: " + esc(String(ev.second_opinion[c.id].value))}</div>` : ""}
        <div class="small muted">Модель ${esc(ev.model?.name)} · уверенность ${(r.confidence ?? 0).toFixed(2)}</div>
        <div class="row">${r.evidence_turns?.[0] ? `<a class="btn sm" href="#t${r.evidence_turns[0]}" onclick="document.getElementById('t${r.evidence_turns[0]}')?.scrollIntoView({behavior:'smooth',block:'center'});return false">${ic("link")}Перейти к реплике #${r.evidence_turns[0]}</a>` : ""}${state.role !== "mgr" ? `<a class="btn sm" href="#/dialog/${esc(cid)}/appeal/${c.id}">${ic("scale")}Оспорить оценку</a>` : ""}</div></div>` : ""}`; }).join("") : "";
  const body = `<div class="cmdbar"><a class="cmd" href="#/dialogs">${ic("back")}</a>${cmd("refresh", "Переоценить", "", `reEval('${esc(cid)}')`)}<span class="cmdsep"></span>${ev ? `<a class="cmd" href="#/dialog/${esc(cid)}/appeal/${open}">${ic("scale")}Апелляция</a>` : ""}<a class="cmd" href="${API}/api/conversations/${esc(cid)}" target="_blank">${ic("doc")}JSON карточки</a>${isCall ? `<a class="cmd" href="${API}/api/audio/${esc(cid)}" target="_blank">${ic("play")}Запись</a>` : ""}<button class="cmd primary" onclick="navigator.clipboard&&navigator.clipboard.writeText(location.href);toast('Ссылка скопирована','good')">${ic("share")}Поделиться</button></div>
    <div class="rec"><div class="rec-head"><div><div class="title">Диалог ${esc(cid)}<span class="st">· ${ev ? (ev.status === "ok" ? "Оценён" : "Ошибка оценки") : "Не оценён"}</span></div><div class="ent">Диалог поддержки · ${isCall ? "Звонок" : "Чат"} · ${esc(rec.language)} · набор ${esc(rec.group_id)}</div></div>
      <div class="hf"><div><b class="num">${fmt2(fin?.final_score ?? score?.final_score)}</b><small>Итог из 100${fin ? " (после апелляций)" : ""}</small></div><div><b>${score ? (score.critical_flag ? "Да" : "Нет") : "—"}</b><small>Грубая ошибка</small></div><div><b>${esc(d.facts.first_operator_text ? (d.facts.first_operator_text.match(/(?:меня зовут|я|мен|I'?m)\s+([^\s.,!]+)/i)?.[1] || "—") : "—")}</b><small>Оператор</small></div><div><b>${ev ? dt(ev.created_at) : "—"}</b><small>Дата оценки</small></div><div><b>v${cl.version} · ${esc(ev?.model?.name || "—")}</b><small>Чек-лист · модель</small></div></div></div>
      <div class="ftabs"><a class="${openCrit ? "" : "on"}" href="#/dialog/${esc(cid)}">Сводка</a><a class="${openCrit ? "on" : ""}" href="#/dialog/${esc(cid)}/c/${open}">Оценка</a><a href="#/appeals">Апелляции (${d.appeals.length})</a><a href="#/runs">Журнал вызовов</a></div></div>
    <div class="body"><div class="cols" style="grid-template-columns:minmax(0,1fr) minmax(0,1fr)">
      <div class="panel"><div class="ph"><span>Транскрипт · ${d.turns.length} реплик</span><div class="tools"><span>${ic("filter")}</span><span>${ic("list")}</span></div></div>
        ${isCall ? `<div class="player"><audio controls preload="none" src="${API}/api/audio/${esc(cid)}" style="width:100%"></audio><div class="row between"><span class="small muted">запись подтягивается по свежей ссылке организаторов (действует 60 минут)</span><a class="btn sm" href="${API}/api/audio/${esc(cid)}" target="_blank">Открыть запись</a></div></div>` : ""}
        <div class="pb tight" style="padding-top:8px">${transcript(d.turns, ev, openCrit ? open : null)}</div></div>
      <div class="col" style="gap:8px">
        ${ev ? `<div class="panel"><div class="ph"><span>Итог оценки</span><span class="small muted">чек-лист v${cl.version} · ${ev.calls.length} вызовов · ${(ev.duration_ms / 1000).toFixed(1)} с · $${ev.cost_usd.toFixed(3)}</span></div>
          <div class="pb"><div class="row" style="gap:20px;align-items:flex-start">${ring(fin?.final_score ?? score?.final_score, score?.critical_flag)}<div class="grow col" style="gap:8px">
            <div class="row wrap">${score?.critical_flag ? `<span class="bdg flag wrapok">Грубое нарушение</span>` : `<span class="bdg ok">Без грубых нарушений</span>`}${d.appeals.some(a => a.status === "open") ? `<span class="bdg warn">Апелляция открыта</span>` : ""}${fin ? `<span class="bdg info">Итог ИИ ${fmt2(score.final_score)} → после решения ${fmt2(fin.final_score)}</span>` : ""}</div>
            ${score ? `<div class="formula">итог = Σ баллов / Σ весов × 100 = ${fmt2((score.rows || []).reduce((s, r) => s + (r.points || 0), 0))} / ${(score.rows || []).filter(r => r.applicable).reduce((s, r) => s + r.weight, 0)} × 100 = ${fmt2(score.final_score)}</div>
            <div class="small muted">N/A: ${(score.rows || []).filter(r => !r.applicable && critOf(r.criterion_id).type !== "flag").map(r => critOf(r.criterion_id).code).join(", ") || "нет"} · веса перераспределены</div>` : `<div class="msgbar bad">${esc(ev.error)}</div>`}</div></div></div></div>
        <div class="panel"><div class="ph"><span>Оценка по критериям</span><span class="small muted">выберите критерий</span></div>${critRows}</div>` : `<div class="panel"><div class="pb" style="text-align:center;padding:40px"><div class="muted" style="margin-bottom:12px">Диалог ещё не оценён</div><button class="btn primary" onclick="reEval('${esc(cid)}')">${ic("play")}Оценить сейчас</button></div></div>`}
        ${d.appeals.length ? `<div class="panel"><div class="ph"><span>Апелляции</span><a class="small" href="#/appeals">Все</a></div><div class="pb"><div class="hist">${d.appeals.map(a => { const c = critOf(a.criterion_id); return `
          <div class="hi"><span class="dot ${a.status === "open" ? "bad" : "on"}"></span><div><div class="row between"><span class="sb">Апелляция #${a.id} · ${c.code} ${esc(c.title)} · ${esc(a.submitted_by)}</span><span class="small muted">${dt(a.created_at)}</span></div><div class="small">${esc(a.comment)}</div>
          ${a.status === "decided" ? `<div class="small" style="margin-top:4px"><b>${a.decision === "confirm" ? "Оценка подтверждена" : "Оценка изменена"}</b> · ${esc(a.reviewer)} · ${dt(a.decided_at)} — ${esc(a.reason)}${a.score_after != null ? ` · итог ${fmt2(a.score_before)} → ${fmt2(a.score_after)}` : ""}</div>` : `<a class="btn sm primary" style="margin-top:6px" href="#/appeal/${a.id}">Рассмотреть</a>`}</div></div>`; }).join("")}</div></div></div>` : ""}
      </div></div></div>`;
  const f = d.facts;
  const pane = `<h2>Помощник оценки</h2><div class="sb small" style="color:var(--muted)">ФАКТЫ, ВЫЧИСЛЕННЫЕ КОДОМ</div>
    <div class="kv"><div class="k">Первая реплика оператора</div><div class="v">${f.first_operator_turn ? "#" + f.first_operator_turn : "—"}</div><div class="k">Приветствие + имя</div><div class="v">${f.greeting_in_first_operator_turn && f.name_in_first_operator_turn ? "да" : "нет"}</div><div class="k">Прощание в конце</div><div class="v">${f.farewell_in_last_operator_turn ? "да" : "нет"}</div><div class="k">Итог / предложение помощи</div><div class="v">${f.offer_or_summary_near_end ? "да" : "нет"}</div><div class="k">Подтверждение личности</div><div class="v">${f.identity_verified_turns?.length ? "#" + f.identity_verified_turns.join(", #") : "нет"}</div><div class="k">Системные события</div><div class="v">${f.system_events?.length || 0}</div><div class="k">Завершение</div><div class="v">${esc(f.ending?.event || "реплика оператора")}</div><div class="k">Язык</div><div class="v">${esc(f.language)}</div></div>
    ${ev?.second_opinion ? `<div class="sb small" style="color:var(--muted);margin-top:8px">ВТОРОЕ МНЕНИЕ</div><div class="msgbar ${Object.values(ev.second_opinion).every(x => x.agrees) ? "good" : "warn"}">${Object.values(ev.second_opinion).filter(x => x.agrees).length} из ${Object.keys(ev.second_opinion).length} критериев совпадают.</div>` : ""}
    ${ev ? `<div class="sb small" style="color:var(--muted);margin-top:8px">ВЫЗОВЫ МОДЕЛИ</div><div class="kv">${ev.calls.map(c => `<div class="k">${critOf(c.criterion_id).code} ${esc(c.provider)}</div><div class="v">${c.tokens_in}→${c.tokens_out} · ${(c.latency_ms / 1000).toFixed(1)} с${c.status !== "ok" ? " · " + esc(c.status) : ""}</div>`).join("")}</div>` : ""}
    <div class="sb small" style="color:var(--muted);margin-top:8px">ИСТОРИЯ ОЦЕНОК</div><div class="kv">${d.history.map(h => `<div class="k">#${h.id} · v${state.checklists?.find(c => c.id === h.checklist_version_id)?.version || "?"} · ${dt(h.created_at)}</div><div class="v">${h.status === "ok" ? fmt2(h.final_score) : "ошибка"}${h.is_latest ? "" : " (старая)"}</div>`).join("")}</div>`;
  return shell("dialogs", body, { pane, tabs: [[cid, isCall ? "phone" : "chat", true, `#/dialog/${cid}`]] });
}

/* ---------- appeal quick create ---------- */
async function pageAppealNew(cid, critId) {
  const base = await pageDialog(cid, critId);
  const d = await api(`/api/conversations/${encodeURIComponent(cid)}?group_id=${encodeURIComponent(state.group)}`); const ev = d.evaluation; const c = critOf(critId); const r = ev?.criteria?.[critId];
  if (!ev || !r) return base;
  const opts = c.type === "scale" ? c.scale.map(s => `<label class="radio"><input type="radio" name="pv" value="${s[0]}" ${s[0] === r.value ? "" : ""}> ${s[0]}</label>`).join("") : `<label class="radio"><input type="radio" name="pv" value="true" ${r.value === false ? "checked" : ""}> Да</label><label class="radio"><input type="radio" name="pv" value="false" ${r.value === true ? "checked" : ""}> Нет</label>${c.allow_na ? `<label class="radio"><input type="radio" name="pv" value="null"> N/A</label>` : ""}`;
  const pane = `<div class="qc-wrap"><div class="qc"><div class="qh"><h2>Быстрое создание: Апелляция</h2><a class="btn sm lnk" href="#/dialog/${esc(cid)}/c/${critId}">${ic("close")}</a></div>
    <div class="qb"><div class="form"><div class="frow"><label>Диалог</label><div class="val">${esc(cid)}</div></div><div class="frow"><label>Критерий <i>*</i></label><div class="val">${c.code} ${esc(c.title)}</div></div><div class="frow"><label>Оценка ИИ</label><div class="val">${bdg(c, r.value)}</div></div></div>
      <div class="quote"><div class="m">обоснование ИИ · ${esc(ev.model?.name)}</div>${esc(r.rationale)}</div>
      <div class="form"><div class="frow"><label>Предлагаемая оценка</label><div class="val"><div class="row wrap" id="pv">${opts}</div></div></div>
        <div class="frow"><label>Комментарий <i>*</i></label><div class="val"><textarea class="input" id="ap-comment" placeholder="Почему оценка неверна, со ссылкой на реплики"></textarea></div></div>
        <div class="frow"><label>Подал</label><div class="val"><input class="input" id="ap-by" value="${esc(state.role === "op" ? "оператор" : state.user)}"></div></div></div>
      <div class="msgbar info">Проверяющий увидит спорную оценку, комментарий и фрагмент диалога с репликами ${(r.evidence_turns || []).map(t => "#" + t).join(", ")}. Итог не меняется до решения.</div></div>
    <div class="qf"><button class="btn primary" onclick="submitAppeal(${ev.id},'${critId}','${esc(cid)}')">${ic("save")}Сохранить и закрыть</button><a class="btn" href="#/dialog/${esc(cid)}/c/${critId}">Отмена</a></div></div></div>`;
  return base + pane;
}
window.submitAppeal = async (evaluationId, critId, cid) => {
  const pv = document.querySelector("input[name=pv]:checked"); const comment = $("#ap-comment").value.trim(); if (!comment) return toast("Напишите комментарий", "warn");
  const val = pv ? (pv.value === "null" ? null : pv.value === "true" ? true : pv.value === "false" ? false : Number(pv.value)) : undefined;
  try { const body = { evaluation_id: evaluationId, criterion_id: critId, comment, submitted_by: $("#ap-by").value }; if (pv) body.proposed_value = val; await api("/api/appeals", { method: "POST", body }); toast("Апелляция создана", "good"); location.hash = "#/appeals"; } catch (e) { toast(e.message, "bad"); }
};

/* ---------- appeals ---------- */
async function pageAppeals() {
  await ensureChecklist(); const rows = await api(`/api/appeals`);
  const body = `<div class="cmdbar">${cmd("refresh", "Обновить", "", "render()")}<span class="cmdsep"></span>${cmd("export", "Экспорт в Excel")}${cmd("columns", "Изменить столбцы")}${cmd("filter", "Изменить фильтры")}</div>
    <div class="viewbar"><div class="viewsel">Открытые и решённые апелляции <span class="chev">${ic("chev")}</span></div></div>
    <div class="body" style="padding-top:0"><div class="panel"><table class="grid"><tr><th>Апелляция</th><th>Диалог</th><th>Критерий</th><th>Оценка ИИ</th><th>Предложено</th><th>Подал</th><th>Создана</th><th>Статус</th><th>Проверяющий</th><th>Итог</th></tr>
    ${rows.map(a => { const c = critOf(a.criterion_id); return `<tr><td><a href="#/appeal/${a.id}">#${a.id}</a></td><td><a href="#/dialog/${esc(a.conversation_id)}/c/${a.criterion_id}">${esc(a.conversation_id)}</a></td><td>${c.code} ${esc(c.title)}</td><td>${bdg(c, a.ai_value)}</td><td>${a.proposed_value === undefined || a.proposed_value === null && !c.allow_na ? "—" : bdg(c, a.proposed_value)}</td><td>${esc(a.submitted_by)}</td><td class="muted">${dt(a.created_at)}</td><td>${a.status === "open" ? `<span class="bdg warn">Открыта</span>` : `<span class="bdg neu">${a.decision === "confirm" ? "Подтверждена" : "Изменена"}</span>`}</td><td>${esc(a.reviewer || "—")}</td><td class="num">${a.score_after != null ? `${fmt2(a.score_before)} → ${fmt2(a.score_after)}` : fmt2(a.score_before)}</td></tr>`; }).join("")}
    ${!rows.length ? `<tr><td colspan="10" class="muted" style="text-align:center;padding:40px">Апелляций пока нет. Оператор подаёт их из карточки диалога кнопкой «Оспорить оценку».</td></tr>` : ""}
    </table><div class="gfoot"><span>Строк: ${rows.length}</span><span>SLA рассмотрения 24 ч</span></div></div></div>`;
  return shell("appeals", body);
}
async function pageAppeal(aid) {
  await ensureChecklist(); const rows = await api("/api/appeals"); const a = rows.find(x => x.id === +aid); if (!a) return shell("appeals", `<div class="body"><div class="panel"><div class="pb">Апелляция не найдена</div></div></div>`);
  const d = await api(`/api/conversations/${encodeURIComponent(a.conversation_id)}`); const ev = d.evaluation; const c = critOf(a.criterion_id); const r = ev.criteria[a.criterion_id];
  const vals = c.type === "scale" ? c.scale.map(s => `<label class="radio"><input type="radio" name="nv" value="${s[0]}"> ${s[0]}</label>`).join("") : `<label class="radio"><input type="radio" name="nv" value="true"> Да</label><label class="radio"><input type="radio" name="nv" value="false"> Нет</label>${c.allow_na ? `<label class="radio"><input type="radio" name="nv" value="null"> N/A</label>` : ""}`;
  const body = `<div class="cmdbar"><a class="cmd" href="#/appeals">${ic("back")}</a>${a.status === "open" ? `${cmd("check", "Подтвердить оценку", "", `decide(${a.id},'confirm')`)}${cmd("edit", "Изменить оценку", "", `decide(${a.id},'change')`)}` : ""}<span class="cmdsep"></span><a class="cmd" href="#/dialog/${esc(a.conversation_id)}/c/${a.criterion_id}">${ic("chat")}Открыть диалог</a></div>
    <div class="rec"><div class="rec-head"><div><div class="title">Апелляция #${a.id}<span class="st">· ${a.status === "open" ? "Ожидает решения" : "Решена"}</span></div><div class="ent">Апелляция · ${c.code} ${esc(c.title)}</div></div>
      <div class="hf"><div><b><a href="#/dialog/${esc(a.conversation_id)}">${esc(a.conversation_id)}</a></b><small>Диалог</small></div><div><b>${esc(a.submitted_by)}</b><small>Подал</small></div><div><b>${dt(a.created_at)}</b><small>Создана</small></div><div><b>${a.status === "open" ? "Открыта" : a.decision === "confirm" ? "Подтверждена" : "Изменена"}</b><small>Статус</small></div></div></div>
      <div class="ftabs"><a class="on" href="#">Сводка</a><a href="#/dialog/${esc(a.conversation_id)}/c/${a.criterion_id}">Диалог</a></div></div>
    <div class="body"><div class="cols c12"><div class="col" style="gap:8px">
      <div class="panel"><div class="ph"><span>Спорная оценка</span>${a.status === "open" ? `<span class="bdg warn">Ожидает решения</span>` : `<span class="bdg neu">Решена</span>`}</div><div class="pb"><div class="form">
        <div class="frow"><label>Критерий</label><div class="val">${c.code} ${esc(c.title)} <span class="muted" style="font-weight:400">· вес ${c.weight}</span></div></div><div class="frow"><label>Оценка ИИ</label><div class="val">${bdg(c, r.value)}</div></div><div class="frow"><label>Предложено</label><div class="val">${a.proposed_value === undefined ? "—" : bdg(c, a.proposed_value)}</div></div><div class="frow"><label>Правило</label><div class="val plain">${esc(c.yes_rule || "")}${c.allow_na ? ` <span class="muted">N/A — ${esc(c.na_rule || "")}</span>` : ""}</div></div></div>
        <div class="quote" style="margin-top:8px"><div class="m">обоснование ИИ · ${esc(ev.model?.name)}</div>${esc(r.rationale)}</div><div class="quote" style="border-color:#C19C00;margin-top:8px"><div class="m">аргумент · ${esc(a.submitted_by)} · ${dt(a.created_at)}</div>${esc(a.comment)}</div></div></div>
      <div class="panel"><div class="ph"><span>Решение проверяющего</span></div><div class="pb"><div class="form">
        ${a.status === "open" ? `<div class="frow"><label>Новое значение</label><div class="val"><div class="row wrap" style="gap:14px">${vals}</div><div class="small muted" style="margin-top:4px">нужно только для «Изменить оценку»</div></div></div>
          <div class="frow"><label>Причина <i>*</i></label><div class="val"><textarea class="input" id="dec-reason" placeholder="Почему подтверждаете или меняете, со ссылкой на правило чек-листа"></textarea></div></div>
          <div class="frow"><label>Проверяющий</label><div class="val"><input class="input" id="dec-reviewer" value="${esc(state.user)}"></div></div>
          <div class="frow"><label>Итог сейчас</label><div class="val num">${fmt2(a.score_before)}</div></div>
          <div class="frow"><label></label><div class="val"><div class="row"><button class="btn primary" onclick="decide(${a.id},'confirm')">${ic("check")}Подтвердить оценку ИИ</button><button class="btn" onclick="decide(${a.id},'change')">${ic("edit")}Изменить оценку</button></div></div></div>` :
        `<div class="frow"><label>Решение</label><div class="val">${a.decision === "confirm" ? "Оценка подтверждена" : "Оценка изменена на " + bdg(c, a.new_value)}</div></div><div class="frow"><label>Причина</label><div class="val plain">${esc(a.reason)}</div></div><div class="frow"><label>Проверяющий</label><div class="val">${esc(a.reviewer)} · ${dt(a.decided_at)}</div></div><div class="frow"><label>Итог</label><div class="val">исходный ${fmt2(a.score_before)} → финальный ${fmt2(a.score_after)}</div></div>`}
      </div></div></div></div>
      <div class="panel"><div class="ph"><span>Фрагмент диалога ${esc(a.conversation_id)}</span><a class="small" href="#/dialog/${esc(a.conversation_id)}/c/${a.criterion_id}">Весь транскрипт</a></div><div class="pb tight" style="padding-top:8px">${transcript(d.turns, ev, a.criterion_id, true)}</div></div></div></div>`;
  return shell("appeals", body, { tabs: [[`Апелляция #${a.id}`, "scale", true, `#/appeal/${a.id}`]] });
}
window.decide = async (aid, decision) => {
  const reason = $("#dec-reason")?.value.trim(); if (!reason) return toast("Укажите причину решения", "warn");
  const nv = document.querySelector("input[name=nv]:checked"); if (decision === "change" && !nv) return toast("Выберите новое значение", "warn");
  const body = { decision, reason, reviewer: $("#dec-reviewer")?.value }; if (decision === "change") body.new_value = nv.value === "null" ? null : nv.value === "true" ? true : nv.value === "false" ? false : Number(nv.value);
  try { const r = await api(`/api/appeals/${aid}/decision`, { method: "POST", body }); toast(`Решение сохранено${r.final_after_appeals ? " · итог " + fmt2(r.final_after_appeals.final_score) : ""}`, "good"); render(); } catch (e) { toast(e.message, "bad"); }
};

/* ---------- checklists ---------- */
async function pageChecklists(editId, applyMode) {
  const all = await api("/api/checklists"); state.checklists = all; const cl = all.find(c => c.id === +(state.clView || 0)) || all.find(c => c.is_active) || all[0]; state.checklist = all.find(c => c.is_active) || all[0];
  const editC = editId ? cl.criteria.find(c => c.id === editId) : null;
  const body = `<div class="cmdbar"><a class="cmd" href="#/dialogs">${ic("back")}</a>${cmd("add", "Критерий", "", "newCriterion()")}${cmd("upload", "Импорт JSON", "", "importChecklist()")}<a class="cmd" href="${API}/api/checklists/${cl.id}" target="_blank">${ic("export")}Экспорт JSON</a><span class="cmdsep"></span>${cmd("play", "Применить к диалогам", "", "location.hash='#/checklists/apply'")}${cl.is_active ? "" : `<button class="cmd primary" onclick="activate(${cl.id})">${ic("check")}Активировать версию</button>`}</div>
    <div class="rec"><div class="rec-head"><div><div class="title">${esc(cl.name)}<span class="st">· версия ${cl.version}${cl.is_active ? ", активна" : ""}</span></div><div class="ent">Чек-лист · канал: ${esc(cl.channel)} · ${cl.criteria.length} критериев · ${esc(cl.note || "")}</div></div>
      <div class="hf"><div><b>${cl.criteria.filter(c => c.type !== "flag").reduce((s, c) => s + c.weight, 0)}</b><small>Сумма весов</small></div><div><b>${cl.criteria.length}</b><small>Критериев</small></div><div><b>${dt(cl.created_at)}</b><small>Создана</small></div><div><b>${esc(cl.created_by || "—")}</b><small>Автор</small></div></div></div>
      <div class="ftabs">${all.map(v => `<a class="${v.id === cl.id ? "on" : ""}" href="#/checklists" onclick="state.clView=${v.id}">v${v.version}${v.is_active ? " · активна" : ""}</a>`).join("")}</div></div>
    <div class="body"><div class="cols" style="grid-template-columns:minmax(0,1fr) 360px"><div class="col" style="gap:8px">
      <div class="panel"><table class="grid auto"><tr><th>№</th><th>Критерий</th><th>Тип ответа</th><th>Вес</th><th>N/A</th><th></th></tr>
        ${cl.criteria.map(c => `<tr class="${editC?.id === c.id ? "sel" : ""}"><td class="mono">${esc(c.code)}</td><td><a href="#/checklists/edit/${c.id}">${esc(c.title)}</a><div class="small muted">${esc(c.section || "")}</div></td><td>${c.type === "binary" ? "Да / Нет" : c.type === "scale" ? `Шкала ${(c.scale || []).map(s => s[0]).join("/")}` : "Флаг"}</td><td class="num sb">${c.weight || "—"}</td><td>${c.allow_na ? "Разрешён" : "—"}</td><td><a class="btn sm" href="#/checklists/edit/${c.id}">${ic("edit")}</a></td></tr>`).join("")}
      </table><div class="gfoot"><span>${cl.criteria.length} критериев · сумма весов применимых ${cl.criteria.filter(c => c.type !== "flag").reduce((s, c) => s + c.weight, 0)}</span><span></span></div></div>
      ${editC ? `<div class="panel" id="edit"><div class="ph"><span>Критерий ${esc(editC.code)} · ${esc(editC.title)}</span><span class="small muted">сохранение создаёт новую версию; прошлые оценки не меняются</span></div><div class="pb"><div class="cols c2"><div class="form">
          <div class="frow"><label>Код</label><div class="val"><input class="input" id="e-code" value="${esc(editC.code)}" style="width:80px"></div></div>
          <div class="frow"><label>Название <i>*</i></label><div class="val"><input class="input" id="e-title" value="${esc(editC.title)}"></div></div>
          <div class="frow"><label>Секция</label><div class="val"><input class="input" id="e-section" value="${esc(editC.section || "")}"></div></div>
          <div class="frow"><label>Тип ответа <i>*</i></label><div class="val"><select class="input" id="e-type"><option value="binary" ${editC.type === "binary" ? "selected" : ""}>Да / Нет</option><option value="scale" ${editC.type === "scale" ? "selected" : ""}>Шкала</option><option value="flag" ${editC.type === "flag" ? "selected" : ""}>Флаг нарушения</option></select></div></div>
          <div class="frow"><label>Вес <i>*</i></label><div class="val"><input class="input" id="e-weight" style="width:100px" value="${editC.weight}"></div></div>
          <div class="frow"><label>N/A допустим</label><div class="val"><label class="tog"><input type="checkbox" id="e-na" ${editC.allow_na ? "checked" : ""} style="width:16px;height:16px"> разрешить N/A</label></div></div></div>
        <div class="form"><div class="frow"><label>Условие «Да»</label><div class="val"><textarea class="input" id="e-yes">${esc(editC.yes_rule || "")}</textarea></div></div>
          <div class="frow"><label>Условие N/A</label><div class="val"><input class="input" id="e-narule" value="${esc(editC.na_rule || "")}"></div></div>
          <div class="frow"><label>Ступени шкалы</label><div class="val"><textarea class="input" id="e-scale" placeholder="20: описание (по строке на ступень)">${(editC.scale || []).map(s => `${s[0]}: ${s[1]}`).join("\n")}</textarea></div></div>
          <div class="frow"><label>Пояснение для модели</label><div class="val"><textarea class="input" id="e-guidance">${esc(editC.guidance || "")}</textarea></div></div></div></div>
        <div class="row" style="margin-top:8px"><button class="btn primary" onclick="saveCriterion(${cl.id},'${editC.id}',false)">${ic("save")}Сохранить как версию ${Math.max(...all.filter(x => x.key === cl.key).map(x => x.version)) + 1}</button><button class="btn" onclick="saveCriterion(${cl.id},'${editC.id}',true)">${ic("check")}Сохранить и активировать</button><button class="btn" onclick="removeCriterion(${cl.id},'${editC.id}')">${ic("close")}Удалить критерий</button><a class="btn lnk" href="#/checklists">Отмена</a></div></div></div>` : ""}
    </div><div class="col" style="gap:8px"><div class="panel"><div class="ph"><span>Версии</span></div>${all.filter(v => v.key === cl.key).map(v => `<div class="prov"><div><div class="nm">v${v.version} ${v.is_active ? `<span class="bdg ok">Активна</span>` : `<span class="bdg neu">Версия</span>`}</div><div class="mt">${dt(v.created_at)} · ${esc(v.created_by || "")}</div><div class="small" style="margin-top:4px">${esc(v.note || "")}</div></div><div class="col" style="gap:4px"><button class="btn sm" onclick="state.clView=${v.id};render()">Открыть</button>${v.is_active ? "" : `<button class="btn sm" onclick="activate(${v.id})">Активировать</button>`}${v.id !== cl.id ? `<button class="btn sm" onclick="diffVersions(${cl.id},${v.id})">Сравнить</button>` : ""}</div></div>`).join("")}</div>
      <div class="panel"><div class="ph"><span>Правила расчёта</span></div><div class="pb small" style="display:flex;flex-direction:column;gap:6px"><div>1. N/A только там, где разрешён и выполнено условие.</div><div>2. «Да» — полный вес, «Нет» — 0, шкала — вес × ступень / верхняя ступень.</div><div>3. N/A исключаются, веса перераспределяются: итог = Σ баллов / Σ весов применимых × 100.</div><div>4. Округление до 2 знаков half-up; грубые ошибки — отдельный флаг.</div><div class="formula">пример: 55,5 / 65 × 100 = 85,38</div></div></div></div></div>
    ${applyMode ? `<div class="modal-wrap"><div class="modal"><div class="mh"><h2>Применить версию ${cl.version} к диалогам набора ${esc(state.group)}</h2><a class="btn sm lnk" href="#/checklists">${ic("close")}</a></div><div class="mb">
      <div class="msgbar info">Каждый диалог будет оценён заново по версии ${cl.version}. Вызовы с неизменёнными критериями берутся из кеша, если они уже делались в этой сессии.</div>
      <div class="form"><div class="frow" style="grid-template-columns:120px 1fr"><label>Область</label><div class="val"><label class="radio"><input type="radio" name="scope" value="all" checked> Все диалоги набора</label> <label class="radio"><input type="radio" name="scope" value="unevaluated"> Только неоценённые по этой версии</label></div></div></div></div>
      <div class="mf"><a class="btn" href="#/checklists">Отмена</a><button class="btn primary" onclick="applyChecklist(${cl.id})">${ic("play")}Запустить переоценку</button></div></div></div>` : ""}
    <div id="diff"></div>`;
  return shell("checklists", body, { tabs: [[cl.name, "check", true, "#/checklists"]] });
}
function readCriterionForm(orig) {
  const scale = $("#e-scale").value.split("\n").map(l => l.trim()).filter(Boolean).map(l => { const m = l.match(/^(\d+)\s*[:—-]\s*(.*)$/); return m ? [Number(m[1]), m[2]] : null; }).filter(Boolean);
  return { ...orig, code: $("#e-code").value.trim(), title: $("#e-title").value.trim(), section: $("#e-section").value.trim(), type: $("#e-type").value, weight: Number($("#e-weight").value || 0), allow_na: $("#e-na").checked, yes_rule: $("#e-yes").value.trim(), na_rule: $("#e-narule").value.trim(), scale, guidance: $("#e-guidance").value.trim() };
}
async function saveVersion(baseId, criteria, note, activate) {
  const base = state.checklists.find(c => c.id === baseId);
  try { const v = await api("/api/checklists", { method: "POST", body: { base_id: baseId, note, created_by: state.user, activate, definition: { general_rules: base.general_rules, sections: base.sections, criteria } } }); state.clView = v.id; state.checklist = null; toast(`Сохранена версия ${v.version}${activate ? " и активирована" : ""}`, "good"); location.hash = "#/checklists"; render(); } catch (e) { toast(e.message, "bad", 8000); }
}
window.saveCriterion = async (clId, critId, activate) => { const cl = state.checklists.find(c => c.id === clId); const criteria = cl.criteria.map(c => c.id === critId ? readCriterionForm(c) : c); await saveVersion(clId, criteria, `Изменён критерий ${critId}`, activate); };
window.removeCriterion = async (clId, critId) => { if (!confirm("Удалить критерий из новой версии?")) return; const cl = state.checklists.find(c => c.id === clId); await saveVersion(clId, cl.criteria.filter(c => c.id !== critId), `Удалён критерий ${critId}`, false); };
window.newCriterion = async () => { const cl = state.checklists.find(c => c.id === +(state.clView || 0)) || state.checklist; const id = prompt("Идентификатор нового критерия (латиница, например followup):"); if (!id) return; const title = prompt("Название критерия:"); if (!title) return; const weight = Number(prompt("Вес:", "10") || 0);
  await saveVersion(cl.id, [...cl.criteria, { id: id.trim().toLowerCase(), code: String(cl.criteria.length + 1).padStart(2, "0"), title: title.trim(), section: cl.sections?.[0] || "", type: "binary", weight, allow_na: false, yes_rule: "", na_rule: "", scale: [], guidance: "" }], `Добавлен критерий ${id}`, false); location.hash = `#/checklists/edit/${id.trim().toLowerCase()}`; };
window.activate = async (id) => { try { await api(`/api/checklists/${id}/activate`, { method: "POST" }); state.checklist = null; toast("Версия активирована", "good"); render(); } catch (e) { toast(e.message, "bad"); } };
window.applyChecklist = async (clId) => { const scope = document.querySelector("input[name=scope]:checked")?.value; location.hash = "#/checklists"; startJob({ checklist_version_id: clId, only_unevaluated: scope === "unevaluated", parallel_dialogs: 3 }); };
window.importChecklist = async () => { const txt = prompt("Вставьте JSON чек-листа (как в экспорте):"); if (!txt) return; try { const d = JSON.parse(txt); await api("/api/checklists", { method: "POST", body: { note: "Импорт JSON", created_by: state.user, definition: { general_rules: d.general_rules, sections: d.sections, criteria: d.criteria } } }); state.checklist = null; toast("Импортировано", "good"); render(); } catch (e) { toast(e.message, "bad", 8000); } };
window.diffVersions = async (a, b) => { try { const r = await api(`/api/checklists/${a}/diff`, { method: "POST", body: { group_id: state.group, other_id: b } }); $("#diff").innerHTML = `<div class="modal-wrap" onclick="this.remove()"><div class="modal" onclick="event.stopPropagation()"><div class="mh"><h2>Сравнение v${r.a} → v${r.b} · набор ${esc(state.group)}</h2><button class="btn sm lnk" onclick="document.getElementById('diff').innerHTML=''">${ic("close")}</button></div><div class="mb"><table class="grid"><tr><th>Диалог</th><th>Итог v${r.a}</th><th>Итог v${r.b}</th><th>Δ</th><th>Изменились критерии</th></tr>${r.rows.map(x => `<tr><td>${esc(x.conversation_id)}</td><td class="num">${fmt2(x.score_a)}</td><td class="num">${fmt2(x.score_b)}</td><td class="num" style="color:${x.delta > 0 ? "var(--good)" : x.delta < 0 ? "var(--bad)" : "inherit"}">${x.delta == null ? "—" : (x.delta > 0 ? "+" : "") + fmt2(x.delta)}</td><td class="muted">${x.changed_criteria.join(", ") || "—"}</td></tr>`).join("")}${!r.rows.length ? `<tr><td colspan="5" class="muted" style="padding:20px;text-align:center">Нет оценок для сравнения</td></tr>` : ""}</table></div></div></div>`; } catch (e) { toast(e.message, "bad"); } };

/* ---------- runs & trace ---------- */
async function pageRuns(traceId) {
  await ensureChecklist(); const [jobs, calls] = await Promise.all([api("/api/jobs?limit=15"), api("/api/llm-calls?limit=60")]);
  const j = jobs[0]; const st = { done: ["ok", "Готово"], running: ["info", "Выполняется"], queued: ["neu", "В очереди"], failed: ["no", "Ошибка"] };
  const sel = traceId != null ? calls.find(c => c.id === +traceId) : null;
  const body = `<div class="cmdbar">${cmd("refresh", "Обновить", "", "render()")}<span class="cmdsep"></span><a class="cmd" href="${API}/api/llm-calls?limit=1000" target="_blank">${ic("export")}Экспорт журнала JSON</a><a class="cmd" href="${API}/metrics" target="_blank">${ic("chart")}Метрики Prometheus</a></div>
    <div class="viewbar"><div class="viewsel">Запуски оценки ${j ? `· #${j.id} · набор ${esc(j.group_id)}` : ""} <span class="chev">${ic("chev")}</span></div>${j ? `<span class="bdg ${st[j.status][0]}">${st[j.status][1]} · ${j.done} из ${j.total}</span>` : ""}</div>
    <div class="body" style="padding-top:0">${j ? `<div class="cols c4"><div class="tile"><div class="l">Прогресс</div><div class="v">${j.done} / ${j.total}</div><div class="d">${j.started_at ? "старт " + dt(j.started_at) : ""}${j.finished_at ? " · финиш " + dt(j.finished_at) : ""}</div></div><div class="tile"><div class="l">Ошибок</div><div class="v" style="color:${j.failed ? "var(--bad)" : "var(--ink)"}">${j.failed}</div><div class="d">${esc(j.error || "диалоги со статусом error остаются в results.json")}</div></div><div class="tile"><div class="l">Стоимость</div><div class="v">$${j.cost_usd.toFixed(3)}</div><div class="d">чек-лист v${state.checklists?.find(c => c.id === j.checklist_version_id)?.version || "?"}</div></div><div class="tile"><div class="l">Режим</div><div class="v" style="font-size:20px">${j.options?.second_opinion ? "hybrid" : "external_api"}</div><div class="d">параллельно ${j.options?.parallel_dialogs || 1} диалогов</div></div></div>` : ""}
    <div class="cols stretch" style="grid-template-columns:minmax(0,4fr) minmax(0,8fr)"><div class="panel"><div class="ph"><span>Запуски</span></div><table class="grid"><tr><th>#</th><th>Набор</th><th>Статус</th><th>Готово</th><th>$</th></tr>${jobs.map(x => `<tr><td>${x.id}</td><td>${esc(x.group_id)}</td><td><span class="bdg ${st[x.status][0]}">${st[x.status][1]}</span></td><td class="num">${x.done} / ${x.total}${x.failed ? ` <span class="bdg no">${x.failed}</span>` : ""}</td><td class="num">$${x.cost_usd.toFixed(3)}</td></tr>`).join("")}${!jobs.length ? `<tr><td colspan="5" class="muted" style="padding:20px;text-align:center">Запусков ещё не было</td></tr>` : ""}</table></div>
      <div class="panel"><div class="ph"><span>Журнал вызовов модели</span><span class="small muted">каждый вызов: промпт, ответ, токены, стоимость</span></div><table class="grid"><tr><th>Время</th><th>Диалог</th><th>Критерий</th><th>Модель</th><th>Токены</th><th>Статус</th></tr>
        ${calls.map(c => `<tr class="${sel?.id === c.id ? "sel" : ""}" onclick="location.hash='#/runs/trace/${c.id}'" style="cursor:pointer"><td class="mono">${new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(c.created_at) ? c.created_at : c.created_at + "Z").toLocaleTimeString("ru-RU")}</td><td>${esc(c.conversation_id)}</td><td class="ell" style="max-width:240px">${critOf(c.criterion_id).code} ${esc(critOf(c.criterion_id).title)}</td><td class="ell" style="max-width:140px">${esc(c.provider)}/${esc(c.model)}</td><td class="num">${c.tokens_in} → ${c.tokens_out}</td><td><span class="bdg ${c.status === "ok" ? "ok" : c.status === "cache" ? "neu" : "warn"}">${esc(c.status)}</span></td></tr>`).join("")}</table>
        ${sel ? `<div class="pb" style="border-top:1px solid var(--line2)"><div class="row between" style="margin:8px 0"><span class="sb">Вызов #${sel.id} · ${esc(sel.conversation_id)} · ${critOf(sel.criterion_id).code}</span><span class="small muted">${(sel.latency_ms / 1000).toFixed(1)} с · $${sel.cost_usd.toFixed(4)} · prompt sha256 ${esc(sel.prompt_sha256)}</span></div><div class="small muted" style="margin-bottom:4px">Ответ модели (JSON по схеме)</div><div class="code">${esc((() => { try { return JSON.stringify(JSON.parse(sel.response_text), null, 2); } catch (_) { return sel.response_text; } })())}</div></div>` : ""}</div></div></div>`;
  return shell("runs", body);
}

/* ---------- violations ---------- */
async function pageViolations() {
  await ensureChecklist(); const st = await api(`/api/stats?group_id=${encodeURIComponent(state.group)}`);
  const sub = r => /обход/i.test(r || "") ? "Предложение услуги в обход компании" : /оскорб/i.test(r || "") ? "Оскорбление клиента" : /раскрыт|конфиденц/i.test(r || "") ? "Раскрытие конфиденциальной информации" : "Грубое нарушение";
  const counts = {}; st.violations.forEach(v => { const k = sub(v.rationale); counts[k] = (counts[k] || 0) + 1; });
  const body = `<div class="cmdbar">${cmd("refresh", "Обновить", "", "render()")}<span class="cmdsep"></span>${cmd("export", "Экспорт в Excel")}${cmd("filter", "Изменить фильтры")}</div>
    <div class="viewbar"><div class="viewsel">Грубые нарушения · набор ${esc(state.group)} <span class="chev">${ic("chev")}</span></div></div>
    <div class="body" style="padding-top:0"><div class="cols c3">${["Предложение услуги в обход компании", "Раскрытие конфиденциальной информации", "Оскорбление клиента"].map(t => `<div class="tile"><div class="l">${t}</div><div class="v" style="color:${counts[t] ? "var(--bad)" : "var(--ink)"}">${counts[t] || 0}</div><div class="d">из ${st.evaluated} оценённых</div></div>`).join("")}</div>
    <div class="panel"><table class="grid"><tr><th>Диалог</th><th>Язык</th><th>Подтип</th><th>Обоснование</th><th>Реплики</th><th>Итог</th></tr>${st.violations.map(v => `<tr><td><a href="#/dialog/${esc(v.conversation_id)}/c/critical">${esc(v.conversation_id)}</a></td><td>${lang(v.language)}</td><td><span class="bdg flag">${sub(v.rationale)}</span></td><td class="wrap muted" style="white-space:normal">${esc(v.rationale)}</td><td class="mono">${(v.evidence_turns || []).map(t => "#" + t).join(", ")}</td><td>${sbar(v.final_score)}</td></tr>`).join("")}${!st.violations.length ? `<tr><td colspan="6" class="muted" style="padding:30px;text-align:center">Грубых нарушений не выявлено</td></tr>` : ""}</table><div class="gfoot"><span>Строк: ${st.violations.length}</span><span></span></div></div></div>`;
  return shell("violations", body);
}

/* ---------- analytics ---------- */
async function pageAnalytics() {
  await ensureChecklist(); const st = await api(`/api/stats?group_id=${encodeURIComponent(state.group)}`);
  const dist = st.distribution; const maxD = Math.max(1, ...Object.values(dist));
  const weakest = st.pass_rate.filter(p => p.applicable && p.pass !== undefined).sort((a, b) => a.pass / a.applicable - b.pass / b.applicable)[0];
  const body = `<div class="cmdbar">${cmd("refresh", "Обновить всё", "", "render()")}${cmd("dash", "Выбрать панель")}<span class="cmdsep"></span><a class="cmd" href="${API}/api/stats?group_id=${esc(state.group)}" target="_blank">${ic("export")}Экспорт JSON</a></div>
    <div class="viewbar"><div class="viewsel">Качество обслуживания · набор ${esc(state.group)} <span class="chev">${ic("chev")}</span></div></div>
    <div class="body" style="padding-top:0"><div class="cols c4"><div class="tile"><div class="l">Средний итог</div><div class="v num">${fmt2(st.avg)}</div><div class="d">медиана ${fmt2(st.median)}</div></div><div class="tile"><div class="l">Доля диалогов ≥ 80</div><div class="v">${st.evaluated ? Math.round(((dist["80-90"] + dist["90-100"]) / st.evaluated) * 100) : 0}%</div><div class="d">${dist["80-90"] + dist["90-100"]} из ${st.evaluated}</div></div><div class="tile"><div class="l">Самый слабый критерий</div><div class="v" style="font-size:18px;line-height:36px">${weakest ? `${weakest.code} ${esc(weakest.title)}` : "—"}</div><div class="d bad">${weakest ? `выполнен в ${Math.round((weakest.pass / weakest.applicable) * 100)}%` : ""}</div></div><div class="tile"><div class="l">Грубые нарушения</div><div class="v" style="color:${st.critical ? "var(--bad)" : "var(--ink)"}">${st.critical}</div><div class="d">${st.evaluated ? ((st.critical / st.evaluated) * 100).toFixed(1) : 0}% диалогов</div></div></div>
    <div class="cols c2"><div class="panel"><div class="ph"><span>Выполнение критериев</span><span class="small muted">доля «Да» или верхней ступени среди применимых</span></div><div class="pb">${st.pass_rate.filter(p => p.pass !== undefined).map(p => { const pct = p.applicable ? Math.round((p.pass / p.applicable) * 100) : 0; return `<div class="hbar"><span>${p.code} ${esc(p.title)}</span><span class="b" style="--w:${pct}%;--c:${pct < 50 ? "var(--bad)" : pct < 80 ? "#C19C00" : "var(--brand)"}"></span><span class="num" style="text-align:right">${pct}%</span></div>`; }).join("")}</div></div>
      <div class="panel"><div class="ph"><span>Распределение итогов</span></div><div class="pb"><div class="row" style="align-items:flex-end;gap:16px;height:170px;padding:0 8px">${Object.entries(dist).map(([l, n]) => `<div class="grow col" style="align-items:center;gap:6px;height:100%;justify-content:flex-end"><span class="small num">${n}</span><div style="width:100%;height:${(n / maxD) * 120}px;background:${l === "0-40" ? "var(--bad)" : l === "40-60" ? "#C19C00" : "var(--brand)"}"></div><span class="small muted">${l.replace("-", "–")}</span></div>`).join("")}</div></div></div>
      <div class="panel"><div class="ph"><span>По языкам</span></div><table class="grid"><tr><th>Язык</th><th>Диалогов</th><th>Средний итог</th></tr>${Object.entries(st.by_language).map(([l, v]) => `<tr><td>${lang(l)} ${{ RU: "Русский", KZ: "Казахский", EN: "Английский" }[l] || l}</td><td class="num">${v.n}</td><td>${sbar(v.avg)}</td></tr>`).join("")}</table></div>
      <div class="panel"><div class="ph"><span>N/A и флаги</span></div><table class="grid"><tr><th>Критерий</th><th>Применим</th><th>N/A</th></tr>${st.pass_rate.map(p => `<tr><td>${p.code} ${esc(p.title)}</td><td class="num">${p.applicable}</td><td class="num">${p.na ?? "—"}</td></tr>`).join("")}</table></div></div></div>`;
  return shell("analytics", body);
}

/* ---------- settings ---------- */
async function pageSettings() {
  const s = await api("/api/settings"); state.settings = s; const groups = await api("/api/datasets");
  const body = `<div class="cmdbar"><a class="cmd" href="#/dialogs">${ic("back")}</a>${cmd("refresh", "Проверить провайдеров", "", "checkProviders()")}${cmd("upload", "Загрузить набор", "", "fetchGroup()")}<a class="cmd" href="${API}/api/docs" target="_blank">${ic("doc")}API</a></div>
    <div class="rec"><div class="rec-head"><div><div class="title">Модели и источники данных</div><div class="ent">Параметры из окружения (.env) · команда ${esc(s.team_name)}</div></div><div class="hf"><div><b>${esc(s.provider_chain[0] || "—")} · ${esc(s.primary_model || "")}</b><small>Основная модель</small></div><div><b>${esc(s.second_opinion || "выкл")}</b><small>Второе мнение</small></div><div><b>${s.llm_parallel}</b><small>Параллельность</small></div><div><b>$${s.budget_usd}</b><small>Бюджет на сессию</small></div><div><b>${esc(s.database)} · ${esc(s.queue)}</b><small>БД · очередь</small></div></div></div></div>
    <div class="body"><div class="cols c12"><div class="col" style="gap:8px"><div class="panel"><div class="ph"><span>Цепочка провайдеров</span><span class="small muted">при ошибке или лимите запрос уходит следующему</span></div>
      ${s.provider_chain.map((p, i) => `<div class="prov"><div><div class="nm">${esc(p)} <span class="bdg ${i === 0 ? "ok" : "info"}">${i === 0 ? "Основная" : "Резерв " + i}</span> <span id="ph-${p}"></span></div><div class="mt">${{ openai: "Structured Outputs (JSON Schema strict)", anthropic: "tool use → JSON", gemini: "OpenAI-совместимый endpoint", deepseek: "OpenAI-совместимый endpoint", ollama: "локально, OpenAI-совместимый endpoint", lmstudio: "локально, OpenAI-совместимый endpoint", rules: "офлайн-правила из фактов кода (последний резерв)" }[p] || ""}</div></div></div>`).join("")}
      <div class="pb" style="border-top:1px solid var(--line2)"><div class="form"><div class="frow"><label>Маскирование ПДн</label><div class="val plain">${s.mask_pii ? "включено: ИИН, телефоны, e-mail, номера счетов заменяются до отправки модели" : "выключено"}</div></div><div class="frow"><label>Режим в results.json</label><div class="val plain">определяется по журналу вызовов: external_api, local или hybrid</div></div><div class="frow"><label>Доступные провайдеры</label><div class="val plain">${s.providers.map(p => `<span class="bdg ${p.configured ? "ok" : "neu"}" style="margin:0 4px 4px 0">${esc(p.id)}</span>`).join("")}</div></div></div></div></div></div>
    <div class="col" style="gap:8px"><div class="panel"><div class="ph"><span>Источник данных</span><span class="bdg ${s.org_api_configured ? "ok" : "warn"}">${s.org_api_configured ? "API организаторов настроен" : "API не настроен"}</span></div><div class="pb"><div class="form"><div class="frow"><label>Наборы</label><div class="val plain">${groups.map(g => `<div class="row between" style="padding:2px 0"><span>${esc(g.group_id)}</span><span class="muted">${g.dialogs} диалогов · оценено ${g.evaluated} · ${dt(g.fetched_at)}</span></div>`).join("") || "—"}</div></div><div class="frow"><label></label><div class="val"><button class="btn primary" onclick="fetchGroup()">${ic("upload")}Загрузить набор по group_id</button></div></div></div></div></div>
      <div class="panel"><div class="ph"><span>Система</span></div><div class="pb"><div class="form"><div class="frow"><label>Версия</label><div class="val plain mono">1.0.0</div></div><div class="frow"><label>Метрики</label><div class="val plain"><a href="${API}/metrics" target="_blank">/metrics</a> (Prometheus)</div></div><div class="frow"><label>Документация API</label><div class="val plain"><a href="${API}/api/docs" target="_blank">/api/docs</a></div></div></div></div></div></div></div></div>`;
  return shell("settings", body);
}
window.checkProviders = async () => { toast("Проверяю провайдеров…"); try { const r = await api("/api/providers/check", { method: "POST" }); r.providers.forEach(p => { const el = document.getElementById(`ph-${p.id}`); if (el) el.innerHTML = `<span class="bdg ${p.healthy ? "ok" : "no"}">${p.healthy ? "в сети" : "недоступен"} · ${esc(p.model)}</span>`; }); toast(`Проверено · потрачено $${r.spent_usd}`, "good"); } catch (e) { toast(e.message, "bad"); } };

/* ---------- export ---------- */
async function pageExport() {
  const [runs, preview] = await Promise.all([api("/api/export/runs"), api(`/api/export/preview?group_id=${encodeURIComponent(state.group)}`)]);
  const doc = preview.document; const ok = doc.results.filter(r => r.status === "ok").length; const target = state.group === "DEV" ? "dev" : "prod";
  const checks = [["schema_version = \"1.0\", team_name, model.mode", true], ["Ровно 8 критериев на диалог, каждый по разу", !preview.problems.some(p => /exactly the 8/.test(p))], ["value по типу критерия", !preview.problems.some(p => /out of domain/.test(p))], ["evidence_turns в пределах транскрипта, нумерация с 1", !preview.problems.some(p => /evidence/.test(p))], ["critical_flag = critical.value", !preview.problems.some(p => /critical_flag/.test(p))], ["final_score с 2 знаками", !preview.problems.some(p => /decimals/.test(p))], ["Нет дублей conversation_id", !preview.problems.some(p => /duplicate/.test(p))], [`Все ${doc.results.length} диалогов набора со статусом ok`, ok === doc.results.length && doc.results.length > 0]];
  const body = `<div class="cmdbar"><a class="cmd" href="#/dialogs">${ic("back")}</a>${cmd("refresh", "Обновить", "", "render()")}<span class="cmdsep"></span><a class="cmd" href="${API}/api/export/preview?group_id=${esc(state.group)}" target="_blank">${ic("doc")}Предпросмотр JSON</a><button class="cmd primary" onclick="doExport('${target}')">${ic("save")}Записать results/${target}/results.json</button></div>
    <div class="rec"><div class="rec-head"><div><div class="title">Сдача результатов<span class="st">· набор ${esc(state.group)} → results/${target}</span></div><div class="ent">results.json по контракту организаторов 1.0 · только значения модели · апелляции не влияют на файл</div></div><div class="hf"><div><b>${ok} / ${doc.results.length}</b><small>оценено ok</small></div><div><b>${esc(doc.model.mode)}</b><small>model.mode</small></div><div><b class="ell" style="max-width:260px;display:block">${esc(doc.model.name)}</b><small>model.name</small></div><div><b>${preview.problems.length ? `<span style="color:var(--bad)">${preview.problems.length}</span>` : "0"}</b><small>замечаний валидатора</small></div></div></div></div>
    <div class="body"><div class="cols c12"><div class="col" style="gap:8px"><div class="panel"><div class="ph"><span>Предпросмотр results.json</span><span class="bdg ${preview.problems.length ? "warn" : "ok"}">${preview.problems.length ? "есть замечания" : "валиден"}</span></div><div class="pb"><div class="code" style="max-height:520px">${esc(JSON.stringify({ ...doc, results: doc.results.slice(0, 2) }, null, 2))}\n… ещё ${Math.max(0, doc.results.length - 2)} записей</div></div></div></div>
      <div class="col" style="gap:8px"><div class="panel"><div class="ph"><span>Проверки перед push</span><span class="small muted">JSON Schema + семантика</span></div><div class="pb">${checks.map(([t, okk]) => `<div class="chk"><span class="${okk ? "ok" : "pend"}">${okk ? "✓" : "✗"}</span><span>${esc(t)}</span></div>`).join("")}${preview.problems.length ? `<div class="msgbar warn" style="margin-top:8px">${preview.problems.slice(0, 6).map(esc).join("<br>")}</div>` : ""}</div></div>
      <div class="panel"><div class="ph"><span>История экспортов</span></div><table class="grid"><tr><th>Когда</th><th>Цель</th><th>Набор</th><th>Записей</th><th>Валиден</th></tr>${runs.map(r => `<tr><td class="muted">${dt(r.created_at)}</td><td>${esc(r.target)}</td><td>${esc(r.group_id)}</td><td class="num">${r.records}</td><td>${r.valid ? `<span class="bdg ok">да</span>` : `<span class="bdg no" title="${esc(r.problems.join("; "))}">нет</span>`}</td></tr>`).join("")}${!runs.length ? `<tr><td colspan="5" class="muted" style="padding:20px;text-align:center">Экспортов ещё не было</td></tr>` : ""}</table></div>
      <div class="msgbar info">Контрольный час: «Загрузить набор» с новым group_id → «Оценить все неоценённые» → здесь «Записать results/prod» → commit и push. Файл формирует код, ручное редактирование запрещено. В консоли то же самое делает одна команда: <span class="mono">make prod GROUP=&lt;group_id&gt;</span>.</div></div></div></div>`;
  return shell("export", body);
}
window.doExport = async (target) => { try { const r = await api("/api/export", { method: "POST", body: { group_id: state.group, target, expected_count: target === "prod" ? 10 : undefined } }); toast(`${r.path}: ${r.records} записей · ${r.valid ? "валиден" : "ЕСТЬ ЗАМЕЧАНИЯ: " + r.problems.slice(0, 2).join("; ")}`, r.valid ? "good" : "warn", 10000); render(); } catch (e) { toast(e.message, "bad", 8000); } };

/* ---------- router ---------- */
async function render() {
  const h = location.hash.replace(/^#\/?/, "") || "dialogs"; const p = h.split("/"); let html;
  try {
    if (p[0] === "dialogs") html = await pageDialogs();
    else if (p[0] === "dialog" && p[2] === "appeal") html = await pageAppealNew(decodeURIComponent(p[1]), p[3]);
    else if (p[0] === "dialog") html = await pageDialog(decodeURIComponent(p[1]), p[2] === "c" ? p[3] : null);
    else if (p[0] === "appeals") html = await pageAppeals();
    else if (p[0] === "appeal") html = await pageAppeal(p[1]);
    else if (p[0] === "checklists") html = await pageChecklists(p[1] === "edit" ? p[2] : null, p[1] === "apply");
    else if (p[0] === "runs") html = await pageRuns(p[1] === "trace" ? p[2] : null);
    else if (p[0] === "violations") html = await pageViolations();
    else if (p[0] === "analytics") html = await pageAnalytics();
    else if (p[0] === "settings") html = await pageSettings();
    else if (p[0] === "export") html = await pageExport();
    else html = await pageDialogs();
  } catch (e) { html = shell(p[0], `<div class="body"><div class="msgbar bad">Ошибка: ${esc(e.message)}. Проверьте, что API запущен (${API || location.origin}/api/health).</div></div>`); }
  document.getElementById("root").innerHTML = html;
}
window.render = render; window.state = state;
window.addEventListener("hashchange", render); render();
