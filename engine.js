/* voicecap engine v2 — one drawing function shared by the live player and the video renderer. */
(function (root) {
  const ASPECTS = { "16:9": [1920, 1080], "9:16": [1080, 1920], "1:1": [1080, 1080], "4:5": [1080, 1350] };
  const FONTS = {
    "EB Garamond": { w: [400, 800], gf: "EB+Garamond:wght@400..800", file: "EBGaramond[wght].ttf", label: "Classic serif" },
    "Newsreader": { w: [200, 800], gf: "Newsreader:opsz,wght@6..72,200..800", file: "Newsreader[opsz,wght].ttf", label: "Editorial serif" },
    "Fraunces": { w: [100, 900], gf: "Fraunces:opsz,wght@9..144,100..900", file: "Fraunces[SOFT,WONK,opsz,wght].ttf", label: "Soft serif" },
    "Source Serif 4": { w: [200, 900], gf: "Source+Serif+4:opsz,wght@8..60,200..900", file: "SourceSerif4[opsz,wght].ttf", label: "Modern serif" },
    "Hanken Grotesk": { w: [100, 900], gf: "Hanken+Grotesk:wght@100..900", file: "HankenGrotesk[wght].ttf", label: "Humanist sans" },
    "Inter": { w: [100, 900], gf: "Inter:opsz,wght@14..32,100..900", file: "Inter[opsz,wght].ttf", label: "Neutral sans" },
    "DM Sans": { w: [100, 1000], gf: "DM+Sans:opsz,wght@9..40,100..1000", file: "DMSans[opsz,wght].ttf", label: "Geometric sans" },
    "Bricolage Grotesque": { w: [200, 800], gf: "Bricolage+Grotesque:opsz,wght@12..96,200..800", file: "BricolageGrotesque[opsz,wdth,wght].ttf", label: "Expressive sans" },
  };
  const PALETTES = {
    Blush: { bg: "#F4D8CD", ink: "#2B1712", neutral: "#A1857C", accent: "#D9381E" },
    Cobalt: { bg: "#2846C4", ink: "#FBF6EC", neutral: "#8D9EE3", accent: "#FFD23F" },
    Pistachio: { bg: "#D5E5C1", ink: "#1E2A17", neutral: "#83956F", accent: "#C2410C" },
    Marigold: { bg: "#F2B33D", ink: "#24180B", neutral: "#94723A", accent: "#6D1F59" },
    Tomato: { bg: "#DF4A2F", ink: "#FFF4E8", neutral: "#F1A792", accent: "#1C2766" },
    Plum: { bg: "#3B1E3F", ink: "#F7EAF1", neutral: "#987C9C", accent: "#F7B267" },
    Paper: { bg: "#F1ECE2", ink: "#1F1C18", neutral: "#A69F93", accent: "#B4532A" },
    Ink: { bg: "#151413", ink: "#EEE7DA", neutral: "#6F6A62", accent: "#F2A541" },
  };
  const DEFAULTS = {
    preset: "Typewriter", aspect: "16:9", palette: "Blush", font: "Newsreader", size: 84, weight: 380, textCase: "as-is", punct: true,
    placement: "block", align: "center", width: 0.76, lineHeight: 1.32, position: 0.5, maxLines: 3,
    semantic: 1, recede: 0.85, emphasis: 0.45,
    weightAmt: 0.8, sizeAmt: 0.25, lift: 0.5, tilt: 0.25, stretch: 0.4, attack: 0.5, trace: 0,
    unit: "letter", entrance: "instant", enterMs: 220, after: "live", ghost: 0, pauseBreak: 0.7, hold: 1.0,
    fillers: "hide", edits: {}, thEdits: {},
  };
  const PRESETS = {
    Typewriter: {},
    Manuscript: { palette: "Paper", font: "EB Garamond", placement: "page", size: 62, weight: 420, align: "left", maxLines: 7, lineHeight: 1.42,
      unit: "word", entrance: "fade", enterMs: 260, after: "settle", weightAmt: 0.6, sizeAmt: 0.1, lift: 0.2, tilt: 0, stretch: 0.2, attack: 0.15 },
    Poster: { palette: "Cobalt", font: "Bricolage Grotesque", placement: "editorial", size: 118, weight: 520, maxLines: 4, lineHeight: 1.08,
      unit: "syllable", entrance: "scale", enterMs: 180, after: "live", weightAmt: 1, sizeAmt: 0.45, lift: 0.35, tilt: 0.15, stretch: 0.2, attack: 0.8 },
    Score: { palette: "Pistachio", font: "Fraunces", size: 84, weight: 300, textCase: "lower", unit: "letter", after: "breathe",
      weightAmt: 0.9, sizeAmt: 0.2, lift: 1.2, tilt: 0.6, stretch: 0.8, attack: 0.4, trace: 0.6 },
    Ticker: { palette: "Marigold", font: "Hanken Grotesk", placement: "ticker", size: 76, weight: 500, unit: "word", entrance: "rise", enterMs: 160,
      after: "settle", weightAmt: 0.7, sizeAmt: 0.15, lift: 0.3, tilt: 0, stretch: 0.2, attack: 0.3 },
    Plain: { palette: "Ink", font: "Inter", size: 72, weight: 450, maxLines: 2, unit: "word", entrance: "fade", enterMs: 120, after: "settle",
      ghost: 0.35, weightAmt: 0, sizeAmt: 0, lift: 0, tilt: 0, stretch: 0, attack: 0, emphasis: 0, semantic: 0, recede: 0, trace: 0 },
  };
  function params(p) {
    p = p || {};
    const base = Object.assign({}, DEFAULTS, PRESETS[p.preset] || {});
    const out = Object.assign(base, p);
    out.edits = Object.assign({}, p.edits || {}); out.thEdits = Object.assign({}, p.thEdits || {});
    return out;
  }
  // ---------- color
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const hex = (h) => { h = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(h.substr(i, 2), 16)); };
  const toHex = (c) => "#" + c.map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, "0")).join("");
  const mix = (a, b, k) => { const A = hex(a), B = hex(b); return toHex(A.map((v, i) => v + (B[i] - v) * k)); };
  const lin = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const lum = (h) => { const [r, g, b] = hex(h).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  function oklch(L, C, Hdeg) {
    const h = (Hdeg * Math.PI) / 180, a = C * Math.cos(h), b = C * Math.sin(h);
    const l_ = L + 0.3963377774 * a + 0.2158037573 * b, m_ = L - 0.1055613458 * a - 0.0638541728 * b, s_ = L - 0.0894841775 * a - 1.291485548 * b;
    const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
    const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      bb = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
    const enc = (x) => 255 * (x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(Math.max(x, 0), 1 / 2.4) - 0.055);
    const out = [r, g, bb]; return { rgb: out.map(enc), ok: out.every((x) => x >= -0.001 && x <= 1.001) };
  }
  function hueOf(h) {
    const [r, g, b] = hex(h).map((v) => v / 255), mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    if (d < 1e-6) return -1;
    let H = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return (H * 60 + 360) % 360;
  }
  /* n distinct theme colors that read against the palette background (>= 3:1), hues spread by the golden angle */
  function themeColors(pal, n) {
    const dark = lum(pal.bg) < 0.25, bgH = hueOf(pal.bg), out = [];
    let h = (hueOf(pal.accent) + 360) % 360, tries = 0;
    while (out.length < n && tries < n * 12) {
      tries++; const hh = h; h = (h + 137.508) % 360;
      if (bgH >= 0 && Math.min(Math.abs(hh - bgH), 360 - Math.abs(hh - bgH)) < 28 && lum(pal.bg) > 0.03 && lum(pal.bg) < 0.6) continue;
      let L = dark ? 0.84 : 0.47, C = 0.15, col = null;
      for (let k = 0; k < 40; k++) {
        let o = oklch(L, C, hh); let c2 = C; while (!o.ok && c2 > 0.02) { c2 -= 0.01; o = oklch(L, c2, hh); }
        const hx = toHex(o.rgb);
        if (contrast(hx, pal.bg) >= 3.2) { col = hx; break; }
        L += dark ? 0.015 : -0.015; if (L < 0.12 || L > 0.97) break;
      }
      if (col && !out.some((c) => contrast(c, col) < 1.12 && Math.abs(hueOf(c) - hueOf(col)) < 20)) out.push(col);
    }
    while (out.length < n) out.push(pal.accent);
    return out;
  }
  // ---------- data helpers
  const b64 = (s) => { const bin = (typeof atob !== "undefined" ? atob : (x) => Buffer.from(x, "base64").toString("binary"))(s); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; };
  function envelope(data) {
    if (data._env) return data._env;
    const e = data.env || { hz: 50, loud: "", pitch: "" };
    data._env = { hz: e.hz, loud: b64(e.loud), pitch: b64(e.pitch) };
    return data._env;
  }
  const loudAt = (env, t) => { const i = Math.floor(t * env.hz); return i >= 0 && i < env.loud.length ? env.loud[i] / 255 : 0; };
  const pitchAt = (env, t) => { const i = Math.floor(t * env.hz); const v = i >= 0 && i < env.pitch.length ? env.pitch[i] : 0; return v ? (v - 128) / 8 : null; };
  function displayText(s, P) {
    let t = s.trim();
    if (!P.punct) t = t.replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, "") || t;
    if (P.textCase === "lower") t = t.toLowerCase(); else if (P.textCase === "upper") t = t.toUpperCase();
    return t;
  }
  const ease = (p) => 1 - Math.pow(1 - clamp(p, 0, 1), 3); // decelerate, no overshoot

  // ---------- scene
  function buildScene(data, Pin, measure) {
    const P = params(Pin);
    const [W, H] = ASPECTS[P.aspect] || ASPECTS["16:9"];
    const S = P.size * (Math.min(W, H) / 1080);
    const F = FONTS[P.font] || FONTS.Inter, [wmin, wmax] = F.w;
    const pal = PALETTES[P.palette] || PALETTES.Blush;
    const themes = data.themes || [];
    const tcol = themeColors(pal, Math.max(8, themes.length));
    // receding words: as close to the background as possible while keeping >= 3.4:1 contrast
    let neutral = pal.ink;
    for (let k = 0.05; k <= 0.75; k += 0.05) { const c = mix(pal.ink, pal.bg, k); if (contrast(c, pal.bg) >= 3.4) neutral = c; else break; }
    const env = envelope(data);
    const thr = P.emphasis > 0 ? 2.4 - 1.7 * P.emphasis : Infinity;
    const vertical = H > W;
    // safe box: YouTube Shorts UI keeps clear of right rail and bottom band on 9:16
    const box = vertical ? { x0: 60, x1: 888, y0: 288, y1: 1248 } : { x0: W * (1 - P.width) / 2, x1: W * (1 + P.width) / 2, y0: H * 0.08, y1: H * 0.9 };
    if (vertical) { const cx = (box.x0 + box.x1) / 2, hw = ((box.x1 - box.x0) / 2) * clamp(P.width / 0.76, 0.6, 1); box.x0 = cx - hw; box.x1 = cx + hw; }
    const maxW = box.x1 - box.x0;
    const placement = P.placement;
    const align = placement === "editorial" || placement === "ticker" ? "left" : placement === "page" ? P.align : P.align;
    const maxLines = placement === "ticker" ? 1 : P.maxLines;
    const wOf = (a, w) => {
      let x = P.weight + P.weightAmt * (a - 0.55) * (wmax - wmin) * 1.1;
      if (w.emph) x += 140; if (w.quiet) x -= 120; if (w.fn) x -= P.recede * 90;
      return Math.round(clamp(x, wmin, wmax) / 10) * 10;
    };
    const sOf = (a, w) => 1 + P.sizeAmt * (a - 0.55) * 0.6 + (w.emph ? 0.05 : 0) - (w.fn ? P.recede * 0.06 : 0);
    const words = [];
    // fillers (um, uh...) flagged in the data: hidden ones leave the layout entirely and neighbours take their cleaned text (wh)
    const hideF = P.fillers !== "show";
    let lastE = 0;
    data.words.forEach((d, i) => {
      if (d.fl && hideF) return;
      const src = hideF && d.wh != null ? d.wh : d.w;
      const text = displayText(src, P); if (!text) return;
      const raw = src.trim(), off = P.punct ? 0 : raw.length - raw.replace(/^[^\p{L}\p{N}']+/u, "").length;
      const ed = P.edits[i];
      // pauses count a hidden filler as speech (phrasing matches the shown version); sentence breaks use the visible gap
      const vgap = Math.max(0, d.s - lastE); lastE = d.e;
      const w = { i, text, s: d.s, e: d.e, gap: d.gap || 0, vgap, fn: (!!d.fn || !!d.fl) && ed !== "emph" && ed !== "normal", th: d.th, fl: !!d.fl,
        emph: ed === "emph" || (ed !== "normal" && ed !== "quiet" && !d.fn && (d.emph || 0) >= thr), quiet: ed === "quiet",
        pitch: d.pitch, slope: d.slope || 0, stretch: d.stretch || 0, p: d.p };
      const te = (P.thEdits || {})[i];
      if (te != null) { w.th = te < 0 ? null : te; if (te >= 0) w.fn = false; }
      let color = pal.ink;
      if (w.th != null && P.semantic > 0) color = mix(pal.ink, tcol[w.th % tcol.length], P.semantic);
      else if (w.emph && P.semantic <= 0) color = mix(pal.ink, pal.accent, 0.75);
      if (w.fn || w.quiet) color = mix(color, neutral, P.recede || (w.quiet ? 0.8 : 0));
      w.color = color;
      const em = S, sp = P.stretch * Math.max(0, clamp(w.stretch, -1, 2.5)) * 0.045 * em;
      const chars = [...text];
      const lo = d.lo || [], lc = d.lc || "", la = d.la || [], lp = d.lp || [], sy = d.sy || [0];
      const shift = off;
      let x = 0, sIdx = 0;
      w.chars = chars.map((c, k) => {
        const kk = clamp(k + shift, 0, Math.max(0, lo.length - 1));
        const a = la.length ? la[kk] / 255 : 0.55;
        while (sIdx + 1 < sy.length && sy[sIdx + 1] <= kk) sIdx++;
        const onset = d.s + (lo.length ? lo[kk] / 1000 : 0);
        const sOn = d.s + (lo.length ? lo[clamp(sy[sIdx], 0, lo.length - 1)] / 1000 : 0);
        const wt = wOf(a, w), sc = sOf(a, w), size = em * sc;
        const cw = measure(c, P.font, wt, size);
        const ch = { c, x, cw, a, wt, size, onset, sOn, cls: lc[kk] || "V", pit: lp.length && lp[kk] ? (lp[kk] - 128) / 8 : null };
        x += cw + sp;
        return ch;
      });
      w.chars.forEach((c, k) => { c.end = k + 1 < w.chars.length ? Math.max(c.onset + 0.04, w.chars[k + 1].onset) : w.e; });
      w.width = Math.max(0, x - sp);
      words.push(w);
    });
    const space = measure(" ", P.font, P.weight, S);
    // ---- lines
    const lines = [];
    const newLine = (w, para) => { const L = { words: [w], width: w.width, para: !!para }; lines.push(L); return L; };
    let phrases = [], cur = null;
    if (placement === "page") {
      let L = null;
      for (const w of words) {
        const para = L && w.gap >= Math.max(1.6, P.pauseBreak * 2.5);
        if (!L || para || L.width + space + w.width > maxW) { L = newLine(w, para); continue; }
        L.words.push(w); L.width += space + w.width;
      }
      lines.forEach((L) => { L.start = L.words[0].s; L.end = L.words[L.words.length - 1].e; });
    } else {
      for (const w of words) {
        const last = cur && cur.words[cur.words.length - 1];
        const brk = !cur || w.gap >= P.pauseBreak || (cur.words.length >= 3 && /[.?!…]["')\]]?$/.test(last.text) && w.vgap >= 0.12);
        if (!brk) {
          const L = cur.lines[cur.lines.length - 1];
          if (L.width + space + w.width <= maxW) { L.words.push(w); L.width += space + w.width; cur.words.push(w); continue; }
          if (cur.lines.length < maxLines) { cur.lines.push({ words: [w], width: w.width }); cur.words.push(w); continue; }
        }
        cur = { words: [w], lines: [{ words: [w], width: w.width }] }; phrases.push(cur);
      }
    }
    const pitchPx = P.lift * S * 0.07;
    const placeLine = (L, base, ref) => {
      let x = align === "left" ? box.x0 : (box.x0 + box.x1 - L.width) / 2;
      L.words.forEach((w) => {
        w.x = x; w.base = base; x += w.width + space;
        // pitch per letter: fill unvoiced letters from neighbours, smooth, then lift = word level + damped contour
        const pv = w.chars.map((c) => c.pit), n = pv.length, known = pv.map((v, k) => (v == null ? -1 : k)).filter((k) => k >= 0);
        if (ref == null || !known.length) { w.chars.forEach((c) => (c.dy = 0)); }
        else {
          const filled = pv.map((v, k) => {
            if (v != null) return v;
            let a = -1, b = -1; for (const q of known) { if (q < k) a = q; if (q > k && b < 0) b = q; }
            if (a < 0) return pv[b]; if (b < 0) return pv[a]; return pv[a] + ((pv[b] - pv[a]) * (k - a)) / (b - a);
          });
          const sm = filled.map((v, k) => (filled[Math.max(0, k - 1)] + 2 * v + filled[Math.min(n - 1, k + 1)]) / 4);
          const mean = sm.reduce((x, y) => x + y, 0) / n;
          w.chars.forEach((c, k) => { c.dy = -clamp(((mean - ref) + 0.6 * clamp(sm[k] - mean, -3, 3)) * pitchPx, -0.55 * S, 0.55 * S); });
        }
        w.rot = clamp(P.tilt * w.slope * 0.5, -9, 9);
      });
    };
    const median = (arr) => { const a = arr.filter((v) => v != null).sort((x, y) => x - y); return a.length ? a[Math.floor(a.length / 2)] : null; };
    const pitchLH = P.lineHeight * S;
    if (placement === "page") {
      lines.forEach((L) => { L.ref = median(L.words.flatMap((w) => w.chars.map((c) => c.pit))); placeLine(L, 0, L.ref); });
    } else {
      phrases.forEach((ph, k) => {
        ph.start = ph.words[0].s; ph.end = ph.words[ph.words.length - 1].e;
        ph.ref = median(ph.words.flatMap((w) => w.chars.map((c) => c.pit)));
        const n = ph.lines.length;
        let top;
        if (placement === "ticker") top = vertical ? box.y1 - pitchLH : H * 0.74;
        else if (placement === "editorial") top = vertical ? box.y0 + (box.y1 - box.y0) * 0.18 : H * clamp(P.position - 0.14, 0.1, 0.6);
        else top = (vertical ? box.y0 + (box.y1 - box.y0) * P.position : H * P.position) - (n * pitchLH) / 2;
        ph.lines.forEach((L, li) => placeLine(L, top + (li + 0.75) * pitchLH, ph.ref));
        ph.top = top; ph.bottom = top + n * pitchLH;
        ph.x0 = Math.min(...ph.lines.map((L) => L.words[0].x)); ph.x1 = Math.max(...ph.lines.map((L) => L.words[0].x + L.width));
      });
      phrases.forEach((ph, k) => {
        const nx = phrases[k + 1];
        ph.on = ph.start - 0.05;
        ph.off = nx ? Math.min(ph.end + P.hold, Math.max(ph.end + 0.05, nx.start - 0.06)) : ph.end + P.hold + 1.5;
      });
    }
    return { W, H, S, P, pal, tcol, neutral, themes, words, phrases, lines, env, box, pitchLH, placement, duration: data.duration };
  }

  // ---------- drawing
  function charState(c, w, t, scene) {
    const P = scene.P;
    const ta = P.unit === "letter" ? c.onset : P.unit === "syllable" ? c.sOn : w.s;
    let alpha = 1, dy = 0, sc = 1, blur = 0;
    if (t < ta) { if (P.ghost <= 0) return null; alpha = P.ghost; }
    else if (P.entrance !== "instant" && P.entrance !== "none") {
      const p = (t - ta) / Math.max(0.02, P.enterMs / 1000), e = ease(p);
      if (P.entrance === "fade") alpha = P.ghost + (1 - P.ghost) * e;
      else if (P.entrance === "rise") { alpha = P.ghost + (1 - P.ghost) * e; dy = (1 - e) * 0.22 * scene.S; }
      else if (P.entrance === "scale") { alpha = P.ghost + (1 - P.ghost) * Math.min(1, e * 1.6); sc = 0.55 + 0.45 * e; }
      else if (P.entrance === "blur") { alpha = P.ghost + (1 - P.ghost) * e; blur = (1 - e) * 0.12 * scene.S; }
    }
    // loudness driving weight/size
    let a = c.a;
    if (t >= ta) {
      if (P.after === "live") {
        const live = loudAt(scene.env, t), end = c.end + 0.1;
        if (t <= end) a = Math.max(live, c.a * 0.35);
        else a = c.a + (Math.max(loudAt(scene.env, end), c.a * 0.35) - c.a) * (1 - ease((t - end) / 0.18));
      } else if (P.after === "breathe") a = c.a * 0.72 + loudAt(scene.env, t) * 0.4;
    }
    if (P.attack > 0 && (c.cls === "P" || c.cls === "F") && t >= ta) {
      const q = (t - ta) / 0.14; if (q < 1) sc *= 1 + P.attack * 0.22 * (1 - q) * (1 - q);
    }
    return { alpha, dy, sc, blur, a };
  }
  function weightFor(a, w, scene) {
    const P = scene.P, [wmin, wmax] = (FONTS[P.font] || FONTS.Inter).w;
    let x = P.weight + P.weightAmt * (a - 0.55) * (wmax - wmin) * 1.1;
    if (w.emph) x += 140; if (w.quiet) x -= 120; if (w.fn) x -= P.recede * 90;
    return Math.round(clamp(x, wmin, wmax) / 10) * 10;
  }
  function drawWord(ctx, w, t, scene, y0, fade, boxes) {
    const P = scene.P, S = scene.S;
    const cx = w.x + w.width / 2, cy = y0 + w.base - S * 0.3;
    let drew = false;
    ctx.save();
    if (w.rot) { ctx.translate(cx, cy); ctx.rotate((-w.rot * Math.PI) / 180); ctx.translate(-cx, -cy); }
    ctx.fillStyle = w.color; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    let lastFont = "";
    for (const c of w.chars) {
      const st = charState(c, w, t, scene); if (!st) continue;
      const wt = weightFor(st.a, w, scene);
      const size = S * (1 + P.sizeAmt * (st.a - 0.55) * 0.6 + (w.emph ? 0.05 : 0) - (w.fn ? P.recede * 0.06 : 0)) * st.sc;
      const f = `${wt} ${size.toFixed(1)}px "${P.font}"`; if (f !== lastFont) { ctx.font = f; lastFont = f; }
      ctx.globalAlpha = st.alpha * fade;
      if (st.blur > 0.4 && typeof ctx.filter === "string") ctx.filter = `blur(${st.blur.toFixed(1)}px)`; else if (ctx.filter && ctx.filter !== "none") ctx.filter = "none";
      ctx.fillText(c.c, w.x + c.x + c.cw / 2, y0 + w.base + c.dy + st.dy);
      drew = true;
    }
    ctx.restore();
    if (drew && boxes) boxes.push({ i: w.i, x: w.x, y: y0 + w.base - S * 0.85, w: w.width, h: S * 1.15 });
  }
  function drawTrace(ctx, ph, t, scene, fade) {
    const env = scene.env, S = scene.S, x0 = ph.x0, x1 = ph.x1, yb = ph.bottom + 0.25 * S, tEnd = Math.min(t, ph.end);
    if (tEnd <= ph.start || ph.ref == null) return;
    ctx.save(); ctx.globalAlpha = scene.P.trace * fade; ctx.strokeStyle = scene.neutral; ctx.lineWidth = Math.max(1.5, S * 0.02);
    ctx.lineJoin = ctx.lineCap = "round"; ctx.beginPath(); let pen = false;
    for (let tt = ph.start; tt <= tEnd; tt += 0.04) {
      const v = pitchAt(env, tt); if (v == null) { pen = false; continue; }
      const x = x0 + ((tt - ph.start) / (ph.end - ph.start)) * (x1 - x0), y = yb - clamp(v - ph.ref, -6, 6) * S * 0.05;
      if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true; }
    }
    ctx.stroke(); ctx.restore();
  }
  function findLast(arr, t, key) { let lo = 0, hi = arr.length - 1, best = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (arr[m][key] <= t) { best = m; lo = m + 1; } else hi = m - 1; } return best; }
  /* draw(ctx, scene, t): ctx already scaled so 1 unit = 1 output pixel. Returns hit boxes of visible words. */
  function draw(ctx, scene, t) {
    const { W, H, P, pal, S } = scene, boxes = [];
    ctx.save(); ctx.globalAlpha = 1; ctx.fillStyle = pal.bg; ctx.fillRect(0, 0, W, H);
    if (scene.placement === "page") {
      const L = scene.lines, k = findLast(L, t, "start");
      const lh = scene.pitchLH, n = P.maxLines;
      // scroll so the current line sits on the last row; ease between rows
      const target = (i) => Math.max(0, i - n + 1);
      let scroll = target(Math.max(k, 0));
      if (k >= 0) { const prev = target(k - 1), p = ease((t - L[k].start) / 0.45); scroll = prev + (scroll - prev) * p; }
      const top = (H - n * lh) / 2 + 0.75 * lh;
      for (let i = Math.max(0, Math.floor(scroll) - 1); i <= Math.min(L.length - 1, Math.ceil(scroll) + n); i++) {
        const row = i - scroll, y0 = top + row * lh - L[i].words[0].base;
        if (row < -1 || row > n) continue;
        const fade = row < 0 ? clamp(1 + row, 0, 1) : 1;
        for (const w of L[i].words) if (w.s - 0.3 <= t || P.ghost > 0) drawWord(ctx, w, t, scene, y0, fade, boxes);
      }
    } else {
      const k = findLast(scene.phrases, t, "on");
      for (const j of [k - 1, k]) {
        const ph = scene.phrases[j]; if (!ph || t > ph.off || t < ph.on) continue;
        const fade = clamp((ph.off - t) / 0.25, 0, 1);
        if (P.trace > 0) drawTrace(ctx, ph, t, scene, fade);
        for (const L of ph.lines) for (const w of L.words) drawWord(ctx, w, t, scene, 0, fade, boxes);
      }
    }
    ctx.restore();
    return boxes;
  }
  const api = { ASPECTS, FONTS, PALETTES, DEFAULTS, PRESETS, params, buildScene, draw, themeColors, mix, contrast, clamp };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.VC = api;
})(typeof window !== "undefined" ? window : globalThis);
