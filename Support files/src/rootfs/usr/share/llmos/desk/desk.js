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
  let dialogOpen = false, speaking = false, wallpaper = "", autoHide = null, modelOk = true;
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
    const inline = (s) => {
      const codes = [], links = [];
      let t = String(s).replace(/`([^`\n]+)`/g, (m, c) => { codes.push(c); return "\u0001" + (codes.length - 1) + "\u0001"; });
      t = t.replace(/https?:\/\/[^\s<>"')\]]+/g, (u) => { links.push(u); return "\u0002" + (links.length - 1) + "\u0002"; });
      t = esc(t)
        .replace(/\*\*(\S(?:[^*\n]*?\S)?)\*\*/g, "<b>$1</b>")
        .replace(/(^|[\s(])\*(\S(?:[^*\n]*?\S)?)\*(?=[\s.,;:!?)]|$)/g, "$1<i>$2</i>");
      t = t.replace(/\u0002(\d+)\u0002/g, (m, i) => `<a href="#" data-url="${esc(links[i])}">${esc(links[i])}</a>`);
      return t.replace(/\u0001(\d+)\u0001/g, (m, i) => `<code>${esc(codes[i])}</code>`);
    };
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
  // the owner's apps talk to the OS only through these messages: load their saved state, save it, hand over a file
  window.addEventListener("message", (e) => {
    const f = [...document.querySelectorAll("iframe.app")].find(x => x.contentWindow === e.source);
    if (!f || !e.data || typeof e.data !== "object") return;
    const m = e.data, id = f.dataset.app;
    if (m.llmos === "load") e.source.postMessage({ llmos: "state", state: f.llmosState == null ? null : f.llmosState }, "*");
    else if (m.llmos === "save") { f.llmosState = m.state; post({ t: "app.save", id, state: m.state }); }
    else if (m.llmos === "export" && typeof m.data === "string") post({ t: "app.export", id, name: String(m.name || "picture.png"), data: m.data });
    else if (m.llmos === "pressed" || m.llmos === "page") post({ t: "app.result", id, data: m });
  });
  // the OS uses an open app the way a person would: press a control by its label, or read what the page shows
  window.llmosApp = (what, text, id) => {
    const fs = [...document.querySelectorAll("iframe.app")];
    const f = (id && fs.find(x => x.dataset.app === id)) || fs[fs.length - 1];
    if (!f) { post({ t: "app.result", id: "", data: { llmos: what === "read" ? "page" : "pressed", ok: false, none: true } }); return; }
    f.contentWindow.postMessage({ llmos: what, text }, "*");
  };
  // a button: the OS does it at once (never behind a request the model is still working on)
  // a button pressed: the previous answer (folded at the bottom) is not about this, so it steps aside instead of
  // staying on screen as if it were the result (the button's own result comes as a notice or a window)
  function act(text) { if (text && text.trim()) { post({ t: "act", text: text.trim() }); if (!busy && !cur && typeof hideReply === "function") hideReply(); } }
  // Do (act on it) or Ask (an answer in words, no actions): the owner's choice, remembered on this computer
  let askMode = false;
  try { askMode = localStorage.getItem("llmos-mode") === "ask"; } catch (e) {}
  function paintMode() {
    const b = $("mode"); if (!b) return;
    b.textContent = askMode ? t("d_mode_ask") : t("d_mode_do"); b.setAttribute("aria-pressed", askMode ? "true" : "false");
    b.title = askMode ? t("d_mode_ask_tip") : t("d_mode_do_tip");
  }
  if ($("mode")) $("mode").onclick = () => { askMode = !askMode; try { localStorage.setItem("llmos-mode", askMode ? "ask" : "do"); } catch (e) {} paintMode(); $("in").focus(); };
  paintMode();
  function say(text) { if (!text || !text.trim()) return; if (text.trim().toLowerCase() === "lock") { post({ t: "lock" }); return; } post({ t: "say", text: text.trim(), mode: askMode ? "ask" : "do" }); }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-url]");
    if (a) { e.preventDefault(); say("open " + a.dataset.url + " in the browser"); }
  });

  // ---------------------------------------------------------------- theme / strings
  function applyTheme(m) {
    const root = document.documentElement.style;
    for (const k of ["--bg", "--fg", "--accent", "--on-accent", "--on-danger"]) root.removeProperty(k);
    for (const [k, v] of Object.entries(m.css || {})) root.setProperty(k, v);
    document.body.className = m.mode === "light" ? "light" : "dark";
    let st = $("owner-style");
    if (!st) { st = document.createElement("style"); st.id = "owner-style"; document.head.append(st); }
    st.textContent = m.style || "";
    ownerStyle();
    document.documentElement.dataset.motion = ["full", "reduced", "off"].includes(m.motion) ? m.motion : "full";
    const layout = ["windows", "mac"].includes(m.layout) ? m.layout : "clean";
    if (document.documentElement.dataset.layout !== layout) { document.documentElement.dataset.layout = layout; startMenu(false); dock(); }
    software = !!m.software;
    if (software) document.documentElement.dataset.software = "1"; else delete document.documentElement.dataset.software;
    document.documentElement.lang = m.lang || "en";
    clock24 = typeof m.clock24 === "boolean" ? m.clock24 : null;     // the owner's 24-hour choice (null: the language's own)
    clock();
    document.documentElement.dir = m.dir || "ltr";
    lang = m.lang || "en";
    Object.assign(S, m.strings || {});
    document.querySelectorAll("[data-s]").forEach(e => { e.textContent = t(e.dataset.s); });
    document.querySelectorAll("[data-ph]").forEach(e => { e.placeholder = t(e.dataset.ph); e.setAttribute("aria-label", t(e.dataset.ph)); });
    $("in").placeholder = t("hint", "Tell me what you want…");
    paintMode();
    $("in").setAttribute("aria-label", t("hint", "Tell me what you want…"));
    const desk = $("desk");
    if ((m.wallpaper || "") !== wallpaper && wallpaper && !motionOff()) {
      // the old picture fades out over the new one
      const old = el("div", ""); old.id = "wallfade"; old.style.backgroundImage = `url("${wallpaper}")`;
      desk.prepend(old); setTimeout(() => old.remove(), 900);
    }
    wallpaper = m.wallpaper || "";
    if (m.wallpaper) { desk.style.backgroundImage = `url("${m.wallpaper}")`; desk.classList.add("wall"); }
    else { desk.style.backgroundImage = ""; desk.classList.remove("wall"); }
    try { LLMBG.theme({ mode: m.mode, style: m.backdrop || (m.wallpaper ? "photo" : "living"), motion: document.documentElement.dataset.motion, software: !!m.software }); } catch (e) { console.log(e); }
    if (wizard.active) wizard.render();
  }

  // ---------------------------------------------------------------- the computer's presence
  // idle | thinking | speaking | listening | attention | off -- shown by the orb in the bar and on the reply card
  let online = false;        // the current reply comes from the online model
  function orb(state, label) {
    try { LLMBG.mood(state, online); } catch (e) {}
    for (const id of ["orb", "reply-orb"]) {
      const e = $(id); if (!e) continue;
      e.className = (id === "reply-orb" ? "orb small " : "orb ") + (state === "idle" ? "" : state) + (online && state !== "idle" ? " online" : "");
    }
    const st = $("reply-state"); if (st && label !== undefined) { lastLabel = label; st.textContent = stateText(); }
  }
  // how long it has been thinking, and how long that usually takes on this machine (the OS sends an estimate from
  // the model's own speed figures); updated once a second, text only
  let lastLabel = "";
  function hms(s) { s = Math.max(0, Math.round(s)); if (s < 60) return s + " s"; const m = Math.floor(s / 60), h = Math.floor(m / 60); if (h) return h + " h " + (m % 60) + " min"; return m + " min" + (m < 5 && s % 60 ? " " + (s % 60) + " s" : ""); }
  function stateText() {
    if (!cur || !cur.t0 || !lastLabel) return lastLabel;
    const e = (Date.now() - cur.t0) / 1000;
    // past twice the usual time the estimate means nothing: say so plainly and point at Stop
    const late = cur.eta && e > 2 * cur.eta + 10;
    return lastLabel + (e >= 2 ? " · " + hms(e) + (cur.eta && !late ? " / " + fmt("d_usually", { s: hms(cur.eta) }) : late ? " · " + t("d_slow_turn", "this is taking long; Stop ends it") : "") : "");
  }
  setInterval(() => { if (cur && cur.t0 && lastLabel) { const st = $("reply-state"); if (st) st.textContent = stateText(); } }, 1000);
  function replyBrain(m) {
    online = !!m.online;
    const e = $("reply-brain"); e.textContent = online ? fmt("d_online_tag", { model: m.label || "" }) : ""; e.classList.toggle("hidden", !online);
    for (const id of ["orb", "reply-orb"]) $(id).classList.toggle("online", online && $(id).className.indexOf("thinking") >= 0);
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
    box.innerHTML = `<div><div class="orb big"><i class="halo"></i></div><h1>${esc(ownerName ? g + ", " + ownerName : g)}</h1><p>${esc(t("d_idle_hint"))}</p><div class="sugg"></div></div>`;
    const sg = box.querySelector(".sugg");
    ["g_ex1", "g_ex2", "g_ex3"].forEach((k, i) => { const b = el("button", "btn small", esc(t(k))); b.style.setProperty("--i", i); b.onclick = () => say(t(k)); sg.append(b); });
    box.classList.remove("closing", "hidden");
  }
  // the orb's idle breathing: one style change 8 times a second, nothing when motion is reduced or off
  // Continuous motion is rationed: every change repaints the screen, and a software-rendered VM pays
  // ~14 ms for each. The idle glow breathes at 4 changes/s there (10 on real hardware); the thinking
  // ring turns 8 times a second only while something is thinking; one-shot transitions stay smooth.
  // Big orbs carry their halo in the markup (index.html and the idle template).
  let lastGlow = "", lastSpin = -1, software = false;
  function tick() {
    const lvl = document.documentElement.dataset.motion || "full";
    const full = lvl === "full" && !document.hidden;
    const g = full ? (0.25 + 0.75 * (1 - Math.cos(performance.now() / 4600 * 2 * Math.PI)) / 2).toFixed(2) : "0.3";
    if (g !== lastGlow) { lastGlow = g; for (const h of document.querySelectorAll(".screen:not(.hidden) .halo, #desk:not(.hidden) .halo")) h.style.opacity = g; }
    const thinking = document.querySelectorAll(".orb.thinking");
    if (lvl === "full" && thinking.length) { const a = Math.round(performance.now() / 125) * 45 % 360; if (a !== lastSpin) { lastSpin = a; thinking.forEach(o => o.style.setProperty("--spin", a + "deg")); } }
    setTimeout(tick, software ? 250 : 100);
  }
  tick();
  function presence() {
    if (dialogOpen) return orb("attention", t("d_waiting"));
    if (listening) return orb("listening", t("d_listening"));
    if (speaking) return orb("speaking", t("d_speaking"));
    if (busy) return;                        // the reply code sets thinking / writing
    orb(modelOk ? "idle" : "off", "");
  }

  // ---------------------------------------------------------------- status bar
  // an icon opens its window; clicking the same icon again closes it (the window it opened is remembered by its words)
  const launched = new Map(); let pendingLaunch = null;
  function launch(sayText) {
    const id = launched.get(sayText), w = id && wins.get(id);
    if (w && !w.min) { launched.delete(sayText); closeWindow(id, true); return; }
    pendingLaunch = { say: sayText, at: performance.now() };
    act(sayText);
  }
  function noteLaunch(id) {
    if (pendingLaunch && performance.now() - pendingLaunch.at < 15000) { launched.set(pendingLaunch.say, id); pendingLaunch = null; }
  }
  function chip(html, sayText, title) {
    const c = el("button", "chip", html);
    c.type = "button";
    if (sayText) { c.onclick = () => (sayText === "lock" ? post({ t: "lock" }) : launch(sayText)); c.title = title || sayText; c.setAttribute("aria-label", title || sayText); }   // lock: at once, like typing it
    else { c.disabled = true; }
    return c;
  }
  function status(m) {
    busy = !!m.busy; listening = !!m.listening;
    if (m.volume != null) document.querySelectorAll("input.npvol").forEach(v => { if (document.activeElement !== v) v.value = m.volume; });
    const box = $("status"); box.innerHTML = "";
    const dot = m.model_ok ? (busy ? "busy" : "ok") : "";
    box.append(chip(`<i class="dot ${dot}"></i>${esc(m.model || t("loading_model"))}`, "models", (m.host_gpu ? t("d_host_gpu") + " · " : "") + t("models")));
    fullTrust = m.autonomy === "hands-off";
    box.append(chip(esc({ "hands-off": t("q_autonomy_0_s"), "balanced": t("q_autonomy_1_s"), "hands-on": t("q_autonomy_2_s") }[m.autonomy] || m.autonomy), "settings", t("settings")));
    if (m.internet !== "yes") box.append(chip(esc(m.internet === "no" ? "offline" : "internet: ask"), "settings"));
    if (m.brain && m.brain !== "local") { const c = chip(`<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M6.5 20a4.5 4.5 0 0 1-.4-8.98A6 6 0 0 1 17.7 9.1 4 4 0 0 1 18 17h-.5v3h-11z"/></svg> ${esc(m.brain === "cloud" ? (m.cloud || t("v_not_set_up")) : t("d_brain_chip_ask"))}`, "settings", t("s_brain")); c.classList.add("online"); box.append(c); }
    if (m.tor) box.append(chip("Tor", "settings"));
    if (m.focus) box.append(chip("focus", "turn off focus mode"));
    if (m.vault !== "off") box.append(chip(`<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M17 9V7a5 5 0 0 0-10 0v2H5v12h14V9h-2zm-8-2a3 3 0 0 1 6 0v2H9V7z"/></svg>${m.vault === "on" ? "" : " " + esc(t("locked_short"))}`, m.vault === "on" ? "lock" : null, t("d_lock_tip")));
    // the everyday controls every computer shows: apps, network, sound, battery, power -- each opens its panel at once
    const ic = (d) => `<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="${d}"/></svg>`;
    box.prepend(chip(ic("M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h6v6h-6z"), "show my apps", t("d_myapps")));
    if (m.live) { const c = chip(esc(t("d_live_chip")), "install llm os on this computer", t("d_live_title")); c.classList.add("warn"); box.prepend(c); }
    box.append(chip(m.net === "offline" ? ic("M2 4.3 3.3 3 21 20.7 19.7 22l-3.4-3.4L12 21 .6 9.6a17 17 0 0 1 4.2-2.9zM12 3c4.4 0 8.4 1.7 11.4 4.6l-6.5 6.5L8.6 5.8A16 16 0 0 1 12 3z")
                        : m.net === "wired" ? ic("M7 3h10v6h-3v4h5v4h2v4h-6v-4h2v-2H7v2h2v4H3v-4h2v-4h5V9H7z")
                        : ic("M12 21 .6 9.6A16.5 16.5 0 0 1 12 5c4.4 0 8.4 1.7 11.4 4.6z"), "network", t("d_network")));
    if (m.volume != null) box.append(chip(ic(m.volume === 0 || m.muted ? "M3 9v6h4l5 5V4L7 9zm13.6 3 2.7-2.7-1.4-1.4L15.2 10.6 12.5 7.9l-1.4 1.4 2.7 2.7-2.7 2.7 1.4 1.4 2.7-2.7 2.7 2.7 1.4-1.4z"
                        : "M3 9v6h4l5 5V4L7 9zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4z"), "sound", t("d_sound") + " " + (m.muted ? t("d_muted", "muted") : m.volume + "%")));
    if (m.battery) box.append(chip(ic("M16 4h-2V2h-4v2H8a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1z") + ` ${m.battery.pct}%${m.battery.charging ? "⚡" : ""}`, "power", t("d_battery")));
    box.append(chip(ic("M13 3h-2v10h2zm4.8 2.2-1.4 1.4A6.96 6.96 0 0 1 19 12a7 7 0 1 1-11.4-5.4L6.2 5.2A9 9 0 1 0 21 12c0-2.7-1.2-5.2-3.2-6.8z"), "power", t("d_power")));
    $("greet").textContent = m.name ? "· " + m.name : "";
    if (m.name !== ownerName) { ownerName = m.name || ""; const h = $("idle").querySelector("h1"); if (h) { const g = h.textContent.split(",")[0]; h.textContent = ownerName ? g + ", " + ownerName : g; } }
    $("mic").classList.toggle("off", !m.mic);
    $("reply-stop").classList.toggle("hidden", !busy);
    $("reply").classList.toggle("busy", busy);
    $("cmd").classList.toggle("busy", busy);
    modelOk = !!m.model_ok;
    presence();
  }
  let clock24 = null;
  function clock() {
    const now = new Date();
    try { $("clock").textContent = now.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit", hour12: clock24 === null ? undefined : !clock24 }) + "   " + now.toLocaleDateString(lang, { weekday: "short", day: "numeric", month: "short" }); }
    catch (e) { $("clock").textContent = now.toLocaleTimeString(); }
  }
  setInterval(clock, 1000);
  $("clock").style.cursor = "pointer"; $("clock").title = t("d_clock_title", "Clock & calendar");
  const openClock = () => act("open the clock");
  $("clock").tabIndex = 0; $("clock").setAttribute("role", "button"); $("clock").setAttribute("aria-label", t("d_clock_title", "Clock & calendar"));
  $("clock").addEventListener("click", openClock);
  $("clock").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openClock(); } });

  // ---------------------------------------------------------------- screens
  function ownerStyle() {           // the owner's own style applies to the desk only: never the lock screen or setup
    const st = $("owner-style");
    if (st) st.disabled = $("desk").classList.contains("hidden");
  }
  function screen(m) {
    ["screen-boot", "screen-lock", "screen-wizard", "screen-bye", "desk"].forEach(id => $(id).classList.add("hidden"));
    setTimeout(ownerStyle, 0);
    $("boot-orb").classList.remove("thinking");
    if (m.name === "lock") { lockOpen = !!(m.data || {}).open; $("lock-pass").classList.toggle("hidden", lockOpen); $("lock-go").disabled = false; $("screen-lock").classList.remove("hidden"); $("lock-error").textContent = ""; $("lock-note").textContent = (m.data || {}).note || ""; $("lock-pass").value = ""; setTimeout(() => (lockOpen ? $("lock-go") : $("lock-pass")).focus(), 50); }
    else if (m.name === "wizard") { $("screen-wizard").classList.remove("hidden"); wizard.start(m.data || {}); }
    else if (m.name === "bye") { $("screen-bye").classList.remove("hidden"); $("bye-text").textContent = (m.data || {}).text || ""; }
    else if (m.name === "desk") { $("desk").classList.remove("hidden"); try { LLMBG.show(); } catch (e) {} wizard.active = false; if (!conv.length) $("hint").textContent = t("d_shortcuts"); setTimeout(() => $("in").focus(), 50); idle(); }
    else $("screen-boot").classList.remove("hidden");
  }
  let lockOpen = false;   // locked without a passphrase: the button alone unlocks
  $("lock-go").onclick = () => { const p = $("lock-pass").value; if (lockOpen) { post({ t: "unlock", passphrase: "" }); return; } if (p && !$("lock-go").disabled) { $("lock-go").disabled = true; $("lock-busy").classList.remove("hidden"); post({ t: "unlock", passphrase: p }); } };
  $("lock-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") $("lock-go").click(); });

  // ---------------------------------------------------------------- first-run set-up
  // a trailing note reads as its own sentence: capital first letter, full stop at the end (display only, not in i18n)
  const slowNote = s => { s = String(s); s = s.charAt(0).toUpperCase() + s.slice(1); return /[.!?。！？]$/.test(s) ? s : s + "."; };
  const wizard = {
    active: false, i: 0, data: {}, answers: {}, tz: null, wifiSel: null, nets: null, wifiNeeded: false, cloudNeeded: false, summary: null,
    steps: ["welcome", "language", "name", "timezone", "profile", "passphrase", "wifi", "cloud", "done"],
    start(data) { this.active = true; this.i = 0; this.data = data; this.answers = {}; this.capTier = null; this.modelPick = ""; this.tz = data.tz_label || null; this.wifiNeeded = false; this.cloudNeeded = false; this.summary = null; this.nets = null; this.answers.language = data.lang_hint || "en"; this.render(); },
    step() { return this.steps[this.i]; },
    hidden(s) { return (s === "wifi" && !this.wifiNeeded) || (s === "cloud" && !this.cloudNeeded); },
    visible() { return this.steps.filter(s => s !== "welcome" && s !== "done" && !this.hidden(s)); },
    render() {
      const body = $("wiz-body"), nav = $("wiz-nav"), st = this.step();
      $("wiz-error").textContent = "";
      document.querySelector(".wizard").classList.toggle("wide", st === "profile");
      body.classList.remove("swap", "backwards"); void body.offsetWidth; body.classList.add("swap"); if (this.back) body.classList.add("backwards"); this.back = false;
      const vis = this.visible(), n = vis.indexOf(st);
      $("wiz-dots").innerHTML = vis.map((s, k) => `<i class="${k <= n || st === "done" ? "on" : ""}"></i>`).join("");
      $("wiz-step").textContent = "";   // the dots already say where we are
      nav.innerHTML = "";
      const next = el("button", "btn primary", esc(t("d_next")));
      const back = el("button", "btn ghost", esc(t("d_back")));
      back.onclick = () => { if (this.i > 0) { this.i--; while (this.i > 0 && this.hidden(this.step())) this.i--; this.back = true; this.render(); } };
      const submit = (value) => { if (!["cloud", "passphrase", "wifi"].includes(st)) this.answers[st] = value; post({ t: "wizard", step: st, value }); next.disabled = true; };
      const pickList = (box, items, key, render) => {
        for (const it of items) {
          const b = el("button", "opt" + (this.answers[key] === it.value ? " sel" : ""), render(it));
          b.onclick = () => { box.querySelectorAll(".opt").forEach(x => x.classList.remove("sel")); b.classList.add("sel"); this.answers[key] = it.value; };
          box.appendChild(b);
        }
      };
      if (st === "welcome") {
        body.innerHTML = `<div class="orb big" style="margin:8px auto 4px"><i class="halo"></i></div><h2 style="font-size:30px;margin-top:10px;text-align:center">${esc(t("w_title"))}</h2><p class="lead">${esc(t("w_text"))}</p>`;
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
      } else if (st === "profile") {
        // one card per setting: its two or three choices as buttons and, under them, what the chosen one means.
        // The on-device model's choices are this computer's real models (worked out by the OS from its memory),
        // with what each needs; the model and the screen get a recommendation from the computer's specs.
        const D = this.data, sys = D.system || {}, tiersAll = D.tiers || { on: [], off: [] }, recAll = D.recommend || { on: {}, off: {} };
        const Q = [{ k: "autonomy", n: 3 }, { k: "internet", n: 3 }, { k: "brain", n: 3 }, { k: "capability", n: 3 }, { k: "guidance", n: 2 }, { k: "motion", n: 3 }];
        const TIER = ["fast", "balanced", "capable"];
        const val = (q, i) => q.n === 2 ? i * 100 : i * 50;                                    // what the OS reads
        const idx = (q, v) => q.n === 2 ? (v < 50 ? 0 : 1) : (v < 34 ? 0 : v < 67 ? 1 : 2);
        const online = () => !this.answers.profile || idx(Q[1], this.answers.profile.internet) !== 2;
        const tiers = () => (online() ? tiersAll.on : tiersAll.off) || [];
        const allAll = D.all_models || { on: [], off: [] };
        const allModels = () => (online() ? allAll.on : allAll.off) || [];   // every model the owner may pick ("More models")
        const rec = () => (online() ? recAll.on : recAll.off) || {};
        if (!this.answers.profile) {
          const r = rec();
          this.answers.profile = { autonomy: 0, internet: 0, brain: 0, capability: val(Q[3], Math.max(0, TIER.indexOf(r.capability))),
                                   guidance: 0, motion: val(Q[5], r.motion == null ? 2 : r.motion), model: "" };
        }
        const P = this.answers.profile;
        const specs = [sys.ram_gb ? fmt("w_sys_mem", { n: sys.ram_gb }) : "", sys.cores ? fmt("w_sys_cores", { n: sys.cores }) : "",
                       sys.accel ? (sys.gpu ? fmt("w_sys_gpu", { name: sys.gpu }) : "") : t("w_sys_gpu_basic")].filter(Boolean);
        body.innerHTML = `<h2>${esc(t("w_quiz_title"))}</h2>
          <div class="intro"><p class="lead2">${esc(t("w_quiz_text"))}</p>${specs.length ? `<div class="syscheck">${esc(fmt("w_sys", { parts: specs.join(" · ") }))}</div>` : ""}</div>
          <div class="quiz" id="wz-quiz"></div>`;
        const box = $("wz-quiz"), cards = {};
        const recNote = (el2, same, choice) => { el2.className = "qx" + (same ? " rec" : ""); el2.textContent = same ? "✓ " + t("w_rec_this") : fmt("w_rec_other", { choice }); };   // in the card's title row
        const fill = (q) => {
          const card = cards[q.k], seg = card.querySelector(".seg"), qd = card.querySelector(".qd"), qx = card.querySelector(".qx"), mm = card.querySelector(".morem");
          seg.innerHTML = ""; qx.textContent = ""; qx.className = "qx"; mm.innerHTML = "";
          let opts = [], desc = "";
          if (q.k === "capability") {
            const ts = tiers(), all = allModels();
            if (!all.length) { seg.classList.add("hidden"); qd.textContent = t("w_model_none"); P.model = ""; return; }
            seg.classList.remove("hidden");
            // the owner's pick (or the recommendation) where it exists; offline only installed models can be chosen, and
            // going back online returns to the pick. The slider's stop is the tier; a model picked under "More models" wins.
            const st = ts.find(x => x.tier === (this.capTier || rec().capability)) || ts.find(x => x.tier === rec().capability) || ts[0];
            const sel = (this.modelPick && all.find(x => x.id === this.modelPick)) || st;
            P.model = sel.id; P.capability = val(q, TIER.indexOf(st.tier));
            opts = ts.map(x => ({ label: t(`q_capability_${TIER.indexOf(x.tier)}_s`), on: x === st && sel === st,
                                  pick: () => { this.capTier = x.tier; this.modelPick = ""; fill(q); } }));
            desc = fmt("w_model_need", { model: sel.name, need: sel.need_gb, ram: sys.ram_gb || "?" }) + " " +
                   (sel.installed ? t("w_model_ready") : fmt("w_model_dl", { size: sel.size_gb })) + (sel.bigger ? " " + slowNote(t("w_model_slow")) : "");
            const r = ts.find(x => x.tier === rec().capability);
            if (r && ts.length > 1) recNote(qx, r === sel, t(`q_capability_${TIER.indexOf(r.tier)}_s`));
            // "More models": a plain link that opens a list of every model; a row picks that model id into P.model
            const more = el("button", "btn morem", esc(t("w_more_models")));
            more.type = "button"; more.setAttribute("aria-expanded", String(!!this.modelsOpen));
            more.onclick = () => { this.modelsOpen = !this.modelsOpen; fill(q); };
            mm.appendChild(more);
            if (this.modelsOpen) {
              const list = el("div", "modelist");
              for (const m of all) {
                const row = el("button", "btn", esc(`${m.name} — ${Number(m.size_gb).toFixed(1)} GB` +(m.bigger ? ` — ${t("w_model_slow")}` : "")));
                row.type = "button"; row.setAttribute("aria-pressed", String(sel.id === m.id));
                row.onclick = () => { this.modelPick = m.id; fill(q); };
                list.appendChild(row);
              }
              mm.appendChild(list);
            }
          } else {
            const lock = q.k === "brain" && !online(), cur = lock ? 0 : idx(q, P[q.k]);
            opts = Array.from({ length: q.n }, (_, i) => ({ label: t(`q_${q.k}_${i}_s`), on: i === cur, off: lock && i > 0,
              pick: () => { P[q.k] = val(q, i); fill(q); if (q.k === "internet") { fill(Q[2]); fill(Q[3]); } } }));
            desc = lock ? t("q_brain_offline") : t(`q_${q.k}_${cur}`);
            if (q.k === "motion" && rec().motion != null) recNote(qx, rec().motion === cur, t(`q_motion_${rec().motion}_s`));
          }
          for (const o of opts) {
            const b = el("button", "", esc(o.label));
            b.type = "button"; b.setAttribute("role", "radio"); b.setAttribute("aria-checked", String(!!o.on));
            if (o.off) b.disabled = true;
            b.onclick = () => { o.pick(); const back = [...cards[q.k].querySelectorAll(".seg button")].find(x => x.textContent === o.label); if (back) back.focus(); };
            seg.appendChild(b);
          }
          qd.textContent = desc;
        };
        for (const q of Q) {
          const card = el("section", "q");
          card.innerHTML = `<div class="qh"><span class="qt" id="ql-${q.k}">${esc(t("q_" + q.k))}</span><span class="qx"></span></div><div class="seg" role="radiogroup" aria-labelledby="ql-${q.k}"></div><div class="qd"></div><div class="morem"></div>`;
          cards[q.k] = card; box.appendChild(card);
        }
        Q.forEach(fill);
        next.onclick = () => submit({ ...P });
      } else if (st === "cloud") {
        // connect an online model by signing in: the service's own key page opens in a window; the key the owner
        // copies there comes in by itself (the OS reads it from the clipboard and checks it; it never reaches this page)
        const provs = (this.data.cloud_providers || []).filter(p => p.signin);
        const C = this.answers.cloud || (this.answers.cloud = { provider: provs[0] ? provs[0].id : "anthropic", connected: false });
        body.innerHTML = `<h2>${esc(t("w_cloud_title"))}</h2><p class="lead2">${esc(t("w_cloud_text"))}</p>
          <div class="seg big" id="wz-prov" role="radiogroup" aria-label="${esc(t("w_cloud_title"))}"></div>
          <button class="btn primary big" id="wz-signin" type="button"></button>
          <p class="how">${esc(t("w_cloud_signin_how"))}</p>
          <div class="note" id="wz-cnote" role="status"></div>
          <details class="paste"><summary>${esc(t("w_cloud_paste"))}</summary>
            <div class="pwrow"><input id="wz-ckey" type="password" autocomplete="off"><button class="btn" id="wz-ccheck" type="button">${esc(t("w_cloud_check"))}</button></div></details>`;
        const prov = () => provs.find(p => p.id === C.provider) || provs[0] || { name: "", key_hint: "" };
        const note = (text, cls) => { const n = $("wz-cnote"); text = String(text || ""); n.textContent = text.charAt(0).toUpperCase() + text.slice(1); n.className = "note" + (cls ? " " + cls : ""); };
        const drawProv = () => {
          const box = $("wz-prov"); box.innerHTML = "";
          for (const p of provs) {
            const b = el("button", "", esc(p.name)); b.type = "button"; b.setAttribute("role", "radio"); b.setAttribute("aria-checked", String(p.id === C.provider));
            b.onclick = () => { C.provider = p.id; drawProv(); };
            box.appendChild(b);
          }
          $("wz-signin").textContent = fmt("w_cloud_signin", { name: prov().name });
          $("wz-ckey").placeholder = prov().key_hint || t("w_cloud_key");
        };
        drawProv();
        $("wz-signin").onclick = () => { note(t("w_cloud_waiting")); post({ t: "signin", provider: C.provider }); };
        $("wz-ccheck").onclick = () => { const key = $("wz-ckey").value.trim(); if (!key) return; note(t("w_cloud_checking")); submit({ provider: C.provider, model: "", url: "", key }); };
        $("wz-ckey").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.stopImmediatePropagation(); e.preventDefault(); $("wz-ccheck").click(); } });
        this.onCloudError = (m) => { note(m.text || t("error"), "bad"); next.disabled = !C.connected; };   // a pasted key that did not work
        this.onSignin = (m) => {
          if (m.waiting) return note(m.note);
          if (m.ok) { C.connected = true; note(m.note, "ok"); next.disabled = false; next.focus(); return; }
          note(m.note, "bad");
          if (m.none) { const d = body.querySelector("details.paste"); if (d) d.open = true; }
        };
        if (C.connected) note(fmt("w_cloud_ok", { model: prov().name }), "ok");
        const skip = el("button", "btn ghost", esc(t("w_cloud_skip"))); skip.onclick = () => submit({}); nav.appendChild(skip);
        next.disabled = !C.connected;
        next.onclick = () => submit(C.connected ? { connected: true } : {});
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
        // what was chosen, in the words of the settings step (what the OS actually set, e.g. offline forces "this computer")
        const s = this.summary, rows = [];
        if (s) {
          const pick = (k, order) => { const i = order.indexOf(s[k]); return i < 0 ? "" : t(`q_${k}_${i}_s`); };
          rows.push([t("q_autonomy"), pick("autonomy", ["hands-off", "balanced", "hands-on"])], [t("q_internet"), pick("internet", ["yes", "ask", "no"])],
                    [t("q_brain"), pick("brain", ["local", "ask", "cloud"])],
                    [t("q_capability"), s.model ? s.model + (s.download ? ` (${t("w_quiz_download")})` : "") : ""],
                    [t("q_guidance"), pick("guidance", ["owner", "standard"])], [t("q_motion"), pick("motion", ["off", "reduced", "full"])]);
        }
        const recap = rows.filter(r => r[1]).map(([a, b]) => `<dt>${esc(a)}</dt><dd>${esc(b)}</dd>`).join("");
        body.innerHTML = `<h2>${esc(t("w_done_title"))}</h2>${recap ? `<p class="dim small">${esc(t("w_done_choices"))}</p><dl class="recap">${recap}</dl>` : ""}
          <p>${esc(t("w_done_text"))}</p><div class="opts" id="wz-try"></div>`;
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
      body.onscroll = () => this.fade(); requestAnimationFrame(() => this.fade());
      // nothing to type on this step: Enter (or Next) goes on, with the preselected answers
      if (["welcome", "language", "profile", "done"].includes(st)) setTimeout(() => { if (!document.activeElement || document.activeElement === document.body) next.focus({ preventScroll: true }); }, 40);
      const inp = body.querySelector("input[type=text], input[type=password]");
      if (inp && st !== "timezone") inp.addEventListener("keydown", (e) => { if (e.key === "Enter") next.click(); });
      if (st === "timezone") $("wz-tz").addEventListener("keydown", (e) => { if (e.key === "Enter") { const f = $("wz-tzlist").querySelector(".tzitem"); if (f) f.click(); else next.click(); } });
    },
    ok(m) {
      if (!this.active) return;
      if (m.step === "internet") this.wifiNeeded = !!m.wifi;
      if (m.step === "profile") { this.wifiNeeded = !!m.wifi; this.cloudNeeded = !!m.cloud_setup; this.summary = m; }
      if (m.step === "cloud" && m.note) toast({ text: m.note, long: true });
      if (m.step === "timezone" && m.value) { this.tz = { zone: m.value, label: m.value.replace(/_/g, " "), offset: "" }; }
      if (m.step === "wifi" && m.note !== undefined) toast({ text: t("w_wifi_ok") });
      if (m.step === "done") { this.active = false; if (this.pending) { const p = this.pending; this.pending = null; setTimeout(() => say(p), 600); } return; }
      const k = this.steps.indexOf(m.step);
      this.i = (k >= 0 ? k : this.i) + 1;
      while (this.i < this.steps.length - 1 && this.hidden(this.step())) this.i++;
      this.render();
    },
    error(m) {
      if (this.step() === "cloud" && this.onCloudError) return this.onCloudError(m);
      $("wiz-error").textContent = m.text || t("error"); const b = $("wiz-nav").querySelector(".primary"); if (b) b.disabled = false;
    },
    // a step taller than the screen scrolls; the fade at the bottom says more follows, until the end is reached
    fade() { const b = $("wiz-body"); b.classList.toggle("more", b.scrollTop + b.clientHeight < b.scrollHeight - 4); }
  };
  window.addEventListener("resize", () => { if (wizard.active) wizard.fade(); });

  // ---------------------------------------------------------------- windows
  const SIZES = { s: 380, m: 560, l: 780, xl: 980 };
  const SYSTEM_IDS = new Set(["files", "notes", "history", "screenshot", "system-panel"]);
  const isSystem = (id, spec) => (spec && spec.slot) ? spec.slot === "side" : (id.startsWith("panel-") || SYSTEM_IDS.has(id));
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
    noteLaunch(id);
    if (w && m.quiet) { w.el.querySelector(".title").textContent = spec.title || ""; renderBody(w.el.querySelector(".body"), spec); w.spec = spec; return; }   // a background refresh: same place, same layer
    if (w) { w.el.querySelector(".title").textContent = spec.title || ""; renderBody(w.el.querySelector(".body"), spec); w.min = false; w.el.classList.remove("hidden"); raise(w.el, !cur); dock(); overlaps(); if (cur) cur.opened = true; return; }
    const win = el("div", "win kind-" + (spec.kind || "panel") + " " + (spec.size || (spec.kind === "image" ? "l" : spec.kind === "media" ? "s" : "m")));
    win.dataset.id = id;
    const head = el("div", "head", `<i class="dot"></i><span class="title">${esc(spec.title || "")}</span>
      <button class="min" title="${esc(t("d_minimize"))}">–</button><button class="max" title="${esc(t("d_maximize"))}">▢</button><button class="x" title="${esc(t("d_close"))}">✕</button>`);
    const body = el("div", "body");
    const grip = el("div", "grip");
    win.append(head, body, grip);
    renderBody(body, spec);
    const stage = $("stage");
    const wpx = Math.min(SIZES[spec.size] || SIZES.m, stage.clientWidth - 24);
    let x, y;
    if (isSystem(id, spec)) {
      // the system's own windows (settings, lists, files, models…) share one slot on the right and replace
      // each other; the stage stays free for what the owner asked for. The away card and the passphrase
      // form are not slot windows: nothing evicts them and they evict nothing.
      // (they used to replace each other; now each new one opens beside the others, stepped, so Settings and Files
      // can be open together)
      const n = [...wins].filter(([oid, ow]) => oid !== id && isSystem(oid, ow.spec) && !ow.min).length % 6;
      x = Math.max(12, stage.clientWidth - wpx - 20 - n * 36); y = 20 + n * 30;
    } else {
      // conversation windows cascade from the top left and never start below the upper third
      if (24 + (cascade % 7) * 30 > stage.clientHeight * 0.34) cascade = 0;
      x = Math.max(12, Math.min(stage.clientWidth - wpx - 12, 40 + (cascade % 7) * 36));
      y = Math.max(8, 24 + (cascade % 7) * 30);
      cascade++;
    }
    win.style.left = x + "px"; win.style.top = y + "px";
    win.style.maxHeight = Math.max(160, stage.clientHeight - y - 12 - barRoom()) + "px";   // opens above the bar
    if (spec.kind === "app" || spec.kind === "chat") win.style.height = Math.min(stage.clientHeight - y - 12 - barRoom(), { s: 600, m: 640, l: 700, xl: 760 }[spec.size] || 640) + "px";
    stage.appendChild(win);
    wins.set(id, { el: win, spec, min: false, max: false });
    if (cur) cur.opened = true;
    if (busy && !motionOff()) handoff(win);
    raise(win, !cur); idle(); overlaps();
    // at most two of the system's own windows open at once: a third tucks the oldest into the dock (four stacked
    // in one corner hid each other and the answer)
    if (isSystem(id, spec)) {
      const others = [...wins].filter(([oid, ow]) => oid !== id && isSystem(oid, ow.spec) && !ow.min);
      if (others.length >= 2) minimize(others.sort((p, q) => (parseInt(p[1].el.style.zIndex) || 0) - (parseInt(q[1].el.style.zIndex) || 0))[0][0]);
    }
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
    if (![...wins.values()].some(x => !x.min)) winFront(false);
    if (tell) post({ t: "window.closed", id });
    afterAnim(w.el, "closing", () => { w.el.remove(); overlaps(); });
    dock(); idle(); overlaps();
  }
  function minimize(id) {
    const w = wins.get(id); if (!w) return; w.min = true;
    if (![...wins.values()].some(x => !x.min)) winFront(false);
    towards(w.el, $("dock"));
    afterAnim(w.el, "mini", () => { w.el.classList.add("hidden"); w.el.classList.remove("mini"); overlaps(); });
    dock(); idle();
  }
  function maximize(id) {
    const w = wins.get(id); if (!w) return;
    w.el.classList.add("geo"); setTimeout(() => w.el.classList.remove("geo"), 350);
    if (!w.max) { w.saved = { left: w.el.offsetLeft + "px", top: w.el.offsetTop + "px", width: w.el.offsetWidth + "px", height: w.el.style.height, maxHeight: w.el.style.maxHeight }; w.el.classList.add("maxed"); w.el.style.left = "12px"; w.el.style.top = "8px"; w.el.style.width = "calc(100% - 24px)"; w.el.style.height = "calc(100% - 16px)"; w.el.style.maxHeight = "none"; }
    else { Object.assign(w.el.style, w.saved || {}); w.el.classList.remove("maxed"); const el2 = w.el; setTimeout(() => onScreen(el2), 360); }   // after the animation: mid-way it is still full width
    w.max = !w.max; raise(w.el); setTimeout(overlaps, 360);
  }
  // a window put back (restore, a smaller screen) is moved so its title bar is on screen and it fits
  function onScreen(win) {
    const st = $("stage"), W = st.clientWidth, H = st.clientHeight;
    const left = parseFloat(win.style.left) || 0, top = parseFloat(win.style.top) || 0;
    if (win.offsetWidth > W - 8) win.style.width = Math.max(260, W - 16) + "px";
    win.style.left = Math.min(Math.max(0, left), Math.max(0, W - Math.min(win.offsetWidth, W))) + "px";
    win.style.top = Math.min(Math.max(0, top), Math.max(0, H - 44)) + "px";
    if (win.offsetHeight > H - (parseFloat(win.style.top) || 0)) win.style.maxHeight = Math.max(160, H - (parseFloat(win.style.top) || 0) - 12) + "px";
  }
  // front=false: a window the computer opens while answering stays under the answer card (a Sources window covered it)
  function raise(win, front = true) { win.style.zIndex = ++z; if (focused) focused.classList.remove("focus"); focused = win; win.classList.add("focus"); if (front) winFront(true); if (!busy && !cur) collapseReply(); }
  // the window in use goes in front of the input bar; the bar comes back to the front when it is wanted
  function winFront(on) { $("desk").classList.toggle("winfront", !!on && [...wins.values()].some(w => !w.min)); }
  // room kept free at the bottom of the window area so a new window opens above the input bar (moving, resizing and
  // maximizing may still use all of it)
  function barRoom() { const st = $("stage").getBoundingClientRect(), c = $("cmd").getBoundingClientRect(); return Math.max(0, st.bottom - c.top + 12); }
  function collapseReply() { const r = $("reply"); if (r.classList.contains("hidden") || r.classList.contains("collapsed")) return; clearTimeout(autoHide); r.classList.add("collapsed"); r.scrollTop = 0; }
  function expandReply() { const r = $("reply"); if (!r.classList.contains("collapsed")) return; r.classList.remove("collapsed"); r.style.animation = "none"; void r.offsetWidth; r.style.animation = ""; }
  // one pair of window-level listeners per gesture, attached on mousedown and removed on mouseup (nothing leaks)
  function gesture(start, onMove, onEnd) {
    start.addEventListener("mousedown", (e) => {
      if (e.target.tagName === "BUTTON") return;
      const st = onMove.begin(e); if (!st) return;
      e.preventDefault(); e.stopPropagation();
      const move = (ev) => onMove.move(ev, st);
      const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); onEnd(); };
      window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
    });
  }
  function drag(handle, win) {
    gesture(handle, {
      begin: (e) => { win.classList.add("dragging"); return { sx: e.clientX, sy: e.clientY, ox: win.offsetLeft, oy: win.offsetTop }; },
      // the title bar always stays on screen (a window dragged too far could not be reached again)
      move: (e, s) => { const st = $("stage"); win.style.left = Math.min(st.clientWidth - 120, Math.max(120 - win.offsetWidth, s.ox + e.clientX - s.sx)) + "px";
                        win.style.top = Math.min(st.clientHeight - 44, Math.max(0, s.oy + e.clientY - s.sy)) + "px"; }
    }, () => { win.classList.remove("dragging"); overlaps(); });
  }
  function resize(grip, win) {
    gesture(grip, {
      begin: (e) => { win.classList.add("dragging"); return { sx: e.clientX, sy: e.clientY, ow: win.offsetWidth, oh: win.offsetHeight }; },
      move: (e, s) => { win.style.width = Math.max(280, s.ow + e.clientX - s.sx) + "px"; win.style.height = Math.max(120, s.oh + e.clientY - s.sy) + "px"; win.style.maxHeight = "none"; }
    }, () => { win.classList.remove("dragging"); overlaps(); });
  }
  // the traditional layouts: a start menu (Windows style: bottom-left button; Mac style: the name at the top-left)
  const START_ITEMS = [["settings", "open the settings"], ["models", "open the models"], ["d_start_files", "show my files"], ["d_lists", "show my lists"],
                       ["memory", "show my memory"], ["tasks", "show my tasks"], ["d_history", null], ["d_lock_tip", "lock"], ["d_shutdown_item", "shut down"]];
  function startMenu(show) {
    const sm = $("startmenu"); if (!sm) return;
    if (show === undefined) show = sm.classList.contains("hidden");
    sm.classList.toggle("hidden", !show); if (!show) return;
    sm.innerHTML = "";
    for (const [k, s] of START_ITEMS) { const b = el("button", "item", esc(t(k))); b.onclick = () => { startMenu(false); if (s) act(s); else $("reply-hist").click(); }; sm.append(b); }
  }
  $("start").onclick = () => startMenu();
  { const brand = document.querySelector("#top .brand"); brand.setAttribute("role", "button"); brand.tabIndex = 0;
    brand.onclick = () => { if (document.documentElement.dataset.layout === "mac") startMenu(); };
    brand.onkeydown = (e) => { if ((e.key === "Enter" || e.key === " ") && document.documentElement.dataset.layout === "mac") { e.preventDefault(); startMenu(); } }; }
  document.addEventListener("click", (e) => { if (!e.target.closest("#startmenu, #start, #top .brand")) startMenu(false); });
  function dock() {
    const d = $("dock"); d.innerHTML = "";
    const layout = document.documentElement.dataset.layout || "clean";
    if (layout === "windows") for (const [wid, w] of wins) { if (w.min) continue; const c = el("button", "chip open", esc(w.spec.title || "…")); c.type = "button"; c.setAttribute("aria-label", (w.spec.title || t("d_window"))); c.onclick = () => (focused === w.el ? minimize(wid) : raise(w.el)); d.appendChild(c); }
    if (layout === "mac") for (const [k, s] of [["settings", "open the settings"], ["d_start_files", "show my files"], ["d_lists", "show my lists"]]) { const c = el("button", "chip launch", esc(t(k))); c.type = "button"; c.onclick = () => launch(s); d.appendChild(c); }
    for (const [id, w] of wins) {
      if (!w.min) continue;
      const c = el("button", "chip", esc(w.spec.title || "…")); c.type = "button"; c.setAttribute("aria-label", (w.spec.title || t("d_window")));
      c.onclick = () => { w.min = false; w.el.classList.remove("hidden"); w.el.style.animation = "none"; void w.el.offsetWidth; w.el.style.animation = ""; raise(w.el); dock(); idle(); overlaps(); };
      d.appendChild(c);
    }
    for (const a of apps) {
      const c = el("button", "chip", `${esc(a.name)} <span class="x" title="${esc(t("d_close_app"))}" aria-hidden="true">✕</span>`); c.type = "button"; c.setAttribute("aria-label", a.name);
      c.querySelector(".x").onclick = (e) => { e.stopPropagation(); post({ t: "app.close", pid: a.pid }); };
      c.onclick = () => post({ t: "app.focus", pid: a.pid });
      d.appendChild(c);
    }
  }
  let apps = [];

  // ---------------------------------------------------------------- blocks
  function renderBody(body, spec) {
    if (spec.kind === "chat") {
      if (body.querySelector(".chatlog")) return;            // already open: keep what is in it
      body.innerHTML = "";
      const log = el("div", "chatlog");
      for (const m of spec.transcript || []) log.append(el("div", "msg " + (m.role === "user" ? "me" : "ai"), m.role === "user" ? esc(m.content) : md(m.content)));
      if (!(spec.transcript || []).length) log.append(el("div", "hint2", esc(t("d_chat_ph"))));
      const f = el("form", "chatin"), i = el("input"); i.type = "text"; i.placeholder = t("d_chat_ph"); i.autocomplete = "off";
      const b = el("button", "btn primary", "➤"); b.type = "submit"; f.append(i, b);
      f.onsubmit = (ev) => { ev.preventDefault(); const v = i.value.trim(); if (!v) return; const h = log.querySelector(".hint2"); if (h) h.remove();
        log.append(el("div", "msg me", esc(v))); i.value = ""; log.scrollTop = 1e6; post({ t: "chat.say", chat: spec.chat, text: v }); };
      body.append(log, f); setTimeout(() => { log.scrollTop = 1e6; i.focus(); }, 200);
      return;
    }
    if (spec.kind === "app") {
      // the owner's app: its own page in a sandbox (scripts yes; no network, no access to this page or to files)
      let f = body.querySelector("iframe.app");
      if (f && f.dataset.src === spec.src) { f.llmosState = spec.state; return; }
      body.innerHTML = "";
      f = el("iframe", "app"); f.dataset.src = spec.src; f.dataset.app = spec.app; f.llmosState = spec.state;
      f.setAttribute("sandbox", "allow-scripts allow-modals allow-forms"); f.setAttribute("referrerpolicy", "no-referrer");
      f.src = spec.src; f.title = spec.title || "app";
      body.appendChild(f);
      setTimeout(() => { try { f.focus(); } catch (e) {} }, 300);
      return;
    }
    body.innerHTML = "";
    for (const b of spec.blocks || []) { const e = renderBlock(b); if (e) body.appendChild(e); }
    if (spec.actions && spec.actions.length) body.appendChild(renderBlock({ type: "buttons", items: spec.actions }));
  }
  let fullTrust = false;   // the owner chose full trust: a delete button deletes, no "Sure?" first
  // a row whose delete/cancel was pressed greys out at once and can't be pressed again while the window refreshes
  function fade(b) { const row = b.closest(".item"); if (row) { const was = b.innerHTML; row.classList.add("gone"); b.innerHTML = "…"; setTimeout(() => { row.classList.remove("gone"); b.innerHTML = was; }, 8000); } }   // back if nothing changed
  function actionBtn(a) {
    const b = el("button", "btn small" + (a.primary ? " primary" : "") + (a.danger ? " danger" : ""), esc(a.label));
    if (!a.danger || fullTrust) {
      b.onclick = () => { act(a.say); if (a.danger) fade(b); if (a.closes) { const w = b.closest(".win"); if (w && w.dataset.id) closeWindow(w.dataset.id, true); } };
      return b;
    }
    // a button that deletes or ends something asks once more, right where it is: first press "Sure?", second does it
    let armed = null;
    b.onclick = () => {
      if (armed) { clearTimeout(armed); armed = null; b.innerHTML = esc(a.label); act(a.say); fade(b); return; }
      b.innerHTML = esc(t("d_sure") === "d_sure" ? "Sure? Press again" : t("d_sure"));
      armed = setTimeout(() => { armed = null; b.innerHTML = esc(a.label); }, 4000);
    };
    return b;
  }
  function renderBlock(b) {
    switch (b.type) {
      case "text": return el("div", "b-text" + (b.dim ? " dim" : ""), md(b.text));
      case "heading": return el("div", "b-heading", esc(b.text));
      case "divider": return el("div", "b-divider");
      case "slider": {
        const e = el("label", "slider-row"), r = el("input"); r.type = "range"; r.min = b.min; r.max = b.max; r.value = b.value;
        const v = el("span", "slider-val", esc(String(b.value)));
        if (b.label) e.append(el("span", "k", esc(b.label)));
        r.oninput = () => { v.textContent = r.value; };
        r.onchange = () => act(b.say.replace("{v}", r.value));
        e.append(r, v); return e;
      }
      case "kv": { const e = el("div", "kv"); for (const [k, v] of b.rows) { e.append(el("span", "k", esc(k)), el("span", "v", esc(v))); } return e; }
      case "stat": {
        const e = el("div"); e.append(el("div", "stat", `<span>${esc(b.label)}</span><span class="v">${esc(b.value)}</span>`));
        if (b.fraction != null) e.append(el("div", "bar", `<i style="width:${Math.round(b.fraction * 100)}%"></i>`));
        return e;
      }
      case "progress": { const e = el("div"); e.append(el("div", "stat", `<span>${esc(b.label)}</span><span class="v">${Math.round(b.fraction * 100)}%</span>`), el("div", "bar", `<i style="width:${Math.round(b.fraction * 100)}%"></i>`)); return e; }
      case "list": {
        const e = el("div", "list" + (b.columns > 1 ? " cols-" + b.columns : "") + (b.view === "icons" ? " icons" : ""));
        b.items.forEach((it, i) => {
          const row = el("div", "item" + (it.done ? " done" : ""));
          row.style.setProperty("--i", Math.min(i, 12));
          if (b.numbered) row.append(el("span", "n", (i + 1) + "."));
          const main = el("div", "main", `<div class="t">${esc(it.title)}${it.meta ? `<span class="meta">${esc(it.meta)}</span>` : ""}</div>${it.subtitle ? `<div class="st">${esc(it.subtitle)}</div>` : ""}`);
          if (it.detail) main.append(el("div", "det", md(it.detail)));
          row.append(main);
          if (it.actions && it.actions.length) { const acts = el("div", "acts"); it.actions.forEach(a => acts.append(actionBtn(a))); row.append(acts); }
          // a file or folder opens from its name too (a click on the name, a double-click on the row), as in any file window
          // (a list item's name ticks it off or back on, like its Done button)
          const open1 = (it.actions || []).find(a => !a.danger && /^(show my files in|open the file|tick off item|untick item) /.test(a.say));
          if (open1) { const tt = main.querySelector(".t"); tt.classList.add("opens"); tt.onclick = () => act(open1.say); row.ondblclick = (ev) => { if (!ev.target.closest("button, .t")) act(open1.say); }; }
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
      case "gallery": {
        const e = el("div", "b-gallery");
        for (const it of b.items) {
          const c = el("button", "ph", `<img loading="lazy" src="${esc(it.src.startsWith("/") ? "file://" + it.src : it.src)}" alt="${esc(it.title)}"><span>${esc(it.title)}</span>`);
          c.type = "button"; c.title = it.title; if (it.say) c.onclick = () => act(it.say);
          e.append(c);
        }
        return e;
      }
      case "buttons": { const e = el("div", "b-buttons"); b.items.forEach(a => e.append(actionBtn(a))); return e; }
      case "choices": {
        const e = el("div", "choices");
        b.items.forEach(a => {
          const c = el("button", "choice" + (b.selected && (a.label === b.selected) ? " sel" : ""), `<i class="r"></i><span><div>${esc(a.label)}</div>${a.description ? `<div class="d">${esc(a.description)}</div>` : ""}</span>`);
          c.onclick = () => { e.querySelectorAll(".choice").forEach(x => x.classList.remove("sel")); c.classList.add("sel"); act(a.say); };
          e.append(c);
        });
        return e;
      }
      case "toggle": {
        const e = el("div", "toggle", `<span>${esc(b.label)}${b.hint ? `<div class="d">${esc(b.hint)}</div>` : ""}</span>`);
        const sw = el("button", "sw" + (b.on ? " on" : "")); let on = !!b.on;
        sw.type = "button"; sw.setAttribute("role", "switch"); sw.setAttribute("aria-checked", String(on));
        if (b.label) sw.setAttribute("aria-label", b.label);
        sw.onclick = () => { on = !on; sw.classList.toggle("on", on); sw.setAttribute("aria-checked", String(on)); act(on ? b.say_on : b.say_off); };
        e.append(sw); return e;
      }
      case "form": {
        const e = el("form", "form"); const inputs = {};
        for (const f of b.fields) {
          const lab = el("label", "", esc(f.label));
          let inp;
          if (f.name === "t") continue;                                    // reserved: the message type
          if (f.kind === "hidden") { inp = el("input"); inp.type = "hidden"; inp.value = f.value || ""; inputs[f.name] = inp; e.append(inp); continue; }
          if (f.kind === "textarea") { inp = el("textarea", "mono"); inp.value = f.value || ""; inp.placeholder = f.placeholder || ""; inp.rows = 13; inp.spellcheck = false; }
          else if (f.options && f.options.length) { inp = el("select", "", f.options.map(o => `<option${o === f.value ? " selected" : ""}>${esc(o)}</option>`).join("")); }
          else { inp = el("input"); inp.type = f.kind === "password" ? "password" : f.kind === "email" ? "email" : "text"; inp.value = f.value || ""; inp.placeholder = f.placeholder || ""; inp.autocomplete = "off"; }
          inputs[f.name] = inp; lab.append(inp); e.append(lab);
        }
        const btn = el("button", "btn primary", esc(b.submit.label)); btn.type = "submit";
        const row = el("div", "row"); row.append(btn); e.append(row);
        e.onsubmit = (ev) => {
          ev.preventDefault();
          if (b.submit.post) { const m = {}; for (const [k, inp] of Object.entries(inputs)) { if (k !== "t") m[k] = inp.value; if (inp.type !== "hidden") inp.value = ""; } m.t = b.submit.post; post(m); return; }
          let s = b.submit.say || ""; for (const [k, inp] of Object.entries(inputs)) s = s.split("{" + k + "}").join(inp.value); say(s);
        };
        return e;
      }
      case "quote": return el("div", "quote", `“${esc(b.text)}”${b.author ? `<div class="who">— ${esc(b.author)}</div>` : ""}${b.source ? `<div class="src"><a href="#" data-url="${esc(b.source)}">${esc(b.source)}</a></div>` : ""}`);
      case "code": return el("pre", "", esc(b.text));
      case "media": {
        const loading = b.state === "loading";      // found, the player still starting (a video can take ~10 s)
        const e = el("div", "media", `${b.thumbnail ? `<img src="${esc(b.thumbnail)}" alt="">` : ""}<div><div class="t">${esc(b.title)}</div><div class="st">${esc(loading ? t("d_starting") : b.subtitle)}</div><div class="ctl"></div></div>`);
        const ctl = e.querySelector(".ctl");
        const pb = el("button", "btn small", esc(b.state === "paused" ? t("d_resume") : t("d_pause")));
        pb.onclick = () => post({ t: "media", action: b.state === "paused" ? "resume" : "pause" });
        const sb = el("button", "btn small ghost", esc(t("d_stop"))); sb.onclick = () => post({ t: "media", action: "stop" });
        // the computer's own volume, the same number as the Sound panel (status updates keep it in step)
        const vol = el("input", "npvol"); vol.type = "range"; vol.min = 0; vol.max = 100; vol.value = b.volume ?? 100; vol.title = t("d_volume");
        vol.onchange = () => post({ t: "media", action: "volume", value: +vol.value });
        ctl.append(pb, sb);
        if (b.video) { const fb = el("button", "btn small ghost", esc(t("d_fullscreen"))); fb.onclick = () => post({ t: "media", action: "fullscreen" }); ctl.append(fb); }
        ctl.append(vol); return e;
      }
      case "sources": { const e = el("div", "sources"); b.items.forEach(s => { const a = el("a", "", esc(s.title)); a.href = "#"; a.dataset.url = s.url; e.append(a); }); return e; }
    }
    return null;
  }

  // ---------------------------------------------------------------- reply card
  const THINK = '<span class="think"><i></i><i></i><i></i></span>';
  function replyStart(m) {
    $("hint").textContent = "";
    winFront(false);                                  // the computer is answering: its card comes to the front
    replyBrain({ online: false });
    cur = { req: m.request, text: "", activity: [], t0: Date.now(), eta: null };
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
    if (m.reset) cur.text = "";        // a later round writes the answer anew
    if (!cur.text) { orb("thinking", t("d_writing")); $("reply").classList.add("writing"); $("reply-progress").classList.add("hidden"); prog = null; }
    cur.text += m.text;
    // one repaint per frame, however fast tokens arrive
    if (!paintQueued) { paintQueued = true; requestAnimationFrame(paintReply); }
  }
  // a one-line answer ("Done — animations off.") steps aside by itself so the windows stay in view;
  // anything longer waits for the owner (Esc / Close), and the pointer over the card keeps it
  function replyEnd(m) {
    if (!cur) return; cur.text = m.text || cur.text;
    // nothing to say (a window opened and is the answer): no empty "LLM OS" card left above the bar
    if (!String(cur.text || "").trim()) { cur = null; histPos = -1; $("reply-progress").classList.add("hidden"); $("reply").classList.remove("writing"); orb("idle", ""); hideReply(); return; } $("reply-text").innerHTML = md(cur.text); paintQueued = false;
    // questions, failures and "no" answers stay until the owner moves on: they need reading, maybe an answer
    const needs = /\?\s*$|\b(?:not|no|can'?t|cannot|couldn'?t|didn'?t|failed|isn'?t|error|unable)\b/i.test(cur.text);
    const short = cur.text.length < 90 && !cur.text.includes("\n") && !needs, opened = !!cur.opened;
    conv.push(cur); cur = null; histPos = -1; $("reply-progress").classList.add("hidden"); $("reply").classList.remove("writing"); orb("idle", "");
    clearTimeout(autoHide);
    // the window IS the answer: a short reply that opened one folds at once; a short answer alone steps aside after a while
    if (opened && short) setTimeout(() => { if (!busy && !cur) collapseReply(); }, motionOff() ? 0 : 900);
    else if (short && !motionOff()) autoHide = setTimeout(() => { if (!$("reply").matches(":hover") && !busy) hideReply(); }, Math.max(12000, 250 * $("reply-text").textContent.length));
  }
  function replyError(m) {
    // Stop: what was already written stays, with a clear end line (the text used to just stop, or be replaced)
    if (m.stopped && cur && cur.text) { replyEnd({ text: cur.text.replace(/\s+$/, "") + "\n\n*— " + (m.text || "Stopped.") + "*" }); return; }
    if (!cur) replyStart({ request: "" }); $("reply-text").className = "text err"; $("reply-text").textContent = m.text; cur.text = m.text; conv.push(cur); cur = null; histPos = -1; orb("attention", ""); setTimeout(presence, 1500); }
  function activity(m) {
    if (!cur) return;
    const box = $("reply-activity"), last = box.lastElementChild;
    if (m.replace && last) { last.textContent = m.text; cur.activity[cur.activity.length - 1] = m.text; }
    else { cur.activity.push(m.text); box.append(el("div", "", esc(m.text))); }
    $("reply").scrollTop = 1e6; orb("thinking", t("d_working"));
  }
  // the requests waiting behind the one in progress: in order, each with ✕ to take it out of the queue
  function queueStrip(m) {
    const q = $("reply-queue"), items = m.items || [];
    q.innerHTML = ""; q.classList.toggle("hidden", !items.length);
    if (!items.length) return;
    q.append(el("div", "", esc(t("d_queue_next"))));
    items.forEach((it, i) => {
      const row = el("div", "q", `<span class="n">${i + 1}.</span><span class="t">${esc(it.text)}</span>`);
      const x = el("button", "", "✕"); x.type = "button"; x.title = t("d_queue_remove"); x.setAttribute("aria-label", t("d_queue_remove") + ": " + it.text);
      x.onclick = (e) => { e.stopPropagation(); post({ t: "queue.drop", id: it.id }); };
      row.append(x); q.append(row);
    });
    const r = $("reply"); if (r.classList.contains("hidden")) r.classList.remove("hidden");
  }
  function hideReply() { const r = $("reply"); if (r.classList.contains("hidden")) return; afterAnim(r, "closing", () => { r.classList.add("hidden"); r.classList.remove("closing"); idle(); }); }
  // a progress bar with the time left, from the average rate since this phase began
  let prog = null;
  function progress(m) {
    const p = $("reply-progress"); p.classList.remove("hidden");
    const pct = m.total ? Math.round(m.done * 100 / m.total) : 0; p.querySelector("i").style.width = pct + "%";
    const now = Date.now(); let left = "";
    if (!prog || prog.label !== m.label || m.done < prog.d0) prog = { label: m.label, t0: now, d0: m.done };
    else if (now - prog.t0 >= 3000 && m.done > prog.d0 && m.total > m.done) { const rate = (m.done - prog.d0) / ((now - prog.t0) / 1000); if (rate > 0) left = " · " + fmt("d_left", { s: hms((m.total - m.done) / rate) }); }
    p.querySelector("span").textContent = `${m.label} ${pct}%${left}`;
    if (m.done >= m.total) { prog = null; setTimeout(() => p.classList.add("hidden"), 1500); }
  }
  $("reply-close").onclick = hideReply;
  $("reply").addEventListener("click", (e) => { if ($("reply").classList.contains("collapsed")) { e.preventDefault(); expandReply(); } });
  $("reply-stop").onclick = () => post({ t: "cancel" });
  $("reply-hist").onclick = () => act("conversations");

  // ---------------------------------------------------------------- side chats: their replies go to their own window
  function sideEvent(m) {
    const w = wins.get("chat-" + m.chat); if (!w) return;
    const log = w.el.querySelector(".chatlog"); if (!log) return;
    let b = log.querySelector(".msg.ai.pending");
    if (m.t === "reply.start") { if (!b) { b = el("div", "msg ai pending", THINK); log.append(b); } }
    else if (m.t === "reply.delta") { if (!b) { b = el("div", "msg ai pending"); log.append(b); } b.dataset.raw = (m.reset ? "" : (b.dataset.raw || "")) + m.text; b.innerHTML = md(b.dataset.raw); }
    else if (m.t === "activity") { if (b && !b.dataset.raw) { let a = b.querySelector(".act"); if (!a) { b.innerHTML = THINK; a = el("div", "act"); b.append(a); } a.textContent = m.text; } }
    else { if (!b) { b = el("div", "msg ai"); log.append(b); } b.classList.remove("pending"); if (m.t === "reply.error") b.classList.add("err"); b.innerHTML = md(m.text || b.dataset.raw || ""); delete b.dataset.raw; }
    log.scrollTop = 1e6;
  }

  // ---------------------------------------------------------------- toasts, dialogs
  function toast(m) {
    if (m.sticky) { const old = sticky.get(m.sticky); if (old) { old.remove(); sticky.delete(m.sticky); } if (!m.text) return; }
    const e = el("div", "toast", esc(m.text));
    $("toasts").append(e);
    if (m.sticky) sticky.set(m.sticky, e); else setTimeout(() => afterAnim(e, "out", () => e.remove()), Math.max(m.long ? 10000 : 6000, 90 * String(m.text).length));
  }
  function dialogDone(ov) { ov.classList.add("hidden"); dialogOpen = false; presence(); }
  function dialog(m) {
    const ov = $("overlay"); ov.innerHTML = ""; ov.classList.remove("hidden"); dialogOpen = true; presence();
    const d = el("div", "dlg" + (m.danger ? " danger" : ""), `<h3><i class="orb small attention"></i>${esc(m.title)}</h3><div class="body${m.mono ? " mono" : ""}">${esc(m.text)}</div>`);
    const row = el("div", "row");
    const shown = Date.now();
    for (const b of m.buttons) {
      const btn = el("button", "btn" + (b.primary ? " primary" : ""), esc(b.label));
      btn.dataset.value = b.value;
      btn.onclick = (e) => { if (e.detail === 0 && Date.now() - shown < 600) return; dialogDone(ov); post({ t: "dialog", id: m.id, value: b.value }); };
      row.append(btn);
    }
    d.append(row); ov.append(d);
    ov.dataset.id = m.id;
    d.tabIndex = -1;
    setTimeout(() => { const first = m.danger ? d.querySelector('[data-value="no"]') : d.querySelector(".btn.primary"); (first || d).focus(); }, 30);
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
  $("mic").onclick = () => post({ t: listening ? "voice.stop" : "voice" });     // a second press stops listening
  // the OS auto-locks after idle time: tell it the owner is here (at most once every 20 s)
  let lastPing = 0;
  const ping = () => { const now = Date.now(); if (now - lastPing > 20000) { lastPing = now; post({ t: "active" }); } };
  for (const ev of ["keydown", "mousedown", "mousemove", "wheel", "touchstart"]) document.addEventListener(ev, ping, { passive: true });
  // arrow keys move through a radio group (.seg) with wrap-around; the focused option is selected
  function nextIndex(i, n, key) {
    if (n < 1 || i < 0) return -1;
    const step = key === "ArrowLeft" || key === "ArrowUp" ? -1 : key === "ArrowRight" || key === "ArrowDown" ? 1 : 0;
    if (!step) return -1;
    return ((i + step) % n + n) % n;
  }
  document.addEventListener("keydown", (e) => {
    const r = e.target;
    if (r && r.getAttribute && r.getAttribute("role") === "radio" && r.parentElement && r.parentElement.getAttribute("role") === "radiogroup") {
      const opts = [...r.parentElement.querySelectorAll('[role="radio"]:not(:disabled)')];
      const j = nextIndex(opts.indexOf(r), opts.length, e.key);
      if (j >= 0) { e.preventDefault(); opts[j].focus(); opts[j].click(); return; }
    }
  });
  document.addEventListener("keydown", (e) => {
    const ov = $("overlay");
    if (!ov.classList.contains("hidden")) {
      if (e.key === "Escape") { dialogDone(ov); post({ t: "dialog", id: ov.dataset.id, value: "no" }); }
      // Enter confirms a plain question (never a danger one, and never while typing or on a focused button, which clicks itself)
      else if (e.key === "Enter") {
        const ae = document.activeElement, tag = ae && ae.tagName;
        const yes = ov.querySelector(".dlg:not(.danger) .btn.primary");
        if (yes && tag !== "TEXTAREA" && tag !== "INPUT" && tag !== "BUTTON") { e.preventDefault(); yes.click(); }
      }
      return;
    }
    if (wizard.active || $("desk").classList.contains("hidden")) return;
    if (e.key === "Escape") {
      if (listening) { post({ t: "voice.stop" }); return; }      // Esc stops listening; it closes nothing
      if (document.activeElement === inp && inp.value) { inp.value = ""; return; }
      if (focused && wins.has(focused.dataset.id)) { closeWindow(focused.dataset.id, true); focused = null; return; }
      hideReply();
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "l") { e.preventDefault(); inp.focus(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "w" && focused && wins.has(focused.dataset.id)) { e.preventDefault(); closeWindow(focused.dataset.id, true); focused = null; }
    if (e.key === "F1") { e.preventDefault(); post({ t: "voice" }); }
    if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key.length === 1 && !(e.key === " " && document.activeElement.tagName === "BUTTON") && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA" && document.activeElement.tagName !== "SELECT") inp.focus();
  });

  // the orb in the bar brings back the current task's card (or the last answer) after it was hidden or folded
  function showReply() {
    const r = $("reply");
    if (!cur && !conv.length && r.classList.contains("hidden")) { inp.focus(); return; }
    clearTimeout(autoHide);
    r.classList.remove("hidden", "closing"); expandReply(); winFront(false);
    if (cur) $("reply").scrollTop = 1e6;
  }
  { const o = $("orb"); o.setAttribute("role", "button"); o.tabIndex = 0; o.style.cursor = "pointer";
    o.setAttribute("aria-label", t("d_show_task", "Show what I'm working on"));
    o.addEventListener("click", showReply);
    o.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showReply(); } }); }
  // a bigger text size (zoom) or a smaller screen: every window is moved back so it fits (A+ pushed Settings off the edge)
  let refit = null;
  window.addEventListener("resize", () => { clearTimeout(refit); refit = setTimeout(() => { for (const [, w] of wins) if (!w.min) onScreen(w.el); overlaps(); }, 150); });
  inp.addEventListener("focus", () => winFront(false));
  $("cmd").addEventListener("mousedown", () => winFront(false));
  $("stage").parentElement.addEventListener("mousedown", (e) => { if (!e.target.closest(".win, #cmd, #reply, #top, #dock, #start, #startmenu, #overlay")) winFront(false); });

  // ---------------------------------------------------------------- dispatch
  window.llmos = {
    receive(m) {
      switch (m.t) {
        case "theme": return applyTheme(m);
        case "status": return status(m);
        case "screen": return screen(m);
        case "window": return openWindow(m);
        case "window.close": return closeWindow(m.id, false);
        case "reply.start": return m.chat && m.chat !== "main" ? sideEvent(m) : replyStart(m);
        case "reply.delta": return m.chat && m.chat !== "main" ? sideEvent(m) : replyDelta(m);
        case "reply.end": return m.chat && m.chat !== "main" ? sideEvent(m) : replyEnd(m);
        case "reply.error": return m.chat && m.chat !== "main" ? sideEvent(m) : replyError(m);
        case "reply.brain": return replyBrain(m);
        case "reply.eta": if (cur) cur.eta = m.seconds; return;
        case "queue": return queueStrip(m);
        case "activity": return m.chat && m.chat !== "main" ? sideEvent(m) : activity(m);
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
        case "signin.result": if (wizard.active && wizard.onSignin) wizard.onSignin(m); return;
        case "wifi.list": wizard.nets = m.items || []; if (wizard.active && wizard.onWifi) wizard.onWifi(wizard.nets); return;
        case "unlock.error": { $("lock-go").disabled = false; $("lock-busy").classList.add("hidden"); $("lock-error").textContent = m.text; $("lock-pass").value = ""; $("lock-pass").focus();
          const c = $("lock-card"); c.classList.remove("shake"); void c.offsetWidth; c.classList.add("shake"); return; }
        case "speaking": speaking = !!m.on; presence(); return;
        case "unlock.busy": $("lock-busy").classList.remove("hidden"); return;
        case "clear": for (const id of [...wins.keys()]) closeWindow(id, false); conv.length = 0; $("reply").classList.add("hidden"); idle(); return;
        case "eval": try { (0, eval)(m.js); } catch (e) { console.log(e); } return;
      }
    }
  };
  clock();
  try { LLMBG.start($("backdrop")); } catch (e) { console.log(e); }
  post({ t: "ready" });
})();
