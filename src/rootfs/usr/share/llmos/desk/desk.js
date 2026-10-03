/* LLM OS desk — renderer. All decisions are made by the OS (Python); this
   file draws what it is told and sends back what the owner does. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const post = (m) => { try { window.webkit.messageHandlers.llmos.postMessage(m); } catch (e) { console.log("no bridge", m); } };
  const S = {};                      // strings from the OS
  const wins = new Map();            // id -> {el, spec, min, max}
  let z = 10, cascade = 0, focused = null, lang = "en", busy = false, listening = false;
  const conv = [];                   // conversation log
  let cur = null;                    // current turn {req, text, activity[]}
  const sticky = new Map();          // sticky toasts by key
  let histPos = -1;                  // Up/Down through earlier requests
  let dialogOpen = false, speaking = false, wallpaper = "", autoHide = null;
  const motionOff = () => document.documentElement.dataset.motion === "off";

  // ---------------------------------------------------------------- utils
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function t(k, d) { return S[k] || d || k; }
  function fmt(k, vars) { let s = t(k); for (const [a, b] of Object.entries(vars)) s = s.split("{" + a + "}").join(b); return s; }
  function md(text) {
    // markdown-lite: paragraphs, bullets, numbered lists, **bold**, `code`, links
    const lines = String(text || "").split("\n");
    let html = "", list = null;
    const inline = (s) => esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .replace(/(^|[\s(])\*([^*\n]+?)\*(?=[\s.,;:!?)]|$)/g, "$1<i>$2</i>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/(https?:\/\/[^\s<)]+)/g, '<a href="#" data-url="$1">$1</a>');
    const flush = () => { if (list) { html += `</${list}>`; list = null; } };
    for (const raw of lines) {
      const ln = raw.trimEnd();
      let m;
      if ((m = ln.match(/^\s*(?:[-•*]|·)\s+(.*)/))) { if (list !== "ul") { flush(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
      else if ((m = ln.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { flush(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
      else if (!ln.trim()) { flush(); }
      else { flush(); html += `<p>${inline(ln)}</p>`; }
    }
    flush();
    return html;
  }
  function say(text) { if (text && text.trim()) post({ t: "say", text: text.trim() }); }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-url]");
    if (a) { e.preventDefault(); say("open " + a.dataset.url + " in the browser"); }
  });

  // ---------------------------------------------------------------- theme / strings
  function applyTheme(m) {
    const root = document.documentElement.style;
    for (const k of ["--bg", "--fg", "--accent"]) root.removeProperty(k);
    for (const [k, v] of Object.entries(m.css || {})) root.setProperty(k, v);
    document.body.className = m.mode === "light" ? "light" : "dark";
    document.documentElement.dataset.motion = ["full", "reduced", "off"].includes(m.motion) ? m.motion : "full";
    software = !!m.software;
    document.documentElement.lang = m.lang || "en";
    document.documentElement.dir = m.dir || "ltr";
    lang = m.lang || "en";
    Object.assign(S, m.strings || {});
    document.querySelectorAll("[data-s]").forEach(e => { e.textContent = t(e.dataset.s); });
    document.querySelectorAll("[data-ph]").forEach(e => { e.placeholder = t(e.dataset.ph); });
    $("in").placeholder = t("hint", "Tell me what you want…");
    const desk = $("desk");
    if ((m.wallpaper || "") !== wallpaper && wallpaper && !motionOff()) {
      // the old picture fades out over the new one
      const old = el("div", ""); old.id = "wallfade"; old.style.backgroundImage = `url("${wallpaper}")`;
      desk.prepend(old); setTimeout(() => old.remove(), 900);
    }
    wallpaper = m.wallpaper || "";
    if (m.wallpaper) { desk.style.backgroundImage = `url("${m.wallpaper}")`; desk.classList.add("wall"); }
    else { desk.style.backgroundImage = ""; desk.classList.remove("wall"); }
    if (wizard.active) wizard.render();
  }

  // ---------------------------------------------------------------- the computer's presence
  // idle | thinking | speaking | listening | attention | off -- shown by the orb in the bar and on the reply card
  function orb(state, label) {
    for (const id of ["orb", "reply-orb"]) {
      const e = $(id); if (!e) continue;
      e.className = (id === "reply-orb" ? "orb small " : "orb ") + (state === "idle" ? "" : state);
    }
    const st = $("reply-state"); if (st && label !== undefined) st.textContent = label;
  }
  // the empty desk belongs to the computer: greeting, presence, three suggestions
  let ownerName = "";
  function idle() {
    const box = $("idle"); if (!box) return;
    const anyWin = [...wins.values()].some(w => !w.min);
    const show = !$("desk").classList.contains("hidden") && !anyWin && $("reply").classList.contains("hidden") && !wizard.active;
    if (!show) { if (!box.classList.contains("hidden")) afterAnim(box, "closing", () => { box.classList.add("hidden"); box.classList.remove("closing"); }); return; }
    if (!box.classList.contains("hidden")) return;
    const h = new Date().getHours();
    const g = t(h < 12 ? "d_morning" : h < 18 ? "d_afternoon" : "d_evening");
    box.innerHTML = `<div><div class="orb big"></div><h1>${esc(ownerName ? g + ", " + ownerName : g)}</h1><p>${esc(t("d_idle_hint"))}</p><div class="sugg"></div></div>`;
    const sg = box.querySelector(".sugg");
    ["g_ex1", "g_ex2", "g_ex3"].forEach((k, i) => { const b = el("button", "btn small", esc(t(k))); b.style.setProperty("--i", i); b.onclick = () => say(t(k)); sg.append(b); });
    box.classList.remove("closing", "hidden");
  }
  // the orb's idle breathing: one style change 8 times a second, nothing when motion is reduced or off
  // every big orb gets its glow halo (a separate layer whose opacity breathes)
  function halos() { document.querySelectorAll(".orb:not(.small)").forEach(o => { if (!o.querySelector(".halo")) o.prepend(el("i", "halo")); }); }
  new MutationObserver(halos).observe(document.body, { childList: true, subtree: true });
  halos();
  // Continuous motion is rationed: every change repaints the screen, and a software-rendered
  // VM pays ~14 ms for each. The idle glow breathes at 4 changes/s there (10 on real hardware),
  // the thinking ring turns 8 times a second; one-shot transitions stay smooth.
  let lastGlow = "", software = false;
  function tick() {
    const lvl = document.documentElement.dataset.motion || "full";
    const full = lvl === "full" && !document.hidden;
    const g = full ? (0.25 + 0.75 * (1 - Math.cos(performance.now() / 4600 * 2 * Math.PI)) / 2).toFixed(2) : "0.3";
    if (g !== lastGlow) { lastGlow = g; document.querySelectorAll(".orb:not(.thinking):not(.off) > .halo").forEach(h => { h.style.opacity = g; }); }
    if (lvl !== "off") { const a = Math.round(performance.now() / 125) * 45 % 360; document.querySelectorAll(".orb.thinking").forEach(o => o.style.setProperty("--spin", a + "deg")); }
    setTimeout(tick, software ? 250 : 100);
  }
  tick();
  function presence() {
    if (dialogOpen) return orb("attention", t("d_waiting"));
    if (listening) return orb("listening", t("d_listening"));
    if (speaking) return orb("speaking", t("d_speaking"));
    if (busy) return;                        // the reply code sets thinking / writing
    orb("idle", "");
  }

  // ---------------------------------------------------------------- status bar
  function chip(html, sayText, title) {
    const c = el("button", "chip", html);
    if (sayText) { c.onclick = () => say(sayText); c.title = title || sayText; }
    return c;
  }
  function status(m) {
    busy = !!m.busy; listening = !!m.listening;
    const box = $("status"); box.innerHTML = "";
    const dot = m.model_ok ? (busy ? "busy" : "ok") : "";
    box.append(chip(`<i class="dot ${dot}"></i>${esc(m.model || t("loading_model"))}`, "models", (m.host_gpu ? t("d_host_gpu") + " · " : "") + t("models")));
    box.append(chip(esc(m.autonomy), "settings", t("settings")));
    if (m.internet !== "yes") box.append(chip(esc(m.internet === "no" ? "offline" : "internet: ask"), "settings"));
    if (m.tor) box.append(chip("Tor", "settings"));
    if (m.focus) box.append(chip("focus", "turn off focus mode"));
    if (m.vault !== "off") box.append(chip(`<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M17 9V7a5 5 0 0 0-10 0v2H5v12h14V9h-2zm-8-2a3 3 0 0 1 6 0v2H9V7z"/></svg>${m.vault === "on" ? "" : " " + esc(t("locked_short"))}`, m.vault === "on" ? "lock" : null, t("d_lock_tip")));
    $("greet").textContent = m.name ? "· " + m.name : "";
    if (m.name !== ownerName) { ownerName = m.name || ""; const h = $("idle").querySelector("h1"); if (h) { const g = h.textContent.split(",")[0]; h.textContent = ownerName ? g + ", " + ownerName : g; } }
    $("mic").classList.toggle("off", !m.mic);
    $("reply-stop").classList.toggle("hidden", !busy);
    $("reply").classList.toggle("busy", busy);
    $("cmd").classList.toggle("busy", busy);
    if (!m.model_ok && !busy) orb("off", ""); else presence();
  }
  function clock() {
    const now = new Date();
    try { $("clock").textContent = now.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" }) + "   " + now.toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "short" }); }
    catch (e) { $("clock").textContent = now.toLocaleTimeString(); }
  }
  setInterval(clock, 1000);

  // ---------------------------------------------------------------- screens
  function screen(m) {
    ["screen-boot", "screen-lock", "screen-wizard", "screen-bye", "desk"].forEach(id => $(id).classList.add("hidden"));
    if (m.name === "lock") { $("screen-lock").classList.remove("hidden"); $("lock-error").textContent = ""; $("lock-pass").value = ""; setTimeout(() => $("lock-pass").focus(), 50); }
    else if (m.name === "wizard") { $("screen-wizard").classList.remove("hidden"); wizard.start(m.data || {}); }
    else if (m.name === "bye") { $("screen-bye").classList.remove("hidden"); $("bye-text").textContent = (m.data || {}).text || ""; }
    else if (m.name === "desk") { $("desk").classList.remove("hidden"); wizard.active = false; if (!conv.length) $("hint").textContent = t("d_shortcuts"); setTimeout(() => $("in").focus(), 50); idle(); }
    else $("screen-boot").classList.remove("hidden");
  }
  $("lock-go").onclick = () => { const p = $("lock-pass").value; if (p) { $("lock-busy").classList.remove("hidden"); post({ t: "unlock", passphrase: p }); } };
  $("lock-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") $("lock-go").click(); });

  // ---------------------------------------------------------------- first-run set-up
  const wizard = {
    active: false, i: 0, data: {}, answers: {}, tz: null, wifiSel: null, nets: null, wifiNeeded: false,
    steps: ["welcome", "language", "name", "timezone", "autonomy", "internet", "wifi", "passphrase", "done"],
    start(data) { this.active = true; this.i = 0; this.data = data; this.answers = {}; this.tz = data.tz_label || null; this.wifiNeeded = false; this.nets = null; if (data.lang_hint) this.answers.language = data.lang_hint; this.render(); },
    step() { return this.steps[this.i]; },
    visible() { return this.steps.filter(s => s !== "welcome" && s !== "done" && (s !== "wifi" || this.wifiNeeded)); },
    render() {
      const body = $("wiz-body"), nav = $("wiz-nav"), st = this.step();
      $("wiz-error").textContent = "";
      body.classList.remove("swap", "backwards"); void body.offsetWidth; body.classList.add("swap"); if (this.back) body.classList.add("backwards"); this.back = false;
      const vis = this.visible(), n = vis.indexOf(st);
      $("wiz-dots").innerHTML = vis.map((s, k) => `<i class="${k <= n ? "on" : ""}"></i>`).join("");
      $("wiz-step").textContent = "";   // the dots already say where we are
      nav.innerHTML = "";
      const next = el("button", "btn primary", esc(t("d_next")));
      const back = el("button", "btn ghost", esc(t("d_back")));
      back.onclick = () => { if (this.i > 0) { this.i--; if (this.step() === "wifi" && !this.wifiNeeded) this.i--; this.back = true; this.render(); } };
      const submit = (value) => { this.answers[st] = value; post({ t: "wizard", step: st, value }); next.disabled = true; };
      const pickList = (box, items, key, render) => {
        for (const it of items) {
          const b = el("button", "opt" + (this.answers[key] === it.value ? " sel" : ""), render(it));
          b.onclick = () => { box.querySelectorAll(".opt").forEach(x => x.classList.remove("sel")); b.classList.add("sel"); this.answers[key] = it.value; };
          box.appendChild(b);
        }
      };
      if (st === "welcome") {
        body.innerHTML = `<div class="orb big" style="margin:8px auto 4px"></div><h2 style="font-size:30px;margin-top:10px;text-align:center">${esc(t("w_title"))}</h2><p class="lead">${esc(t("w_text"))}</p>`;
        next.textContent = t("w_begin");
        next.onclick = () => submit("");
      } else if (st === "language") {
        body.innerHTML = `<h2>${esc(t("ask_language"))}</h2><div class="opts grid" id="wz-langs"></div><input id="wz-other" type="text" placeholder="${esc(t("d_type_language"))}" style="margin-top:10px">`;
        pickList($("wz-langs"), (this.data.languages || []).map(l => ({ value: l.code, label: l.label })), "language", it => `<b>${esc(it.label)}</b>`);
        $("wz-other").addEventListener("input", () => { if ($("wz-other").value.trim()) { $("wz-langs").querySelectorAll(".opt").forEach(x => x.classList.remove("sel")); } });
        next.onclick = () => submit($("wz-other").value.trim() || this.answers.language || "");
      } else if (st === "name") {
        body.innerHTML = `<h2>${esc(t("ask_name"))}</h2><input id="wz-name" type="text" autocomplete="off" value="${esc(this.answers.name || "")}">`;
        setTimeout(() => $("wz-name").focus(), 30);
        next.onclick = () => submit($("wz-name").value.trim());
      } else if (st === "timezone") {
        const cur = this.tz;
        body.innerHTML = `<h2>${esc(t("ask_timezone").replace(/\s*\(.*\)\s*$/, ""))}</h2>
          <div class="tzpick"><input id="wz-tz" type="text" autocomplete="off" placeholder="${esc(t("w_tz_search"))}"><div id="wz-tzlist" class="tzlist"></div></div>
          <div class="tzsel" id="wz-tzsel">${cur ? `<b>${esc(cur.label)}</b> <span class="dim">${esc(cur.offset)}</span>` : ""}</div>
          <p class="dim small">${esc(t("w_tz_hint"))}</p>`;
        const inp = $("wz-tz"), list = $("wz-tzlist");
        let timer = null;
        const ask = () => { post({ t: "tz.search", q: inp.value.trim() }); };
        inp.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(ask, 180); });
        inp.addEventListener("focus", () => { if (!list.children.length) ask(); });
        this.onTz = (items) => {
          list.innerHTML = "";
          for (const it of items) {
            const b = el("button", "tzitem", `<span>${esc(it.label)}</span><span class="dim">${esc(it.offset)}</span>`);
            b.onclick = () => { this.tz = it; $("wz-tzsel").innerHTML = `<b>${esc(it.label)}</b> <span class="dim">${esc(it.offset)}</span>`; list.innerHTML = ""; inp.value = ""; };
            list.appendChild(b);
          }
        };
        setTimeout(() => inp.focus(), 30);
        next.onclick = () => submit(this.tz ? this.tz.zone : "");
      } else if (st === "autonomy") {
        body.innerHTML = `<h2>${esc(t("ask_autonomy"))}</h2><div class="opts" id="wz-auto"></div>`;
        if (!this.answers.autonomy) this.answers.autonomy = "hands-off";
        const descs = { "hands-off": "w_auto_off_d", "balanced": "w_auto_bal_d", "hands-on": "w_auto_on_d" };
        pickList($("wz-auto"), ["hands-off", "balanced", "hands-on"].map(v => ({ value: v })), "autonomy",
          it => { const [head] = t("v_" + it.value).split(":"); return `<b>${esc(head)}${it.value === "hands-off" ? ` <em class="badge">${esc(t("w_recommended"))}</em>` : ""}</b><span>${esc(t(descs[it.value]))}</span>`; });
        next.onclick = () => submit(this.answers.autonomy);
      } else if (st === "internet") {
        body.innerHTML = `<h2>${esc(t("w_net_title"))}</h2><div class="opts" id="wz-net"></div>`;
        if (!this.answers.internet) this.answers.internet = "yes";
        pickList($("wz-net"), [{ value: "yes", l: "w_net_yes", d: "w_net_yes_d", rec: true }, { value: "tor", l: "w_net_tor", d: "w_net_tor_d" }, { value: "no", l: "w_net_no", d: "w_net_no_d" }],
          "internet", it => `<b>${esc(t(it.l))}${it.rec ? ` <em class="badge">${esc(t("w_recommended"))}</em>` : ""}</b><span>${esc(t(it.d))}</span>`);
        next.onclick = () => submit(this.answers.internet);
      } else if (st === "wifi") {
        body.innerHTML = `<h2>${esc(t("w_wifi_title"))}</h2><div id="wz-wifi" class="wifilist"><span class="dim">${esc(t("w_wifi_none"))}</span></div>
          <div id="wz-wifipw" class="hidden"><input id="wz-pw" type="password" autocomplete="off" placeholder="${esc(t("w_wifi_pass"))}" style="margin-top:10px"></div>`;
        const scan = el("button", "btn ghost", esc(t("w_wifi_scan"))); scan.onclick = () => { post({ t: "wifi.scan" }); };
        const skip = el("button", "btn ghost", esc(t("w_wifi_skip"))); skip.onclick = () => submit({});
        nav.append(scan, skip);
        this.onWifi = (items) => {
          const box = $("wz-wifi"); box.innerHTML = items.length ? "" : `<span class="dim">${esc(t("w_wifi_none"))}</span>`;
          for (const n of items) {
            const b = el("button", "tzitem" + (this.wifiSel === n.ssid ? " sel" : ""), `<span>${n.secured ? "🔒 " : ""}${esc(n.ssid)}</span><span class="dim">${"▂▄▆█".slice(0, Math.max(1, Math.min(4, n.signal)))}</span>`);
            b.onclick = () => { this.wifiSel = n.ssid; box.querySelectorAll(".tzitem").forEach(x => x.classList.remove("sel")); b.classList.add("sel"); $("wz-wifipw").classList.toggle("hidden", !n.secured); if (n.secured) $("wz-pw").focus(); };
            box.appendChild(b);
          }
        };
        if (this.nets) this.onWifi(this.nets); else post({ t: "wifi.scan" });
        next.textContent = t("w_wifi_connect");
        next.onclick = () => { if (!this.wifiSel) return; submit({ ssid: this.wifiSel, password: $("wz-pw").value }); };
      } else if (st === "passphrase") {
        body.innerHTML = `<h2>${esc(t("passphrase"))}</h2><p>${esc(t("ask_passphrase"))}</p>
          <div class="pwrow"><input id="wz-p1" type="password" autocomplete="off"><button id="wz-eye" class="btn small ghost">${esc(t("w_show"))}</button></div>
          <input id="wz-p2" type="password" autocomplete="off" placeholder="${esc(t("ask_passphrase_again"))}" style="margin-top:10px">
          <p class="dim small">${esc(t("w_pass_hint"))}</p>`;
        $("wz-eye").onclick = () => { const show = $("wz-p1").type === "password"; ["wz-p1", "wz-p2"].forEach(id => $(id).type = show ? "text" : "password"); $("wz-eye").textContent = show ? t("w_hide") : t("w_show"); };
        const skip = el("button", "btn ghost", esc(t("d_skip")));
        skip.onclick = () => submit("");
        nav.appendChild(skip);
        setTimeout(() => $("wz-p1").focus(), 30);
        next.onclick = () => {
          const a = $("wz-p1").value, b = $("wz-p2").value;
          if (!a) return submit("");
          if (a !== b) { $("wiz-error").textContent = t("passphrase_mismatch"); return; }
          submit(a);
        };
      } else if (st === "done") {
        body.innerHTML = `<h2>${esc(t("w_done_title"))}</h2><p>${esc(t("w_done_text"))}</p><div class="opts" id="wz-try"></div>`;
        for (const k of ["g_ex1", "g_ex2", "g_ex3"]) {
          const b = el("button", "opt", `<b>“${esc(t(k))}”</b>`);
          b.onclick = () => { this.pending = t(k); next.click(); };
          $("wz-try").appendChild(b);
        }
        next.textContent = t("w_finish");
        next.onclick = () => submit("");
      }
      if (n > 0 && st !== "done") nav.appendChild(back);
      nav.appendChild(next);
      const inp = body.querySelector("input[type=text], input[type=password]");
      if (inp && st !== "timezone") inp.addEventListener("keydown", (e) => { if (e.key === "Enter") next.click(); });
      if (st === "timezone") $("wz-tz").addEventListener("keydown", (e) => { if (e.key === "Enter") { const f = $("wz-tzlist").querySelector(".tzitem"); if (f) f.click(); else next.click(); } });
    },
    ok(m) {
      if (!this.active) return;
      if (m.step === "internet") this.wifiNeeded = !!m.wifi;
      if (m.step === "timezone" && m.value) { this.tz = { zone: m.value, label: m.value.replace(/_/g, " "), offset: "" }; }
      if (m.step === "wifi" && m.note !== undefined) toast({ text: t("w_wifi_ok") });
      if (m.step === "done") { this.active = false; if (this.pending) { const p = this.pending; this.pending = null; setTimeout(() => say(p), 600); } return; }
      const k = this.steps.indexOf(m.step);
      this.i = (k >= 0 ? k : this.i) + 1;
      if (this.step() === "wifi" && !this.wifiNeeded) this.i++;
      this.render();
    },
    error(m) { $("wiz-error").textContent = m.text || t("error"); const b = $("wiz-nav").querySelector(".primary"); if (b) b.disabled = false; }
  };

  // ---------------------------------------------------------------- windows
  const SIZES = { s: 380, m: 560, l: 780, xl: 980 };
  const SYSTEM_IDS = new Set(["files", "notes", "away", "history", "vault-form", "sources", "screenshot"]);
  const isSystem = (id) => id.startsWith("panel-") || SYSTEM_IDS.has(id);
  // a window with another one behind it goes (nearly) solid, so nothing shows through its text
  function overlaps() {
    const list = [...wins.values()].filter(w => !w.min).map(w => ({ w, r: w.el.getBoundingClientRect() }));
    for (const a of list) {
      const hit = list.some(b => b !== a && b.r.left < a.r.right && b.r.right > a.r.left && b.r.top < a.r.bottom && b.r.bottom > a.r.top);
      a.w.el.classList.toggle("solid", hit);
    }
  }
  function openWindow(m) {
    const spec = m.spec, id = m.id;
    let w = wins.get(id);
    if (w) { w.el.querySelector(".title").textContent = spec.title || ""; renderBody(w.el.querySelector(".body"), spec); w.min = false; w.el.classList.remove("hidden"); raise(w.el); dock(); return; }
    const win = el("div", "win kind-" + (spec.kind || "panel") + " " + (spec.size || (spec.kind === "image" ? "l" : spec.kind === "media" ? "s" : "m")));
    win.dataset.id = id;
    const head = el("div", "head", `<i class="dot"></i><span class="title">${esc(spec.title || "")}</span>
      <button class="min" title="${esc(t("d_minimize"))}">–</button><button class="max" title="max">▢</button><button class="x" title="${esc(t("d_close"))}">✕</button>`);
    const body = el("div", "body");
    const grip = el("div", "grip");
    win.append(head, body, grip);
    renderBody(body, spec);
    const stage = $("stage");
    const wpx = Math.min(SIZES[spec.size] || SIZES.m, stage.clientWidth - 24);
    let x, y;
    if (isSystem(id)) {
      // the system's own windows (settings, lists, files, models, what happened while away…) share
      // one slot on the right and replace each other; the stage stays free for what the owner asked for
      for (const [oid, ow] of wins) if (oid !== id && isSystem(oid) && !ow.min) closeWindow(oid, true);
      x = Math.max(12, stage.clientWidth - wpx - 20); y = 20;
    } else {
      // conversation windows cascade from the top left and never start below the upper third
      if (24 + (cascade % 7) * 30 > stage.clientHeight * 0.34) cascade = 0;
      x = Math.max(12, Math.min(stage.clientWidth - wpx - 12, 40 + (cascade % 7) * 36));
      y = Math.max(8, 24 + (cascade % 7) * 30);
      cascade++;
    }
    win.style.left = x + "px"; win.style.top = y + "px";
    win.style.maxHeight = Math.max(160, stage.clientHeight - y - 12) + "px";   // never under the bar
    stage.appendChild(win);
    wins.set(id, { el: win, spec, min: false, max: false });
    if (cur) cur.opened = true;
    if (busy && !motionOff()) handoff(win);
    raise(win); idle(); overlaps();
    head.querySelector(".x").onclick = (e) => { e.stopPropagation(); closeWindow(id, true); };
    head.querySelector(".min").onclick = (e) => { e.stopPropagation(); minimize(id); };
    head.querySelector(".max").onclick = (e) => { e.stopPropagation(); maximize(id); };
    head.addEventListener("dblclick", (e) => { if (e.target.tagName !== "BUTTON") maximize(id); });
    win.addEventListener("mousedown", () => raise(win));
    drag(head, win); resize(grip, win);
    dock();
  }
  // a window the computer opens grows out of its own column (the bar) into place
  function towards(win, target) {
    const c = target.getBoundingClientRect(), r = win.getBoundingClientRect();
    win.style.setProperty("--dx", Math.round(c.left + c.width / 2 - (r.left + r.width / 2)) + "px");
    win.style.setProperty("--dy", Math.round(c.top + c.height / 2 - (r.top + r.height / 2)) + "px");
  }
  function handoff(win) { towards(win, $("cmd")); win.classList.add("from-ai"); win.addEventListener("animationend", () => win.classList.remove("from-ai"), { once: true }); }
  function afterAnim(e, cls, fn) {
    if (motionOff()) return fn();
    let done = false; const go = () => { if (!done) { done = true; fn(); } };
    e.addEventListener("animationend", go, { once: true }); e.classList.add(cls); setTimeout(go, 450);
  }
  function closeWindow(id, tell) {
    const w = wins.get(id); if (!w) return;
    wins.delete(id);
    if (tell) post({ t: "window.closed", id });
    afterAnim(w.el, "closing", () => { w.el.remove(); overlaps(); });
    dock(); idle(); overlaps();
  }
  function minimize(id) {
    const w = wins.get(id); if (!w) return; w.min = true;
    towards(w.el, $("dock"));
    afterAnim(w.el, "mini", () => { w.el.classList.add("hidden"); w.el.classList.remove("mini"); });
    dock(); idle();
  }
  function maximize(id) {
    const w = wins.get(id); if (!w) return;
    w.el.classList.add("geo"); setTimeout(() => w.el.classList.remove("geo"), 350);
    if (!w.max) { w.saved = { left: w.el.style.left, top: w.el.style.top, width: w.el.style.width, height: w.el.style.height, maxHeight: w.el.style.maxHeight }; w.el.classList.add("maxed"); w.el.style.left = "12px"; w.el.style.top = "8px"; w.el.style.width = "calc(100% - 24px)"; w.el.style.height = "calc(100% - 16px)"; w.el.style.maxHeight = "none"; }
    else { Object.assign(w.el.style, w.saved || {}); w.el.classList.remove("maxed"); }
    w.max = !w.max; raise(w.el);
  }
  function raise(win) { win.style.zIndex = ++z; if (focused) focused.classList.remove("focus"); focused = win; win.classList.add("focus"); if (!busy && !cur) collapseReply(); }
  function collapseReply() { const r = $("reply"); if (r.classList.contains("hidden") || r.classList.contains("collapsed")) return; clearTimeout(autoHide); r.classList.add("collapsed"); r.scrollTop = 0; }
  function expandReply() { const r = $("reply"); if (!r.classList.contains("collapsed")) return; r.classList.remove("collapsed"); r.style.animation = "none"; void r.offsetWidth; r.style.animation = ""; }
  function drag(handle, win) {
    let sx, sy, ox, oy, on = false;
    handle.addEventListener("mousedown", (e) => { if (e.target.tagName === "BUTTON") return; on = true; sx = e.clientX; sy = e.clientY; ox = win.offsetLeft; oy = win.offsetTop; win.classList.add("dragging"); e.preventDefault(); });
    window.addEventListener("mousemove", (e) => { if (!on) return; win.style.left = Math.max(-40, ox + e.clientX - sx) + "px"; win.style.top = Math.max(0, oy + e.clientY - sy) + "px"; });
    window.addEventListener("mouseup", () => { if (on) { win.classList.remove("dragging"); overlaps(); } on = false; });
  }
  function resize(grip, win) {
    let sx, sy, ow, oh, on = false;
    grip.addEventListener("mousedown", (e) => { on = true; sx = e.clientX; sy = e.clientY; ow = win.offsetWidth; oh = win.offsetHeight; win.classList.add("dragging"); e.preventDefault(); e.stopPropagation(); });
    window.addEventListener("mousemove", (e) => { if (!on) return; win.style.width = Math.max(280, ow + e.clientX - sx) + "px"; win.style.height = Math.max(120, oh + e.clientY - sy) + "px"; win.style.maxHeight = "none"; });
    window.addEventListener("mouseup", () => { if (on) { win.classList.remove("dragging"); overlaps(); } on = false; });
  }
  function dock() {
    const d = $("dock"); d.innerHTML = "";
    for (const [id, w] of wins) {
      if (!w.min) continue;
      const c = el("span", "chip", esc(w.spec.title || "…"));
      c.onclick = () => { w.min = false; w.el.classList.remove("hidden"); w.el.style.animation = "none"; void w.el.offsetWidth; w.el.style.animation = ""; raise(w.el); dock(); idle(); };
      d.appendChild(c);
    }
    for (const a of apps) {
      const c = el("span", "chip", `${esc(a.name)} <span class="x" title="${esc(t("d_close_app"))}">✕</span>`);
      c.querySelector(".x").onclick = (e) => { e.stopPropagation(); post({ t: "app.close", pid: a.pid }); };
      d.appendChild(c);
    }
  }
  let apps = [];

  // ---------------------------------------------------------------- blocks
  function renderBody(body, spec) {
    body.innerHTML = "";
    for (const b of spec.blocks || []) { const e = renderBlock(b); if (e) body.appendChild(e); }
    if (spec.actions && spec.actions.length) body.appendChild(renderBlock({ type: "buttons", items: spec.actions }));
  }
  function actionBtn(a) {
    const b = el("button", "btn small" + (a.primary ? " primary" : "") + (a.danger ? " danger" : ""), esc(a.label));
    b.onclick = () => say(a.say);
    return b;
  }
  function renderBlock(b) {
    switch (b.type) {
      case "text": return el("div", "b-text" + (b.dim ? " dim" : ""), md(b.text));
      case "heading": return el("div", "b-heading", esc(b.text));
      case "divider": return el("div", "b-divider");
      case "kv": { const e = el("div", "kv"); for (const [k, v] of b.rows) { e.append(el("span", "k", esc(k)), el("span", "v", esc(v))); } return e; }
      case "stat": {
        const e = el("div"); e.append(el("div", "stat", `<span>${esc(b.label)}</span><span class="v">${esc(b.value)}</span>`));
        if (b.fraction != null) e.append(el("div", "bar", `<i style="width:${Math.round(b.fraction * 100)}%"></i>`));
        return e;
      }
      case "progress": { const e = el("div"); e.append(el("div", "stat", `<span>${esc(b.label)}</span><span class="v">${Math.round(b.fraction * 100)}%</span>`), el("div", "bar", `<i style="width:${Math.round(b.fraction * 100)}%"></i>`)); return e; }
      case "list": {
        const e = el("div", "list" + (b.columns > 1 ? " cols-" + b.columns : ""));
        b.items.forEach((it, i) => {
          const row = el("div", "item" + (it.done ? " done" : ""));
          row.style.setProperty("--i", Math.min(i, 12));
          if (b.numbered) row.append(el("span", "n", (i + 1) + "."));
          const main = el("div", "main", `<div class="t">${esc(it.title)}${it.meta ? `<span class="meta">${esc(it.meta)}</span>` : ""}</div>${it.subtitle ? `<div class="st">${esc(it.subtitle)}</div>` : ""}`);
          if (it.detail) main.append(el("div", "det", md(it.detail)));
          row.append(main);
          if (it.actions && it.actions.length) { const acts = el("div", "acts"); it.actions.forEach(a => acts.append(actionBtn(a))); row.append(acts); }
          e.append(row);
        });
        return e;
      }
      case "table": {
        const e = el("table", "tbl");
        if (b.columns && b.columns.some(c => c)) e.append(el("tr", "", b.columns.map(c => `<th>${esc(c)}</th>`).join("")));
        for (const r of b.rows) e.append(el("tr", "", r.map(c => `<td>${esc(c)}</td>`).join("")));
        return e;
      }
      case "image": {
        const e = el("div", "b-image", `<img src="${esc(b.src.startsWith("/") ? "file://" + b.src : b.src)}" alt="">` +
          (b.caption ? `<div class="cap">${esc(b.caption)}</div>` : "") + (b.credit ? `<div class="credit">${esc(b.credit)}</div>` : ""));
        const img = e.querySelector("img"); const shown = () => img.classList.add("loaded");
        img.onload = shown; img.onerror = shown; if (img.complete) shown();
        return e;
      }
      case "buttons": { const e = el("div", "b-buttons"); b.items.forEach(a => e.append(actionBtn(a))); return e; }
      case "choices": {
        const e = el("div", "choices");
        b.items.forEach(a => {
          const c = el("button", "choice" + (b.selected && (a.label === b.selected) ? " sel" : ""), `<i class="r"></i><span><div>${esc(a.label)}</div>${a.description ? `<div class="d">${esc(a.description)}</div>` : ""}</span>`);
          c.onclick = () => { e.querySelectorAll(".choice").forEach(x => x.classList.remove("sel")); c.classList.add("sel"); say(a.say); };
          e.append(c);
        });
        return e;
      }
      case "toggle": {
        const e = el("div", "toggle", `<span>${esc(b.label)}</span>`);
        const sw = el("button", "sw" + (b.on ? " on" : "")); let on = !!b.on;
        sw.onclick = () => { on = !on; sw.classList.toggle("on", on); say(on ? b.say_on : b.say_off); };
        e.append(sw); return e;
      }
      case "form": {
        const e = el("form", "form"); const inputs = {};
        for (const f of b.fields) {
          const lab = el("label", "", esc(f.label));
          let inp;
          if (f.options && f.options.length) { inp = el("select", "", f.options.map(o => `<option${o === f.value ? " selected" : ""}>${esc(o)}</option>`).join("")); }
          else { inp = el("input"); inp.type = f.kind === "password" ? "password" : f.kind === "email" ? "email" : "text"; inp.value = f.value || ""; inp.placeholder = f.placeholder || ""; inp.autocomplete = "off"; }
          inputs[f.name] = inp; lab.append(inp); e.append(lab);
        }
        const btn = el("button", "btn primary", esc(b.submit.label)); btn.type = "submit";
        const row = el("div", "row"); row.append(btn); e.append(row);
        e.onsubmit = (ev) => {
          ev.preventDefault();
          if (b.submit.post) { const m = { t: b.submit.post }; for (const [k, inp] of Object.entries(inputs)) { m[k] = inp.value; inp.value = ""; } post(m); return; }
          let s = b.submit.say || ""; for (const [k, inp] of Object.entries(inputs)) s = s.split("{" + k + "}").join(inp.value); say(s);
        };
        return e;
      }
      case "quote": return el("div", "quote", `“${esc(b.text)}”${b.author ? `<div class="who">— ${esc(b.author)}</div>` : ""}${b.source ? `<div class="src"><a href="#" data-url="${esc(b.source)}">${esc(b.source)}</a></div>` : ""}`);
      case "code": return el("pre", "", esc(b.text));
      case "media": {
        const e = el("div", "media", `${b.thumbnail ? `<img src="${esc(b.thumbnail)}" alt="">` : ""}<div><div class="t">${esc(b.title)}</div><div class="st">${esc(b.subtitle)}</div><div class="ctl"></div></div>`);
        const ctl = e.querySelector(".ctl");
        const pb = el("button", "btn small", esc(b.state === "paused" ? t("d_resume") : t("d_pause")));
        pb.onclick = () => post({ t: "media", action: b.state === "paused" ? "resume" : "pause" });
        const sb = el("button", "btn small ghost", esc(t("d_stop"))); sb.onclick = () => post({ t: "media", action: "stop" });
        const vol = el("input"); vol.type = "range"; vol.min = 0; vol.max = 100; vol.value = 100; vol.title = t("d_volume");
        vol.onchange = () => post({ t: "media", action: "volume", value: +vol.value });
        ctl.append(pb, sb, vol); return e;
      }
      case "sources": { const e = el("div", "sources"); b.items.forEach(s => { const a = el("a", "", esc(s.title)); a.href = "#"; a.dataset.url = s.url; e.append(a); }); return e; }
    }
    return null;
  }

  // ---------------------------------------------------------------- reply card
  const THINK = '<span class="think"><i></i><i></i><i></i></span>';
  function replyStart(m) {
    $("hint").textContent = "";
    cur = { req: m.request, text: "", activity: [] };
    const r = $("reply"); r.classList.remove("closing", "writing", "collapsed");
    if (r.classList.contains("hidden")) { r.classList.remove("hidden"); } else { r.style.animation = "none"; void r.offsetWidth; r.style.animation = ""; }
    idle();
    clearTimeout(autoHide);
    // a very long request (pasted text) is previewed, not echoed whole; History keeps all of it
    $("reply-req").textContent = m.request.length > 220 ? m.request.slice(0, 220).trimEnd() + "…" : m.request;
    $("reply-activity").innerHTML = "";
    $("reply-text").className = "text"; $("reply-text").innerHTML = THINK;
    $("reply-progress").classList.add("hidden");
    orb("thinking", t("d_thinking"));
  }
  let paintQueued = false;
  function paintReply() { paintQueued = false; if (cur) { $("reply-text").innerHTML = md(cur.text); $("reply").scrollTop = 1e6; } }
  function replyDelta(m) {
    if (!cur) replyStart({ request: "" });
    if (!cur.text) { orb("thinking", t("d_writing")); $("reply").classList.add("writing"); }
    cur.text += m.text;
    // one repaint per frame, however fast tokens arrive
    if (!paintQueued) { paintQueued = true; requestAnimationFrame(paintReply); }
  }
  // a one-line answer ("Done — animations off.") steps aside by itself so the windows stay in view;
  // anything longer waits for the owner (Esc / Close), and the pointer over the card keeps it
  function replyEnd(m) {
    if (!cur) return; cur.text = m.text || cur.text; $("reply-text").innerHTML = md(cur.text); paintQueued = false;
    const short = cur.text.length < 90 && !cur.text.includes("\n"), opened = !!cur.opened;
    conv.push(cur); cur = null; histPos = -1; $("reply-progress").classList.add("hidden"); $("reply").classList.remove("writing"); orb("idle", "");
    clearTimeout(autoHide);
    // the window IS the answer: a short reply that opened one folds at once; a short answer alone steps aside after a while
    if (opened && short) setTimeout(() => { if (!busy && !cur) collapseReply(); }, motionOff() ? 0 : 900);
    else if (short && !motionOff()) autoHide = setTimeout(() => { if (!$("reply").matches(":hover") && !busy) hideReply(); }, 6000);
  }
  function replyError(m) { if (!cur) replyStart({ request: "" }); $("reply-text").className = "text err"; $("reply-text").textContent = m.text; cur.text = m.text; conv.push(cur); cur = null; histPos = -1; orb("attention", ""); setTimeout(presence, 1500); }
  function activity(m) {
    if (!cur) return;
    const box = $("reply-activity"), last = box.lastElementChild;
    if (m.replace && last) { last.textContent = m.text; cur.activity[cur.activity.length - 1] = m.text; }
    else { cur.activity.push(m.text); box.append(el("div", "", esc(m.text))); }
    $("reply").scrollTop = 1e6; orb("thinking", t("d_working"));
  }
  function hideReply() { const r = $("reply"); if (r.classList.contains("hidden")) return; afterAnim(r, "closing", () => { r.classList.add("hidden"); r.classList.remove("closing"); idle(); }); }
  function progress(m) { const p = $("reply-progress"); p.classList.remove("hidden"); const pct = m.total ? Math.round(m.done * 100 / m.total) : 0; p.querySelector("i").style.width = pct + "%"; p.querySelector("span").textContent = `${m.label} ${pct}%`; if (m.done >= m.total) setTimeout(() => p.classList.add("hidden"), 1500); }
  $("reply-close").onclick = hideReply;
  $("reply").addEventListener("click", (e) => { if ($("reply").classList.contains("collapsed")) { e.preventDefault(); expandReply(); } });
  $("reply-stop").onclick = () => post({ t: "cancel" });
  $("reply-hist").onclick = () => {
    const items = conv.slice(-40).map(c => ({ title: c.req, detail: c.text }));
    openWindow({ id: "history", spec: { title: t("d_conversation"), kind: "text", size: "m", blocks: [{ type: "list", items: items.length ? items : [{ title: t("d_empty") }], numbered: false }] } });
  };

  // ---------------------------------------------------------------- toasts, dialogs
  function toast(m) {
    if (m.sticky) { const old = sticky.get(m.sticky); if (old) { old.remove(); sticky.delete(m.sticky); } if (!m.text) return; }
    const e = el("div", "toast", esc(m.text));
    $("toasts").append(e);
    if (m.sticky) sticky.set(m.sticky, e); else setTimeout(() => afterAnim(e, "out", () => e.remove()), m.long ? 9000 : 3500);
  }
  function dialogDone(ov) { ov.classList.add("hidden"); dialogOpen = false; presence(); }
  function dialog(m) {
    const ov = $("overlay"); ov.innerHTML = ""; ov.classList.remove("hidden"); dialogOpen = true; presence();
    const d = el("div", "dlg" + (m.danger ? " danger" : ""), `<h3><i class="orb small attention"></i>${esc(m.title)}</h3><div class="body${m.mono ? " mono" : ""}">${esc(m.text)}</div>`);
    const row = el("div", "row");
    for (const b of m.buttons) { const btn = el("button", "btn" + (b.primary ? " primary" : ""), esc(b.label)); btn.onclick = () => { dialogDone(ov); post({ t: "dialog", id: m.id, value: b.value }); }; row.append(btn); }
    d.append(row); ov.append(d);
    ov.dataset.id = m.id;
    setTimeout(() => { const p = d.querySelector(".primary"); if (p) p.focus(); }, 30);
  }

  // ---------------------------------------------------------------- input
  const inp = $("in");
  function send() {
    const v = inp.value; histPos = -1; if (!v.trim()) return;
    inp.classList.remove("sent"); void inp.offsetWidth; inp.classList.add("sent");
    setTimeout(() => { inp.value = ""; inp.classList.remove("sent"); }, motionOff() ? 0 : 140);
    say(v);
  }
  $("send").onclick = send;
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); send(); }
    else if (e.key === "ArrowUp" && conv.length) { e.preventDefault(); histPos = histPos < 0 ? conv.length - 1 : Math.max(0, histPos - 1); inp.value = conv[histPos].req; }
    else if (e.key === "ArrowDown" && histPos >= 0) { e.preventDefault(); histPos = histPos + 1 >= conv.length ? -1 : histPos + 1; inp.value = histPos < 0 ? "" : conv[histPos].req; }
  });
  $("mic").onclick = () => post({ t: "voice" });
  // the OS auto-locks after idle time: tell it the owner is here (at most once every 20 s)
  let lastPing = 0;
  const ping = () => { const now = Date.now(); if (now - lastPing > 20000) { lastPing = now; post({ t: "active" }); } };
  for (const ev of ["keydown", "mousedown", "mousemove", "wheel", "touchstart"]) document.addEventListener(ev, ping, { passive: true });
  document.addEventListener("keydown", (e) => {
    const ov = $("overlay");
    if (!ov.classList.contains("hidden")) {
      if (e.key === "Escape") { dialogDone(ov); post({ t: "dialog", id: ov.dataset.id, value: "no" }); }
      return;
    }
    if (wizard.active) return;
    if (e.key === "Escape") {
      if (document.activeElement === inp && inp.value) { inp.value = ""; return; }
      if (focused && wins.has(focused.dataset.id)) { closeWindow(focused.dataset.id, true); focused = null; return; }
      hideReply();
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "l") { e.preventDefault(); inp.focus(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "w" && focused && wins.has(focused.dataset.id)) { e.preventDefault(); closeWindow(focused.dataset.id, true); focused = null; }
    if (e.key === "F1") { e.preventDefault(); post({ t: "voice" }); }
    if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key.length === 1 && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA" && document.activeElement.tagName !== "SELECT") inp.focus();
  });

  // ---------------------------------------------------------------- dispatch
  window.llmos = {
    receive(m) {
      switch (m.t) {
        case "theme": return applyTheme(m);
        case "status": return status(m);
        case "screen": return screen(m);
        case "window": return openWindow(m);
        case "window.close": return closeWindow(m.id, false);
        case "reply.start": return replyStart(m);
        case "reply.delta": return replyDelta(m);
        case "reply.end": return replyEnd(m);
        case "reply.error": return replyError(m);
        case "activity": return activity(m);
        case "progress": return progress(m);
        case "toast": return toast(m);
        case "dialog": return dialog(m);
        case "dialog.close": if ($("overlay").dataset.id === m.id) dialogDone($("overlay")); return;
        case "listening": $("mic").classList.toggle("on", !!m.on); listening = !!m.on; presence(); if (m.on) toast({ text: t("listening"), sticky: "listen" }); else toast({ text: "", sticky: "listen" }); return;
        case "heard": return toast({ text: t("heard") + ": " + m.text });
        case "apps": apps = m.items || []; return dock();
        case "wizard.ok": return wizard.ok(m);
        case "wizard.error": return wizard.error(m);
        case "tz.results": if (wizard.active && wizard.onTz) wizard.onTz(m.items || []); return;
        case "wifi.list": wizard.nets = m.items || []; if (wizard.active && wizard.onWifi) wizard.onWifi(wizard.nets); return;
        case "unlock.error": { $("lock-busy").classList.add("hidden"); $("lock-error").textContent = m.text; $("lock-pass").value = ""; $("lock-pass").focus();
          const c = $("lock-card"); c.classList.remove("shake"); void c.offsetWidth; c.classList.add("shake"); return; }
        case "speaking": speaking = !!m.on; presence(); return;
        case "unlock.busy": $("lock-busy").classList.remove("hidden"); return;
        case "clear": for (const id of [...wins.keys()]) closeWindow(id, false); conv.length = 0; $("reply").classList.add("hidden"); idle(); return;
        case "eval": try { (0, eval)(m.js); } catch (e) { console.log(e); } return;
      }
    }
  };
  clock();
  post({ t: "ready" });
})();
