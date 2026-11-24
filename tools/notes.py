#!/usr/bin/env python3
"""Local steps of the "process my voice notes" pipeline (Claude runs these; Drive and Notion steps go through its connectors).

  notes.py setup                                   deps + speech model + fonts (once per session; ~1-2 min)
  notes.py prepare AUDIO --id ID --title T [--recorded ISO] [--vocab FILE]
        transcribe (accurate settings + forced alignment) -> WORK/ID/: captions.json, listen.m4a, verbatim.txt, clean.txt
  notes.py join OUT PART [PART ...] [--sha256 HEX]  rebuild a long recording from its Drive "Parts" pieces
  notes.py restore AUDIO CAPTIONS.json             rebuild WORK/ID in a fresh session (before apply/render)
  notes.py apply WORK/ID EDITS.json [--vocab FILE]  bake the studio's word corrections in (re-timed), rev+1, remap for the app
  notes.py retime AUDIO CAPTIONS.json              fix captions that drift from the audio (same words and rev; studio edits still fit)
  notes.py glossary ROWS.json [-o glossary.json]    Notion Glossary rows -> glossary.json (themes, colors, terms)
  notes.py tag CAPTIONS.json glossary.json [--vocab vocabulary.txt]   color glossary terms by theme; prints themes for the Notion row
  notes.py publish CAPTIONS.json ... [--extra FILE ...] [--library library.json] [--drive-dir DIR]
        hand a run's files to Drive in one step: updates Captions/library.json; with --drive-dir writes into a Drive for desktop
        folder, otherwise prints one upload plan for the Drive connector
  notes.py render WORK/ID EDITS.json               render the requested video (+ .srt) with the studio's look
  notes.py clean WORK/ID AUDIO                    noise-reduced listening copies (light, full) for a recording already transcribed
  notes.py thumb WORK/ID EDITS.json [--glossary glossary.json]   the studio's thumbnail as a PNG (3840 x 2160 for 16:9)
  notes.py set WORK/ID key=value ...               set captions fields before upload (listen=<Drive id of the listening copy>)
  notes.py ref FILE                                file reference for the Drive connector's create_file (no bytes through chat)

Drive layout (inside "Voice Notes Inbox"):
  <recordings>.m4a            the phone app's uploads (Parts/ holds <=9 MB pieces of long ones)
  Captions/ID.captions.json   written here: {v, audioId, title, recordedAt, duration, rev, listen, video, remap, data}
  Captions/ID.mp4, ID.srt     rendered on request
  Captions/vocabulary.txt     names and terms for the transcriber (grows from corrections)
  Captions/library.json       {items: {ID: {rev, title, duration, notion, videoId, videoAt, srtId}}}: what the Library shows
  Captions/glossary.json      copy of the Notion Glossary (themes, colors, terms)
  Listening copies/ID.m4a     small copy that Notion's audio player fetches (folder shared by link)
  Listening copies/ID.light.m4a, ID.full.m4a   noise-reduced copies; description {snr, rec, level}; the studio's Sound switch plays them
                              (over 3 MB they go up as byte parts ID.full.m4a.p1of3 ..., which the studio joins)
  Studio/ID.edits.json        written by the app: {base, params, fixes, render, glossary, thumb}
  Studio/ID.thumbnail.png     the studio's thumbnail, when saved to Drive from the Thumbnail tab
"""
import argparse, difflib, hashlib, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("VN_WORK", "/home/claude/vn")
VC = os.path.join(HERE, "vc.py")
NOTION_MAX = 5 * 1024 * 1024  # Notion free workspaces fetch files up to 5 MiB
PART_MAX = 3_000_000  # the Drive connector takes about 3.1 MB of file per call; larger listening copies go up as byte parts


def sh(*cmd, **kw):
    return subprocess.run(list(cmd), check=True, **kw)


def ref(path):
    path = os.path.abspath(path)
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return f"sha256:{h}:{path}"


def vocab_prompt(path):
    if not path or not os.path.exists(path):
        return None
    terms = [t.strip() for t in re.split(r"[\n,]+", open(path).read()) if t.strip() and not t.strip().startswith("#")]
    return ", ".join(dict.fromkeys(terms))[:600] + "." if terms else None


