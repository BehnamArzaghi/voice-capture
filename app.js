/* Voice capture: record on the phone, keep every chunk on the device, upload to a Google Drive folder. */
"use strict";
(() => {
  const CFG = Object.assign({ clientId: "", folderName: "Voice Notes Inbox" }, window.VC_CONFIG || {});
  const SCOPE = "https://www.googleapis.com/auth/drive.file";
  const APP_URL = location.origin + location.pathname.replace(/index\.html$/, "");
  const CHUNK_MS = 4000;                 // each 4 s of audio is written to the phone as it is recorded
  const UPLOAD_CHUNK = CFG.uploadChunk || 5 * 1024 * 1024;  // resumable upload piece (multiple of 256 KiB)
  const PART_LIMIT = CFG.partLimit || 9000000;  // long recordings are also saved as pieces under this size (see "parts")
  const NOSLEEP_MP4 = "data:video/mp4;base64,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";
  const $ = (id) => document.getElementById(id);

  // ---------------------------------------------------------------- settings
  const S = {
    get(k, d) { try { const v = localStorage.getItem("vc." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("vc." + k, JSON.stringify(v)); } catch (e) {} },
    del(k) { try { localStorage.removeItem("vc." + k); } catch (e) {} },
  };
  const conf = () => ({
    clientId: (/\.apps\.googleusercontent\.com$/.test((S.get("clientId", "") || "").trim()) ? S.get("clientId", "").trim() : (CFG.clientId || "").trim()),
    folderName: S.get("folderName", CFG.folderName) || CFG.folderName,
    autoStart: S.get("autoStart", false),
    keepAwake: S.get("keepAwake", true),
    processing: S.get("processing", "raw"),
    quality: S.get("quality", "standard"),
    keepDays: S.get("keepDays", 7),
  });

  // ---------------------------------------------------------------- storage (IndexedDB; audio kept as ArrayBuffers for Safari safety)
  const DB = (() => {
    let p = null;
    const open = () => p || (p = new Promise((res, rej) => {
      const r = indexedDB.open("voice-capture", 1);
      r.onupgradeneeded = () => { const db = r.result; db.createObjectStore("recs", { keyPath: "id" }); db.createObjectStore("chunks", { keyPath: ["rec", "seq"] }); };
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    }));
    const done = (t) => new Promise((res, rej) => { t.oncomplete = () => res(); t.onerror = () => rej(t.error); t.onabort = () => rej(t.error || new Error("aborted")); });
    const val = (r) => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
    const range = (id) => IDBKeyRange.bound([id, 0], [id, Number.MAX_SAFE_INTEGER]);
    return {
      async putRec(m) { const t = (await open()).transaction("recs", "readwrite"); t.objectStore("recs").put(m); await done(t); },
      async getRec(id) { return val((await open()).transaction("recs").objectStore("recs").get(id)); },
      async allRecs() { return val((await open()).transaction("recs").objectStore("recs").getAll()); },
      async putChunk(rec, seq, data) { const t = (await open()).transaction("chunks", "readwrite"); t.objectStore("chunks").put({ rec, seq, data }); await done(t); },
      async chunks(id) { return val((await open()).transaction("chunks").objectStore("chunks").getAll(range(id))); },
      async remove(id) {
        const t = (await open()).transaction(["recs", "chunks"], "readwrite");
        t.objectStore("chunks").delete(range(id)); t.objectStore("recs").delete(id); await done(t);
      },
      async dropAudio(id) { const t = (await open()).transaction("chunks", "readwrite"); t.objectStore("chunks").delete(range(id)); await done(t); },
    };
  })();
  async function assemble(m) {
    const ch = (await DB.chunks(m.id)).sort((a, b) => a.seq - b.seq);
    return new Blob(ch.map((c) => c.data), { type: baseMime(m.mime) });
  }

  // ---------------------------------------------------------------- helpers
  const pad = (n) => String(n).padStart(2, "0");
  const fmtDur = (s) => { s = Math.max(0, Math.round(s || 0)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return (h ? h + ":" + pad(m) : m) + ":" + pad(s % 60); };
  const fmtSize = (b) => (b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1e3)) + " KB");
  const stamp = (t) => { const d = new Date(t); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}.${pad(d.getMinutes())}`; };
  const when = (t) => new Date(t).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const baseMime = (m) => (m || "audio/mp4").split(";")[0];
  const extFor = (m) => ({ "audio/mp4": ".m4a", "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/mpeg": ".mp3" }[baseMime(m)] || ".m4a");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function pickMime() {
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return "";
    for (const t of ["audio/mp4;codecs=mp4a.40.2", "audio/mp4", "audio/webm;codecs=opus", "audio/webm"]) if (MediaRecorder.isTypeSupported(t)) return t;
    return "";
  }
  let noticeAction = null;
  function notice(text, btn, action) {
    $("noticeText").textContent = text; $("notice").classList.add("on");
    noticeAction = action || null; $("noticeBtn").hidden = !btn; $("noticeBtn").textContent = btn || "";
  }
  $("noticeX").onclick = () => $("notice").classList.remove("on");
  $("noticeBtn").onclick = () => { const a = noticeAction; $("notice").classList.remove("on"); if (a) a(); };

  // ---------------------------------------------------------------- keep the screen awake while recording
  const Awake = {
    lock: null, video: null,
    async on() {
      if (!conf().keepAwake) return;
      try { if ("wakeLock" in navigator) { this.lock = await navigator.wakeLock.request("screen"); this.lock.addEventListener("release", () => { this.lock = null; }); return; } } catch (e) {}
      try { // older iOS: a muted, looping, invisible video keeps the screen on
        if (!this.video) { const v = document.createElement("video"); v.muted = true; v.loop = true; v.setAttribute("playsinline", ""); v.setAttribute("muted", ""); v.src = NOSLEEP_MP4; v.style.cssText = "position:fixed;width:1px;height:1px;opacity:0;pointer-events:none"; document.body.appendChild(v); this.video = v; }
        await this.video.play();
      } catch (e) {}
    },
    off() { try { this.lock && this.lock.release(); } catch (e) {} this.lock = null; try { this.video && this.video.pause(); } catch (e) {} },
  };

  // ---------------------------------------------------------------- level meter (optional; recording never depends on it)
  const Meter = {
    ctx: null, raf: 0,
    start(stream) {
      try {
        const C = window.AudioContext || window.webkitAudioContext; if (!C) return;
        this.ctx = new C(); if (this.ctx.state === "suspended") this.ctx.resume().catch(() => {});
        const an = this.ctx.createAnalyser(); an.fftSize = 1024; this.ctx.createMediaStreamSource(stream).connect(an);
        const buf = new Float32Array(an.fftSize); let lvl = 0;
        const tick = () => {
          an.getFloatTimeDomainData(buf); let s = 0; for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
          const db = 20 * Math.log10(Math.sqrt(s / buf.length) + 1e-6), v = Math.min(1, Math.max(0, (db + 60) / 50));
          lvl = v > lvl ? v : lvl * 0.9 + v * 0.1; $("ring").style.transform = `scale(${1 + lvl * 0.16})`;
          this.raf = requestAnimationFrame(tick);
        };
        tick();
      } catch (e) { this.stop(); }
    },
    stop() { cancelAnimationFrame(this.raf); this.raf = 0; $("ring").style.transform = ""; try { this.ctx && this.ctx.close(); } catch (e) {} this.ctx = null; },
  };

  // ---------------------------------------------------------------- recording
  let cur = null, tickTimer = 0;
  async function startRecording() {
    if (cur) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) { notice("This browser can't record audio. On iPhone, open the app from the Home Screen or in Safari."); return; }
    const c = conf(), voice = c.processing === "voice";
    $("rec").disabled = true;
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: voice, noiseSuppression: voice, autoGainControl: voice, channelCount: 1 } });
    } catch (e) {
      $("rec").disabled = false;
      notice(e && e.name === "NotAllowedError" ? "Microphone access is off. Allow it when asked, or in Settings › Safari › Microphone." : "The microphone couldn't start: " + (e && e.message || e));
      return;
    }
    try { await begin(stream, c); } catch (e) {
      stream.getTracks().forEach((t) => t.stop()); cur = null; $("rec").disabled = false; Awake.off(); Meter.stop();
      notice("Recording couldn't start: " + (e && e.message || e)); render();
    }
  }
  async function begin(stream, c) {
    const mime = pickMime();
    let mr;
    try { mr = new MediaRecorder(stream, Object.assign(mime ? { mimeType: mime } : {}, { audioBitsPerSecond: c.quality === "compact" ? 64000 : 128000 })); }
    catch (e) { mr = new MediaRecorder(stream); }
    const startedAt = Date.now(), id = "r" + startedAt.toString(36) + Math.random().toString(36).slice(2, 6);
    const m = { id, startedAt, mime: mr.mimeType || mime || "audio/mp4", status: "recording", duration: 0, size: 0, chunks: 0, name: stamp(startedAt) + " Voice note", processing: c.processing };
    await DB.putRec(m);
    const r = { id, m, mr, stream, startedAt, seq: 0, chain: Promise.resolve(), reason: "stopped", failed: false };
    cur = r;
    mr.ondataavailable = (ev) => {
      if (!ev.data || !ev.data.size) return;
      const seq = r.seq++, blob = ev.data;
      r.chain = r.chain.then(async () => {
        const buf = await blob.arrayBuffer();
        await DB.putChunk(id, seq, buf);
        m.size += buf.byteLength; m.chunks = seq + 1; m.duration = (Date.now() - startedAt) / 1000;
        await DB.putRec(m);
      }).catch((e) => { r.failed = true; notice("Couldn't write audio to the phone's storage: " + (e && e.message || e)); });
    };
    mr.onstop = () => finish(r);
    mr.onerror = (e) => { r.reason = "error"; try { mr.state !== "inactive" && mr.stop(); } catch (x) { finish(r); } };
    const track = stream.getAudioTracks()[0];
    if (track) track.addEventListener("ended", () => stopRecording("interrupted"));
    mr.start(CHUNK_MS);
    Awake.on(); Meter.start(stream);
    $("rec").disabled = false;
    render(); tickTimer = setInterval(tickUI, 250); tickUI();
  }
  function stopRecording(reason) {
    const r = cur; if (!r || r.stopping) return;
    r.stopping = true; r.reason = reason || "stopped";
    try { if (r.mr.state !== "inactive") r.mr.stop(); else finish(r); } catch (e) { finish(r); }
  }
  async function finish(r) {
    if (r.finished) return; r.finished = true;
    await r.chain;
    r.stream.getTracks().forEach((t) => t.stop());
    clearInterval(tickTimer); Meter.stop(); Awake.off();
    const m = r.m;
    m.duration = (Date.now() - r.startedAt) / 1000; m.endedAt = Date.now(); m.stopReason = r.reason;
    if (!m.chunks) { await DB.remove(m.id); cur = null; render(); notice("Nothing was recorded."); return; }
    m.status = "saved"; await DB.putRec(m);
    cur = null; render();
    if (r.reason === "interrupted") notice(`iOS stopped the microphone (a call, Siri or another app). ${fmtDur(m.duration)} was saved.`, "Record again", startRecording);
    else if (r.reason === "error") notice(`The recorder hit an error; ${fmtDur(m.duration)} was saved.`);
    Queue.kick();
  }
  function tickUI() {
    if (!cur) return;
    $("timer").textContent = fmtDur((Date.now() - cur.startedAt) / 1000);
    $("sub").textContent = cur.m.chunks ? `Recording · ${fmtSize(cur.m.size)} saved on this phone so far` : "Recording…";
  }
  // a recording left unfinished (app closed, phone restarted) is finished from the chunks already on the phone
  async function recover() {
    for (const m of await DB.allRecs()) {
      if (m.status !== "recording" || (cur && cur.id === m.id)) continue;
      const ch = await DB.chunks(m.id);
      if (!ch.length) { await DB.remove(m.id); continue; }
      m.size = ch.reduce((a, c) => a + c.data.byteLength, 0); m.chunks = ch.length;
      m.duration = Math.max(m.duration || 0, ch.length * CHUNK_MS / 1000 - CHUNK_MS / 2000);
      m.status = "saved"; m.recovered = true; await DB.putRec(m);
      notice(`Recovered an unfinished recording (${fmtDur(m.duration)}) from when the app closed.`);
    }
  }

  // ---------------------------------------------------------------- Google sign-in (OAuth 2.0 for client-side web apps, redirect flow)
  class AuthError extends Error {}
  const Auth = {
    token() { const t = S.get("token", null); return t && t.exp > Date.now() + 90000 ? t.value : null; },
    signIn(silent) {
      const cid = conf().clientId;
      if (!cid) { openSettings(); notice("Paste your Google client ID in Settings first."); return; }
      if (cur) return; // never leave the page while recording
      const state = Math.random().toString(36).slice(2) + Date.now().toString(36);
      S.set("oauth", { state, silent: !!silent, at: Date.now() });
      const p = new URLSearchParams({ client_id: cid, redirect_uri: APP_URL, response_type: "token", scope: SCOPE, include_granted_scopes: "true", state });
      if (silent) p.set("prompt", "none");
      const em = S.get("email", ""); if (em) p.set("login_hint", em);
      location.assign("https://accounts.google.com/o/oauth2/v2/auth?" + p.toString());
    },
    fromRedirect() {
      if (!location.hash || location.hash.length < 2) return null;
      const h = new URLSearchParams(location.hash.slice(1));
      if (!h.has("access_token") && !h.has("error")) return null;
      history.replaceState(null, "", APP_URL + location.search);
      const saved = S.get("oauth", null); S.del("oauth");
      if (!saved || saved.state !== h.get("state")) return { error: "state_mismatch" };
      if (h.get("error")) return { error: h.get("error"), silent: saved.silent };
      if (!(h.get("scope") || SCOPE).includes("drive.file")) return { error: "scope_denied" };
      S.set("token", { value: h.get("access_token"), exp: Date.now() + (+h.get("expires_in") || 3600) * 1000 });
      return { ok: true };
    },
    signOut() {
      const t = S.get("token", null);
      if (t) fetch("https://oauth2.googleapis.com/revoke?token=" + encodeURIComponent(t.value), { method: "POST", mode: "no-cors" }).catch(() => {});
      ["token", "email", "folderId", "folderFor"].forEach(S.del); render();
    },
  };
  async function api(method, url, opts = {}) {
    const tok = Auth.token(); if (!tok) throw new AuthError("signed out");
    const r = await fetch(url, { method, headers: Object.assign({ Authorization: "Bearer " + tok }, opts.headers || {}), body: opts.body });
    if (r.status === 401) { S.del("token"); throw new AuthError("expired"); }
    return r;
  }
  async function why(r, what) {
    let msg = "", reason = "";
    try { const j = await r.clone().json(); msg = (j.error && j.error.message) || ""; reason = (j.error && j.error.errors && j.error.errors[0] && j.error.errors[0].reason) || (j.error && j.error.status) || ""; } catch (e) {}
    if (/accessNotConfigured|SERVICE_DISABLED|has not been used|is disabled/i.test(reason + " " + msg)) return "Google Drive API is off in your Google Cloud project; turn it on there";
    if (/insufficient|PERMISSION_DENIED.*scope|ACCESS_TOKEN_SCOPE/i.test(reason + " " + msg)) return "Drive permission wasn't granted; disconnect and reconnect, ticking the Drive box";
    if (/domain|admin|policy/i.test(reason + " " + msg)) return "this Google account's administrator blocks the app; try a personal account";
    return `${what} ${r.status}${msg ? ": " + msg.slice(0, 120) : ""}`;
  }
  async function fetchEmail() {
    try { const r = await api("GET", "https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)"); if (r.ok) { const j = await r.json(); S.set("email", j.user && j.user.emailAddress || ""); } } catch (e) {}
  }
  async function ensureFolder() {
    const name = conf().folderName;
    const id = S.get("folderId", null);
    if (id && S.get("folderFor", "") === name) {
      const r = await api("GET", `https://www.googleapis.com/drive/v3/files/${id}?fields=id,trashed`);
      if (r.ok && !(await r.json()).trashed) return id;
    }
    const q = `name = '${name.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false`;
    const r = await api("GET", "https://www.googleapis.com/drive/v3/files?spaces=drive&pageSize=10&fields=files(id,name)&q=" + encodeURIComponent(q));
    if (!r.ok) throw new Error(await why(r, "folder lookup"));
    let fid = ((await r.json()).files || [])[0];
    fid = fid && fid.id;
    if (!fid) {
      const c = await api("POST", "https://www.googleapis.com/drive/v3/files?fields=id", { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, mimeType: "application/vnd.google-apps.folder" }) });
      if (!c.ok) throw new Error(await why(c, "folder create"));
      fid = (await c.json()).id;
    }
    S.set("folderId", fid); S.set("folderFor", name);
    return fid;
  }

  // ---------------------------------------------------------------- uploads (Drive resumable protocol; survives drops and restarts)
  const progress = {};
  function xhr(method, url, headers, body, onProgress) {
    return new Promise((res, rej) => {
      const x = new XMLHttpRequest(); x.open(method, url);
      for (const k in headers) x.setRequestHeader(k, headers[k]);
      if (onProgress && x.upload) x.upload.onprogress = (e) => onProgress(e.loaded);
      x.onload = () => res(x); x.onerror = () => rej(new Error("network")); x.ontimeout = () => rej(new Error("timeout"));
      x.timeout = 120000; x.send(body == null ? null : body);
    });
  }
  const rangeEnd = (h) => { const m = /bytes=0-(\d+)/.exec(h || ""); return m ? +m[1] + 1 : 0; };
  const hex = (b) => Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, "0")).join("");
  // One Drive resumable upload. `st` is kept inside the recording's record, so a dropped connection or a
  // closed app carries on from where Drive says it stopped. `meta` is only called when a new session is needed.
  async function resumable(m, st, blob, meta, onProgress) {
    const total = blob.size;
    const auth = () => { const t = Auth.token(); return t ? { Authorization: "Bearer " + t } : {}; };
    const result = (x) => { let j = {}; try { j = JSON.parse(x.responseText || "{}"); } catch (e) {} return j; };
    const expired = async () => { delete st.session; await DB.putRec(m); return new Error("upload expired; starting over"); };
    if (!st.session || st.total !== total) {
      const r = await api("POST", "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name", {
        headers: { "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": blob.type || "application/octet-stream", "X-Upload-Content-Length": String(total) }, body: JSON.stringify(await meta()),
      });
      if (!r.ok) throw new Error(await why(r, "couldn't start upload"));
      const loc = r.headers.get("Location"); if (!loc) throw new Error("no upload address returned");
      st.session = loc; st.total = total; await DB.putRec(m);
    }
    // ask Drive how much it already has (resumes after a drop or app restart)
    let off = 0;
    const q = await xhr("PUT", st.session, Object.assign({ "Content-Range": `bytes */${total}` }, auth()), null);
    if (q.status === 200 || q.status === 201) return result(q);
    if (q.status === 308) off = rangeEnd(q.getResponseHeader("Range"));
    else if (q.status === 404 || q.status === 410) throw await expired();
    else if (q.status === 401) { S.del("token"); throw new AuthError("expired"); }
    while (off < total) {
      const end = Math.min(off + UPLOAD_CHUNK, total), from = off;
      const r = await xhr("PUT", st.session, Object.assign({ "Content-Range": `bytes ${off}-${end - 1}/${total}` }, auth()), blob.slice(off, end), (n) => onProgress(from + n));
      if (r.status === 308) { off = rangeEnd(r.getResponseHeader("Range")); onProgress(off); continue; }
      if (r.status === 200 || r.status === 201) return result(r);
      if (r.status === 404 || r.status === 410) throw await expired();
      if (r.status === 401) { S.del("token"); throw new AuthError("expired"); }
      throw new Error("upload failed (" + r.status + ")");
    }
    throw new Error("upload ended early; will check with Drive and continue");
  }
  async function uploadOne(m) {
    if (m.session) { m.up = { session: m.session, total: m.sessionTotal }; delete m.session; delete m.sessionTotal; } // begun by an earlier version
    const blob = await assemble(m), total = blob.size;
    if (!total) throw new Error("empty recording");
    const show = (f) => { progress[m.id] = f; paintProgress(m.id); };
    if (m.status === "saved") {
      m.up = m.up || {};
      const j = await resumable(m, m.up, blob, async () => ({
        name: m.name + extFor(m.mime), parents: [await ensureFolder()], mimeType: baseMime(m.mime),
        description: `Recorded ${new Date(m.startedAt).toString()} · ${fmtDur(m.duration)} · Voice capture`,
        appProperties: { app: "voice-capture", recId: m.id, recordedAt: new Date(m.startedAt).toISOString(), durationSec: String(Math.round(m.duration)), processing: m.processing || "raw" },
      }), (n) => show(n / total));
      m.driveId = j.id || m.driveId; delete m.up;
      if (total <= PART_LIMIT) return uploaded(m);
      m.status = "parts"; await DB.putRec(m); show(0); render();
    }
    if (m.status === "parts") return uploadParts(m, blob, show);
  }

  // ---------------------------------------------------------------- parts: a long recording is also saved as pieces under 9 MB,
  // because Claude's Google Drive connector downloads at most 10 MB per file.
  // iPhone recordings are fragmented MP4: a header (ftyp + moov), then one fragment (moof + mdat) per ~4 s.
  // Each piece is the header plus a run of whole fragments, so every piece plays on its own, and the original
  // is piece 1 followed by every later piece without its header, byte for byte (SHA-256 recorded to check).
  function splitPlan(buf, limit) {
    const v = new DataView(buf), n = buf.byteLength, boxes = [];
    for (let off = 0; off < n; ) {
      if (off + 8 > n) return null;
      let size = v.getUint32(off);
      const type = String.fromCharCode(v.getUint8(off + 4), v.getUint8(off + 5), v.getUint8(off + 6), v.getUint8(off + 7));
      if (size === 1) { if (off + 16 > n) return null; size = Number(v.getBigUint64(off + 8)); } else if (size === 0) size = n - off;
      if (size < 8 || off + size > n) return null;
      boxes.push({ type, a: off, b: off + size }); off += size;
    }
    const first = boxes.findIndex((x) => x.type === "moof");
    if (first < 1) return null;
    const header = boxes[first].a, room = limit - header, frags = [];
    for (const x of boxes.slice(first)) { if (x.type === "moof") frags.push([x.a, x.b]); else frags[frags.length - 1][1] = x.b; }
    if (room <= 0 || frags.some(([a, b]) => b - a > room)) return null;
    const ranges = []; let s = frags[0][0], e = s;
    for (const [a, b] of frags) { if (b - s > room) { ranges.push([s, e]); s = a; } e = b; }
    ranges.push([s, e]);
    return { header, ranges };
  }
  async function ensurePartsFolder() {
    const parent = await ensureFolder(), id = S.get("partsFolderId", null);
    if (id && S.get("partsFor", "") === parent) {
      const r = await api("GET", `https://www.googleapis.com/drive/v3/files/${id}?fields=id,trashed`);
      if (r.ok && !(await r.json()).trashed) return id;
    }
    const q = `name = 'Parts' and '${parent}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false`;
    const r = await api("GET", "https://www.googleapis.com/drive/v3/files?spaces=drive&pageSize=10&fields=files(id,name)&q=" + encodeURIComponent(q));
    if (!r.ok) throw new Error(await why(r, "parts folder lookup"));
    let fid = ((await r.json()).files || [])[0]; fid = fid && fid.id;
    if (!fid) {
      const c = await api("POST", "https://www.googleapis.com/drive/v3/files?fields=id", { headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        name: "Parts", mimeType: "application/vnd.google-apps.folder", parents: [parent],
        description: "Long recordings cut into pieces under 9 MB for processing. The full recordings are in the folder above." }) });
      if (!c.ok) throw new Error(await why(c, "parts folder create"));
      fid = (await c.json()).id;
    }
    S.set("partsFolderId", fid); S.set("partsFor", parent);
    return fid;
  }
  const partName = (m, i, n) => `${m.name} · part ${i + 1} of ${n}${extFor(m.mime)}`;
  async function uploadParts(m, blob, show) {
    if (!m.parts) {
      const buf = await blob.arrayBuffer(), plan = splitPlan(buf, PART_LIMIT);
      if (!plan) { m.partsSkipped = "not a fragmented MP4"; return uploaded(m); }
      m.parts = { n: plan.ranges.length, header: plan.header, ranges: plan.ranges, sha256: hex(await crypto.subtle.digest("SHA-256", buf)), ids: [], up: {} };
      await DB.putRec(m);
    }
    const P = m.parts, mime = baseMime(m.mime);
    const sizes = P.ranges.map(([a, b]) => P.header + b - a), all = sizes.reduce((x, y) => x + y, 0);
    for (let i = P.ids.length; i < P.n; i++) {
      const [a, b] = P.ranges[i], before = sizes.slice(0, i).reduce((x, y) => x + y, 0);
      const piece = new Blob([blob.slice(0, P.header), blob.slice(a, b)], { type: mime });
      const j = await resumable(m, P.up, piece, async () => ({
        name: partName(m, i, P.n), parents: [await ensurePartsFolder()], mimeType: mime,
        description: `Part ${i + 1} of ${P.n} of “${m.name}”${m.driveId ? ` (Drive file ${m.driveId})` : ""}. Each part plays on its own. The original is part 1 followed by each later part without its first ${P.header} bytes. SHA-256 of the original: ${P.sha256}`,
        appProperties: { app: "voice-capture", recId: m.id, partOf: m.driveId || "", part: String(i + 1), parts: String(P.n), headerBytes: String(P.header), sha256: P.sha256 },
      }), (k) => show((before + k) / all));
      P.ids.push(j.id || ""); P.up = {}; await DB.putRec(m);
    }
    return uploaded(m);
  }
  async function uploaded(m) {
    m.status = "uploaded"; m.uploadedAt = Date.now();
    ["up", "lastError", "tries", "retryAt"].forEach((k) => delete m[k]);
    if (m.parts) delete m.parts.up;
    await DB.putRec(m); delete progress[m.id];
  }
  const Queue = {
    running: false, needAuth: false, timer: 0,
    async kick() {
      if (this.running || cur) return;
      this.running = true;
      try {
        const waiting = (await DB.allRecs()).filter((m) => m.status === "saved" || m.status === "parts").sort((a, b) => a.startedAt - b.startedAt);
        if (!waiting.length) { this.needAuth = false; return; }
        if (!navigator.onLine) return;
        if (!Auth.token()) { this.needAuth = true; maybeSilentSignIn(); return; }
        this.needAuth = false;
        if (!S.get("email", "")) await fetchEmail();
        for (const m of waiting) {
          if (cur) break;
          if (m.retryAt && m.retryAt > Date.now()) continue;
          progress[m.id] = progress[m.id] || 0; render();
          try { await uploadOne(m); }
          catch (e) {
            delete progress[m.id];
            if (e instanceof AuthError) { this.needAuth = true; maybeSilentSignIn(); break; }
            m.tries = (m.tries || 0) + 1; m.lastError = String(e && e.message || e); m.retryAt = Date.now() + Math.min(300000, 15000 * m.tries);
            await DB.putRec(m);
          }
          render();
        }
      } finally { this.running = false; render(); }
    },
  };
  function maybeSilentSignIn() {
    // one quiet round-trip to Google to renew the 1-hour access token; never while recording; at most every 10 minutes
    if (cur || document.visibilityState !== "visible" || !conf().clientId || !S.get("email", "")) return;
    const last = S.get("silentAt", 0); if (Date.now() - last < 600000) return;
    S.set("silentAt", Date.now()); Auth.signIn(true);
  }
  setInterval(() => { if (document.visibilityState === "visible") Queue.kick(); }, 20000);
  window.addEventListener("online", () => Queue.kick());

  // ---------------------------------------------------------------- housekeeping: free phone space for recordings already in Drive
  async function cleanup() {
    const days = conf().keepDays; if (days < 0) return;
    for (const m of await DB.allRecs()) if (m.status === "uploaded" && !m.audioGone && Date.now() - (m.uploadedAt || 0) > days * 864e5) { await DB.dropAudio(m.id); m.audioGone = true; await DB.putRec(m); }
  }

  // ---------------------------------------------------------------- UI
  async function render() {
    const recording = !!cur;
    document.body.classList.toggle("recording", recording);
    $("rec").setAttribute("aria-label", recording ? "Stop and save" : "Start recording");
    const t = $("timer");
    if (!recording) { t.className = "timer idle"; t.textContent = "Tap to record"; }
    else t.className = "timer";
    const signed = !!Auth.token(), email = S.get("email", "");
    $("acct").className = "chip " + (signed ? "ok" : "off");
    $("acct").textContent = signed ? (email || "Google Drive") : (email ? "Sign-in needed" : "Not connected");
    const recs = (await DB.allRecs()).filter((m) => m.status !== "recording").sort((a, b) => b.startedAt - a.startedAt);
    const waiting = recs.filter((m) => m.status === "saved" || m.status === "parts").length, onlyParts = waiting && !recs.some((m) => m.status === "saved");
    if (!recording) {
      $("sub").textContent = onlyParts && !Queue.needAuth && navigator.onLine ? `In “${conf().folderName}” · sending pieces for processing` : waiting ? (Queue.needAuth ? `${waiting} waiting · sign in to Google to upload` : !navigator.onLine ? `${waiting} waiting · will upload when back online` : `${waiting} uploading to “${conf().folderName}”`)
        : recs.length ? `Everything is in “${conf().folderName}”.` : "Recordings are kept on this phone until they reach Google Drive.";
    }
    $("syncBtn").hidden = !waiting || recording;
    $("syncBtn").textContent = Queue.needAuth ? "Sign in to upload" : "Upload now";
    const list = $("list");
    if (!recs.length) { list.innerHTML = `<div class="empty">No recordings yet.</div>`; return; }
    list.innerHTML = recs.slice(0, 60).map((m) => {
      const up = m.status === "uploaded", parts = m.status === "parts", busy = progress[m.id] != null, P = m.parts;
      const badge = up ? `<span class="badge b-up">In Drive</span>` : busy ? `<span class="badge b-go">${parts ? "Sending parts" : "Uploading"}</span>` : m.lastError ? `<span class="badge b-err">Will retry</span>` : `<span class="badge b-wait">${parts ? "Parts waiting" : "On phone"}</span>`;
      const partsNote = parts && P ? ` · part ${Math.min(P.ids.length + 1, P.n)} of ${P.n}` : parts ? " · splitting into parts" : up && P ? ` · ${P.n} parts` : "";
      const err = !up && m.lastError ? ` · ${esc(m.lastError)}` : "";
      return `<div class="item" data-id="${m.id}"><div class="top"><div class="name">${esc(m.name)}</div>${badge}</div>
        <div class="meta">${when(m.startedAt)} · ${fmtDur(m.duration)} · ${fmtSize(m.size)}${m.recovered ? " · recovered" : ""}${partsNote}${err}</div>
        <div class="bar" style="display:${busy ? "block" : "none"}"><i style="width:${Math.round((progress[m.id] || 0) * 100)}%"></i></div>
        <div class="acts">${m.audioGone ? "" : `<button data-a="play">Play</button>`}<button data-a="rename">Rename</button>${(up || parts) && m.driveId ? `<a href="https://drive.google.com/file/d/${m.driveId}/view" target="_blank" rel="noopener">Open in Drive</a>` : ""}<button data-a="delete">${up || parts ? "Remove from phone" : "Delete"}</button></div></div>`;
    }).join("");
  }
  function paintProgress(id) { const el = document.querySelector(`.item[data-id="${id}"] .bar i`); if (el) el.style.width = Math.round((progress[id] || 0) * 100) + "%"; }
  $("list").addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-a]"); if (!b) return;
    const id = b.closest(".item").dataset.id, m = await DB.getRec(id); if (!m) return;
    if (b.dataset.a === "play") {
      const item = b.closest(".item"); let a = item.querySelector("audio");
      if (!a) { a = document.createElement("audio"); a.controls = true; a.src = URL.createObjectURL(await assemble(m)); item.appendChild(a); }
      a.play().catch(() => {});
    } else if (b.dataset.a === "rename") {
      const name = prompt("Name this recording", m.name); if (!name || name.trim() === m.name) return;
      m.name = name.trim(); await DB.putRec(m);
      if (m.driveId) {
        const named = [[m.driveId, m.name + extFor(m.mime)]].concat(((m.parts && m.parts.ids) || []).map((pid, i) => [pid, partName(m, i, m.parts.n)]));
        try { for (const [fid, nm] of named) if (fid) await api("PATCH", `https://www.googleapis.com/drive/v3/files/${fid}?fields=id`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: nm }) }); }
        catch (x) { notice("Renamed on the phone; the Drive name didn't update (sign in and rename again)."); }
      }
      render();
    } else if (b.dataset.a === "delete") {
      if (m.status === "parts" && !confirm("The full recording is in Drive, but its pieces for processing haven't all uploaded. Remove it from the phone anyway?")) return;
      if (m.status === "saved" && !confirm("This recording hasn't reached Google Drive yet. Delete it for good?")) return;
      if (m.status === "uploaded") { await DB.dropAudio(m.id); await DB.remove(m.id); } else await DB.remove(m.id);
      render();
    }
  });
  $("rec").addEventListener("click", () => (cur ? stopRecording("stopped") : startRecording()));
  $("syncBtn").addEventListener("click", () => { if (Queue.needAuth) Auth.signIn(false); else { recsClearRetry().then(() => Queue.kick()); } });
  async function recsClearRetry() { for (const m of await DB.allRecs()) if ((m.status === "saved" || m.status === "parts") && m.retryAt) { m.retryAt = 0; await DB.putRec(m); } }
  $("acct").addEventListener("click", () => openSettings());
  $("gear").addEventListener("click", () => openSettings());
  $("sheetBg").addEventListener("click", closeSheet);
  window.addEventListener("beforeunload", (e) => { if (cur) { e.preventDefault(); e.returnValue = ""; } });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (cur) {
      Awake.on();
      const tr = cur.stream.getAudioTracks()[0];
      if (cur.mr.state === "inactive" || (tr && tr.readyState === "ended")) stopRecording("interrupted");
    } else Queue.kick();
  });

  // ---------------------------------------------------------------- settings sheet
  function closeSheet() { $("sheet").classList.remove("on"); $("sheetBg").classList.remove("on"); }
  function seg(key, opts, value) { return `<div class="seg" data-k="${key}">${opts.map(([v, l]) => `<button data-v="${esc(JSON.stringify(v))}" class="${JSON.stringify(v) === JSON.stringify(value) ? "on" : ""}">${l}</button>`).join("")}</div>`; }
  async function openSettings() {
    const c = conf(), signed = !!Auth.token(), email = S.get("email", "");
    let storage = "";
    try { const e = await navigator.storage.estimate(); storage = `Using ${fmtSize(e.usage || 0)} of this phone's storage for recordings.`; } catch (e) {}
    $("sheetBody").innerHTML = `<h3>Settings</h3>
      <div class="field"><label>Google Drive</label>
        <div class="help" style="margin:0 0 8px">${signed ? `Connected${email ? " as " + esc(email) : ""}.` : email ? `Signed out of ${esc(email)} (sign-ins last an hour; the app renews them quietly).` : "Not connected."}</div>
        <button class="btn ${signed ? "" : "primary"}" id="sAuth">${signed ? "Disconnect" : "Connect Google Drive"}</button></div>
      <div class="field"><label for="sFolder">Drive folder</label><input type="text" id="sFolder" value="${esc(c.folderName)}" autocapitalize="words">
        <div class="help">Created in your Drive the first time something uploads.</div></div>
      <div class="field"><label>Start recording when the app opens</label>${seg("autoStart", [[false, "Off"], [true, "On"]], c.autoStart)}
        <div class="help">One tap on the Home Screen icon starts a recording.</div></div>
      <div class="field"><label>Keep the screen on while recording</label>${seg("keepAwake", [[true, "On"], [false, "Off"]], c.keepAwake)}
        <div class="help">iPhone usually pauses web apps when the screen locks, which would stop the recording, so leave this on.</div></div>
      <div class="field"><label>Microphone</label>${seg("processing", [["raw", "Raw"], ["voice", "Phone voice processing"]], c.processing)}
        <div class="help">Raw keeps the full sound for later clean-up. Voice processing applies the phone's call-style noise and echo reduction.</div></div>
      <div class="field"><label>Quality</label>${seg("quality", [["standard", "Standard"], ["compact", "Smaller files"]], c.quality)}</div>
      <div class="field"><label>Keep recordings on the phone after upload</label>${seg("keepDays", [[1, "1 day"], [7, "7 days"], [30, "30 days"], [-1, "Always"]], c.keepDays)}</div>
      <div class="field"><label for="sCid">Google client ID</label><input type="text" id="sCid" value="${esc(c.clientId)}" placeholder="….apps.googleusercontent.com" autocapitalize="off" autocorrect="off" spellcheck="false"></div>
      <button class="btn primary" id="sDone">Done</button>
      <div class="small">${esc(storage)} Recordings are written to the phone every few seconds while you record, so a crash or a closed app loses at most the last few seconds.</div>`;
    $("sheet").classList.add("on"); $("sheetBg").classList.add("on");
    $("sheetBody").querySelectorAll(".seg").forEach((g) => g.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      S.set(g.dataset.k, JSON.parse(b.dataset.v)); g.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    }));
    const save = () => {
      const f = $("sFolder").value.trim(); if (f && f !== c.folderName) { S.set("folderName", f); S.del("folderId"); }
      const id = $("sCid").value.trim(); if (id !== c.clientId) S.set("clientId", id);
    };
    $("sAuth").onclick = () => { save(); if (signed) { Auth.signOut(); openSettings(); } else Auth.signIn(false); };
    $("sDone").onclick = () => { save(); closeSheet(); render(); Queue.kick(); };
  }

  // ---------------------------------------------------------------- start
  (async () => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
    try { navigator.storage && navigator.storage.persist && navigator.storage.persist(); } catch (e) {}
    const back = Auth.fromRedirect();
    if (back && back.ok) { await fetchEmail(); S.del("silentAt"); }
    else if (back && back.error && !back.silent) notice(back.error === "access_denied" ? "Google access wasn't granted." : "Google sign-in didn't finish (" + back.error + ").");
    await recover();
    await cleanup();
    await render();
    const wantRecord = !back && (new URLSearchParams(location.search).has("record") || conf().autoStart);
    if (wantRecord) startRecording();
    else Queue.kick();
  })();
  window.__vc = { DB, Queue, Auth, conf, S, startRecording, stopRecording, cur: () => cur };
})();
