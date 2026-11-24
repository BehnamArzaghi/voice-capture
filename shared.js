/* Google Drive helpers shared by the recorder (index.html) and the caption studio (studio.html).
   Both pages run on the same origin, so they share the sign-in token kept in localStorage ("vc.token"). */
"use strict";
window.VCDrive = (() => {
  const CFG = Object.assign({ folderName: "Voice Notes Inbox" }, window.VC_CONFIG || {});
  const S = {
    get(k, d) { try { const v = localStorage.getItem("vc." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("vc." + k, JSON.stringify(v)); } catch (e) {} },
    del(k) { try { localStorage.removeItem("vc." + k); } catch (e) {} },
  };
  const FILES = "https://www.googleapis.com/drive/v3/files";
  const UPLOAD = "https://www.googleapis.com/upload/drive/v3/files";
  class AuthError extends Error {}
  const token = () => { const t = S.get("token", null); return t && t.exp > Date.now() + 90000 ? t.value : null; };
  // reading files the app didn't create (captions Claude writes) needs drive.readonly on top of drive.file
  const canRead = () => /drive\.readonly|auth\/drive(\s|$)/.test(S.get("scopes", "") || "");
  const quote = (s) => String(s).replace(/\\/g, "\\\\").replace(/'/g, "\\'");

  async function api(method, url, opts = {}) {
    const tok = token(); if (!tok) throw new AuthError("Google sign-in needed");
    const r = await fetch(url, { method, headers: Object.assign({ Authorization: "Bearer " + tok }, opts.headers || {}), body: opts.body });
    if (r.status === 401) { S.del("token"); throw new AuthError("Google sign-in expired"); }
    return r;
  }
  async function why(r, what) {
    let msg = "", reason = "";
    try { const j = await r.clone().json(); msg = (j.error && j.error.message) || ""; reason = (j.error && j.error.errors && j.error.errors[0] && j.error.errors[0].reason) || (j.error && j.error.status) || ""; } catch (e) {}
    if (/insufficient|PERMISSION_DENIED.*scope|ACCESS_TOKEN_SCOPE/i.test(reason + " " + msg)) return "Drive permission is missing; reconnect from the Library";
    return `${what} ${r.status}${msg ? ": " + msg.slice(0, 120) : ""}`;
  }
  async function list(query, fields = "id,name,modifiedTime", order = "modifiedTime desc") {
    const out = []; let page = "";
    do {
      const u = `${FILES}?spaces=drive&pageSize=200&orderBy=${encodeURIComponent(order)}&fields=${encodeURIComponent(`nextPageToken,files(${fields})`)}&q=${encodeURIComponent(query)}${page ? "&pageToken=" + encodeURIComponent(page) : ""}`;
      const r = await api("GET", u); if (!r.ok) throw new Error(await why(r, "Drive list"));
      const j = await r.json(); out.push(...(j.files || [])); page = j.nextPageToken || "";
    } while (page && out.length < 2000);
    return out;
  }
  async function findFolder(name, parent) {
    const f = await list(`name = '${quote(name)}' and '${parent}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false`, "id,name", "createdTime");
    return f[0] ? f[0].id : null;
  }
  async function createFolder(name, parent, description) {
    const r = await api("POST", `${FILES}?fields=id`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, mimeType: "application/vnd.google-apps.folder", parents: parent ? [parent] : undefined, description }) });
    if (!r.ok) throw new Error(await why(r, "folder create"));
    return (await r.json()).id;
  }
  // the recorder's own folder (it creates it on first upload; cached by the recorder as "folderId")
  async function inbox() {
    const id = S.get("folderId", null);
    if (id) return id;
    const name = S.get("folderName", CFG.folderName) || CFG.folderName;
    const f = await list(`name = '${quote(name)}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false`, "id,name", "createdTime");
    if (f[0]) { S.set("folderId", f[0].id); S.set("folderFor", name); return f[0].id; }
    throw new Error(`No “${name}” folder yet; record and upload something first`);
  }
  // a subfolder the app creates and therefore may write into ("Studio": looks, corrections, render requests)
  async function ensureSub(parent, name, description) {
    const key = "sub." + name, id = S.get(key, null);
    if (id && S.get(key + ".parent", "") === parent) return id;
    const fid = (await findFolder(name, parent)) || (await createFolder(name, parent, description));
    S.set(key, fid); S.set(key + ".parent", parent);
    return fid;
  }
  async function getJson(id) {
    const r = await api("GET", `${FILES}/${id}?alt=media`); if (!r.ok) throw new Error(await why(r, "Drive read"));
    return r.json();
  }
  async function getBlob(id, type) {
    const r = await api("GET", `${FILES}/${id}?alt=media`); if (!r.ok) throw new Error(await why(r, "Drive download"));
    const b = await r.blob(); return type && !b.type ? new Blob([b], { type }) : b;
  }
  // create or overwrite a small JSON file the app owns; DESCRIPTION is a short summary the Library reads without downloading
  async function saveJson(parent, name, obj, id, description) {
    const body = JSON.stringify(obj);
    if (id) {
      const r = await api("PATCH", `${UPLOAD}/${id}?uploadType=multipart&fields=id,modifiedTime`, multipart({ description }, body));
      if (r.ok) return r.json();
      if (r.status !== 404) throw new Error(await why(r, "Drive save"));
    }
    const r = await api("POST", `${UPLOAD}?uploadType=multipart&fields=id,modifiedTime`, multipart({ name, parents: [parent], mimeType: "application/json", description }, body));
    if (!r.ok) throw new Error(await why(r, "Drive save"));
    return r.json();
  }
  // create or overwrite a file the app owns from a Blob (the studio's thumbnail image)
  async function saveBlob(parent, name, blob, id, description) {
    const type = blob.type || "application/octet-stream";
    const body = (m) => {
      const b = "vc" + Math.random().toString(36).slice(2);
      return { headers: { "Content-Type": "multipart/related; boundary=" + b },
        body: new Blob([`--${b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(JSON.parse(JSON.stringify(m)))}\r\n--${b}\r\nContent-Type: ${type}\r\n\r\n`, blob, `\r\n--${b}--`]) };
    };
    if (id) {
      const r = await api("PATCH", `${UPLOAD}/${id}?uploadType=multipart&fields=id,modifiedTime`, body({ description }));
      if (r.ok) return r.json();
      if (r.status !== 404) throw new Error(await why(r, "Drive save"));
    }
    const r = await api("POST", `${UPLOAD}?uploadType=multipart&fields=id,modifiedTime`, body({ name, parents: [parent], mimeType: type, description }));
    if (!r.ok) throw new Error(await why(r, "Drive save"));
    return r.json();
  }
  function multipart(meta, body) {
    const b = "vc" + Math.random().toString(36).slice(2);
    const clean = JSON.parse(JSON.stringify(meta));
    return { headers: { "Content-Type": "multipart/related; boundary=" + b },
      body: `--${b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(clean)}\r\n--${b}\r\nContent-Type: application/json\r\n\r\n${body}\r\n--${b}--` };
  }
  const meta = (s) => { try { return s ? JSON.parse(s) : {}; } catch (e) { return {}; } };
  return { S, CFG, AuthError, token, canRead, api, why, list, findFolder, ensureSub, inbox, getJson, getBlob, saveJson, saveBlob, meta, quote };
})();
