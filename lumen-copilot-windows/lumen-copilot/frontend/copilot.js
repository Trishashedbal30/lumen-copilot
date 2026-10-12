/* Copilot panel: chat, live action trace, verification, answer cards, evidence and sources. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const log = $("#log");
  const input = $("#input");
  let sessionId = null;
  let busy = false;
  try { sessionId = sessionStorage.getItem("lumen_sid"); } catch (e) { /* storage blocked */ }

  const EXAMPLES = [
    "Why did South revenue drop in August?",
    "Top 5 cities by revenue last quarter",
    "Open the stockout monitor for Chennai DC",
    "Compare North vs South revenue this year",
    "Show the on-time delivery trend in the West for the last 6 months",
    "south ka revenue dikhao pichle mahine",
  ];

  function md(text) {
    const lines = String(text || "").split("\n");
    return lines.map((ln) => {
      let h = esc(ln)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(strong|moderate|weak)\*/g, '<em class="conf $1">$1</em>')
        .replace(/(^|\s)\*(.+?)\*(?=\s|$|[.,])/g, "$1<em>$2</em>");
      if (/^_.*_$/.test(ln.trim())) return `<p class="note">${h.replace(/^_|_$/g, "")}</p>`;
      return `<p>${h}</p>`;
    }).join("");
  }

  function scrollDown() { log.scrollTop = log.scrollHeight; }

  function welcome() {
    const real = document.querySelector("#datasetMode").value === "retail";
    const olist=document.querySelector("#datasetMode").value === "olist";
    const examples = olist ? [["Sales", "Show monthly sales value for 2017"], ["Delivery", "Top 5 states by late delivery rate in 2017"], ["Reviews", "Compare review scores for late and on-time deliveries in 2017"]] : real ? [
      ["Trends", "Show monthly revenue for 2011"],
      ["Rankings", "Top 5 countries by revenue in 2011"],
      ["Comparisons", "Compare revenue in two available months"]
    ] : [["Trends", "Show monthly revenue this year"], ["Rankings", "Top 5 cities by revenue last quarter"], ["Comparisons", "Compare North vs South revenue this year"]];
    log.innerHTML = `<div class="cp-empty"><div class="welcome-mark" aria-hidden="true">&#10022;</div><span class="eyebrow">YOUR WORKSPACE ASSISTANT</span><h2>Explore your data.</h2>
      <p>Find a report, adjust your view, or ask a question. Get an answer with evidence you can check.</p>
      <div class="starter-list">${examples.map(([label, question]) => `<button class="starter" data-say="${esc(question)}"><span class="starter-label">${label}</span><span>${esc(question)}</span><span class="starter-arrow" aria-hidden="true">&#8599;</span></button>`).join("")}</div>
      <p class="welcome-note">Filters and dates from your current view provide context.</p></div>`;
  }
  document.addEventListener("lumen:state", () => { if (log.querySelector(".cp-empty")) welcome(); });
  $("#newChat").addEventListener("click", () => {
    if (busy) return;
    sessionId = null;
    try { sessionStorage.removeItem("lumen_sid"); } catch (_) {}
    welcome();
  });

  function addUser(text) {
    const el = document.createElement("div");
    el.className = "msg-user";
    el.textContent = text;
    log.appendChild(el);
    scrollDown();
  }

  function miniChart(canvas, c) {
    const fmt = Lumen.fmt;
    const horizontal = c.type === "bar" && (c.horizontal || c.labels.length > 5);
    const colors = ["#3e7c5a", "rgba(47,111,143,.45)"];
    if (c.type === "drivers") {
      return new Chart(canvas, { type: "bar", data: { labels: c.labels, datasets: [{ data: c.values, backgroundColor: c.values.map((v, i) => (i === 0 ? "#e3a018" : "#a7c4b2")), borderRadius: 3 }] },
        options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (x) => `${x.parsed.x}% of the change · ${c.detail[x.dataIndex]}` } } },
          scales: { x: { ticks: { callback: (v) => v + "%" }, grid: { color: "#eef2ef" } }, y: { grid: { display: false } } } } });
    }
    const ds = c.series.map((s, i) => ({ label: s.name, data: s.values, backgroundColor: colors[i] || "#7aa98a", borderColor: colors[i] || "#7aa98a",
      borderRadius: 3, tension: .25, pointRadius: c.anomalies ? c.labels.map((l) => (c.anomalies.includes(l) ? 5 : 1.5)) : 1.5,
      pointBackgroundColor: c.anomalies ? c.labels.map((l) => (c.anomalies.includes(l) ? "#e3a018" : colors[i])) : colors[i], fill: false, borderWidth: 2 }));
    return new Chart(canvas, { type: c.type === "line" ? "line" : "bar", data: { labels: c.labels, datasets: ds },
      options: { indexAxis: horizontal ? "y" : "x", responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
        plugins: { legend: { display: ds.length > 1, labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (x) => `${x.dataset.label}: ${fmt(horizontal ? x.parsed.x : x.parsed.y, c.fmt)}` } } },
        scales: { [horizontal ? "x" : "y"]: { ...(c.fmt === "rating" ? {min:0, max:5} : {}), ticks: { callback: (v) => Lumen.tick(v, c.fmt), maxTicksLimit: 5, maxRotation: 0 }, grid: { color: "#eef2ef" } }, [horizontal ? "y" : "x"]: { grid: { display: false }, ticks: { autoSkip: !horizontal, maxRotation: 0, maxTicksLimit: 8 } } } } });
  }

  function cardHTML(c, i) {
    if (c.type === "kpi") {
      const cls = c.delta_pct_str && c.delta_pct_str !== "–" ? ((c.direction === "up") === (c.good === "up") ? "delta-good" : c.good === "neutral" ? "delta-flat" : "delta-bad") : "";
      return `<div class="card kpi-card"><div><div class="ct">${esc(c.title)} · ${esc(c.range)}</div><div class="big">${esc(c.value)}</div></div>
        ${c.delta_pct_str ? `<div style="text-align:right"><div class="${cls}">${esc(c.title.includes("%") || c.title.includes("Rate") ? c.delta_abs_str : c.delta_pct_str)}</div><div class="ct">vs ${esc(c.cmp_label)} (${esc(c.prev)})</div></div>` : ""}</div>`;
    }
    if (c.type === "hypotheses") {
      return `<div class="card"><div class="ct">${esc(c.title)}: tested across linked data views</div>${c.items.map((h, j) => `<div class="hyp">
        <div class="h1">${esc(h.title)} <em class="conf ${h.confidence}">${h.confidence}</em></div><div class="h2">${esc(h.detail)}</div>
        ${h.page_id ? `<button class="chip cite" data-hyp="${i}:${j}">Open evidence</button>` : ""}</div>`).join("")}</div>`;
    }
    const h = c.type === "bar" && c.labels.length > 5 ? Math.min(60 + c.labels.length * 22, 300) : 170;
    return `<div class="card"><div class="ct">${esc(c.title)}</div><div class="chart-box" style="height:${h}px"><canvas data-card="${i}"></canvas></div></div>`;
  }

  function factsHTML(facts) {
    const nums = facts.filter(f => f.fmt !== "text").slice(0, 60);
    if (!nums.length) return "";
    const rangeText = range => range ? `${range.start} to ${range.end}` : "Current view";
    const filtersText = filters => Object.entries(filters || {}).map(([key, values]) => `${key.replaceAll("_", " ")}: ${values.join(", ")}`).join("; ") || "All available records";
    return `<details class="more source-details"><summary>Calculation details <span>${nums.length} figures</span></summary><div class="facts">${nums.map(f =>
      `<div class="fact"><div class="fact-value"><strong>${esc(f.formatted)}</strong><span>${esc(f.label)}</span></div><dl><dt>Dataset</dt><dd>${esc(f.dataset || f.view)}</dd><dt>Metric</dt><dd>${esc(f.metric_definition || f.metric)}</dd><dt>Scope</dt><dd>${esc(filtersText(f.filters))}</dd><dt>Dates</dt><dd>${esc(rangeText(f.range))}</dd>${f.comparison_range ? `<dt>Compared with</dt><dd>${esc(rangeText(f.comparison_range))}</dd>` : ""}${f.calculation ? `<dt>Calculation</dt><dd>${esc(f.calculation)}</dd>` : ""}</dl><details class="query-details"><summary>View query</summary><code>${esc(f.sql)}</code></details></div>`).join("")}</div></details>`;
  }

  function understandingHTML(trace) {
    return trace.map(t => {
      const status = t.model_request_status || "not_requested";
      const fallback = status === "failed_fallback_to_rules";
      const blocked = status === "response_received_blocked_slots";
      const label = fallback ? "Built-in understanding / AI unavailable" : blocked ? "AI response needs clarification" : t.source === "llm" ? "AI understood your request" : "Built-in understanding";
      const message = fallback ? (/429|rate limit/i.test(t.model_error || "") ? "AI request limit reached. This answer uses built-in understanding." : "AI could not complete this request. This answer uses built-in understanding.") : blocked ? "Some proposed controls were unavailable. No unsupported changes were applied." : "";
      return `<div class="answer-status ${fallback || blocked ? "warning" : ""}" title="${esc(status)}"><span class="status-dot"></span>${esc(label)}</div>${message ? `<p class="model-notice">${esc(message)}</p>` : ""}`;
    }).join("");
  }

  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true;
    $("#newChat").disabled = true;
    $(".send").disabled = true;
    $("#composer").setAttribute("aria-busy", "true");
    if (log.querySelector(".cp-empty")) log.innerHTML = "";
    addUser(text);
    const bot = document.createElement("div");
    bot.className = "msg-bot";
    bot.innerHTML = `<div class="typing"><i></i><i></i><i></i></div>`;
    log.appendChild(bot);
    scrollDown();
    let r;
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId, state: Lumen.getState() }) });
      if (!res.ok) throw new Error("Request rejected: " + res.status);
      r = await res.json();
    } catch (e) {
      bot.innerHTML = `<div class="text"><p>I couldn't reach the server, so nothing changed. Check that it's running and the message is under 500 characters, then try again.</p></div>`;
      busy = false;
      $("#newChat").disabled = false;
      $(".send").disabled = false;
      $("#composer").setAttribute("aria-busy", "false");
      return;
    }
    sessionId = r.session_id;
    try { sessionStorage.setItem("lumen_sid", sessionId); } catch (e) { /* ignore */ }

    const acts = r.actions || [];
    const understanding = (r.trace || []).filter(t => t.node === "understand");
    bot.innerHTML = `${understandingHTML(understanding)}<div class="text">${md(r.reply)}</div>
      ${acts.length ? `<details class="action-details"><summary>View changes <span>${acts.length}</span></summary><div class="trace" aria-label="Actions taken">${acts.map((a, i) => `<div class="trace-step" data-i="${i}"><span class="dot"></span><span>${esc(a.label)}</span></div>`).join("")}</div></details><div class="verify"></div>` : ""}
      <div class="cards"></div><div class="chips cites"></div><div class="chips sugg"></div><div class="conf-host"></div>
      ${factsHTML(r.facts || [])}`;
    scrollDown();

    if (acts.length && r.kind !== "clarify") {
      const step = (i, status) => { const el = bot.querySelector(`.trace-step[data-i="${i}"]`); if (el) el.className = `trace-step ${status}`; };
      const applied = await Lumen.runActions(acts, step);
      if (r.target_state && r.turn_id) {
        try {
          const v = await (await fetch("/api/verify", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId, turn_id: r.turn_id, applied_state: applied }) })).json();
          const vb = bot.querySelector(".verify");
          if (vb && v.ok !== null) {
            vb.className = `verify ${v.ok ? "ok" : "bad"}`;
            vb.textContent = v.ok ? "Checked: your view matches the request." : `Mismatch on ${v.diff.map((d) => d.field).join(", ")}: please check the view.`;
          }
        } catch (e) { const vb = bot.querySelector(".verify"); if (vb) { vb.className = "verify bad"; vb.textContent = "Verification could not complete: " + e.message; } }
      }
    }

    const cardsHost = bot.querySelector(".cards");
    (r.cards || []).forEach((c, i) => {
      if (c.type === "kpi") return;
      cardsHost.insertAdjacentHTML("beforeend", cardHTML(c, i));
      const cv = cardsHost.querySelector(`canvas[data-card="${i}"]`);
      if (cv) miniChart(cv, c);
    });
    cardsHost.querySelectorAll("[data-hyp]").forEach((b) => b.addEventListener("click", () => {
      const [ci, hj] = b.dataset.hyp.split(":").map(Number);
      const h = r.cards[ci].items[hj];
      const cite = (r.citations || []).find((c) => c.state.page_id === h.page_id);
      if (cite) Lumen.setState(cite.state);
    }));
    const cites = (r.citations || []).filter((c) => c.kind === "evidence");
    bot.querySelector(".cites").innerHTML = cites.map((c, i) => `<button class="chip cite" data-cite="${i}">Evidence: ${esc(c.label)}</button>`).join("");
    bot.querySelectorAll("[data-cite]").forEach((b) => b.addEventListener("click", () => Lumen.setState(cites[+b.dataset.cite].state)));
    bot.querySelector(".sugg").innerHTML = (r.suggestions || []).slice(0, 3).map((s) => `<button class="chip" data-say="${esc(s.utterance)}">${esc(s.label)}</button>`).join("");

    if (r.needs_confirmation) {
      const c = r.needs_confirmation;
      const host = bot.querySelector(".conf-host");
      host.innerHTML = `<div class="confirm-box"><strong>${esc(c.title)}</strong><div>${esc(c.detail)}</div>
        <div class="row"><button class="btn primary" data-ok="1">Save view</button><button class="btn" data-ok="0">Cancel</button></div></div>`;
      host.querySelectorAll("[data-ok]").forEach((b) => b.addEventListener("click", async () => {
        const out = await (await fetch("/api/confirm", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, confirmation_id: c.id, approve: b.dataset.ok === "1" }) })).json();
        if (out.ok && out.saved_view) {
          out.reply = Lumen.bookmark(out.saved_view) ? "Saved in this browser. Open it from Saved views in the sidebar." : "Browser storage is blocked. The view was not saved.";
        }
        host.innerHTML = `<div class="confirm-box">${esc(out.reply)}</div>`;
      }));
    }
    busy = false;
    $("#newChat").disabled = false;
    $(".send").disabled = false;
    $("#composer").setAttribute("aria-busy", "false");
    scrollDown();
    window.__lumenLast = { kind: r.kind, intent: r.intent, target_state: r.target_state, verify: (bot.querySelector(".verify") || {}).textContent || "" };
    window.__lumenTurns = (window.__lumenTurns || 0) + 1;
  }

  log.addEventListener("click", (e) => { const b = e.target.closest("[data-say]"); if (b) send(b.dataset.say); });
  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); const t = input.value; input.value = ""; send(t); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); } });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 130) + "px"; });

  // voice input (Chrome / Edge): en-IN handles Indian English and Hinglish reasonably well
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("#mic");
  if (!SR) mic.style.display = "none";
  else {
    let rec = null;
    mic.addEventListener("click", () => {
      if (rec) { rec.stop(); return; }
      rec = new SR(); rec.lang = "en-IN"; rec.interimResults = true;
      mic.classList.add("rec");
      rec.onresult = (ev) => { input.value = [...ev.results].map((x) => x[0].transcript).join(" "); };
      rec.onend = () => { mic.classList.remove("rec"); rec = null; if (input.value.trim()) { const t = input.value; input.value = ""; send(t); } };
      rec.onerror = () => { mic.classList.remove("rec"); rec = null; };
      rec.start();
    });
  }

  fetch("/api/health").then((r) => r.json()).then((h) => {
    $("#modePill").textContent = "Connected";
    $("#modePill").title = "Connected to the application. Each answer shows how your request was understood.";

  }).catch(() => { $("#modePill").textContent = "Connection unavailable"; });
  welcome();
  window.LumenCopilot = { send };
})();
