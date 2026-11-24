"""Browser test harness: serves the repo locally, fakes the Google Drive API with local files, and drives Chrome (Playwright).

By default it uses the synthetic recording from fixture.py. To try a real recording instead, set CAPS (captions JSON),
AUDIO (its audio) and AID (its Drive id); real data stays outside the repo.
"""
import functools, http.server, json, os, socketserver, sys, threading
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "tools")); sys.path.insert(0, HERE)
import fixture, vc  # noqa: E402

FX = fixture.make()
CAPS = os.environ.get("CAPS", FX["captions"])
AUDIO = os.environ.get("AUDIO", FX["audio"])
AID = os.environ.get("AID", FX["aid"])
GLOSSF = os.environ.get("GLOSS", FX["glossary"])
EDITS = os.environ.get("EDITS", "")
LIBJSON = os.environ.get("LIBJSON", "")  # optional Captions/library.json for the Library tests
OUT = os.path.join(HERE, "shots"); os.makedirs(OUT, exist_ok=True)
SAVES = []  # bodies of every write the page sends to "Drive"
GETS = []   # paths of every file the page downloads from "Drive"
CLEANCOPIES = True  # whether Drive has noise-reduced copies of the recording
CLEANDESC = True    # whether those copies carry the noise reading in their descriptions (else it comes from library.json)
CLEANPARTS = False  # whether the full copy is stored as byte parts (as a long recording's is), with an older incomplete set beside it
# the Library's recordings: (id, captions title or None = not processed yet, duration, put the summary in the description?)
LIB = [(AID, json.load(open(CAPS)).get("title"), round(json.load(open(CAPS))["duration"]), True),
       ("LIBONLY000000000000000000000000", "Summary only in library.json", 300, False),
       ("NEWREC", None, 95, False)]


def serve(port=0):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    h = functools.partial(Quiet, directory=REPO)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    s = socketserver.ThreadingTCPServer(("127.0.0.1", port), h); s.daemon_threads = True  # port 0 = any free port
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{s.server_address[1]}"


async def drive(route):
    u, m = route.request.url, route.request.method
    if "fonts.g" in u: return await route.abort()
    if m != "GET":
        SAVES.append((route.request.post_data_buffer or b"").decode("utf-8", "replace"))  # uploads may be binary (thumbnail PNG)
        return await route.fulfill(json={"id": "SAVED", "modifiedTime": "2026-01-01T00:00:00Z"})
    p = urlparse(u); q = parse_qs(p.query).get("q", [""])[0]
    files = lambda fs: route.fulfill(json={"files": fs})
    if p.path.endswith("/files"):
        if "name = 'Captions'" in q: return await files([{"id": "CAPS", "name": "Captions"}])
        if "name = 'Studio'" in q: return await files([{"id": "STUDIO", "name": "Studio"}])
        if ".captions.json" in q: return await files([{"id": "CAPFILE", "name": AID + ".captions.json"}])
        if "name = 'library.json'" in q: return await files([{"id": "LIBJSON", "name": "library.json"}] if LIBJSON else [])
        if "glossary.json" in q: return await files([{"id": "GLOSS", "name": "glossary.json"}] if os.path.exists(GLOSSF) else [])
        if ".edits.json" in q: return await files([{"id": "EDITS", "name": AID + ".edits.json"}] if EDITS else [])
        if ".full.m4a" in q:  # noise-reduced copies (the fixture's tone stands in for them)
            desc = lambda lv: json.dumps({"snr": 3.2, "rec": "full", "level": lv}) if CLEANDESC else ""
            full = ([{"id": f"PART{i}", "name": f"{AID}.full.m4a.p{i}of3", "description": desc("full")} for i in (2, 1, 3)]
                    + [{"id": "OLDPART", "name": f"{AID}.full.m4a.p1of2", "description": desc("full")}]) if CLEANPARTS \
                else [{"id": "CLEANFULL", "name": AID + ".full.m4a", "description": desc("full")}]
            return await files(full + [{"id": "CLEANLIGHT", "name": AID + ".light.m4a", "description": desc("light")}] if CLEANCOPIES else [])
        if "mimeType contains 'audio/'" in q:
            return await files([{"id": i, "name": (t or "2026-01-01 Walk") + ".m4a", "createdTime": "2026-01-01T16:07:00Z",
                                 "appProperties": {"durationSec": str(d)}} for i, t, d, _ in LIB])
        if "'CAPS' in parents" in q:
            fs = [{"id": "c" + i, "name": i + ".captions.json", "description": json.dumps({"rev": 1, "title": t, "duration": d}) if desc else ""}
                  for i, t, d, desc in LIB if t]
            if LIBJSON: fs.append({"id": "LIBJSON", "name": "library.json"})
            return await files(fs)
        return await files([])
    GETS.append(p.path)
    if "/PART" in p.path:  # byte thirds of the fixture audio
        data = open(AUDIO, "rb").read(); n = -(-len(data) // 3); i = int(p.path[-1]) - 1
        return await route.fulfill(body=data[i * n:(i + 1) * n], content_type="application/octet-stream")
    for key, path, typ in (("/CAPFILE", CAPS, "application/json"), ("/GLOSS", GLOSSF, "application/json"), ("/EDITS", EDITS, "application/json"),
                           ("/LIBJSON", LIBJSON, "application/json"), ("/" + AID, AUDIO, "audio/mp4"),
                           ("/CLEANFULL", AUDIO, "audio/mp4"), ("/CLEANLIGHT", AUDIO, "audio/mp4")):
        if path and p.path.endswith(key): return await route.fulfill(path=path, content_type=typ)
    return await route.fulfill(status=404, json={"error": {"message": "not found"}})


INIT = """(() => { const S=(k,v)=>localStorage.setItem('vc.'+k, JSON.stringify(v));
S('token',{value:'x',exp:Date.now()+3.6e6}); S('scopes','https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/drive.readonly');
S('folderId','INBOX'); S('folderFor','Voice Notes Inbox'); S('folderName','Voice Notes Inbox'); S('email','test@example.com');
S('sub.Studio','STUDIO'); S('sub.Studio.parent','INBOX'); })();"""


async def page(p, w, h, mobile=False):
    b = await p.chromium.launch(executable_path=vc.chrome_path(), args=["--autoplay-policy=no-user-gesture-required"])
    ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if mobile else 1, has_touch=mobile, is_mobile=mobile)
    await ctx.add_init_script(INIT)
    for pat in ("https://www.googleapis.com/**", "https://fonts.googleapis.com/**", "https://fonts.gstatic.com/**"):
        await ctx.route(pat, drive)
    pg = await ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" and "ERR_FAILED" not in m.text and "404" not in m.text else None)
    return b, pg, errs


class Check:
    """Collects pass/fail lines; the runner exits non-zero if anything failed."""
    def __init__(self): self.fails, self.n = [], 0
    def __call__(self, ok, what, got=None):
        self.n += 1
        print(("  ok   " if ok else "  FAIL ") + what + ("" if ok or got is None else f"  (got {got!r})"))
        if not ok: self.fails.append(what)
