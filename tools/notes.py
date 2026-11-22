#!/usr/bin/env python3
"""Local steps of the "process my voice notes" pipeline (Claude runs these; Drive and Notion steps go through its connectors).

  notes.py setup                                   deps + speech model + fonts (once per session; ~1-2 min)
  notes.py prepare AUDIO --id ID --title T [--recorded ISO] [--vocab FILE]
        transcribe (accurate settings + forced alignment) -> WORK/ID/: captions.json, listen.m4a, verbatim.txt, clean.txt
  notes.py join OUT PART [PART ...] [--sha256 HEX]  rebuild a long recording from its Drive "Parts" pieces
  notes.py apply WORK/ID EDITS.json [--vocab FILE]  bake the studio's word corrections in (re-timed), rev+1, remap for the app
  notes.py render WORK/ID EDITS.json               render the requested video (+ .srt) with the studio's look
  notes.py ref FILE                                file reference for the Drive connector's create_file (no bytes through chat)

Drive layout (inside "Voice Notes Inbox"):
  <recordings>.m4a            the phone app's uploads (Parts/ holds <=9 MB pieces of long ones)
  Captions/ID.captions.json   written here: {v, audioId, title, recordedAt, duration, rev, listen, video, remap, data}
  Captions/ID.mp4, ID.srt     rendered on request
  Captions/vocabulary.txt     names and terms for the transcriber (grows from corrections)
  Listening copies/ID.m4a     small copy that Notion's audio player fetches (folder shared by link)
  Studio/ID.edits.json        written by the app: {base, params, fixes, render}
"""
import argparse, difflib, hashlib, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("VN_WORK", "/home/claude/vn")
VC = os.path.join(HERE, "vc.py")
NOTION_MAX = 5 * 1024 * 1024  # Notion free workspaces fetch files up to 5 MiB


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


def describe(meta, notion=None, video_id=None, srt_id=None):
    """Short JSON for the Drive file description of ID.captions.json; the app's Library reads it without downloading."""
    m = {"rev": meta.get("rev", 1), "title": meta.get("title"), "duration": round(meta.get("duration", 0))}
    if notion: m["notion"] = notion
    if video_id: m.update(videoId=video_id, videoAt=(meta.get("video") or {}).get("at", 0), srtId=srt_id)
    return json.dumps(m, separators=(",", ":"))


def cmd_prepare(a):
    d = os.path.join(WORK, a.id)
    os.makedirs(d, exist_ok=True)
    prompt = vocab_prompt(a.vocab)
    t0 = time.time()
    sh(sys.executable, VC, "run", a.audio, "--out", d, *(["--prompt", prompt] if prompt else []))
    data = json.load(open(f"{d}/data.json"))
    words = data["words"]
    verb, clean = texts(words)
    open(f"{d}/verbatim.txt", "w").write(verb)
    open(f"{d}/clean.txt", "w").write(clean)
    dur = data.get("duration") or words[-1]["e"]
    fits = listening_copy(a.audio, f"{d}/listen.m4a", dur)
    meta = {"audioId": a.id, "title": a.title, "recordedAt": a.recorded, "duration": dur, "rev": 1, "listen": None, "video": None, "remap": None}
    write_captions(d, meta, data)
    out = {"dir": d, "words": len(words), "fillers": sum(1 for w in words if w.get("fl")), "clean_words": len(clean.split()),
           "duration_min": round(dur / 60, 2), "minutes_taken": round((time.time() - t0) / 60, 1),
           "captions_ref": ref(f"{d}/captions.json"), "captions_bytes": os.path.getsize(f"{d}/captions.json"),
           "listen_ref": ref(f"{d}/listen.m4a"), "listen_bytes": os.path.getsize(f"{d}/listen.m4a"), "listen_fits_notion": fits,
           "description": describe(meta)}
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


def cmd_render(a):
    d = a.dir
    E = json.load(open(a.edits))
    req = E.get("render") or {}
    params = req.get("params") or E.get("params") or {}
    json.dump(params, open(f"{d}/params.json", "w"))
    sh(sys.executable, VC, "render", d, "--params", f"{d}/params.json")
    sh(sys.executable, VC, "srt", d)
    cap = json.load(open(f"{d}/captions.json"))
    meta = {k: v for k, v in cap.items() if k not in ("data", "v")}
    meta["video"] = {"at": req.get("at") or int(time.time() * 1000), "params": params}
    write_captions(d, meta, cap["data"])
    mp4 = f"{d}/voicecap_full.mp4"
    print(json.dumps({"mp4_ref": ref(mp4), "mp4_mb": round(os.path.getsize(mp4) / 1e6, 1), "srt_ref": ref(f"{d}/captions.srt"),
                      "captions_ref": ref(f"{d}/captions.json")}, indent=1))


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
    elif a.cmd == "ref":
        print(ref(a.file))


if __name__ == "__main__":
    main()
