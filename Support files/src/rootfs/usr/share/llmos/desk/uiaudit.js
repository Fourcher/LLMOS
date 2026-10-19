// UI audit (development): measures the desk page as it is drawn now and returns one JSON report.
// Contrast of every visible text against what is behind it (WCAG 2.2: 4.5:1, large text 3:1), text cut off,
// controls too small to hit (WCAG target size: 24 px minimum, 32 px comfortable), controls off the screen,
// text overlapping text inside the same window, and the inventory a design system keeps small: font sizes,
// families, weights, text colours, radii and spacing values (and how many sit on a 4 px grid).
(() => {
  const vw = innerWidth, vh = innerHeight, cap = 40;
  const out = { viewport: [vw, vh, devicePixelRatio], counts: {}, contrast: [], clipped: [], ellipsis: [], small: [],
                offscreen: [], overlap: [], inventory: {} };
  const parse = (c) => {
    if (!c) return null;
    let m = c.match(/^rgba?\(([^)]+)\)/);
    if (m) { const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
    m = c.match(/^color\(srgb\s+([^)]+)\)/);
    if (m) { const p = m[1].split(/[\s/]+/).filter(Boolean).map(Number); return [p[0] * 255, p[1] * 255, p[2] * 255, p.length > 3 ? p[3] : 1]; }
    return null;
  };
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (top, bot) => { const a = top[3]; return [top[0] * a + bot[0] * (1 - a), top[1] * a + bot[1] * (1 - a), top[2] * a + bot[2] * (1 - a), 1]; };
  const root = getComputedStyle(document.documentElement);
  const pageBg = parse(getComputedStyle(document.body).backgroundColor) || parse(root.getPropertyValue("--bg").trim()) || [16, 18, 24, 1];
  const base = pageBg[3] > 0.5 ? pageBg : [16, 18, 24, 1];
  const name = (el) => {
    const parts = [];
    for (let e = el; e && e !== document.body && parts.length < 4; e = e.parentElement) {
      let s = e.tagName.toLowerCase();
      if (e.id) { s += "#" + e.id; parts.unshift(s); break; }
      const cl = [...e.classList].slice(0, 2).join(".");
      if (cl) s += "." + cl;
      parts.unshift(s);
    }
    return parts.join(" > ");
  };
  const win = (el) => { const w = el.closest(".win"); return w ? (w.querySelector(".title") || {}).textContent || w.dataset.id : (el.closest("#bar,.bar,header") ? "top bar" : "desk"); };
  const visible = (el, r) => {
    if (r.width < 1 || r.height < 1) return false;
    if (r.right < 0 || r.bottom < 0 || r.left > vw || r.top > vh) return false;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) === 0) return false;
      if (e.classList.contains("hidden")) return false;
    }
    return true;
  };
  const behind = (el) => {          // the colour behind el: its own and its parents' backgrounds, over the page
    const layers = []; let image = false, solid = false;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== "none" && !/gradient/.test(cs.backgroundImage)) image = true;
      const c = parse(cs.backgroundColor);
      if (c && c[3] > 0.01) {
        layers.push(c);
        if (c[3] >= 0.95) {
          // an opaque PANEL; the page itself (full screen) is opaque too but the wallpaper is drawn over it
          const er = e.getBoundingClientRect();
          solid = !(e === document.body || e === document.documentElement || (er.width >= vw * 0.95 && er.height >= vh * 0.85));
          break;
        }
      }
    }
    let col = base;
    for (let i = layers.length - 1; i >= 0; i--) col = over(layers[i], col);
    return { col, image, solid };
  };
  out.glass = [];       // text over see-through backgrounds (the wallpaper shows through): judged on the screenshot
  const opacityOf = (el) => { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity) || 1; return o; };
  const inv = { size: {}, family: {}, weight: {}, color: {}, radius: {}, spacing: {}, line: {} };
  const bump = (k, v) => { inv[k][v] = (inv[k][v] || 0) + 1; };
  const texts = [];
  for (const el of document.querySelectorAll("body *")) {
    if (["SCRIPT", "STYLE", "SVG", "PATH", "IMG", "VIDEO", "CANVAS", "IFRAME", "BR"].includes(el.tagName.toUpperCase())) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 0) ||
                (el.tagName === "INPUT" && (el.value || el.placeholder));
    const r = el.getBoundingClientRect();
    if (!visible(el, r)) continue;
    const cs = getComputedStyle(el);
    ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "marginTop", "marginBottom", "gap"].forEach(p => {
      const v = parseFloat(cs[p]); if (v > 0) bump("spacing", Math.round(v));
    });
    const rad = parseFloat(cs.borderTopLeftRadius); if (rad > 0 && rad < 999) bump("radius", Math.round(rad));
    if (!own) continue;
    const fs = parseFloat(cs.fontSize), fw = parseInt(cs.fontWeight) || 400;
    texts.push({ el, r, w: win(el) });
    bump("size", fs.toFixed(1)); bump("weight", fw); bump("family", cs.fontFamily.split(",")[0].replace(/["']/g, "").trim());
    bump("line", (parseFloat(cs.lineHeight) / fs || 1.2).toFixed(2));
    const fg = parse(cs.color); if (!fg) continue;
    bump("color", cs.color);
    const b = behind(el);
    const a = fg[3] * opacityOf(el);
    const shown = over([fg[0], fg[1], fg[2], a], b.col);
    const cr = ratio(shown, b.col);
    const large = fs >= 24 || (fs >= 18.66 && fw >= 700);
    const need = large ? 3 : 4.5;
    const txt = (el.value || el.placeholder || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 50);
    if (!b.solid && out.glass.length < 150) {
      const hit = document.elementFromPoint(Math.min(vw - 1, Math.max(0, r.left + r.width / 2)), Math.min(vh - 1, Math.max(0, r.top + r.height / 2)));
      const onTop = !!hit && (hit === el || el.contains(hit) || hit.contains(el));
      if (onTop) out.glass.push({ where: win(el), el: name(el), text: txt, box: [r.left, r.top, r.width, r.height].map(Math.round), fg: shown.slice(0, 3).map(Math.round), size: fs, need });
    } else if (cr < need) out.contrast.push({ where: out.contrast.length < cap ? win(el) : undefined, el: name(el), text: txt, ratio: +cr.toFixed(2), need, size: fs, overImage: b.image || undefined });
    const clipX = el.scrollWidth > el.clientWidth + 2, clipY = el.scrollHeight > el.clientHeight + 2;
    const hides = ["hidden", "clip"].includes(cs.overflowX) || ["hidden", "clip"].includes(cs.overflowY) || cs.webkitLineClamp !== "none";
    if ((clipX || clipY) && hides && el.clientWidth > 0) {
      (cs.textOverflow === "ellipsis" || cs.webkitLineClamp !== "none" ? out.ellipsis : out.clipped).push({ where: win(el), el: name(el), text: txt, box: [Math.round(r.width), Math.round(r.height)], needs: [el.scrollWidth, el.scrollHeight] });
    }
  }
  for (const el of document.querySelectorAll("button, a[href], input, select, textarea, [role=button], [onclick], .chip, .choice, .opt, .item .t.opens")) {
    const r = el.getBoundingClientRect();
    if (!visible(el, r)) continue;
    const txt = (el.title || el.getAttribute("aria-label") || el.textContent || el.value || "").trim().replace(/\s+/g, " ").slice(0, 40);
    const m = Math.min(r.width, r.height);
    if (m < 32) out.small.push({ where: win(el), el: name(el), text: txt, size: [Math.round(r.width), Math.round(r.height)], fail: m < 24 || undefined });
    if (r.right > vw + 1 || r.bottom > vh + 1 || r.left < -1 || r.top < -1) out.offscreen.push({ where: win(el), el: name(el), text: txt, box: [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)] });
  }
  // text over text in the same window (windows over windows are normal)
  const T = texts.slice(0, 600);
  for (let i = 0; i < T.length; i++) for (let j = i + 1; j < T.length; j++) {
    const a = T[i], b = T[j];
    if (a.w !== b.w || a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const x = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left), y = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (x > 3 && y > 3 && x * y > 0.15 * Math.min(a.r.width * a.r.height, b.r.width * b.r.height)) {
      if (out.overlap.length < cap) out.overlap.push({ where: a.w, a: (a.el.textContent || "").trim().slice(0, 30), b: (b.el.textContent || "").trim().slice(0, 30), px: [Math.round(x), Math.round(y)] });
    }
  }
  const top = (o, n = 12) => Object.entries(o).sort((p, q) => q[1] - p[1]).slice(0, n);
  const sp = Object.entries(inv.spacing); const onGrid = sp.reduce((s, [v, c]) => s + (v % 4 === 0 ? c : 0), 0), allSp = sp.reduce((s, [, c]) => s + c, 0);
  out.inventory = { fontSizes: top(inv.size, 20), families: top(inv.family), weights: top(inv.weight), textColors: Object.keys(inv.color).length,
                    radii: top(inv.radius), lineHeights: top(inv.line, 8), spacingDistinct: sp.length, spacingOn4pxGrid: allSp ? +(onGrid / allSp).toFixed(2) : null };
  out.counts = { texts: texts.length, contrastFails: out.contrast.length, clipped: out.clipped.length, ellipsis: out.ellipsis.length,
                 smallTargets: out.small.length, smallFails: out.small.filter(s => s.fail).length, offscreen: out.offscreen.length, overlaps: out.overlap.length,
                 fontSizes: Object.keys(inv.size).length, families: Object.keys(inv.family).length };
  for (const k of ["contrast", "clipped", "ellipsis", "small", "offscreen"]) out[k] = out[k].slice(0, cap);
  return JSON.stringify(out);
})()
