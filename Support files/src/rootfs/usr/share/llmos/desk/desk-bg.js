/* LLM OS desk — the living background.
   Soft light in the theme's colours drifting behind the windows. It is the computer's mood made visible: calm
   when idle, a slow swirl that gathers and brightens while the model thinks, a pulse while it speaks, ripples
   while it listens, a cooler tint when the online model answers. It leans towards the pointer and ripples where
   the owner clicks. Drawn small (a few hundred pixels across) and scaled up, at ~30 frames a second with a
   graphics card and far fewer on software rendering; nothing at all while the screen is hidden or motion is off. */
(function () {
  "use strict";
  const MOOD_ENERGY = { idle: 0.12, off: 0.02, thinking: 1, writing: 0.7, speaking: 0.55, listening: 0.45, attention: 0.35, error: 0.6 };
  const S = { cv: null, cx: null, w: 0, h: 0, dark: true, style: "living", motion: "full", soft: false, online: false,
              mood: "idle", energy: 0.12, t: Math.random() * 1000, last: 0, px: 0.5, py: 0.5, tx: 0.5, ty: 0.5,
              pal: [], bg: [11, 13, 20], ripples: [], pulse: 0, running: false, timer: 0, motes: [] };

  // ---- colours
  function rgbOf(str) {
    str = String(str || "").trim();
    let m = str.match(/^#([0-9a-f]{6})$/i);
    if (m) return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
    m = str.match(/^#([0-9a-f]{3})$/i);
    if (m) return [0, 1, 2].map(i => parseInt(m[1][i] + m[1][i], 16));
    m = str.match(/rgba?\(([^)]+)\)/);
    if (m) return m[1].split(/[ ,]+/).slice(0, 3).map(Number);
    return null;
  }
  function hsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
    if (mx === mn) return [0, 0, l];
    const d = mx - mn, s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    let h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [h / 6, s, l];
  }
  function rgb(h, s, l) {
    const f = (p, q, t) => { t = (t + 1) % 1; return t < 1 / 6 ? p + (q - p) * 6 * t : t < 0.5 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p; };
    if (!s) return [l * 255, l * 255, l * 255];
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    return [f(p, q, h + 1 / 3) * 255, f(p, q, h) * 255, f(p, q, h - 1 / 3) * 255];
  }
  function palette() {
    const cs = getComputedStyle(document.documentElement);
    const acc = rgbOf(cs.getPropertyValue("--accent")) || [124, 92, 255];
    S.bg = rgbOf(cs.getPropertyValue("--bg")) || [11, 13, 20];
    const [h, s] = hsl(...acc), sat = Math.max(0.45, s);
    const L = S.dark ? [0.55, 0.5, 0.42, 0.35] : [0.72, 0.78, 0.7, 0.82];
    // the accent and its neighbours (never a far hue: orange must not turn into green), one muted cool counterpoint
    S.pal = [rgb(h, sat, L[0]), rgb((h + 0.05) % 1, sat * 0.85, L[1]), rgb((h + 0.95) % 1, sat, L[2]), rgb((h + 0.6) % 1, sat * 0.25, L[3])];
    S.cool = rgb(0.53, 0.8, S.dark ? 0.55 : 0.75);
  }

  // ---- the shapes: five lights on slow, never-repeating paths
  const ORBS = Array.from({ length: 5 }, (_, i) => ({ c: i % 4, r: 0.32 + (i % 3) * 0.09, ax: 0.18 + 0.07 * i, ay: 0.14 + 0.05 * ((i + 2) % 4),
    fx: 0.11 + 0.037 * i, fy: 0.083 + 0.029 * ((i + 3) % 5), p: i * 1.7 }));

  function size() {
    if (!S.cv) return;
    const div = S.soft ? 9 : 5;
    const w = Math.max(64, Math.round(innerWidth / div)), h = Math.max(40, Math.round(innerHeight / div));
    if (w !== S.w || h !== S.h) { S.w = S.cv.width = w; S.h = S.cv.height = h; }
  }

  function frame(dt) {
    const cx = S.cx, w = S.w, h = S.h, m = Math.min(w, h);
    const target = MOOD_ENERGY[S.mood] == null ? 0.12 : MOOD_ENERGY[S.mood];
    S.energy += (target - S.energy) * Math.min(1, dt * 1.5);
    S.t += dt * (0.08 + S.energy * 0.55);
    S.px += (S.tx - S.px) * Math.min(1, dt * 1.2); S.py += (S.ty - S.py) * Math.min(1, dt * 1.2);
    if (S.mood === "speaking") S.pulse = 0.5 + 0.5 * Math.sin(S.t * 9); else S.pulse *= 0.9;

    const [br, bgc, bb] = S.bg;
    cx.globalCompositeOperation = "source-over";
    cx.fillStyle = `rgb(${br},${bgc},${bb})`;
    cx.fillRect(0, 0, w, h);
    cx.globalCompositeOperation = S.dark ? "lighter" : "source-over";

    const gather = S.energy > 0.5 ? (S.energy - 0.5) * 0.9 : 0;          // thinking: the lights draw together and turn
    for (const o of ORBS) {
      let x = 0.5 + o.ax * Math.sin(S.t * o.fx * 6 + o.p) + (S.px - 0.5) * 0.12;
      let y = 0.45 + o.ay * Math.cos(S.t * o.fy * 6 + o.p * 1.3) + (S.py - 0.5) * 0.1;
      if (gather) {
        const a = S.t * 2.2 + o.p, rr = 0.14 + 0.05 * o.c;
        x += (0.5 + Math.cos(a) * rr - x) * gather; y += (0.5 + Math.sin(a) * rr * 0.8 - y) * gather;
      }
      const col = S.online && o.c === 0 ? S.cool : S.pal[o.c];
      const rad = m * o.r * (1 + 0.25 * S.energy + 0.12 * S.pulse) * (S.dark ? 1.15 : 1.25);
      const alpha = (S.dark ? 0.3 : 0.32) + 0.2 * S.energy;
      const g = cx.createRadialGradient(x * w, y * h, 0, x * w, y * h, rad);
      g.addColorStop(0, `rgba(${col[0] | 0},${col[1] | 0},${col[2] | 0},${alpha})`);
      g.addColorStop(1, `rgba(${col[0] | 0},${col[1] | 0},${col[2] | 0},0)`);
      cx.fillStyle = g; cx.fillRect(0, 0, w, h);
    }
    // thinking: motes circling the centre, faster and brighter as the energy rises
    if (S.energy > 0.3) {
      if (!S.motes.length) S.motes = Array.from({ length: 36 }, () => ({ a: Math.random() * 6.28, r: 0.12 + Math.random() * 0.3, s: 0.5 + Math.random() }));
      const c = S.pal[1];
      cx.fillStyle = `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${Math.min(0.8, (S.energy - 0.3) * 1.2)})`;
      for (const p of S.motes) {
        p.a += dt * p.s * (0.6 + S.energy * 1.8);
        const x = w * 0.5 + Math.cos(p.a) * p.r * m * 1.3, y = h * 0.5 + Math.sin(p.a) * p.r * m * 0.9;
        cx.beginPath(); cx.arc(x, y, S.soft ? 0.6 : 0.7, 0, 6.283); cx.fill();
      }
    }
    // listening: rings rising from the bottom; a click: one ring where it landed
    if (S.mood === "listening" && Math.random() < dt * 1.6) S.ripples.push({ x: 0.5, y: 0.95, r: 0, a: 0.5 });
    cx.globalCompositeOperation = "source-over";
    for (const r of S.ripples) {
      r.r += dt * 0.35; r.a -= dt * 0.35;
      if (r.a <= 0) continue;
      const c = S.pal[0];
      cx.strokeStyle = `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${r.a})`; cx.lineWidth = S.soft ? 1 : 1.5;
      cx.beginPath(); cx.arc(r.x * w, r.y * h, r.r * m, 0, 6.283); cx.stroke();
    }
    S.ripples = S.ripples.filter(r => r.a > 0);
    // a soft vignette keeps windows and text readable at the edges
    const v = cx.createRadialGradient(w / 2, h / 2, m * 0.35, w / 2, h / 2, Math.max(w, h) * 0.75);
    v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, S.dark ? "rgba(0,0,0,0.45)" : "rgba(255,255,255,0.35)");
    cx.fillStyle = v; cx.fillRect(0, 0, w, h);
  }

  function fps() {
    const busy = S.energy > 0.3 || S.ripples.length;
    if (S.motion === "reduced") return busy ? 12 : 6;
    if (S.soft) return busy ? 12 : 6;
    return busy ? 30 : 20;
  }
  function loop() {
    S.timer = 0;
    if (!S.cv || S.style !== "living" || S.motion === "off" || document.hidden || S.cv.offsetParent === null) { S.running = false; return; }
    S.running = true;
    const now = performance.now(), dt = Math.min(0.2, (now - (S.last || now)) / 1000); S.last = now;
    frame(dt);
    S.timer = setTimeout(() => requestAnimationFrame(loop), 1000 / fps());
  }
  function kick() { if (!S.running && !S.timer) { S.last = performance.now(); S.timer = setTimeout(() => requestAnimationFrame(loop), 16); } }
  function still() { if (S.cx) { size(); frame(0); } }

  window.LLMBG = {
    start(canvas) {
      S.cv = canvas; S.cx = canvas.getContext("2d", { alpha: false });
      addEventListener("resize", () => { size(); if (S.style !== "living" || S.motion === "off") still(); });
      document.addEventListener("visibilitychange", kick);
      document.addEventListener("pointermove", (e) => { S.tx = e.clientX / innerWidth; S.ty = e.clientY / innerHeight; if (S.style === "living") kick(); }, { passive: true });
      document.addEventListener("pointerdown", (e) => {
        if (S.style !== "living" || S.motion === "off" || e.target.closest(".win, #cmd, #top, #dock, #reply, button, input, #startmenu")) return;
        S.ripples.push({ x: e.clientX / innerWidth, y: e.clientY / innerHeight, r: 0, a: 0.6 }); kick();
      }, { passive: true });
      size(); palette(); still(); kick();
    },
    // style: living | still | plain | photo ; motion: full | reduced | off
    theme(o) {
      S.dark = o.mode !== "light"; S.style = o.style || "living"; S.motion = o.motion || "full"; S.soft = !!o.software;
      if (!S.cv) return;
      S.cv.style.display = (S.style === "living" || S.style === "still") ? "block" : "none";
      size(); palette();
      if (S.style === "living" && S.motion !== "off") kick(); else still();
    },
    mood(state, online) { S.mood = state || "idle"; S.online = !!online; kick(); },
    show() { size(); still(); kick(); },
  };
})();