def listening_copy(src, dest, dur):
    # mono AAC sized for Notion's player: 48 kb/s when it fits under 5 MiB, else 32 kb/s; longer notes get a Drive link only
    for kbps in (48, 32):
        if dur * kbps * 1000 / 8 < NOTION_MAX * 0.97:
            sh("ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "1", "-ar", "24000", "-c:a", "aac", "-b:a", f"{kbps}k", "-movflags", "+faststart", dest)
            return os.path.getsize(dest) < NOTION_MAX
    sh("ffmpeg", "-v", "error", "-y", "-i", src, "-ac", "1", "-ar", "24000", "-c:a", "aac", "-b:a", "32k", "-movflags", "+faststart", dest)
    return False


def _pcm16(src):
    """SRC as 16 kHz mono float samples (for measuring noise)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def _kbps(dur):
    for kbps in (48, 32):
        if dur * kbps * 1000 / 8 < NOTION_MAX * 0.97:
            return kbps
    return 32


def make_clean_copies(src, d, aid, dur, words=None):
    """Noise-reduced listening copies of SRC at both levels (D/<aid>.light.m4a, D/<aid>.full.m4a), plus D/clean.json with the
    measured noise and the recommended level. The studio switches between these and the original; Notion gets the recommended one."""
    sys.path.insert(0, HERE)
    import vc
    snr, rec = vc.noise_level(_pcm16(src), words)
    kb = _kbps(dur)
    files = {}
    for level in ("light", "full"):
        dest = f"{d}/{aid}.{level}.m4a"
        vc.clean_audio(src, level, dest, ["-ac", "1", "-ar", "24000", "-c:a", "aac", "-b:a", f"{kb}k", "-movflags", "+faststart"])
        files[level] = dest
    info = {"snr": snr, "rec": rec, "at": int(time.time() * 1000)}
    json.dump(info, open(f"{d}/clean.json", "w"))
    return info, files


def texts(words):
    verb = " ".join(w["w"].strip() for w in words)
    clean = " ".join((w.get("wh") or w["w"]).strip() for w in words if not w.get("fl"))
    clean = re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r",\s*,", ",", clean))
    return verb, clean


def write_captions(d, meta, data):
    cap = dict(meta, v=1, data=data)
    json.dump(cap, open(f"{d}/captions.json", "w"), separators=(",", ":"))
    json.dump({k: v for k, v in cap.items() if k != "data"}, open(f"{d}/meta.json", "w"), indent=1)
    return cap


def describe(meta):
    """Short JSON for the Drive file description of ID.captions.json; the app's Library reads it without downloading.
    Carries notion / videoId / srtId once they are set (notes.py set ... notion=URL videoId=ID srtId=ID)."""
    m = {"rev": meta.get("rev", 1), "title": meta.get("title"), "duration": round(meta.get("duration") or 0)}
    if meta.get("notion"): m["notion"] = meta["notion"]
    if meta.get("videoId"): m.update(videoId=meta["videoId"], videoAt=(meta.get("video") or {}).get("at", 0), srtId=meta.get("srtId"))
    return json.dumps(m, separators=(",", ":"))


def cmd_prepare(a):
    d = os.path.join(WORK, a.id)
    os.makedirs(d, exist_ok=True)
    prompt = vocab_prompt(a.vocab)
    t0 = time.time()
    sys.path.insert(0, HERE)
    import vc
    src = a.audio
    est, est_rec = vc.noise_level(_pcm16(a.audio))
    if est_rec == "full":  # very noisy (car, wind): Whisper and the voice analysis work on the cleaned sound
        src = vc.clean_audio(a.audio, "full", f"{d}/transcribe_src.flac", ["-ac", "1", "-c:a", "flac"])
    sh(sys.executable, VC, "run", src, "--out", d, *(["--prompt", prompt] if prompt else []))
    if src != a.audio:  # the video's master stays the original; the studio and renders pick the cleaning level
        sh("ffmpeg", "-v", "error", "-y", "-i", a.audio, "-vn", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "2", "-c:a", "flac", f"{d}/master.flac")
    data = json.load(open(f"{d}/data.json"))
    words = data["words"]
    verb, clean = texts(words)
    open(f"{d}/verbatim.txt", "w").write(verb)
    open(f"{d}/clean.txt", "w").write(clean)
    dur = data.get("duration") or words[-1]["e"]
    fits = listening_copy(a.audio, f"{d}/listen.m4a", dur)
    noise, cfiles = make_clean_copies(a.audio, d, a.id, dur, [w for w in words if not w.get("fl")])
    meta = {"audioId": a.id, "title": a.title, "recordedAt": a.recorded, "duration": dur, "rev": 1, "listen": None, "video": None, "remap": None,
            "noise": {"snr": noise["snr"], "rec": noise["rec"]}}
    write_captions(d, meta, data)
    out = {"dir": d, "words": len(words), "fillers": sum(1 for w in words if w.get("fl")), "clean_words": len(clean.split()),
           "duration_min": round(dur / 60, 2), "minutes_taken": round((time.time() - t0) / 60, 1),
           "captions_ref": ref(f"{d}/captions.json"), "captions_bytes": os.path.getsize(f"{d}/captions.json"),
           "listen_ref": ref(f"{d}/listen.m4a"), "listen_bytes": os.path.getsize(f"{d}/listen.m4a"), "listen_fits_notion": fits,
           "noise": noise, "transcribed_cleaned": src != a.audio,
           "clean_files": {k: os.path.basename(v) for k, v in cfiles.items()},
           "notion_audio": "listen.m4a" if noise["rec"] == "off" else os.path.basename(cfiles[noise["rec"]]),
           "description": describe(meta)}
    if os.path.exists(f"{d}/timing_report.json"):
        out["timing_check"] = json.load(open(f"{d}/timing_report.json"))  # "check": stretches (s) left unverified, worth a look in the studio
    print(json.dumps(out, indent=1))


def cmd_join(a):
    sh(sys.executable, os.path.join(HERE, "join_parts.py"), a.out, *a.parts, *(["--sha256", a.sha256] if a.sha256 else []))


def cmd_apply(a):
    """Word corrections from the studio: index -> new text ("" removes). Re-time with forced alignment, bump rev, remap indices."""
    d = a.dir
    E = json.load(open(a.edits))
    cap = json.load(open(f"{d}/captions.json"))
    if (E.get("base") or 1) != cap.get("rev", 1):
        sys.exit(f"edits were made on rev {E.get('base')} but captions are rev {cap.get('rev')}; open the studio once to refresh")
    fixes = {int(k): v for k, v in (E.get("fixes") or {}).items()}
    if not fixes:
        print(json.dumps({"changed": False})); return
    old = cap["data"]["words"]
    toks, src = [], []  # new token list and, for each, the old index it came from (-1 = inserted)
    for i, w in enumerate(old):
        if i in fixes:
            for k, t in enumerate(fixes[i].split()):
                toks.append(t); src.append(i if k == 0 else -1)
        else:
            toks.append(w["w"].strip()); src.append(i)
    # the aligner anchors on the current words; keep the pre-fix file as the anchor source
    shutil.copy(f"{d}/words.json", f"{d}/words.before-rev{cap.get('rev', 1)}.json")
    sh(sys.executable, VC, "fix", d, "--text", _tmp(" ".join(toks)))
    data = json.load(open(f"{d}/data.json"))
    remap = {str(o): n for n, o in enumerate(src) if o >= 0}
    new_terms = sorted({t.strip(".,;:!?\"'()") for i in fixes for t in fixes[i].split()
                        if t[:1].isupper() or not re.fullmatch(r"[a-z']+", t.strip(".,;:!?\"'()").lower() or "x") or len(t) > 9} - {""})
    if a.vocab:
        have = set(vocab_prompt(a.vocab).rstrip(".").split(", ")) if vocab_prompt(a.vocab) else set()
        add = [t for t in new_terms if t not in have]
        if add:
            with open(a.vocab, "a") as f:
                f.write("\n" + "\n".join(add))
    meta = {k: v for k, v in cap.items() if k not in ("data", "v")}
    meta.update(rev=cap.get("rev", 1) + 1, remap={"from": cap.get("rev", 1), "map": remap}, appliedAt=E.get("updatedAt"))
    write_captions(d, meta, data)
    verb, clean = texts(data["words"])
    open(f"{d}/verbatim.txt", "w").write(verb); open(f"{d}/clean.txt", "w").write(clean)
    print(json.dumps({"changed": True, "rev": meta["rev"], "fixes": len(fixes), "new_terms": new_terms,
                      "captions_ref": ref(f"{d}/captions.json"), "description": describe(meta)}, indent=1))


def _tmp(text):
    p = f"/tmp/vn-text-{os.getpid()}.txt"
    open(p, "w").write(text)
    return p


def cmd_clean(a):
    """Noise reduction for a recording that was already transcribed: two cleaned listening copies, without touching its captions."""
    d = a.dir
    cap = json.load(open(f"{d}/captions.json"))
    aid = cap.get("audioId") or os.path.basename(d)
    words = [w for w in cap["data"]["words"] if not w.get("fl")]
    info, files = make_clean_copies(a.audio, d, aid, cap.get("duration") or words[-1]["e"], words)
    print(json.dumps({"noise": info, "files": {k: {"name": os.path.basename(v), "ref": ref(v), "mb": round(os.path.getsize(v) / 1e6, 2)} for k, v in files.items()},
                      "next": "upload both to Listening copies (or pass them to publish with --listening)"}, indent=1))


def render_audio(d, params, cap):
    """The video's sound at the noise-reduction level chosen in the studio ("auto" = the recommended one); None = master.flac as is."""
    level = (params or {}).get("denoise") or "auto"
    if level == "auto":
        info = json.load(open(f"{d}/clean.json")) if os.path.exists(f"{d}/clean.json") else None
        if not info:
            sys.path.insert(0, HERE)
            import vc
            snr, rec = vc.noise_level(_pcm16(f"{d}/master.flac"), [w for w in cap["data"]["words"] if not w.get("fl")])
            info = {"snr": snr, "rec": rec}
        level = info["rec"]
    if level not in ("light", "full"):
        return None, "off"
    sys.path.insert(0, HERE)
    import vc
    dest = f"{d}/master.{level}.flac"
    if not os.path.exists(dest) or os.path.getmtime(dest) < os.path.getmtime(f"{d}/master.flac"):
        vc.clean_audio(f"{d}/master.flac", level, dest, ["-ar", "48000", "-ac", "2", "-c:a", "flac"])
    return dest, level


def cmd_render(a):
    d = a.dir
    E = json.load(open(a.edits))
    req = E.get("render") or {}
    params = req.get("params") or E.get("params") or {}
    json.dump(params, open(f"{d}/params.json", "w"))
    audio, level = render_audio(d, params, json.load(open(f"{d}/captions.json")))
    sh(sys.executable, VC, "render", d, "--params", f"{d}/params.json", *(["--audio", audio] if audio else []))
    sh(sys.executable, VC, "srt", d)
    cap = json.load(open(f"{d}/captions.json"))
    meta = {k: v for k, v in cap.items() if k not in ("data", "v")}
    meta["video"] = {"at": req.get("at") or int(time.time() * 1000), "params": params, "denoise": level}
    write_captions(d, meta, cap["data"])
    mp4 = f"{d}/voicecap_full.mp4"
    print(json.dumps({"mp4_ref": ref(mp4), "mp4_mb": round(os.path.getsize(mp4) / 1e6, 1), "srt_ref": ref(f"{d}/captions.srt"),
                      "next": "upload mp4 + srt to Captions, then: notes.py set DIR videoId=<mp4 id> srtId=<srt id>, upload captions.json, set its description"}, indent=1))


def cmd_thumb(a):
    """Render the thumbnail set up in the studio's Thumbnail tab (edits.json "thumb"), with the captions' themes and the glossary's colors."""
    d = a.dir
    E = json.load(open(a.edits))
    cap = json.load(open(f"{d}/captions.json"))
    data = cap["data"]
    if a.glossary and os.path.exists(a.glossary):  # the studio adds the glossary's themes (with their Notion colors) to the recording's
        G = json.load(open(a.glossary))
        themes, colors = list(data.get("themes") or []), list(data.get("themeColors") or [])
        for t in G.get("themes", []):
            if t.get("name") and t["name"] not in themes:
                themes.append(t["name"]); colors.append(t.get("color"))
        data = dict(data, themes=themes, themeColors=colors)
    th = dict(E.get("thumb") or {})
    if not (th.get("title") or th.get("subtitle")):  # never opened in the studio: start from the recording title, split at the colon
        t = cap.get("title") or ""
        k = t.find(":")
        th.update({"title": t[:k].strip(), "subtitle": t[k + 1:].strip()} if k > 0 else {"title": t})
    spec = {"thumb": th, "params": E.get("params") or {}}
    sp, dp = f"{d}/thumb.spec.json", f"{d}/thumb.data.json"
    json.dump(spec, open(sp, "w")); json.dump(data, open(dp, "w"))
    out = a.out or f"{d}/thumbnail.png"
    sh(sys.executable, VC, "thumb", d, "--spec", sp, "--data", dp, "--out", out)
    print(json.dumps({"png_ref": ref(out), "mb": round(os.path.getsize(out) / 1e6, 2), "name": f"{cap.get('audioId', os.path.basename(d))}.thumbnail.png"}, indent=1))


def cmd_restore(a):
    sys.path.insert(0, HERE)
    import vc
    cap = json.load(open(a.captions))
    d = os.path.join(WORK, cap["audioId"])
    os.makedirs(d, exist_ok=True)
    vc.prepare(a.audio, d)
    data = cap["data"]
    words = {"duration": data.get("duration"), "lang": data.get("lang", "en"), "words": data["words"]}
    json.dump(words, open(f"{d}/words.json", "w"))
    json.dump(words, open(f"{d}/words.whisper.json", "w"))  # current timings anchor any re-alignment
    json.dump(data, open(f"{d}/data.json", "w"))
    shutil.copy(a.captions, f"{d}/captions.json")
    json.dump({k: v for k, v in cap.items() if k != "data"}, open(f"{d}/meta.json", "w"), indent=1)
    verb, clean = texts(data["words"])
    open(f"{d}/verbatim.txt", "w").write(verb); open(f"{d}/clean.txt", "w").write(clean)
    print(json.dumps({"dir": d, "rev": cap.get("rev", 1), "words": len(data["words"])}))


def cmd_retime(a):
    """Captions made before the timing check (Nov 23, 2026) can drift by up to ~20 s around long pauses. Re-time them in place:
    same words, same order, same rev, so the studio's edits and pending corrections keep their word indices."""
    cmd_restore(a)
    cap = json.load(open(a.captions))
    d = os.path.join(WORK, cap["audioId"])
    old = cap["data"]["words"]
    sh(sys.executable, VC, "retime", d)
    data = json.load(open(f"{d}/data.json"))
    if len(data["words"]) != len(old):
        sys.exit(f"retime changed the word count ({len(old)} -> {len(data['words'])}); captions left as they were")
    shifts = sorted(abs(n["s"] - o["s"]) for n, o in zip(data["words"], old))
    meta = {k: v for k, v in cap.items() if k not in ("data", "v")}
    meta["retimedAt"] = int(time.time() * 1000)
    write_captions(d, meta, data)
    rep = json.load(open(f"{d}/timing_report.json")) if os.path.exists(f"{d}/timing_report.json") else {}
    print(json.dumps({"dir": d, "words": len(old), "moved_over_1s": sum(1 for x in shifts if x > 1), "max_shift_s": round(shifts[-1], 1),
                      "timing_check": rep,
                      "captions_ref": ref(f"{d}/captions.json"), "description": describe(meta),
                      "next": "upload captions.json to Captions as <id>.captions.json, set its description, trash the old file"}, indent=1))


# ---------- glossary: Notion themes + terms -> tags on the words of a transcript
# Theme vocabulary (same names and colors as the Theme property in Notion's Substack Articles / Glossary)
THEMES = [("Masculine/Feminine", "pink"), ("Contingency of knowing", "blue"), ("Science as worldview", "purple"), ("Re-enchantment", "green"),
          ("Soul-making", "orange"), ("Attention economy", "red"), ("Religion & theology", "brown"), ("Ethics & politics", "gray"),
          ("Psychology & psychotherapy", "yellow"), ("Ecology & design", "default")]
UNVERIFIED = "[unverified — from training data]"


def _fold(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower().replace("’", "'"))
    return "".join(c for c in s if not unicodedata.combining(c))


def _tok(s):
    return re.sub(r"[^\w'\-]", "", _fold(s)).strip("'-")


def _variants(term, forms):
    out = set()
    for v in [term] + [f.strip() for f in (forms or "").split(";") if f.strip()]:
        seq = tuple(t for t in (_tok(x) for x in re.split(r"[\s,]+", v)) if t)
        if not seq:
            continue
        out.add(seq)
        last = seq[-1]
        for suf in ("s", "es", "'s"):  # plural and possessive of the last word come free
            out.add(seq[:-1] + (last + suf,))
    return out


def build_glossary(rows, themes=None):
    """Notion Glossary rows (Term, Theme, Status, Forms, Definition, Source, Verified, url) -> glossary.json for the studio and tagging."""
    themes = themes or THEMES
    terms = []
    for r in rows:
        t = (r.get("Term") or "").strip()
        if not t or r.get("Status") == "Rejected":
            continue
        src = (r.get("Source") or "").strip()
        terms.append({"term": t, "theme": r.get("Theme") or "", "forms": [f.strip() for f in (r.get("Forms") or "").split(";") if f.strip()],
                      "def": (r.get("Definition") or "").strip(), "src": src.replace(UNVERIFIED, "").strip(),
                      "verified": r.get("Verified") in (True, "__YES__", "Yes"), "status": r.get("Status") or "Suggested", "url": r.get("url") or ""})
    terms.sort(key=lambda x: x["term"].lower())
    return {"v": 1, "updatedAt": int(time.time() * 1000), "themes": [{"name": n, "color": c} for n, c in themes], "terms": terms}


def tag_data(data, G):
    """Tag glossary terms in captions data: words get th (theme index), data.themes/themeColors list every theme in glossary order,
    data.terms lists each term found with its occurrences [[first word, word count]]. Matching ignores filler words, case,
    accents and punctuation; longer terms win. Returns per-theme stats."""
    names = [t["name"] for t in G["themes"]]
    W = data["words"]
    for w in W:
        w.pop("th", None)
    idx = [i for i, w in enumerate(W) if not w.get("fl")]
    toks = [_tok(W[i]["w"]) for i in idx]
    pats = []
    for k, t in enumerate(G["terms"]):
        if t["theme"] not in names:
            continue
        for v in _variants(t["term"], ";".join(t["forms"])):
            pats.append((len(v), v, k))
    pats.sort(key=lambda p: -p[0])
    taken = [False] * len(toks)
    first = {}  # term index -> occurrences
    for n, v, k in pats:
        f0 = v[0]
        for j in range(len(toks) - n + 1):
            if toks[j] != f0 or any(taken[j:j + n]) or tuple(toks[j:j + n]) != v:
                continue
            for q in range(j, j + n):
                taken[q] = True
            a, b = idx[j], idx[j + n - 1]
            first.setdefault(k, []).append([a, b - a + 1])
    terms_out, stats = [], {}
    for k, o in sorted(first.items(), key=lambda kv: min(x[0] for x in kv[1])):
        t = G["terms"][k]; th = names.index(t["theme"]); o.sort()
        for a, n in o:
            for i in range(a, a + n):
                if not W[i].get("fl"):
                    W[i]["th"] = th; W[i]["fn"] = False
        terms_out.append({"t": t["term"], "th": th, "st": "a" if t["status"] == "Accepted" else "s", "def": t["def"], "src": t["src"],
                          "v": bool(t["verified"]), "url": t["url"], "occ": o})
        s = stats.setdefault(t["theme"], {"occurrences": 0, "terms": []})
        s["occurrences"] += len(o); s["terms"].append(t["term"])
    data["themes"] = names
    data["themeColors"] = [t["color"] for t in G["themes"]]
    data["terms"] = terms_out
    return stats


def hard_to_spell(term):
    """Names, non-English words and rare technical terms: the ones worth giving the transcriber."""
    if any(c.isupper() for c in term) or any(ord(c) > 127 for c in term):
        return True
    try:
        from wordfreq import zipf_frequency
        return min(zipf_frequency(w, "en") for w in term.split()) < 2.6
    except ImportError:
        return any(len(w) >= 11 for w in term.split())


def add_vocab(path, G):
    """Glossary terms (their names, never the listed forms: those include mishearings) go into vocabulary.txt."""
    have = {l.strip().lower() for l in open(path)} if os.path.exists(path) else set()
    add = [t["term"] for t in G["terms"] if t.get("status") != "Rejected" and hard_to_spell(t["term"]) and t["term"].lower() not in have]
    if add:
        with open(path, "a") as f:
            f.write(("" if open(path).read().endswith("\n") else "\n") + "\n".join(add) + "\n")
    return add


def note_themes(stats):
    """Themes to suggest on the note's Notion row: 4+ tagged occurrences, or 3+ spread over 2+ different terms.
    (A single passing name-drop does not make a theme.)"""
    return [th for th, s in sorted(stats.items(), key=lambda kv: -kv[1]["occurrences"])
            if s["occurrences"] >= 4 or (s["occurrences"] >= 3 and len(set(s["terms"])) >= 2)]


def cmd_publish(a):
    """Everything a run hands to Drive's Captions folder, in one step.
    Updates library.json (the Library's summary of every captions file). With --drive-dir (a Google Drive for desktop copy of
    "Voice Notes Inbox") it writes the files there and Drive syncs them as updates (the app reads files by name, newest first). Otherwise it prints a
    compact upload plan for the Drive connector: create each file, then trash the previous copy with the same name."""
    cap_dir = os.path.join(a.drive_dir, "Captions") if a.drive_dir else None
    lib_path = a.library or (os.path.join(cap_dir, "library.json") if cap_dir else os.path.join(WORK, "library.json"))
    lib = {"v": 1, "items": {}}
    if os.path.exists(lib_path):
        try: lib = json.load(open(lib_path)); lib.setdefault("items", {})
        except ValueError: pass
    files = []
    for c in a.captions:
        cap = json.load(open(c))
        aid = cap.get("audioId") or os.path.basename(os.path.dirname(os.path.abspath(c)))
        meta = {k: v for k, v in cap.items() if k not in ("data", "v")}
        lib["items"][aid] = dict(json.loads(describe(meta)), at=int(time.time() * 1000))
        files.append((c, f"{aid}.captions.json", describe(meta)))
    for x in a.extra or []:
        files.append((x, os.path.basename(x), None))
    listening = []
    for x in a.listening or []:  # <id>.light.m4a / <id>.full.m4a, described from clean.json beside them
        cj = os.path.join(os.path.dirname(os.path.abspath(x)), "clean.json")
        info = json.load(open(cj)) if os.path.exists(cj) else {}
        name = os.path.basename(x)
        listening.append((x, name, json.dumps(dict(info, level=name.rsplit(".", 2)[-2]), separators=(",", ":"))))
        aid = name.split(".")[0]
        if aid in lib["items"] and info:
            lib["items"][aid]["noise"] = {"snr": info.get("snr"), "rec": info.get("rec")}
    lib["updatedAt"] = int(time.time() * 1000)
    out_lib = os.path.join(WORK, "library.json") if not cap_dir else lib_path
    os.makedirs(os.path.dirname(out_lib), exist_ok=True)
    tmp = out_lib + ".tmp"; json.dump(lib, open(tmp, "w"), ensure_ascii=False, separators=(",", ":")); os.replace(tmp, out_lib)
    if cap_dir:
        os.makedirs(cap_dir, exist_ok=True)
        for folder, group in ((cap_dir, files), (os.path.join(a.drive_dir, "Listening copies"), listening)):
            os.makedirs(folder, exist_ok=True)
            for src, name, _ in group:
                dst = os.path.join(folder, name)
                if os.path.abspath(src) != os.path.abspath(dst):
                    shutil.copyfile(src, dst + ".tmp"); os.replace(dst + ".tmp", dst)
        print(json.dumps({"written_to": cap_dir, "files": [n for _, n, _ in files] + ["library.json"], "library_items": len(lib["items"])}, indent=1))
        return
    plan = [{"name": n, "ref": ref(src), **({"description": d} if d else {})} for src, n, d in files]
    plan.append({"name": "library.json", "ref": ref(out_lib)})
    for src, n, d in listening:
        for pn, pp in split_parts(src, n):
            plan.append({"folder": "Listening copies", "name": pn, "ref": ref(pp), "description": d,
                         "mime": "audio/mp4" if pn == n else "application/octet-stream"})
    print(json.dumps({"folder": "Captions", "upload": plan,
                      "then": "create each file (its mime, else application/json or text/plain; no conversion), then trash the older files with "
                              "the same name; for a listening copy also trash older parts or whole copies of it (<name> and <name>.p*). "
                              "Descriptions are optional now that library.json carries them"}, indent=1, ensure_ascii=False))


def split_parts(src, name):
    """[(name, path)] for one upload: the file itself when it fits in a connector call, else byte parts NAME.p1ofN ... beside it
    in parts/. The studio downloads the parts and joins them back into the original file."""
    size = os.path.getsize(src)
    if size <= PART_MAX:
        return [(name, src)]
    n = -(-size // PART_MAX)
    d = os.path.join(os.path.dirname(os.path.abspath(src)), "parts")
    os.makedirs(d, exist_ok=True)
    out = []
    with open(src, "rb") as f:
        for i in range(1, n + 1):
            pn = f"{name}.p{i}of{n}"
            open(os.path.join(d, pn), "wb").write(f.read(-(-size // n)))
            out.append((pn, os.path.join(d, pn)))
    return out


def cmd_glossary(a):
    rows = json.load(open(a.rows))
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    G = build_glossary(rows)
    json.dump(G, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"glossary": a.out, "terms": len(G["terms"]), "ref": ref(a.out)}, indent=1))


def cmd_tag(a):
    """Tag a captions file in place (same rev: words and indices are unchanged)."""
    G = json.load(open(a.glossary))
    cap = json.load(open(a.captions))
    stats = tag_data(cap["data"], G)
    json.dump(cap, open(a.captions, "w"), separators=(",", ":"))
    found = sorted({t["t"] for t in cap["data"]["terms"]})
    vocab_add = add_vocab(a.vocab, G) if a.vocab else []
    meta = {k: v for k, v in cap.items() if k not in ("data", "v")}
    print(json.dumps({"captions": a.captions, "captions_ref": ref(a.captions), "description": describe(meta),
                      "terms_found": found, "themes": stats, "set_notion_themes": note_themes(stats), "vocab_added": vocab_add}, indent=1, ensure_ascii=False))


def cmd_set(a):
    cap = json.load(open(f"{a.dir}/captions.json"))
    meta = {k: v for k, v in cap.items() if k not in ("data", "v")}
    for kv in a.pairs:
        k, v = kv.split("=", 1)
        meta[k] = None if v in ("", "null") else v
    write_captions(a.dir, meta, cap["data"])
    print(json.dumps({"captions_ref": ref(f"{a.dir}/captions.json"), "description": describe(meta)}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("setup")
    p = sp.add_parser("prepare"); p.add_argument("audio"); p.add_argument("--id", required=True); p.add_argument("--title", required=True)
    p.add_argument("--recorded"); p.add_argument("--vocab")
    j = sp.add_parser("join"); j.add_argument("out"); j.add_argument("parts", nargs="+"); j.add_argument("--sha256")
    x = sp.add_parser("apply"); x.add_argument("dir"); x.add_argument("edits"); x.add_argument("--vocab")
    r = sp.add_parser("render"); r.add_argument("dir"); r.add_argument("edits")
    f = sp.add_parser("ref"); f.add_argument("file")
    cl = sp.add_parser("clean"); cl.add_argument("dir"); cl.add_argument("audio")
    tb = sp.add_parser("thumb"); tb.add_argument("dir"); tb.add_argument("edits"); tb.add_argument("--glossary"); tb.add_argument("--out")
    rs = sp.add_parser("restore"); rs.add_argument("audio"); rs.add_argument("captions")
    st = sp.add_parser("set"); st.add_argument("dir"); st.add_argument("pairs", nargs="+")
    rt = sp.add_parser("retime"); rt.add_argument("audio"); rt.add_argument("captions")
    gl = sp.add_parser("glossary"); gl.add_argument("rows"); gl.add_argument("-o", "--out", default=os.path.join(WORK, "glossary.json"))
    tg = sp.add_parser("tag"); tg.add_argument("captions"); tg.add_argument("glossary"); tg.add_argument("--vocab")
    pb = sp.add_parser("publish"); pb.add_argument("captions", nargs="*"); pb.add_argument("--extra", nargs="*", help="other files for Captions (glossary.json, vocabulary.txt)")
    pb.add_argument("--library", help="current library.json (downloaded from Captions)")
    pb.add_argument("--listening", nargs="*", help="noise-reduced copies (<id>.light.m4a, <id>.full.m4a) for Listening copies"); pb.add_argument("--drive-dir", help="local Google Drive for desktop copy of Voice Notes Inbox")
    a = ap.parse_args()
    if a.cmd == "setup":
        sh(sys.executable, VC, "setup")
    elif a.cmd == "prepare":
        cmd_prepare(a)
    elif a.cmd == "join":
        cmd_join(a)
    elif a.cmd == "apply":
        cmd_apply(a)
    elif a.cmd == "render":
        cmd_render(a)
    elif a.cmd == "thumb":
        cmd_thumb(a)
    elif a.cmd == "clean":
        cmd_clean(a)
    elif a.cmd == "restore":
        cmd_restore(a)
    elif a.cmd == "set":
        cmd_set(a)
    elif a.cmd == "retime":
        cmd_retime(a)
    elif a.cmd == "glossary":
        cmd_glossary(a)
    elif a.cmd == "tag":
        cmd_tag(a)
    elif a.cmd == "publish":
        cmd_publish(a)
    elif a.cmd == "ref":
        print(ref(a.file))


if __name__ == "__main__":
    main()
