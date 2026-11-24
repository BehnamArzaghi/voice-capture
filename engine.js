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
    // live energy (0 = off): how typed letters keep answering the voice after they land
    linger: 0, ripple: 0, sway: 0, shimmer: 0, glow: 0,
    fillers: "hide", edits: {}, thEdits: {}, thOff: [],
    denoise: "auto",  // the recording's sound: "auto" (the recommended level), "off", "light" or "full" (noise-reduced copies)
    cards: 0,  // 1 = a small card with a glossary term's definition at its first appearance (verified terms)
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
    out.thOff = Array.isArray(p.thOff) ? p.thOff.slice() : [];
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
  /* a theme's own color, from its Notion color name: same hue in every recording, lightness chosen to read on the palette.
     [hue, most chroma]: brown is a muted orange and gray nearly neutral, so they stay apart from orange and blue;
     Notion's "default" (no color) gets teal, a hue no other Notion color uses */
  const NOTION_COL = { red: [27, 0.17], orange: [62, 0.17], yellow: [95, 0.16], green: [145, 0.16], blue: [255, 0.16], purple: [305, 0.16],
    pink: [350, 0.16], brown: [38, 0.07], gray: [250, 0.025], default: [195, 0.13] };
  function hueColor(pal, hh, cmax) {
    // search lighter and darker from the usual starting lightness; keep whichever passes contrast with more color left in it
    const dark = lum(pal.bg) < 0.25, best = [];
    for (const dir of dark ? [1, -1] : [-1, 1]) {
      let L = dir > 0 ? 0.84 : 0.47;
      if (dir > 0 && !dark) L = 0.9; if (dir < 0 && dark) L = 0.42;
      for (let k = 0; k < 60; k++) {
        let C = cmax, o = oklch(L, C, hh); while (!o.ok && C > 0.02) { C -= 0.01; o = oklch(L, C, hh); }
        const hx = toHex(o.rgb);
        if (contrast(hx, pal.bg) >= 3.2) { best.push({ hx, C }); break; }
        L += dir * 0.015; if (L < 0.08 || L > 0.98) break;
      }
    }
    if (!best.length) return null;
    return (best.length > 1 && best[1].C > best[0].C + 0.03 ? best[1] : best[0]).hx;
  }
  function themePalette(pal, names, colors) {
    const gold = themeColors(pal, Math.max(8, names.length));
    return names.map((n, i) => { const c = NOTION_COL[(colors || [])[i]]; return (c && hueColor(pal, c[0], c[1])) || gold[i % gold.length]; });
  }
  /* a studio theme edit: a theme name (new), "" = no theme, or an index into data.themes (older edits) */
  function themeIndex(te, themes) {
    if (te == null) return undefined;
    if (typeof te === "number") return te < 0 ? null : te;
    if (te === "") return null;
    const k = themes.indexOf(te); return k >= 0 ? k : undefined;
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
    // themes: the recording's list (glossary order) plus any theme a studio edit names that the list lacks
    const themes = (data.themes || []).slice(), tcolors = (data.themeColors || []).slice();
    Object.values(P.thEdits || {}).forEach((v) => { if (typeof v === "string" && v && !themes.includes(v)) { themes.push(v); tcolors.push(null); } });
    const tcol = themePalette(pal, themes, tcolors);
    const thOff = new Set(P.thOff || []);
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
    const words = [], onsets = [];  // onsets: every letter's onset in order (running max), to find the letter being spoken
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
      const te = themeIndex((P.thEdits || {})[i], themes);
      if (te !== undefined) { w.th = te; if (te != null) w.fn = false; }
      let color = pal.ink;
      if (w.th != null && thOff.has(themes[w.th])) w.th = null;
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
      w.chars.forEach((c) => { c.gi = onsets.length; onsets.push(Math.max(c.onset, onsets.length ? onsets[onsets.length - 1] : 0)); });
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
        w.rot = clamp(P.tilt * w.slope * 0.5, -9, 9); w.ref = ref;
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
    // definition cards: a checked glossary term's definition, shown for a few seconds where the term is first heard (one at a time)
    const cards = [];
    if (+P.cards > 0 && data.terms) {
      const byI = {}; words.forEach((w) => (byI[w.i] = w));
      const first = [];
      data.terms.forEach((t) => {
        if (!t.v || !t.def || t.st === "r") return;
        const o = (t.occ || []).find(([a, n]) => { for (let q = a; q < a + n; q++) if (byI[q] && byI[q].th != null) return true; return false; });
        if (!o) return;
        const w = byI[o[0]] || words.find((x) => x.i >= o[0]); if (!w) return;
        first.push({ s0: w.s, term: t.t, def: t.def, src: t.src || "", color: w.th != null ? tcol[w.th % tcol.length] : pal.accent });
      });
      first.sort((a, b) => a.s0 - b.s0);
      let free = -1;
      for (const c of first) {
        const s = Math.max(c.s0, free + 0.3); if (s - c.s0 > 12) continue;
        c.s = s; c.e = s + clamp(1.8 + c.def.split(/\s+/).length * 0.33, 4, 8); free = c.e; cards.push(c);
      }
    }
    return { W, H, S, P, pal, tcol, neutral, themes, words, phrases, lines, env, box, pitchLH, placement, duration: data.duration, onsets, cur: 0, cards };
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
        else if (P.linger > 0) {  // linger: keep following the voice after the letter is spoken, fading out (or, at full, until the phrase leaves)
          const span = P.linger >= 0.99 ? Infinity : 0.18 + P.linger * 4, k = span === Infinity ? 1 : 1 - ease((t - end) / span);
          a = c.a + (Math.max(live, c.a * 0.35) - c.a) * k;
        } else a = c.a + (Math.max(loudAt(scene.env, end), c.a * 0.35) - c.a) * (1 - ease((t - end) / 0.18));
      } else if (P.after === "breathe") a = c.a * 0.72 + loudAt(scene.env, t) * 0.4;
    }
    if (P.attack > 0 && (c.cls === "P" || c.cls === "F") && t >= ta) {
      const q = (t - ta) / 0.14; if (q < 1) sc *= 1 + P.attack * 0.22 * (1 - q) * (1 - q);
    }
    // live energy: the voice travels back through letters already on screen as a wave (~22 letters a second, fading with distance)
    let dx = 0, rot = 0, heat = 0;
    if (t >= ta && (P.ripple > 0 || P.sway > 0 || P.shimmer > 0 || P.glow > 0)) {
      const dist = Math.max(0, scene.cur - c.gi), delay = dist * 0.045, reach = Math.exp(-dist / 45), tw = t - delay;
      const wave = loudAt(scene.env, tw);
      if (P.ripple > 0) a += P.ripple * 1.2 * (wave - 0.35) * reach;
      if (P.sway > 0 && w.ref != null) {  // sway: typed letters keep riding the current melody (last voiced pitch within 0.25 s)
        let v = null; for (let q = 0; q < 6 && v == null; q++) v = pitchAt(scene.env, tw - q * 0.05);
        if (v != null) dy -= P.sway * clamp(v - w.ref, -5, 5) * scene.S * 0.11 * (0.4 + 0.6 * reach);
      }
      if (P.shimmer > 0) {  // shimmer: a tremor whose size follows the energy of the voice
        const e = P.shimmer * clamp(wave * 1.3 - 0.15, 0, 1) * (0.35 + 0.65 * reach), g = c.gi;
        dx = e * scene.S * 0.055 * (Math.sin(t * 11.3 + g * 1.7) * 0.6 + Math.sin(t * 23.1 + g * 2.9) * 0.4);
        dy += e * scene.S * 0.055 * (Math.sin(t * 13.7 + g * 2.3) * 0.6 + Math.sin(t * 19.9 + g * 0.7) * 0.4);
        rot = e * 9 * Math.sin(t * 9.1 + g * 3.1);
      }
      if (P.glow > 0) heat = P.glow * clamp((wave - 0.45) / 0.35, 0, 1) * (0.25 + 0.75 * reach);
    }
    return { alpha, dy, dx, rot, sc, blur, a: clamp(a, 0, 1.3), heat };
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
      if (P.glow > 0) ctx.fillStyle = st.heat > 0.01 ? mix(w.color, scene.pal.accent, st.heat) : w.color;
      const px = w.x + c.x + c.cw / 2 + st.dx, py = y0 + w.base + c.dy + st.dy;
      if (Math.abs(st.rot) > 0.05) { ctx.save(); ctx.translate(px, py); ctx.rotate((st.rot * Math.PI) / 180); ctx.fillText(c.c, 0, 0); ctx.restore(); }
      else ctx.fillText(c.c, px, py);
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
  function wrapText(ctx, text, maxW) {
    const out = []; let line = "";
    for (const word of String(text).split(/\s+/)) { const tryL = line ? line + " " + word : word; if (line && ctx.measureText(tryL).width > maxW) { out.push(line); line = word; } else line = tryL; }
    if (line) out.push(line); return out;
  }
  function drawCards(ctx, scene, t) {
    const { W, H, pal, box } = scene, c = scene.cards.find((x) => t >= x.s && t < x.e); if (!c) return;
    const u = Math.min(W, H) / 1080, vertical = H > W;
    const a = Math.min(ease((t - c.s) / 0.35), ease((c.e - t) / 0.35));
    const cw = vertical ? W - 2 * 80 * u : Math.min(W * 0.4, 700 * u), pad = 24 * u, bar = 6 * u;
    const x = vertical ? 80 * u : Math.max(48 * u, box.x0 - 40 * u), y = (vertical ? 110 * u : 44 * u) + (1 - a) * 10 * u;
    const fam = '"Inter", system-ui, sans-serif', tw = cw - 2 * pad - bar;
    if (!c.lay || c.lay.W !== W) {
      ctx.font = `400 ${25 * u}px ${fam}`; const lines = wrapText(ctx, c.def, tw).slice(0, 5);
      ctx.font = `400 ${18 * u}px ${fam}`; let src = c.src; while (src && ctx.measureText(src).width > tw) src = src.slice(0, -2).trimEnd() + "…";
      if (src.length > 1 && src.endsWith("……")) src = src.slice(0, -1);
      c.lay = { W, lines, src, h: pad * 2 + 34 * u + lines.length * 34 * u + (src ? 30 * u : 0) };
    }
    const h = c.lay.h, r = 14 * u;
    ctx.save(); ctx.globalAlpha = a;
    ctx.fillStyle = mix(pal.bg, pal.ink, 0.07); ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, cw, h, r); else ctx.rect(x, y, cw, h);
    ctx.fill(); ctx.fillStyle = c.color; ctx.fillRect(x, y + r, bar, h - 2 * r);
    let yy = y + pad + 26 * u; const xx = x + bar + pad; ctx.textBaseline = "alphabetic";
    ctx.fillStyle = c.color; ctx.font = `600 ${29 * u}px ${fam}`; ctx.fillText(c.term, xx, yy); yy += 40 * u;
    ctx.fillStyle = pal.ink; ctx.font = `400 ${25 * u}px ${fam}`; for (const L of c.lay.lines) { ctx.fillText(L, xx, yy); yy += 34 * u; }
    if (c.lay.src) { ctx.fillStyle = scene.neutral; ctx.font = `400 ${18 * u}px ${fam}`; ctx.fillText(c.lay.src, xx, yy + 2 * u); }
    ctx.restore();
  }
  function draw(ctx, scene, t) {
    const { W, H, P, pal, S } = scene, boxes = [];
    { const o = scene.onsets; let lo = 0, hi = o.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (o[m] <= t) { k = m; lo = m + 1; } else hi = m - 1; } scene.cur = k; }
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
    if (scene.cards && scene.cards.length) drawCards(ctx, scene, t);
    ctx.restore();
    return boxes;
  }
  // ---------- thumbnail: a still title card drawn with the captions' palettes, typefaces, looks, voice mapping and theme colors.
  // Words of the title that are heard in the recording borrow their letters' loudness and pitch from where they are spoken.
  const FN_WORDS = new Set(`a an the and or but nor so yet for of in on at to from by with without within about into onto over under
than then as if that this these those there here it its it's is are was were be been being am do does did done have has had having
will would shall should can could may might must not no i me my mine myself you your yours yourself he him his she her hers we us our
ours they them their theirs what which who whom whose when where why how all any some such very just also too really like um uh oh
well kind sort lot gonna wanna i'm you're that's there's i've i'll i'd don't doesn't didn't isn't aren't wasn't weren't can't
won't wouldn't couldn't shouldn't let's maybe actually even more most much many each every one own other another same okay yeah right
you've you'd we're they're he's she's what's here's who's thing things something anything stuff get got go going know mean say said
up out off down quite rather sometimes always never often because while though although whether either neither both`.split(/\s+/));
  const SMALL = new Set("a an the and or but nor for of in on at to by as vs via with from into onto over".split(" "));
  const THUMB_DEFAULTS = { title: "", subtitle: "", follow: true, look: {}, tSize: 200, subRatio: 0.42, rule: 1, edits: {}, thEdits: {} };
  /* starting text from a recording title: the part before the first colon is the title, the rest the subtitle */
  function thumbDefaults(title) {
    const t = String(title || "").trim(), k = t.indexOf(":");
    return Object.assign(JSON.parse(JSON.stringify(THUMB_DEFAULTS)), k > 0 ? { title: t.slice(0, k).trim(), subtitle: t.slice(k + 1).trim() } : { title: t });
  }
  /* the look a thumbnail uses: the video's (follow) or its own; edits and theme tags are the thumbnail's own, hidden themes the recording's */
  function thumbParams(TH, videoP) {
    const T = Object.assign({}, THUMB_DEFAULTS, TH || {});
    const src = Object.assign({}, T.follow ? videoP || {} : T.look || {});
    ["edits", "thEdits", "thOff", "cards"].forEach((k) => delete src[k]);
    const P = params(src);
    P.thOff = ((videoP && videoP.thOff) || []).slice(); P.edits = Object.assign({}, T.edits || {}); P.thEdits = Object.assign({}, T.thEdits || {});
    return { P, T };
  }
  const tnorm = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[’‘]/g, "'")
    .replace(/[^\p{L}\p{N}']/gu, "").replace(/^'+|'+$/g, "");
  const tsame = (a, b) => a === b || a + "s" === b || b + "s" === a || a + "es" === b || b + "es" === a;
  function caseOf(text, mode, first) {
    if (mode === "lower") return text.toLowerCase();
    if (mode === "upper") return text.toUpperCase();
    if (mode === "title") {
      const k = tnorm(text);
      if (!first && SMALL.has(k)) return text.toLowerCase();
      return text.replace(/\p{L}/u, (c) => c.toUpperCase());
    }
    return text;
  }
  /* where each thumbnail word is heard: longest runs of consecutive spoken words first, then single content words near them */
  function voiceSource(data, toks) {
    const idx = [], spoken = [];
    (data.words || []).forEach((w, i) => { if (!w.fl && w.w && w.w.trim()) { idx.push(i); spoken.push(tnorm(w.w)); } });
    const keys = toks.map((t) => tnorm(t.raw)), src = toks.map(() => null);
    let near = -1;
    for (const part of ["t", "s"]) {
      const ks = toks.map((t, k) => k).filter((k) => toks[k].part === part);
      let j = 0;
      while (j < ks.length) {
        let best = 0, at = -1;
        for (let q = 0; q < spoken.length; q++) {
          let n = 0; while (j + n < ks.length && q + n < spoken.length && keys[ks[j + n]] && tsame(keys[ks[j + n]], spoken[q + n])) n++;
          if (n > best || (n === best && n > 0 && near >= 0 && Math.abs(q - near) < Math.abs(at - near))) { best = n; at = q; }
        }
        if (best >= 2) { for (let n = 0; n < best; n++) src[ks[j + n]] = idx[at + n]; near = at + best; j += best; continue; }
        const k = ks[j];
        if (best === 1 && !FN_WORDS.has(keys[k])) {  // a single content word: its mention closest to the words already matched
          let pick = -1; spoken.forEach((s, q) => { if (tsame(keys[k], s) && (pick < 0 || (near >= 0 && Math.abs(q - near) < Math.abs(pick - near)))) pick = q; });
          if (pick >= 0) { src[k] = idx[pick]; if (near < 0) near = pick; }
        }
        j++;
      }
    }
    return src;
  }
  function buildThumb(data, TH, videoP, measure) {
    const { P, T } = thumbParams(TH, videoP);
    const [W, H] = ASPECTS[P.aspect] || ASPECTS["16:9"], u = Math.min(W, H) / 1080;
    const F = FONTS[P.font] || FONTS.Inter, [wmin, wmax] = F.w;
    const pal = PALETTES[P.palette] || PALETTES.Blush;
    const themes = (data.themes || []).slice(), tcolors = (data.themeColors || []).slice();
    Object.values(P.thEdits || {}).forEach((v) => { if (typeof v === "string" && v && !themes.includes(v)) { themes.push(v); tcolors.push(null); } });
    const tcol = themePalette(pal, themes, tcolors), thOff = new Set(P.thOff || []);
    let neutral = pal.ink;
    for (let k = 0.05; k <= 0.75; k += 0.05) { const c = mix(pal.ink, pal.bg, k); if (contrast(c, pal.bg) >= 3.4) neutral = c; else break; }
    const env = envelope(data);
    const thr = P.emphasis > 0 ? 2.4 - 1.7 * P.emphasis : Infinity;
    const vertical = H > W;
    const box = vertical ? { x0: 60, x1: 888, y0: 288, y1: 1248 } : { x0: W * (1 - P.width) / 2, x1: W * (1 + P.width) / 2, y0: H * 0.08, y1: H * 0.92 };
    if (vertical) { const cx = (box.x0 + box.x1) / 2, hw = ((box.x1 - box.x0) / 2) * clamp(P.width / 0.76, 0.6, 1); box.x0 = cx - hw; box.x1 = cx + hw; }
    const maxW = box.x1 - box.x0, maxH = box.y1 - box.y0;
    const align = P.placement === "block" ? P.align : "left";
    // words of the title and subtitle; a new line in the text forces a line break
    const toks = [];
    for (const [part, txt] of [["t", T.title], ["s", T.subtitle]]) {
      let first = true;
      String(txt || "").split(/\n/).forEach((line, li) => line.split(/\s+/).filter(Boolean).forEach((raw, j) => { toks.push({ part, raw, br: li > 0 && j === 0, first }); first = false; }));
    }
    // a word's edits are kept under its text and occurrence ("myth#0"), so they stay with it when other words change
    const seen = {};
    toks.forEach((t) => { const n = tnorm(t.raw) || t.raw; t.key = n + "#" + (seen[n] = (seen[n] == null ? -1 : seen[n]) + 1); });
    const src = voiceSource(data, toks);
    // glossary terms (one or more words) give a theme to words not heard in the recording
    const termTh = toks.map(() => undefined), keys = toks.map((t) => tnorm(t.raw));
    (data.terms || []).filter((t) => t.st !== "r" && t.th != null).map((t) => ({ seq: String(t.t).split(/\s+/).map(tnorm).filter(Boolean), th: t.th }))
      .sort((a, b) => b.seq.length - a.seq.length).forEach(({ seq, th }) => {
        for (let k = 0; k + seq.length <= toks.length; k++) {
          if (seq.every((s, q) => keys[k + q] && tsame(s, keys[k + q]) && toks[k + q].part === toks[k].part) && termTh.slice(k, k + seq.length).every((x) => x === undefined))
            for (let q = 0; q < seq.length; q++) termTh[k + q] = th;
        }
      });
    const wOf = (a, w) => {
      let x = P.weight + P.weightAmt * (a - 0.55) * (wmax - wmin) * 1.1;
      if (w.emph) x += 140; if (w.quiet) x -= 120; if (w.fn) x -= P.recede * 90;
      return Math.round(clamp(x, wmin, wmax) / 10) * 10;
    };
    const sOf = (a, w) => 1 + P.sizeAmt * (a - 0.55) * 0.6 + (w.emph ? 0.05 : 0) - (w.fn ? P.recede * 0.06 : 0);
    const words = toks.map((t, k) => {
      const d = src[k] != null ? data.words[src[k]] : null, key = keys[k], ed = P.edits[t.key];
      const isFn = d ? !!d.fn : FN_WORDS.has(key);
      const w = { i: k, key: t.key, part: t.part, br: t.br, text: caseOf(t.raw, P.textCase, t.first), src: src[k], at: d ? d.s : null,
        fn: isFn && ed !== "emph" && ed !== "normal", quiet: ed === "quiet",
        emph: ed === "emph" || (ed !== "normal" && ed !== "quiet" && !isFn && !!d && (d.emph || 0) >= thr),
        slope: d ? d.slope || 0 : 0, stretch: d ? d.stretch || 0 : 0, la: (d && d.la) || [], lp: (d && d.lp) || [] };
      w.autoTh = d && d.th != null ? d.th : termTh[k] != null ? termTh[k] : null;
      const te = themeIndex(P.thEdits[t.key], themes);
      w.th = te !== undefined ? te : w.autoTh;
      if (w.th != null) w.fn = false;
      if (w.th != null && thOff.has(themes[w.th])) w.th = null;
      let color = pal.ink;
      if (w.th != null && P.semantic > 0) color = mix(pal.ink, tcol[w.th % tcol.length], P.semantic);
      else if (w.emph && P.semantic <= 0) color = mix(pal.ink, pal.accent, 0.75);
      if (w.fn || w.quiet) color = mix(color, neutral, P.recede || (w.quiet ? 0.8 : 0));
      w.color = color;
      return w;
    });
    // letters at a given title size (S) and subtitle size; the text shrinks until it fits the safe box
    const shape = (St, Ss) => {
      for (const w of words) {
        const S = w.part === "t" ? St : Ss, chars = [...w.text], n = chars.length, m = w.la.length;
        const sp = P.stretch * Math.max(0, clamp(w.stretch, -1, 2.5)) * 0.045 * S;
        let x = 0;
        w.S = S;
        w.chars = chars.map((c, k) => {
          const kk = m ? Math.round((k * (m - 1)) / Math.max(1, n - 1)) : 0;
          const a = m ? w.la[kk] / 255 : 0.55, wt = wOf(a, w), size = S * sOf(a, w), cw = measure(c, P.font, wt, size);
          const ch = { c, x, cw, wt, size, pit: w.lp.length && w.lp[kk] ? (w.lp[kk] - 128) / 8 : null };
          x += cw + sp; return ch;
        });
        w.width = Math.max(0, x - sp);
      }
    };
    const wrap = (ws, space) => {  // balanced lines: the fewest lines that fit, then the narrowest width that keeps that count
      const segs = []; ws.forEach((w) => { if (!segs.length || w.br) segs.push([]); segs[segs.length - 1].push(w); });
      const greedy = (seg, lim) => { const out = []; let L = null;
        for (const w of seg) { if (L && L.width + space + w.width <= lim) { L.words.push(w); L.width += space + w.width; } else { L = { words: [w], width: w.width }; out.push(L); } }
        return out; };
      const lines = [];
      for (const seg of segs) {
        const n = greedy(seg, maxW).length;
        let lo = Math.max(...seg.map((w) => w.width)), hi = maxW;
        for (let it = 0; it < 18 && hi - lo > 1; it++) { const mid = (lo + hi) / 2; if (greedy(seg, mid).length <= n) hi = mid; else lo = mid; }
        lines.push(...greedy(seg, Math.max(hi, lo)));
      }
      return lines;
    };
    const tw = words.filter((w) => w.part === "t"), sw = words.filter((w) => w.part === "s");
    let St = T.tSize * u, Ss = St * T.subRatio, tl = [], sl = [], dims = null;
    for (let it = 0; it < 30; it++) {
      shape(St, Ss);
      const spT = measure(" ", P.font, P.weight, St), spS = measure(" ", P.font, P.weight, Ss);
      tl = tw.length ? wrap(tw, spT) : []; sl = sw.length ? wrap(sw, spS) : [];
      const lhT = St * P.lineHeight, lhS = Ss * Math.max(1.18, P.lineHeight);
      const hT = tl.length ? (tl.length - 1) * lhT + St * 1.04 : 0, hS = sl.length ? (sl.length - 1) * lhS + Ss * 1.04 : 0;
      const gap = tl.length && sl.length ? (T.rule || P.trace > 0 ? St * 0.5 : St * 0.32) : 0;
      dims = { lhT, lhS, hT, hS, gap, spT, spS, h: hT + gap + hS };
      const widest = Math.max(0, ...tl.map((L) => L.width), ...sl.map((L) => L.width));
      if ((widest <= maxW + 0.5 && dims.h <= maxH) || St < 24 * u) break;
      const k = Math.min(maxW / Math.max(widest, 1), maxH / Math.max(dims.h, 1), 0.97);
      St *= Math.max(0.6, k * 0.995); Ss = St * T.subRatio;
    }
    // where the block sits: the same placements as the captions
    let top;
    if (P.placement === "editorial") top = vertical ? box.y0 + maxH * 0.1 : H * clamp(P.position - 0.14, 0.08, 0.6);
    else if (P.placement === "ticker") top = (vertical ? box.y1 : H * 0.88) - dims.h;
    else top = (vertical ? box.y0 + maxH * P.position : H * P.position) - dims.h / 2;
    top = clamp(top, box.y0, Math.max(box.y0, box.y1 - dims.h));
    const lineX = (wd) => (align === "left" ? box.x0 : (box.x0 + box.x1 - wd) / 2);
    const median = (arr) => { const a = arr.filter((v) => v != null).sort((x, y) => x - y); return a.length ? a[Math.floor(a.length / 2)] : null; };
    const ref = median(words.flatMap((w) => w.chars.map((c) => c.pit)));
    const place = (lines, y0, lh, S, space) => lines.forEach((L, li) => {
      let x = lineX(L.width); const base = y0 + S * 0.8 + li * lh; L.base = base;
      L.words.forEach((w) => {
        w.x = x; w.base = base; x += w.width + space;
        const pitchPx = P.lift * w.S * 0.07, pv = w.chars.map((c) => c.pit), n = pv.length, known = pv.map((v, k) => (v == null ? -1 : k)).filter((k) => k >= 0);
        if (ref == null || !known.length) w.chars.forEach((c) => (c.dy = 0));
        else {
          const filled = pv.map((v, k) => { if (v != null) return v; let a = -1, b = -1; for (const q of known) { if (q < k) a = q; if (q > k && b < 0) b = q; }
            if (a < 0) return pv[b]; if (b < 0) return pv[a]; return pv[a] + ((pv[b] - pv[a]) * (k - a)) / (b - a); });
          const sm = filled.map((v, k) => (filled[Math.max(0, k - 1)] + 2 * v + filled[Math.min(n - 1, k + 1)]) / 4);
          const mean = sm.reduce((a, b) => a + b, 0) / n;
          w.chars.forEach((c, k) => { c.dy = -clamp(((mean - ref) + 0.6 * clamp(sm[k] - mean, -3, 3)) * pitchPx, -0.55 * w.S, 0.55 * w.S); });
        }
        w.rot = clamp(P.tilt * w.slope * 0.5, -9, 9);
      });
    });
    place(tl, top, dims.lhT, St, dims.spT);
    const subTop = top + dims.hT + dims.gap;
    place(sl, subTop, dims.lhS, Ss, dims.spS);
    // the divider between title and subtitle; with Melody line it draws the tune of the title where it is spoken
    let rule = null, trace = null;
    if (tl.length && sl.length) {
      const y = top + dims.hT + dims.gap * 0.5, rw = Math.max(60 * u, Math.min(W * 0.065, maxW)), th = Math.max(2, 3 * u);
      const heard = tw.filter((w) => w.src != null).map((w) => data.words[w.src]);
      if (P.trace > 0 && heard.length >= 2) {
        const s0 = Math.min(...heard.map((d) => d.s)), e0 = Math.max(...heard.map((d) => d.e));
        if (e0 - s0 > 0.3 && e0 - s0 < 15) {
          const tw2 = Math.min(maxW, Math.max(...tl.map((L) => L.width)));
          trace = { x: lineX(tw2), w: tw2, y, s0, e0, amp: St * 0.14, th: Math.max(1.5, St * 0.018) };
        }
      }
      if (!trace && T.rule) rule = { x: lineX(rw), y: y - th / 2, w: rw, h: th };
    }
    return { thumb: true, W, H, S: St, Ss, P, T, pal, tcol, neutral, themes, words, lines: tl.concat(sl), box, env, rule, trace, ref,
      heard: words.filter((w) => w.src != null).length, total: words.length };
  }
  /* drawThumb(ctx, scene): ctx scaled so 1 unit = 1 output pixel (multiply for a sharper export). Returns hit boxes of the words. */
  function drawThumb(ctx, sc) {
    const { W, H, P, pal } = sc, boxes = [];
    ctx.save(); ctx.globalAlpha = 1; ctx.fillStyle = pal.bg; ctx.fillRect(0, 0, W, H);
    if (sc.rule) { ctx.fillStyle = sc.neutral; ctx.globalAlpha = 0.9; ctx.fillRect(sc.rule.x, sc.rule.y, sc.rule.w, sc.rule.h); ctx.globalAlpha = 1; }
    if (sc.trace) {
      const t = sc.trace; let pen = false;
      ctx.save(); ctx.globalAlpha = clamp(P.trace, 0, 1); ctx.strokeStyle = sc.neutral; ctx.lineWidth = t.th; ctx.lineJoin = ctx.lineCap = "round"; ctx.beginPath();
      for (let tt = t.s0; tt <= t.e0; tt += 0.02) {
        const v = pitchAt(sc.env, tt); if (v == null || sc.ref == null) { pen = false; continue; }
        const x = t.x + ((tt - t.s0) / (t.e0 - t.s0)) * t.w, y = t.y - clamp(v - sc.ref, -6, 6) * t.amp / 6;
        if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true; }
      }
      ctx.stroke(); ctx.restore();
    }
    ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    for (const w of sc.words) {
      if (w.x == null) continue;
      ctx.save();
      if (w.rot) { const cx = w.x + w.width / 2, cy = w.base - w.S * 0.3; ctx.translate(cx, cy); ctx.rotate((-w.rot * Math.PI) / 180); ctx.translate(-cx, -cy); }
      ctx.fillStyle = w.color; let last = "";
      for (const c of w.chars) {
        const f = `${c.wt} ${c.size.toFixed(1)}px "${P.font}"`; if (f !== last) { ctx.font = f; last = f; }
        ctx.fillText(c.c, w.x + c.x + c.cw / 2, w.base + c.dy);
      }
      ctx.restore();
      boxes.push({ i: w.i, x: w.x, y: w.base - w.S * 0.85, w: w.width, h: w.S * 1.15 });
    }
    ctx.restore();
    return boxes;
  }
  const api = { ASPECTS, FONTS, PALETTES, DEFAULTS, PRESETS, params, buildScene, draw, themeColors, themePalette, themeIndex, mix, contrast, clamp,
    buildThumb, drawThumb, thumbParams, thumbDefaults, THUMB_DEFAULTS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.VC = api;
})(typeof window !== "undefined" ? window : globalThis);
