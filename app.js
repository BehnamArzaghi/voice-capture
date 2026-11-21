/* Voice capture: record on the phone, keep every chunk on the device, upload to a Google Drive folder. */
"use strict";
(() => {
  const CFG = Object.assign({ clientId: "", folderName: "Voice Notes Inbox" }, window.VC_CONFIG || {});
  const SCOPE = "https://www.googleapis.com/auth/drive.file";
  const APP_URL = location.origin + location.pathname.replace(/index\.html$/, "");
  const CHUNK_MS = 4000;                 // each 4 s of audio is written to the phone as it is recorded
  const UPLOAD_CHUNK = CFG.uploadChunk || 5 * 1024 * 1024;  // resumable upload piece (multiple of 256 KiB)
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
    if (!r.ok) throw new Error("folder lookup " + r.status);
    let fid = ((await r.json()).files || [])[0];
    fid = fid && fid.id;
    if (!fid) {
      const c = await api("POST", "https://www.googleapis.com/drive/v3/files?fields=id", { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, mimeType: "application/vnd.google-apps.folder" }) });
      if (!c.ok) throw new Error("folder create " + c.status);
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
  async function uploadOne(m) {
    const blob = await assemble(m), total = blob.size;
    if (!total) throw new Error("empty recording");
    const auth = () => { const t = Auth.token(); return t ? { Authorization: "Bearer " + t } : {}; };
    if (!m.session || m.sessionTotal !== total) {
      const folder = await ensureFolder();
      const meta = {
        name: m.name + extFor(m.mime), parents: [folder], mimeType: baseMime(m.mime),
        description: `Recorded ${new Date(m.startedAt).toString()} · ${fmtDur(m.duration)} · Voice capture`,
        appProperties: { app: "voice-capture", recId: m.id, recordedAt: new Date(m.startedAt).toISOString(), durationSec: String(Math.round(m.duration)), processing: m.processing || "raw" },
      };
      const r = await api("POST", "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name", {
        headers: { "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": baseMime(m.mime), "X-Upload-Content-Length": String(total) }, body: JSON.stringify(meta),
      });
      if (!r.ok) throw new Error("couldn't start upload (" + r.status + ")");
      const loc = r.headers.get("Location"); if (!loc) throw new Error("no upload address returned");
      m.session = loc; m.sessionTotal = total; await DB.putRec(m);
    }
    // ask Drive how much it already has (resumes after a drop or app restart)
    let off = 0;
    const q = await xhr("PUT", m.session, Object.assign({ "Content-Range": `bytes */${total}` }, auth()), null);
    if (q.status === 200 || q.status === 201) return complete(m, q);
    if (q.status === 308) off = rangeEnd(q.getResponseHeader("Range"));
    else if (q.status === 404 || q.status === 410) { delete m.session; await DB.putRec(m); throw new Error("upload expired; starting over"); }
    else if (q.status === 401) { S.del("token"); throw new AuthError("expired"); }
    while (off < total) {
      const end = Math.min(off + UPLOAD_CHUNK, total);
      const r = await xhr("PUT", m.session, Object.assign({ "Content-Range": `bytes ${off}-${end - 1}/${total}` }, auth()), blob.slice(off, end),
        (n) => { progress[m.id] = (off + n) / total; paintProgress(m.id); });
      if (r.status === 308) { off = rangeEnd(r.getResponseHeader("Range")); progress[m.id] = off / total; paintProgress(m.id); continue; }
      if (r.status === 200 || r.status === 201) return complete(m, r);
      if (r.status === 404 || r.status === 410) { delete m.session; await DB.putRec(m); throw new Error("upload expired; starting over"); }
      if (r.status === 401) { S.del("token"); throw new AuthError("expired"); }
      throw new Error("upload failed (" + r.status + ")");
    }
  }
  async function complete(m, x) {
    let j = {}; try { j = JSON.parse(x.responseText || "{}"); } catch (e) {}
    m.status = "uploaded"; m.driveId = j.id || m.driveId; m.uploadedAt = Date.now(); delete m.session; delete m.lastError;
    await DB.putRec(m); delete progress[m.id];
  }
  const Queue = {
    running: false, needAuth: false, timer: 0,
    async kick() {
      if (this.running || cur) return;
      this.running = true;
      try {
        const waiting = (await DB.allRecs()).filter((m) => m.status === "saved").sort((a, b) => a.startedAt - b.startedAt);
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
    const waiting = recs.filter((m) => m.status === "saved").length;
    if (!recording) {
      $("sub").textContent = waiting ? (Queue.needAuth ? `${waiting} waiting · sign in to Google to upload` : !navigator.onLine ? `${waiting} waiting · will upload when back online` : `${waiting} uploading to “${conf().folderName}”`)
        : recs.length ? `Everything is in “${conf().folderName}”.` : "Recordings are kept on this phone until they reach Google Drive.";
    }
    $("syncBtn").hidden = !waiting || recording;
    $("syncBtn").textContent = Queue.needAuth ? "Sign in to upload" : "Upload now";
    const list = $("list");
    if (!recs.length) { list.innerHTML = `<div class="empty">No recordings yet.</div>`; return; }
    list.innerHTML = recs.slice(0, 60).map((m) => {
      const up = m.status === "uploaded", busy = progress[m.id] != null;
      const badge = up ? `<span class="badge b-up">In Drive</span>` : busy ? `<span class="badge b-go">Uploading</span>` : m.lastError ? `<span class="badge b-err">Will retry</span>` : `<span class="badge b-wait">On phone</span>`;
      const err = !up && m.lastError ? ` · ${esc(m.lastError)}` : "";
      return `<div class="item" data-id="${m.id}"><div class="top"><div class="name">${esc(m.name)}</div>${badge}</div>
        <div class="meta">${when(m.startedAt)} · ${fmtDur(m.duration)} · ${fmtSize(m.size)}${m.recovered ? " · recovered" : ""}${err}</div>
        <div class="bar" style="display:${busy ? "block" : "none"}"><i style="width:${Math.round((progress[m.id] || 0) * 100)}%"></i></div>
        <div class="acts">${m.audioGone ? "" : `<button data-a="play">Play</button>`}<button data-a="rename">Rename</button>${up && m.driveId ? `<a href="https://drive.google.com/file/d/${m.driveId}/view" target="_blank" rel="noopener">Open in Drive</a>` : ""}<button data-a="delete">${up ? "Remove from phone" : "Delete"}</button></div></div>`;
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
      if (m.status === "uploaded" && m.driveId) { try { await api("PATCH", `https://www.googleapis.com/drive/v3/files/${m.driveId}?fields=id`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: m.name + extFor(m.mime) }) }); } catch (x) { notice("Renamed on the phone; the Drive name will update after you sign in."); } }
      render();
    } else if (b.dataset.a === "delete") {
      if (m.status !== "uploaded" && !confirm("This recording hasn't reached Google Drive yet. Delete it for good?")) return;
      if (m.status === "uploaded") { await DB.dropAudio(m.id); await DB.remove(m.id); } else await DB.remove(m.id);
      render();
    }
  });
  $("rec").addEventListener("click", () => (cur ? stopRecording("stopped") : startRecording()));
  $("syncBtn").addEventListener("click", () => { if (Queue.needAuth) Auth.signIn(false); else { recsClearRetry().then(() => Queue.kick()); } });
  async function recsClearRetry() { for (const m of await DB.allRecs()) if (m.status === "saved" && m.retryAt) { m.retryAt = 0; await DB.putRec(m); } }
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
