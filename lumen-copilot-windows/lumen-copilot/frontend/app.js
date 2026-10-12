/* Lumen app runtime: renders any page purely from /api/meta and exposes an action API that the
   copilot (and Playwright) drive: Lumen.runActions(actions) / Lumen.getState(). */
const Lumen = (() => {
  let META = null;
  let state = null;
  let charts = [];
  let openPop = null;
  let suppressHash = false;
  const $ = (s, el = document) => el.querySelector(s);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const COLORS = ["#3e7c5a", "#2f6f8f", "#e3a018", "#7aa98a", "#6c9db5", "#b4313f", "#93785a", "#4f5d9a", "#a7c4b2", "#c9a24e", "#5b8c85", "#8aa1b1"];

  async function api(path, body) {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    if (!r.ok) throw new Error(`${path} ${r.status}`);
    return r.json();
  }

  // ---------- formatting (mirrors backend/semantic/engine.py) ----------
  function inr(n) { return Math.round(n).toLocaleString("en-IN"); }
  function fmt(v, f) {
    if (v === null || v === undefined || Number.isNaN(v)) return "–";
    const a = Math.abs(v), s = v < 0 ? "-" : "";
    switch (f) {
      case "retail_int": return v.toLocaleString("en-GB", {maximumFractionDigits:0});
      case "brl": return `BRL ${v.toLocaleString("pt-BR", {minimumFractionDigits:2, maximumFractionDigits:2})}`;
      case "days": return `${v.toFixed(2)} days`;
      case "gbp": return `GBP ${v.toLocaleString("en-GB", {minimumFractionDigits:2, maximumFractionDigits:2})}`;
      case "currency": return a >= 1e7 ? `${s}₹${(a / 1e7).toFixed(2)} Cr` : a >= 1e5 ? `${s}₹${(a / 1e5).toFixed(2)} L` : `${s}₹${inr(a)}`;
      case "int": return inr(v);
      case "pct": return `${v.toFixed(1)}%`;
      case "hours": return `${v.toFixed(1)} hrs`;
      case "minutes": return `${v.toFixed(0)} min`;
      case "rating": return `${v.toFixed(2)}/5`;
      case "ratio": return `${v.toFixed(2)}x`;
      default: return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
    }
  }
  function tick(v, f) {
    const a = Math.abs(v);
    if (f === "currency") return a >= 1e7 ? `₹${(v / 1e7).toFixed(1)}Cr` : a >= 1e5 ? `₹${(v / 1e5).toFixed(0)}L` : `₹${inr(v)}`;
    if (f === "int") return a >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : a >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : inr(v);
    if (f === "retail_int") return a >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : a >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : v.toFixed(0);
    if (f === "brl") return `BRL ${a >= 1e6 ? (v / 1e6).toFixed(1) + "m" : a >= 1e3 ? (v / 1e3).toFixed(0) + "k" : v.toFixed(0)}`;
    if (f === "gbp") return `GBP ${a >= 1e6 ? (v / 1e6).toFixed(1) + "m" : a >= 1e3 ? (v / 1e3).toFixed(0) + "k" : v.toFixed(0)}`;
    if (f === "pct") return `${v.toFixed(0)}%`;
    return fmt(v, f);
  }
  function deltaClass(pct, good) {
    if (pct === null || pct === undefined || Math.abs(pct) < 0.05 || good === "neutral") return "delta-flat";
    return (pct > 0) === (good === "up") ? "delta-good" : "delta-bad";
  }

  // ---------- deep links ----------
  function encodeState(st) {
    const m = { p: st.page_id, f: st.filters || {}, d: st.date_range, c: st.compare, cr: st.compare_range || undefined,
      so: st.sort || undefined, n: st.top_n || undefined, g: st.grain && st.grain !== "auto" ? st.grain : undefined };
    return btoa(unescape(encodeURIComponent(JSON.stringify(m)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function decodeState(s) {
    try {
      const m = JSON.parse(decodeURIComponent(escape(atob(s.replace(/-/g, "+").replace(/_/g, "/")))));
      return { page_id: m.p, filters: m.f || {}, date_range: m.d, compare: m.c || "previous_period", compare_range: m.cr || null,
        sort: m.so || null, top_n: m.n || null, grain: m.g || "auto" };
    } catch (e) { return null; }
  }
  function hashFor(st) { return `#${META.pages[st.page_id].route}?s=${encodeState(st)}`; }
  function stateFromHash() {
    const h = location.hash.slice(1);
    if (!h) return null;
    const [route, q] = h.split("?s=");
    if (q) { const st = decodeState(q); if (st && META.pages[st.page_id]) return st; }
    const pid = META.routes[route];
    return pid ? defaultState(pid) : null;
  }

  function defaultState(pid) {
    const ds = META.pages[pid].default_state;
    return { page_id: pid, filters: JSON.parse(JSON.stringify(ds.filters || {})), date_range: { preset: ds.date_range.preset },
      compare: ds.compare, compare_range: null, sort: ds.sort ? { ...ds.sort } : null, top_n: ds.top_n || null, grain: "auto" };
  }

  // ---------- navigation tree ----------
  function buildTree() {
    const tree = $("#tree");
    tree.innerHTML = META.directories.map((d) => {
      const n = d.subdirectories.reduce((a, s) => a + s.pages.length, 0);
      return `<details data-dir="${d.id}"><summary>${esc(d.id === "uci" ? "UCI Retail II" : d.label)}<span class="count">${n}</span></summary>${d.subdirectories.map((s) =>
        `<details class="sub" data-sub="${s.id}"><summary>${esc(s.label)}<span class="count">${s.pages.length}</span></summary>${s.pages.map((pid) =>
          `<a href="#${META.pages[pid].route}" data-pid="${pid}">${esc(META.pages[pid].title)}</a>`).join("")}</details>`).join("")}</details>`;
    }).join("");
    tree.addEventListener("click", (e) => {
      const a = e.target.closest("a[data-pid]");
      if (!a) return;
      e.preventDefault();
      setState(defaultState(a.dataset.pid));
      closePanels();
    });
    $("#navSearch").addEventListener("input", () => filterTree());
  }
  function filterTree() {
    if (!state) return;
    const q = $("#navSearch").value.trim().toLowerCase();
    const dataset = META.pages[state.page_id].view.startsWith("olist_") ? "olist" : META.pages[state.page_id].view === "retail" ? "retail" : "synthetic";
    const tree = $("#tree");
    tree.querySelectorAll("a[data-pid]").forEach(a => {
      const p = META.pages[a.dataset.pid];
      const matches = !q || p.title.toLowerCase().includes(q) || (p.synonyms || []).some(x => x.toLowerCase().includes(q));
      a.style.display = (p.view.startsWith("olist_") ? "olist" : p.view === "retail" ? "retail" : "synthetic") === dataset && matches ? "" : "none";
    });
    tree.querySelectorAll("details").forEach(d => {
      const any = [...d.querySelectorAll("a[data-pid]")].some(a => a.style.display !== "none");
      d.style.display = any ? "" : "none";
      if (q) d.open = any;
    });
  }

  function markTree(pid, touch) {
    document.querySelectorAll("#tree a.active").forEach((a) => a.classList.remove("active"));
    const a = document.querySelector(`#tree a[data-pid="${CSS.escape(pid)}"]`);
    if (!a) return;
    a.classList.add("active");
    let p = a.parentElement;
    while (p && p.id !== "tree") { if (p.tagName === "DETAILS") p.open = true; p = p.parentElement; }
    a.scrollIntoView({ block: "nearest" });
    if (touch) { a.classList.remove("agent-touch"); void a.offsetWidth; a.classList.add("agent-touch"); }
  }

  // ---------- controls ----------
  function closePop() { if (openPop) { openPop.remove(); openPop = null; } }
  document.addEventListener("click", (e) => { if (openPop && !e.target.closest(".pop") && !e.target.closest(".ctl > button")) closePop(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePop(); });

  function drawControls(touched = new Set()) {
    const page = META.pages[state.page_id];
    const c = $("#controls");
    const parts = [];
    for (const f of page.filters) {
      const vals = (state.filters || {})[f.field] || [];
      const v = vals.length === 0 ? "All" : vals.length <= 2 ? vals.join(", ") : `${vals.length} selected`;
      parts.push(`<div class="ctl ${vals.length ? "set" : ""} ${touched.has("filter:" + f.field) ? "agent-set" : ""}" data-ctl="filter:${f.field}">
        <button type="button" data-filter="${f.field}" aria-haspopup="true"><span class="k">${esc(f.label)}</span><span class="v">${esc(v)}</span></button></div>`);
    }
    parts.push(`<span class="sep"></span>`);
    const dr = state.date_range || {};
    const presetOpts = META.date_presets.map((p) => `<option value="${p.id}" ${dr.preset === p.id ? "selected" : ""}>${p.label}</option>`).join("");
    const custom = !dr.preset;
    parts.push(`<div class="ctl ${touched.has("date") ? "agent-set" : ""}" data-ctl="date"><select id="datePreset" aria-label="Date range">
      ${custom ? `<option value="__custom" selected>${esc(dr.label || (dr.start + " – " + dr.end))}</option>` : ""}${presetOpts}<option value="__pick">Custom range…</option></select></div>`);
    const cmpLabel = state.compare === "custom" && state.compare_range ? `vs ${state.compare_range.label}` : null;
    parts.push(`<div class="ctl ${touched.has("compare") ? "agent-set" : ""}" data-ctl="compare"><select id="compareSel" aria-label="Comparison">
      <option value="previous_period" ${state.compare === "previous_period" ? "selected" : ""}>vs previous period</option>
      <option value="previous_year" ${state.compare === "previous_year" ? "selected" : ""}>vs last year</option>
      ${cmpLabel ? `<option value="custom" selected>${esc(cmpLabel)}</option>` : ""}
      <option value="none" ${state.compare === "none" ? "selected" : ""}>No comparison</option></select></div>`);
    if (page.sort_options.length) {
      const s = state.sort || {};
      parts.push(`<div class="ctl ${touched.has("sort") ? "agent-set" : ""}" data-ctl="sort"><select id="sortSel" aria-label="Sort grid">${page.sort_options.flatMap((o) =>
        ["desc", "asc"].map((d) => `<option value="${o.field}:${d}" ${s.field === o.field && s.dir === d ? "selected" : ""}>Sort: ${esc(o.label)} ${d === "desc" ? "↓" : "↑"}</option>`)).join("")}</select></div>`);
      const n = state.top_n || 25;
      const opts = [...new Set([5, 10, 25, 50, n])].sort((a, b) => a - b);
      parts.push(`<div class="ctl ${touched.has("topn") ? "agent-set" : ""}" data-ctl="topn"><select id="topSel" aria-label="Rows">${opts.map((o) => `<option value="${o}" ${o === n ? "selected" : ""}>Top ${o}</option>`).join("")}</select></div>`);
    }
    parts.push(`<div class="ctl ${touched.has("grain") ? "agent-set" : ""}" data-ctl="grain"><select id="grainSel" aria-label="Time grain">${["auto", "day", "week", "month", "quarter"].map((g) =>
      `<option value="${g}" ${(state.grain || "auto") === g ? "selected" : ""}>${g === "auto" ? "Auto grain" : "By " + g}</option>`).join("")}</select></div>`);
    c.innerHTML = parts.join("");

    c.querySelectorAll("button[data-filter]").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); filterPop(b); }));
    $("#datePreset").addEventListener("change", (e) => {
      if (e.target.value === "__pick") return datePick();
      if (e.target.value === "__custom") return;
      setState({ ...state, date_range: { preset: e.target.value } });
    });
    $("#compareSel").addEventListener("change", (e) => setState({ ...state, compare: e.target.value, compare_range: e.target.value === "custom" ? state.compare_range : null }));
    const so = $("#sortSel");
    if (so) so.addEventListener("change", (e) => { const [f, d] = e.target.value.split(":"); setState({ ...state, sort: { field: f, dir: d } }); });
    const tp = $("#topSel");
    if (tp) tp.addEventListener("change", (e) => setState({ ...state, top_n: +e.target.value }));
    $("#grainSel").addEventListener("change", (e) => setState({ ...state, grain: e.target.value }));
    touched.forEach((k) => { const el = c.querySelector(`[data-ctl="${k}"] > *`); if (el) { el.classList.remove("agent-touch"); void el.offsetWidth; el.classList.add("agent-touch"); } });
  }

  function filterPop(btn) {
    closePop();
    const field = btn.dataset.filter;
    const f = META.pages[state.page_id].filters.find((x) => x.field === field);
    const cur = new Set((state.filters || {})[field] || []);
    const pop = document.createElement("div");
    pop.className = "pop";
    pop.innerHTML = f.options.map((o) => `<label><input type="checkbox" value="${esc(o)}" ${cur.has(o) ? "checked" : ""}> ${esc(o)}</label>`).join("") +
      `<div class="pop-foot"><button class="linkbtn" data-a="clear">Clear</button><button class="btn primary" data-a="apply">Apply</button></div>`;
    btn.parentElement.appendChild(pop);
    openPop = pop;
    pop.addEventListener("click", (e) => {
      const a = e.target.dataset.a;
      if (!a) return;
      const vals = a === "clear" ? [] : [...pop.querySelectorAll("input:checked")].map((i) => i.value);
      const filters = { ...(state.filters || {}) };
      if (vals.length) filters[field] = vals; else delete filters[field];
      closePop();
      setState({ ...state, filters });
    });
  }

  function datePick() {
    closePop();
    const host = document.querySelector('[data-ctl="date"]');
    const dr = state.date_range || {};
    const pop = document.createElement("div");
    pop.className = "pop";
    pop.innerHTML = `<label>From <input type="date" id="dFrom" min="${META.app.data_start}" max="${META.app.data_end}" value="${dr.start || ""}"></label>
      <label>To <input type="date" id="dTo" min="${META.app.data_start}" max="${META.app.data_end}" value="${dr.end || ""}"></label>
      <div class="pop-foot"><span></span><button class="btn primary" data-a="apply">Apply</button></div>`;
    host.appendChild(pop);
    openPop = pop;
    pop.querySelector("[data-a=apply]").addEventListener("click", () => {
      const s = $("#dFrom").value, e = $("#dTo").value;
      if (!s || !e || s > e) return;
      closePop();
      setState({ ...state, date_range: { start: s, end: e, label: `${s} – ${e}` } });
    });
  }

  // ---------- widgets ----------
  function destroyCharts() { charts.forEach((c) => c.destroy()); charts = []; }
  function baseOpts(f, horizontal) {
    const axis = { ticks: { callback: (v) => tick(v, f), color: "#7d8c87", font: { family: "Plex" } }, grid: { color: "#eef2ef" }, border: { display: false } };
    const cat = { ticks: { color: "#4b5b56", font: { family: "Plex", size: 11.5 }, autoSkip: !horizontal, maxRotation: 0 }, grid: { display: false }, border: { display: false } };
    if (f === "rating") { axis.min = 0; axis.max = 5; }
    axis.ticks.maxTicksLimit = 6; axis.ticks.maxRotation = 0;
    return {
      responsive: true, maintainAspectRatio: false, animation: { duration: 350 }, indexAxis: horizontal ? "y" : "x",
      plugins: { legend: { display: false, labels: { font: { family: "Plex" }, boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed[horizontal ? "x" : "y"] ?? c.parsed, f)}` } } },
      scales: horizontal ? { x: axis, y: cat } : { x: cat, y: axis },
    };
  }
  function lineChart(canvas, w) {
    const ds = [{ label: w.series[0].name, data: w.series[0].values, borderColor: "#3e7c5a", backgroundColor: "rgba(62,124,90,.08)", fill: true, tension: .25, pointRadius: w.labels.length > 40 ? 0 : 2, borderWidth: 2 }];
    if (w.compare) ds.push({ label: w.compare.name, data: w.compare.values, borderColor: "#2f6f8f", borderDash: [5, 4], pointRadius: 0, borderWidth: 1.5, fill: false, tension: .25 });
    w.series.slice(1).forEach((s, i) => ds.push({ label: s.name, data: s.values, borderColor: COLORS[i + 2], pointRadius: 0, borderWidth: 1.5, yAxisID: "y2" }));
    const o = baseOpts(w.fmt);
    o.plugins.legend.display = ds.length > 1;
    if (w.series.length > 1) o.scales.y2 = { position: "right", grid: { display: false }, ticks: { color: "#7d8c87" }, border: { display: false } };
    const labels = w.labels.map((l) => shortDate(l, w.grain));
    return new Chart(canvas, { type: "line", data: { labels, datasets: ds }, options: o });
  }
  function shortDate(l, grain) {
    const d = new Date(l + "T00:00:00");
    if (Number.isNaN(d.getTime())) return l;
    if (grain === "month") return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
    if (grain === "quarter") return `Q${Math.floor(d.getMonth() / 3) + 1} ${String(d.getFullYear()).slice(2)}`;
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  }
  function barChart(canvas, w, horizontal) {
    const ds = [{ label: "Current", data: w.values, backgroundColor: "#3e7c5a", borderRadius: 3, maxBarThickness: 26 }];
    if (w.prev_values) ds.push({ label: w.cmp_label || "Previous", data: w.prev_values, backgroundColor: "rgba(47,111,143,.35)", borderRadius: 3, maxBarThickness: 26 });
    const o = baseOpts(w.fmt, horizontal);
    o.plugins.legend.display = ds.length > 1;
    return new Chart(canvas, { type: "bar", data: { labels: w.labels, datasets: ds }, options: o });
  }
  function donutChart(canvas, w) {
    return new Chart(canvas, { type: "doughnut", data: { labels: w.labels, datasets: [{ data: w.values, backgroundColor: COLORS, borderWidth: 2, borderColor: "#fff" }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "62%", animation: { duration: 350 },
        plugins: { legend: { position: "right", labels: { boxWidth: 10, font: { family: "Plex" }, color: "#4b5b56", filter: (item) => item.index < 8 } },
          tooltip: { callbacks: { label: (c) => `${c.label}: ${fmt(c.parsed, w.fmt)}` } } } } });
  }

  function drawWidgets(widgets, warnings = []) {
    destroyCharts();
    const board = $("#board");
    const kpis = widgets.filter((w) => w.type === "kpi");
    const rest = widgets.filter((w) => w.type !== "kpi");
    const hasDonut = rest.some((w) => w.type === "donut");
    let html = warnings.map(note => `<div class="data-warning" role="status">${esc(note)}</div>`).join("");
    if (kpis.length) {
      html += `<div class="kpis" data-count="${kpis.length}">${kpis.map((k) => `<div class="kpi widget-kpi" data-wid="${k.id}"><div class="t">${esc(k.title)}</div><div class="v">${esc(k.formatted)}</div>
        <div class="d">${k.delta_pct_str && k.delta_pct_str !== "–" ? `<span class="${deltaClass(k.delta_pct, k.good)}">${esc(k.title.includes("%") || k.title.includes("Rate") || k.title.includes("CTR") ? k.delta_abs_str : k.delta_pct_str)}</span> vs ${esc(k.cmp_label)}` : (k.cmp_label ? "no comparison data" : "&nbsp;")}</div></div>`).join("")}</div>`;
    }
    for (const w of rest) {
      const cls = w.type === "bar" && !hasDonut ? "w-line" : `w-${w.type}`;
      const sub = w.type === "line" ? `<small>by ${w.grain}</small>` : w.type === "grid" ? `<small>${w.rows ? w.rows.length : 0} rows</small>` : "";
      html += `<div class="widget ${cls}" data-wid="${w.id}"><h3>${esc(w.title)} ${sub}</h3>`;
      if (w.error) html += `<div class="w-error">This widget couldn't load: ${esc(w.error)}</div>`;
      else if (w.type === "grid") {
        const s = w.sort || {};
        html += `<div class="grid-wrap"><table class="grid"><thead><tr>${w.columns.map((c) => `<th data-field="${c.field}" ${s.field === c.field ? `aria-sort="${s.dir === "asc" ? "ascending" : "descending"}"` : ""}>${esc(c.label)}${s.field === c.field ? (s.dir === "asc" ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead>
          <tbody>${w.rows.map((r) => `<tr>${r.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      } else {
        const crowdedBar = w.type === "bar" && w.labels.length > 8;
        const chartHeight = crowdedBar ? Math.max(245, w.labels.length * (w.prev_values ? 44 : 30) + 40) : null;
        html += `${crowdedBar ? '<div class="chart-scroll" tabindex="0" aria-label="Scroll to explore all chart categories">' : ''}<div class="chart-box"${chartHeight ? ` style="height:${chartHeight}px"` : ''}><canvas aria-label="${esc(w.title)}"></canvas></div>${crowdedBar ? '</div>' : ''}`;
        if (crowdedBar) html += `<p class="chart-note">${w.labels.length} categories shown. Scroll the chart to see all.</p>`;
        if (w.type === "donut" && w.labels.length > 8) html += `<p class="chart-note">All ${w.labels.length} categories plotted. Legend previews the first 8; hover or tap a segment for its value.</p>`;
      }
      html += `</div>`;
    }
    board.innerHTML = html;
    for (const w of rest) {
      if (w.error || w.type === "grid") continue;
      const cv = board.querySelector(`[data-wid="${CSS.escape(w.id)}"] canvas`);
      if (!cv) continue;
      if (w.type === "line") charts.push(lineChart(cv, w));
      if (w.type === "bar") charts.push(barChart(cv, w, w.labels.length > 6));
      if (w.type === "donut") charts.push(donutChart(cv, w));
    }
    board.querySelectorAll("table.grid th[data-field]").forEach((th) => th.addEventListener("click", () => {
      const f = th.dataset.field;
      const page = META.pages[state.page_id];
      if (!page.sort_options.some((o) => o.field === f)) return;
      const dir = state.sort && state.sort.field === f && state.sort.dir === "desc" ? "asc" : "desc";
      setState({ ...state, sort: { field: f, dir } });
    }));
  }

  function drawHeader() {
    const currentPage = META.pages[state.page_id];
    $("#datasetFoot").textContent = currentPage.view === "retail" ? `Real imported data / GBP / reference date ${currentPage.data_bounds.end}` : "Synthetic demo data / reference date September 2026";
    $("#datasetMode").value = currentPage.view === "retail" ? "retail" : "synthetic";
    const real = currentPage.view === "retail";
    $("#tenant").textContent = real ? "UCI Online Retail II" : "Sahyadri Retail";
    $("#datasetBadge").textContent = real ? "Real imported data \u00b7 GBP" : "Synthetic demonstration data";
    $("#composerContext").textContent = real ? "Using UCI Retail II sales" : "Using the current dashboard";
    const info = META.datasets && META.datasets.retail;
    $("#datasetInfo").textContent = real && info ? `${info.imported_rows.toLocaleString()} eligible sales rows. ${info.date_start} to ${info.date_end}. ${info.excluded_rows.toLocaleString()} rows excluded during cleaning. Source: Chen (2012), UCI Online Retail II, CC BY 4.0.` : "Fictional business data for exploring sales, operations and customer reports. Values are for demonstration purposes.";
    $("#officialSource").hidden = !real;
    const p = META.pages[state.page_id];
    $("#crumbs").innerHTML = p.breadcrumb.slice(0, -1).map((c) => `<span>${esc(c)}</span>`).join("");
    $("#pageTitle").textContent = p.title;
    $("#pageDesc").textContent = real ? "Explore sales over time, compare periods, and discover leading countries and products." : p.description;
    $("#asof").textContent = `Data to ${currentPage.data_bounds ? currentPage.data_bounds.end : META.app.data_end}`;
    document.title = `${p.title} · Lumen`;
    if (currentPage.view.startsWith('olist_')) {
      const report=META.datasets.olist, coverage=report.coverage[currentPage.view];
      $("#datasetMode").value="olist";
      $("#tenant").textContent="Olist Brazil";
      $("#datasetBadge").textContent="Real imported data / BRL";
      $("#datasetFoot").textContent="Real imported Olist orders / BRL";
      $("#composerContext").textContent="Using Olist sales, delivery and reviews";
      $("#datasetInfo").textContent=`${report.imported_orders.toLocaleString()} source orders. This view uses ${coverage.eligible_orders.toLocaleString()} eligible orders, ${coverage.date_start} to ${coverage.date_end}. Source: Olist / Kaggle. ${report.license}.`;
      $("#officialSource").hidden=false;$("#officialSource").textContent="Official Olist source";$("#officialSource").href=report.source_url;
      $("#pageDesc").textContent=currentPage.view==='olist_sales' ? "Delivered-order sales value and orders by Brazilian state and city." : currentPage.view==='olist_delivery' ? "Delivery time and late-delivery rates, grouped by purchase date." : "Review scores across states and delivery outcomes. Associations do not establish causes.";
    } else {$("#officialSource").textContent="Official UCI source";$("#officialSource").href="https://archive.ics.uci.edu/dataset/502/online+retail+ii";}
    filterTree();
    markTree(p.id, false);
  }

  // ---------- state ----------
  let renderSeq = 0;
  async function render(touched) {
    const seq = ++renderSeq;
    $("#loading").classList.add("on");
    $("#board").setAttribute("aria-busy", "true");
    drawHeader();
    drawControls(touched);
    try {
      const out = await api("/api/render", { state });
      if (seq !== renderSeq) return;
      const r = out.state; delete r.cmp_range;
      state = r;
      drawControls(touched);
      drawWidgets(out.widgets, out.warnings || []);
      suppressHash = true;
      history.replaceState(null, "", hashFor(state));
      setTimeout(() => (suppressHash = false), 0);
    } catch (e) {
      $("#board").innerHTML = `<div class="widget w-grid w-error">Couldn't load this page (${esc(e.message)}). Check that the server is running, then reload.</div>`;
    } finally {
      if (seq === renderSeq) { $("#loading").classList.remove("on"); $("#board").setAttribute("aria-busy", "false"); }
    }
  }
  async function setState(st, touched) {
    const pageChanged = !state || st.page_id !== state.page_id;
    state = JSON.parse(JSON.stringify(st));
    if (pageChanged) {
      $("#canvas").scrollTop = 0;
      $("#board").innerHTML = '<div class="board-loading" role="status">Loading your view...</div>';
    }
    await render(touched);
    document.dispatchEvent(new CustomEvent("lumen:state", { detail: state }));
  }

  // ---------- action API used by the copilot ----------
  async function runActions(actions, onStep, opts = {}) {
    const delay = opts.fast ? 0 : 260;
    let st = JSON.parse(JSON.stringify(state));
    const touched = new Set();
    let highlight = null;
    for (let i = 0; i < actions.length; i++) {
      const a = actions[i];
      onStep && onStep(i, "running");
      try {
        switch (a.type) {
          case "navigate":
            if (!META.pages[a.page_id]) throw new Error("unknown page");
            st = defaultState(a.page_id);
            state = JSON.parse(JSON.stringify(st));
            markTree(a.page_id, true);
            drawHeader(); drawControls();
            break;
          case "set_filter": st.filters = { ...(st.filters || {}), [a.field]: a.values }; touched.add("filter:" + a.field); break;
          case "clear_filter": { const f = { ...(st.filters || {}) }; delete f[a.field]; st.filters = f; touched.add("filter:" + a.field); break; }
          case "set_date_range": st.date_range = { start: a.range.start, end: a.range.end, label: a.range.label, preset: a.range.preset || undefined }; touched.add("date"); break;
          case "set_compare": st.compare = a.mode; st.compare_range = a.range || null; touched.add("compare"); break;
          case "set_sort": st.sort = { field: a.field, dir: a.dir }; touched.add("sort"); break;
          case "set_top_n": st.top_n = a.n; touched.add("topn"); break;
          case "set_grain": st.grain = a.grain; touched.add("grain"); break;
          case "highlight": highlight = a.widget_id; break;
          case "export": await exportCSV(st); break;
          default: break;
        }
        if (["set_filter", "clear_filter", "set_date_range", "set_compare", "set_sort", "set_top_n", "set_grain"].includes(a.type)) {
          state = JSON.parse(JSON.stringify(st));
          drawControls(new Set([...touched].slice(-1)));
        }
        if (delay) await sleep(delay);
        onStep && onStep(i, "done");
      } catch (e) {
        onStep && onStep(i, "failed", e.message);
      }
    }
    await setState(st, touched);
    if (highlight) highlightWidget(highlight);
    return getState();
  }
  function highlightWidget(wid) {
    const el = document.querySelector(`[data-wid="${CSS.escape(wid)}"]`);
    if (!el) return;
    const target = el.classList.contains("widget-kpi") ? el.parentElement : el;
    target.classList.add("agent-focus");
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => target.classList.remove("agent-focus"), 2600);
  }
  async function exportCSV(st) {
    const r = await fetch("/api/export", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state: st || state }) });
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(st || state).page_id.replace(/\./g, "_")}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function getState() { return JSON.parse(JSON.stringify(state)); }
  function toast(msg) {
    const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; document.body.appendChild(t);
    setTimeout(() => t.remove(), 2200);
  }

  function refreshBookmarks() {
    const host = $("#savedViews");
    host.replaceChildren();
    let views = [];
    try { views = JSON.parse(localStorage.getItem("lumen_bookmarks") || "[]"); } catch (_) {}
    if (!Array.isArray(views)) views = [];
    for (const view of views.slice(-20)) {
      const row = document.createElement("div");
      const button = document.createElement("button"); button.className = "btn";
      button.textContent = view.name; button.addEventListener("click", () => setState(view.state));
      row.appendChild(button); host.appendChild(row);
    }
    if (!host.children.length) host.textContent = "Ask the copilot to save this view.";
  }
  function bookmark(view) {
    try {
      let views = JSON.parse(localStorage.getItem("lumen_bookmarks") || "[]");
      if (!Array.isArray(views)) views = [];
      views.push(view); localStorage.setItem("lumen_bookmarks", JSON.stringify(views.slice(-20)));
      refreshBookmarks(); return true;
    } catch (_) { toast("Browser storage is blocked; view could not be saved."); return false; }
  }
  function closePanels() {
    $("#nav").classList.remove("open");
    $("#copilot").classList.remove("open");
    $("#panelBackdrop").hidden = true;
    $("#menuBtn").setAttribute("aria-expanded", "false");
    $("#cpBtn").setAttribute("aria-expanded", String(window.innerWidth > 1100 && !document.querySelector(".shell").classList.contains("cp-collapsed")));
  }
  function togglePanel(id) {
    if (id === "copilot" && window.innerWidth > 1100) {
      document.querySelector(".shell").classList.toggle("cp-collapsed");
      $("#cpBtn").setAttribute("aria-expanded", String(!document.querySelector(".shell").classList.contains("cp-collapsed")));
      return;
    }
    const opening = !$("#" + id).classList.contains("open");
    closePanels();
    if (opening) {
      $("#" + id).classList.add("open");
      $("#panelBackdrop").hidden = false;
      $(id === "nav" ? "#menuBtn" : "#cpBtn").setAttribute("aria-expanded", "true");
    }
  }
  async function init() {
    META = await api("/api/meta");
    $("#tenant").textContent = META.app.tenant;
    const retail = META.datasets && META.datasets.retail;
    $("#datasetMode").querySelector('[value="retail"]').disabled = !retail || !retail.available;

    $("#datasetMode").querySelector('[value="olist"]').disabled=!(META.datasets.olist && META.datasets.olist.available);
    $("#datasetMode").addEventListener("change", e => setState(defaultState(e.target.value === "olist" ? "olist.sales.overview" : e.target.value === "retail" ? "uci.sales.overview" : "exec.dashboards.summary")));
    $("#asof").textContent = `Data to ${new Date(META.app.data_end).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`;
    buildTree();
    refreshBookmarks();
    const st = stateFromHash() || defaultState("exec.dashboards.summary");
    await setState(st);
    window.addEventListener("hashchange", () => { if (suppressHash) return; const s = stateFromHash(); if (s) setState(s); });
    $("#copyLink").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(location.href); toast("Link to this exact view copied"); } catch (e) { toast("Copy failed: select the address bar instead"); }
    });
    $("#resetBtn").addEventListener("click", () => setState(defaultState(state.page_id)));
    $("#menuBtn").addEventListener("click", () => togglePanel("nav"));
    $("#cpBtn").addEventListener("click", () => togglePanel("copilot"));
    $("#navClose").addEventListener("click", closePanels);
    $("#cpClose").addEventListener("click", () => {
      if (window.innerWidth > 1100) document.querySelector(".shell").classList.add("cp-collapsed");
      else closePanels();
      $("#cpBtn").setAttribute("aria-expanded", "false");
    });
    $("#panelBackdrop").addEventListener("click", closePanels);
    document.addEventListener("keydown", e => { if (e.key === "Escape") closePanels(); });
    window.addEventListener("resize", closePanels);
    document.dispatchEvent(new CustomEvent("lumen:ready"));
  }

  return { init, bookmark, getState, setState, runActions, highlightWidget, exportCSV, fmt, tick, meta: () => META, defaultState, toast, esc };
})();
window.Lumen = Lumen;
Lumen.init();
