#!/usr/bin/env python3
"""voicecap v2: voice memo -> expressive kinetic captions (live player + YouTube MP4).

  vc.py setup                          install deps, speech model, fonts (once per session)
  vc.py run AUDIO --out DIR [opts]     prepare + transcribe + analyze (letters, envelopes, function words)
  vc.py fix DIR --text corrected.txt   replace transcript words, keep timings
  vc.py concepts DIR --file c.json     color key concepts by theme
  vc.py player DIR [--params p.json]   build DIR/player/ (index.html, audio.mp4, data.json)
  vc.py render DIR [--params p.json] [--start S --dur D] [--out file.mp4]
  vc.py text DIR | vc.py srt DIR       plain transcript | captions.srt for YouTube
  vc.py thumb DIR --spec s.json [--out f.png] [--data captions.json]   the studio's thumbnail as a PNG
"""
import argparse, base64, difflib, hashlib, json, math, os, re, shutil, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# the drawing engine is shared with the phone app's studio page, so it lives at the repo root
ENGINE = next(p for p in (os.path.join(HERE, "engine.js"), os.path.join(HERE, "..", "engine.js")) if os.path.exists(p))
MODEL_DIR = os.path.expanduser("~/.cache/voicecap/whisper-small")
NPM = "https://registry.npmjs.org/@skillninja/shortmovie-telop-model-p{i}/-/shortmovie-telop-model-p{i}-1.0.0.tgz"
NPM_SHA512 = [
    "mbI7QraPOHdI8bSLHV+QpTJ4FGB9+JMRFzPqL40FuqHR5gbLslQhXdph1dIJsZinz1WrzoPN5AdAzfw4aAz/Gg==",
    "t6TNxvNeJcqXIazyw3gKlw/OgNlDxtkaCthho3rcd0aLETMFTnpjspPet8CGACyhLO2XYh3PxNkehsA6PZUPDA==",
    "k5GgG+xSLyXmp55tuUgy7ftLMOre0G+Bdy/8+FbGNngwr9uBY1ObOmsbtHogyTGBaSanN5TU9Gl+u8bAHYJWuw==",
    "0awk1t9YzTjFj33z6ktzBwmWyq4xtAP3hAGsrjXaUzf8bwoOx3o3WFlkBsE7526uCSpFwIudi1ziTEPPdT9hKQ==",
]
MODEL_SHA256 = "ca732cb1379efc49417d028465f543d83a39de2c61f3027678de103dc404ce73"
SR = 16000
HOP = 160  # 10 ms analysis frames
ALIGN_TOL = 1.2  # s: a forced-alignment placement further than this from its checked timing is rejected (see fix)


FONT_SHA = "cc5661d43cd4f9aad5567033a8e15ca28dc35c86"
FONT_FILES = {  # family -> path in github.com/google/fonts (variable TTFs)
    "EB Garamond": "ofl/ebgaramond/EBGaramond[wght].ttf",
    "Newsreader": "ofl/newsreader/Newsreader[opsz,wght].ttf",
    "Fraunces": "ofl/fraunces/Fraunces[SOFT,WONK,opsz,wght].ttf",
    "Source Serif 4": "ofl/sourceserif4/SourceSerif4[opsz,wght].ttf",
    "Hanken Grotesk": "ofl/hankengrotesk/HankenGrotesk[wght].ttf",
    "Inter": "ofl/inter/Inter[opsz,wght].ttf",
    "DM Sans": "ofl/dmsans/DMSans[opsz,wght].ttf",
    "Bricolage Grotesque": "ofl/bricolagegrotesque/BricolageGrotesque[opsz,wdth,wght].ttf",
}
FONT_DIR = os.path.expanduser("~/.cache/voicecap/fonts")
CHROME_CANDIDATES = ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]


def chrome_path():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return p.chromium.executable_path if os.path.exists(p.chromium.executable_path) else None
    except Exception:
        return None


def setup_fonts_and_browser():
    os.makedirs(FONT_DIR, exist_ok=True)
    for fam, path in FONT_FILES.items():
        dest = os.path.join(FONT_DIR, os.path.basename(path))
        if os.path.exists(dest) and os.path.getsize(dest) > 20000:
            continue
        url = f"https://raw.githubusercontent.com/google/fonts/{FONT_SHA}/" + path.replace("[", "%5B").replace("]", "%5D")
        sh(["curl", "-sSf", "-o", dest, url])
    try:
        import pocketsphinx  # noqa
    except ImportError:
        sh([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "pocketsphinx>=5.1"])
    try:
        import playwright  # noqa
    except ImportError:
        sh([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "playwright"])
    if not chrome_path():
        sys.exit("no Chrome/Chromium found for the video renderer")


# ---------------------------------------------------------------- analysis v2 helpers
FUNCTION_WORDS = set("""a an the and or but nor so yet for of in on at to from by with without within about into onto over under
than then as if that this these those there here it its it's is are was were be been being am do does did done have has had having
will would shall should can could may might must not no i me my mine myself you your yours yourself he him his she her hers we us our
ours they them their theirs what which who whom whose when where why how all any some such very just also too really like um uh oh
well kind sort lot gonna wanna i'm you're it's that's there's i've i'll i'd don't doesn't didn't isn't aren't wasn't weren't can't
won't wouldn't couldn't shouldn't let's maybe actually even more most much many each every one own other another same okay yeah right
you've you'd we're they're he's she's what's here's who's thing things something anything stuff get got go going know mean say said
up out off down just quite rather sometimes always never often because while though although whether either neither both""".split())
DIGRAPHS = ("th", "sh", "ch", "ph", "wh", "ck", "ng", "gh", "qu")
VOWELS = set("aeiouy")
SONORANT = set("lrmnwy")
FRIC = set("sfvzhj")
CLASS_TARGET = {"V": 1.0, "S": 0.6, "F": 0.22, "P": 0.08}


def _units(word):
    """Split a word into grapheme units [(class, [char idx...])]; non-letters attach to the previous unit."""
    s = word.lower()
    units, i = [], 0
    while i < len(s):
        ch = s[i]
        if not ch.isalpha():
            if units:
                units[-1][1].append(i)
            else:
                units.append(["X", [i]])
            i += 1
            continue
        if ch in "aeiou" or (ch == "y" and not (i == 0 and i + 1 < len(s) and s[i + 1] in "aeiou")):
            j = i
            while j < len(s) and s[j] in VOWELS:
                j += 1
            units.append(["V", list(range(i, j))]); i = j
            continue
        two = s[i:i + 2]
        if two in DIGRAPHS:
            cls = "S" if two == "ng" else ("F" if two in ("th", "sh", "ph", "gh") else "P")
            if two == "wh":
                cls = "S"
            if two == "qu":
                cls = "P"
            units.append([cls, [i, i + 1]]); i += 2
            continue
        cls = "S" if ch in SONORANT else ("F" if ch in FRIC else "P")
        units.append([cls, [i]]); i += 1
    # silent final e
    letters = [u for u in units if u[0] != "X"]
    if len(letters) >= 3 and letters[-1][0] == "V" and s[letters[-1][1][0]:letters[-1][1][-1] + 1] == "e" \
            and sum(1 for u in letters if u[0] == "V") >= 2:
        letters[-1][0] = "E"
    return units


def _align_word(units, son):
    """Monotonic DP: each unit gets >=1 frame; vowels sit on sonorous frames. Returns frame start per unit."""
    M, N = len(units), len(son)
    tgt = np.array([CLASS_TARGET.get(c, 0.3) if c != "E" else 0.3 for c, _ in units])
    if N < M:
        return [int(round(k * N / M)) for k in range(M)]
    o = son
    if o.max() - o.min() > 1e-6:
        o = (o - o.min()) / (o.max() - o.min())
    cost = np.abs(o[:, None] - tgt[None, :])
    cost[:, [k for k, (c, _) in enumerate(units) if c == "E"]] += 0.4  # silent e: as short as possible
    dp = np.full((N, M), np.inf); bk = np.zeros((N, M), int)
    dp[0, 0] = cost[0, 0]
    for f in range(1, N):
        stay = dp[f - 1]
        move = np.concatenate([[np.inf], dp[f - 1, :-1]])
        better = move < stay
        dp[f] = np.where(better, move, stay) + cost[f]
        bk[f] = np.where(better, 1, 0)
    starts, u = [0] * M, M - 1
    for f in range(N - 1, 0, -1):
        if bk[f, u]:
            starts[u] = f; u -= 1
            if u == 0:
                break
    return starts


def _b64u8(arr):
    return base64.b64encode(np.asarray(arr, np.uint8).tobytes()).decode()


def letters_and_envelopes(W, st, db, floor):
    """Adds per-letter timing/loudness/pitch to words; returns 50 Hz envelopes (base64 uint8)."""
    p97 = np.percentile(db[db > floor + 8], 97) if np.any(db > floor + 8) else floor + 30
    loud = np.clip((db - floor) / max(1e-3, p97 - floor), 0, 1)
    voiced = ~np.isnan(st)
    son = loud * (0.4 + 0.6 * voiced)
    nF = len(st)
    for w in W:
        text = w["w"].strip()
        a = min(nF - 1, int(w["s"] * 100)); b = max(a + 1, min(nF, int(round(w["e"] * 100))))
        units = _units(text)
        letter_units = [u for u in units if u[0] != "X"] or units
        starts = _align_word(letter_units, son[a:b])
        onset = [0] * len(text); cls = ["X"] * len(text); amp = [0] * len(text); pit = [0] * len(text)
        kmap = {id(u): k for k, u in enumerate(letter_units)}
        for u in units:
            if id(u) not in kmap:
                f0, f1 = 0, 1
            else:
                k = kmap[id(u)]
                f0 = starts[k]; f1 = max(f0 + 1, starts[k + 1] if k + 1 < len(starts) else (b - a))
            seg_l = loud[a + f0:a + f1]; seg_p = st[a + f0:a + f1]
            pk = int(round(255 * float(seg_l.max()))) if len(seg_l) else 0
            pp = seg_p[~np.isnan(seg_p)]
            pv = int(np.clip(round(float(np.median(pp)) * 8) + 128, 1, 255)) if len(pp) else 0
            for ci in u[1]:
                onset[ci] = f0 * 10; cls[ci] = u[0]; amp[ci] = pk; pit[ci] = pv
        for ci, ch in enumerate(text):  # punctuation inherits previous char timing
            if not ch.isalpha():
                cls[ci] = "X"
                if ci > 0:
                    onset[ci] = onset[ci - 1]; amp[ci] = amp[ci - 1]; pit[ci] = pit[ci - 1]
        sy, prev = [0], None  # syllables: a vowel after the first takes the consonant unit right before it
        seen_v = False
        for u in letter_units:
            if u[0] == "V":
                if seen_v:
                    start = prev[1][0] if prev is not None and prev[0] in "SFP" else u[1][0]
                    if start > sy[-1]:
                        sy.append(start)
                seen_v = True
            prev = u
        w.update({"lo": onset, "lc": "".join(cls), "la": amp, "lp": pit, "sy": sy,
                  "fn": re.sub(r"[^\w']", "", text.lower()) in FUNCTION_WORDS})
    # 50 Hz envelopes
    l50 = np.convolve(loud, np.ones(3) / 3, mode="same")[::2]
    s50 = st[::2]
    p8 = np.where(np.isnan(s50), 0, np.clip(np.round(np.nan_to_num(s50) * 8) + 128, 1, 255))
    return {"hz": 50, "loud": _b64u8(np.round(l50 * 255)), "pitch": _b64u8(p8)}


def apply_concepts(out, spec):
    """spec: {"themes":[{"name":..}], "terms":[{"term":"archetype","theme":"Soul-making"}, ...]}"""
    D = json.load(open(f"{out}/data.json"))
    themes = [t["name"] if isinstance(t, dict) else t for t in spec.get("themes", [])]
    for t in spec.get("terms", []):
        if t["theme"] not in themes:
            themes.append(t["theme"])
    norm = lambda s: re.sub(r"'s$", "", re.sub(r"[^\w'-]", "", s.lower()))

    def stem(x):
        for suf in ("ically", "ality", "ness", "ally", "ical", "ings", "ing", "ies", "ied", "es", "ed", "al", "ly", "s", "e", "y"):
            if x.endswith(suf) and len(x) - len(suf) >= 4:
                return x[: -len(suf)]
        return x
    terms = []
    for t in spec.get("terms", []):
        toks = [stem(norm(x)) for x in t["term"].split()]
        terms.append((toks, themes.index(t["theme"])))
    terms.sort(key=lambda x: -len(x[0]))
    W = D["words"]
    toks = [stem(norm(w["w"])) for w in W]
    for w in W:
        w.pop("th", None)
    hits = 0
    for i in range(len(W)):
        for tt, th in terms:
            if toks[i:i + len(tt)] == tt and all("th" not in W[j] for j in range(i, i + len(tt))):
                for j in range(i, i + len(tt)):
                    W[j]["th"] = th; W[j]["fn"] = False
                hits += 1
                break
    D["themes"] = themes
    json.dump(D, open(f"{out}/data.json", "w"), separators=(",", ":"))
    log(f"concepts: {len(themes)} themes, {hits} term hits across {sum(1 for w in W if 'th' in w)} words")


def log(*a):
    print(*a, flush=True)


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


# ---------------------------------------------------------------- setup
def setup(_=None):
    try:
        import faster_whisper  # noqa
    except ImportError:
        sh([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "faster-whisper"])
    setup_fonts_and_browser()
    mb = os.path.join(MODEL_DIR, "model.bin")
    if os.path.exists(mb) and os.path.getsize(mb) > 2e8:
        log("setup ok (model cached)")
        return
    os.makedirs(MODEL_DIR, exist_ok=True)
    tmp = os.path.join(MODEL_DIR, "dl")
    os.makedirs(tmp, exist_ok=True)
    procs = [subprocess.Popen(["curl", "-sSf", "-o", f"{tmp}/p{i}.tgz", NPM.format(i=i)]) for i in range(4)]
    if any(p.wait() for p in procs):
        sys.exit("model download failed (npm registry unreachable?)")
    for i in range(4):
        dg = base64.b64encode(hashlib.sha512(open(f"{tmp}/p{i}.tgz", "rb").read()).digest()).decode()
        if dg != NPM_SHA512[i]:
            sys.exit(f"integrity mismatch on model part {i}; refusing to use it")
        sh(["tar", "xzf", f"{tmp}/p{i}.tgz", "-C", tmp])
        for f in os.listdir(f"{tmp}/package"):
            if f.endswith((".json",)) and f != "package.json":
                shutil.copy(f"{tmp}/package/{f}", MODEL_DIR)
            if f.startswith("model.bin.part"):
                shutil.move(f"{tmp}/package/{f}", f"{tmp}/{f}")
        shutil.rmtree(f"{tmp}/package")
    with open(mb, "wb") as o:
        for i in range(4):
            with open(f"{tmp}/model.bin.part{i}", "rb") as f:
                shutil.copyfileobj(f, o)
    if hashlib.sha256(open(mb, "rb").read()).hexdigest() != MODEL_SHA256:
        os.remove(mb)
        sys.exit("model checksum mismatch")
    shutil.rmtree(tmp)
    log("setup ok (Whisper small int8 installed)")


# ---------------------------------------------------------------- prepare
def probe(path):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,channels",
                                   "-of", "json", path], capture_output=True, text=True).stdout or "{}")
    dur = float(j.get("format", {}).get("duration", 0) or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in j.get("streams", []))
    return dur, has_audio


def prepare(src, out, normalize=True):
    os.makedirs(out, exist_ok=True)
    dur, ok = probe(src)
    if not ok:
        sys.exit("no audio stream found in input")
    log(f"input: {os.path.basename(src)}  {dur/60:.1f} min")
    sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", f"{out}/a16.wav"])
    af = ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"] if normalize else []
    sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", *af, "-ar", "48000", "-ac", "2", "-c:a", "flac", f"{out}/master.flac"])
    kbps = int(max(24, min(64, 19.5 * 8 * 1024 / max(dur, 1))))
    sh(["ffmpeg", "-v", "error", "-y", "-i", f"{out}/master.flac", "-ac", "1", "-c:a", "aac", "-b:a", f"{kbps}k",
        "-movflags", "+faststart", f"{out}/audio.m4a"])
    return dur


def load16(out):
    import wave
    with wave.open(f"{out}/a16.wav") as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0


# ---------------------------------------------------------------- noise reduction
# RNNoise (Valin, 2018) through ffmpeg's arnndn, with the "somnolent-hogwash" model trained for speech under recording noise
# (GregorR/rnnoise-models; the model files are not subject to copyright). On Behnam's car and wind recordings it lowered the
# noise between words by 10-17 dB without hurting transcription (Whisper agreed with the transcript as well or better).
RNN_MODEL = os.path.join(HERE, "models", "sh.rnnn")
CLEAN_LEVELS = ("off", "light", "full")


def clean_chain(level):
    """ffmpeg -af chain for a noise-reduction level. Light keeps some room sound; Full also removes the steady hiss left after RNNoise."""
    m = RNN_MODEL.replace("\\", "/").replace(":", "\\:")
    # cleaning lowers the voice too; speechnorm brings it back up per phrase without lifting the quiet gaps (dynaudnorm did, and
    # undid about 2 dB of the gain)
    level_up = "speechnorm=e=6:r=0.0001:l=1,alimiter=limit=0.95"
    if level == "light":
        return f"highpass=f=80,arnndn=m={m}:mix=0.85,{level_up}"
    if level == "full":
        return f"highpass=f=100,arnndn=m={m},afftdn=nr=10:nf=-50:tn=1,{level_up}"
    return None


def clean_audio(src, level, dest, extra=()):
    """Write SRC with noise reduction LEVEL to DEST (format from its extension; EXTRA = output options such as codec and bitrate)."""
    chain = clean_chain(level)
    sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", *(["-af", chain] if chain else []), *extra, dest])
    return dest


def noise_level(x, words=None, sr=SR):
    """How much louder the voice is than the background, in dB (higher is cleaner), and the cleaning level that suits it.
    With word timings: speech frames against the gaps between words (at least 0.2 s from any word). Without (before
    transcription): a rough estimate from the spread of loudness, mapped onto about the same scale."""
    hop = sr // 50
    n = len(x) // hop
    db = 10 * np.log10((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-10)
    fps = sr / hop
    if words:
        sp = np.zeros(n, bool); near = np.zeros(n, bool)
        for w in words:
            a, b = int(w["s"] * fps), int(w["e"] * fps) + 1
            sp[a:b] = True; near[max(0, a - int(0.2 * fps)):b + int(0.2 * fps)] = True
        if sp.sum() > 50 and (~near).sum() > 50:
            snr = float(np.median(db[sp]) - np.median(db[~near]))
            return round(snr, 1), ("full" if snr < 8 else "light" if snr < 16 else "off")
    spread = float(np.percentile(db, 95) - np.percentile(db, 15))
    return round(spread - 10, 1), ("full" if spread < 17 else "light" if spread < 25 else "off")


# ---------------------------------------------------------------- transcribe
def transcribe(out, lang=None, prompt=None, quality="accurate"):
    from faster_whisper import WhisperModel
    audio = load16(out)
    dur = len(audio) / SR
    model = WhisperModel(MODEL_DIR, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 2)
    t0 = time.time()
    # a filler-style prompt makes Whisper write um/uh, so their sound gets its own timestamps instead of stretching neighbours;
    # PROMPT carries the person's vocabulary (names, terms) so they are spelled right
    fp = "Umm, let me think like, hmm... Okay, here's what I'm, like, thinking. Uh, so, um,"
    hot = "Um, uh, hmm" + (" " + prompt if prompt else "")
    if quality == "fast":  # quick draft: greedy, skips silences, no carried context (can drop words)
        kw = dict(beam_size=1, vad_filter=True, vad_parameters={"min_silence_duration_ms": 500}, condition_on_previous_text=False)
    else:  # accurate (default): beam search over the whole recording, context carried between segments;
        # on a 6-min memo this recovered phrases the fast settings dropped (a silence-skipping option dropped a word, so it is off)
        kw = dict(beam_size=5, vad_filter=False, condition_on_previous_text=True)
    segs, info = model.transcribe(audio, language=lang, initial_prompt=fp + (" " + prompt if prompt else ""), hotwords=hot,
                                  word_timestamps=True, **kw)
    words, last = [], 0
    for s in segs:
        for w in s.words or []:
            words.append({"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)})
        if s.end - last > 30 or s.end >= dur - 1:
            last = s.end
            el = time.time() - t0
            log(f"transcribe {100*s.end/dur:5.1f}%  ({el/60:.1f} min elapsed, ~{el*(dur/max(s.end,1)-1)/60:.1f} min left)")
    log(f"transcribed {len(words)} words, language={info.language}, {(time.time()-t0)/60:.1f} min")
    if quality != "fast":  # the whole-recording pass can slide its timestamps across long pauses; pin them to a pass that skips silence
        prop, moved = reanchor(words, anchor_pass(audio, info.language, model))
        words, rep = arbitrate(words, prop, moved, audio, model, info.language)
        json.dump(rep, open(f"{out}/timing_report.json", "w"))
    json.dump({"duration": dur, "lang": info.language, "words": words}, open(f"{out}/words.json", "w"))
    shutil.copy(f"{out}/words.json", f"{out}/words.whisper.json")  # anchors for later fixes


def anchor_pass(audio, lang=None, model=None):
    """A quick second transcription with silences cut out (VAD). Each stretch of speech is timed on its own, so its timestamps
    cannot drift through a long pause the way a whole-recording pass can (seen: up to 20 s on a 36-min walk). Used for timing only."""
    if model is None:
        from faster_whisper import WhisperModel
        model = WhisperModel(MODEL_DIR, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 2)
    t0 = time.time()
    segs, _ = model.transcribe(audio, language=lang, beam_size=1, condition_on_previous_text=False, word_timestamps=True,
                               vad_filter=True, vad_parameters={"min_silence_duration_ms": 700, "speech_pad_ms": 300})
    ref = [{"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in (s.words or [])]
    log(f"timing pass: {len(ref)} words, {(time.time()-t0)/60:.1f} min")
    return ref


def reanchor(words, ref, tol=0.8):
    """Move words whose time disagrees with the timing pass REF. A word moves when it and most of its matched neighbours are off
    by more than TOL seconds (so one common word matched to the wrong place moves nothing). Words REF lacks, next to a moved
    stretch, are spread between their moved neighbours. Text is untouched; returns (words, number moved)."""
    import bisect
    sm = difflib.SequenceMatcher(a=[_norm(w["w"]) for w in words], b=[_norm(w["w"]) for w in ref], autojunk=False)
    m = {}
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for q in range(i2 - i1):
                m[i1 + q] = j1 + q
    keys = sorted(m)
    off = [ref[m[i]]["s"] - words[i]["s"] for i in keys]
    out = [dict(w) for w in words]
    moved = set()
    for k, i in enumerate(keys):
        nb = sorted(abs(x) for x in off[max(0, k - 3):k + 4])
        if abs(off[k]) > tol and nb[len(nb) // 2] > tol:
            r = ref[m[i]]; out[i]["s"], out[i]["e"] = r["s"], r["e"]; moved.add(i)
    for _ in range(3):  # a matched word left just under TOL can end up out of order with moved neighbours: move it too
        for k, i in enumerate(keys):
            if i in moved:
                continue
            p = keys[k - 1] if k > 0 else None; q = keys[k + 1] if k + 1 < len(keys) else None
            if (p in moved and out[p]["s"] > out[i]["s"]) or (q in moved and out[q]["s"] < out[i]["s"]):
                r = ref[m[i]]; out[i]["s"], out[i]["e"] = r["s"], r["e"]; moved.add(i)
    n, i = len(words), 0
    while i < n:  # runs of unmatched words
        if i in m:
            i += 1; continue
        j = i
        while j < n and j not in m:
            j += 1
        k = bisect.bisect_left(keys, i)
        a = keys[k - 1] if k > 0 else None
        b = keys[k] if k < len(keys) else None
        if (a in moved) or (b in moved):
            t0 = out[a]["e"] if a is not None else 0.0
            t1 = out[b]["s"] if b is not None else max(t0, words[-1]["e"])
            if t1 < t0 + 0.05 * (j - i):
                t1 = t0 + 0.05 * (j - i)
            step = (t1 - t0) / (j - i)
            for q in range(i, j):
                out[q]["s"], out[q]["e"] = round(t0 + step * (q - i), 3), round(t0 + step * (q - i + 1), 3)
                moved.add(q)
        i = j
    for q in range(1, n):  # keep order
        if out[q]["s"] < out[q - 1]["s"]:
            out[q]["s"] = out[q - 1]["s"]; out[q]["e"] = max(out[q]["e"], out[q]["s"] + 0.03)
    return out, moved


VOICED_RATE_MAX = 7.0  # words per second: faster than this is not speech, it is a timing error


def _voiced(x):
    fr = x[: len(x) // HOP * HOP].reshape(-1, HOP)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    return db > np.percentile(db, 15) + 8  # per 10 ms frame


def _acoustic_fit(x, toks, t0, t1, dec):
    """Mean acoustic score per frame when TOKS are forced onto x[t0:t1] (higher = the words fit the sound better), or None."""
    words = []
    for t in toks:
        for dw in _dict_words(t):
            if not dec.lookup_word(dw):
                dec.add_word(dw, _g2p(dw), True)
            words.append(dw)
    if not words or t1 - t0 < 0.3:
        return None
    pcm = (np.clip(x[max(0, int(t0 * SR)):int(t1 * SR)], -1, 1) * 32767).astype(np.int16).tobytes()
    try:
        dec.set_align_text(" ".join(words))
        dec.start_utt(); dec.process_raw(pcm, full_utt=True); dec.end_utt()
        dec.set_alignment()
        dec.start_utt(); dec.process_raw(pcm, full_utt=True); dec.end_utt()
        ws = [a for a in dec.get_alignment() if not a.name.startswith(("<", "[", "+"))]
    except Exception:
        return None
    fr = sum(a.duration for a in ws)
    return sum(a.score for a in ws) / fr if len(ws) == len(words) and fr else None


def arbitrate(words, prop, moved, x, model, lang=None, tol=0.8):
    """Decide, stretch by stretch, whether the timing pass's proposal (PROP) or the original timing (WORDS) is right.
    Cheapest evidence first: (1) physical rules, (2) a fresh transcription of just that window, (3) the forced aligner's
    acoustic fit at both positions. When nothing is confident the original stays and the stretch is reported for a check."""
    n = len(words); out = [dict(w) for w in words]
    idx = sorted(i for i in moved if abs(prop[i]["s"] - words[i]["s"]) > 0.05)
    runs, cur = [], []
    for i in idx:  # stretches: moved words with at most 2 unmoved words between them
        if cur and i - cur[-1] > 3:
            runs.append(cur); cur = []
        cur.append(i)
    if cur: runs.append(cur)
    runs = [r[c:c + 25] for r in runs for c in range(0, len(r), 25)]  # long stretches are judged in pieces of up to 25 words
    act = _voiced(x); dur = len(x) / SR
    vfrac = lambda a, b: float(act[int(a * 100):max(int(a * 100) + 1, int(b * 100))].mean()) if b > a else 0.0
    rep = {"stretches": 0, "rule": 0, "listen": 0, "aligner": 0, "small": 0, "kept": 0, "check": []}
    dec = None
    for r in runs:
        i, j = r[0], r[-1] + 1
        shift = max(abs(prop[k]["s"] - words[k]["s"]) for k in range(i, j))
        if shift <= tol:  # small refinements need no proof
            for k in range(i, j): out[k] = dict(prop[k])
            rep["small"] += 1; continue
        rep["stretches"] += 1
        m = j - i
        os_, oe, ps, pe = words[i]["s"], words[j - 1]["e"], prop[i]["s"], prop[j - 1]["e"]
        orate, prate = m / max(oe - os_, 0.05), m / max(pe - ps, 0.05)
        verdict, how, times = None, None, None
        # (1) rules: impossible speech rates, words placed in silence, a proposal with stacked (zero-length) words
        stacked = sum(1 for k in range(i, j) if prop[k]["e"] - prop[k]["s"] < 0.03) >= 0.5 * m
        if m >= 4 and prate > VOICED_RATE_MAX and orate <= VOICED_RATE_MAX: verdict = "orig"
        elif m >= 4 and orate > VOICED_RATE_MAX and prate <= VOICED_RATE_MAX: verdict = "prop"
        elif stacked: verdict = "orig"
        else:
            vo, vp = vfrac(os_, oe), vfrac(ps, pe)
            if vp < 0.2 and vo > 0.5: verdict = "orig"
            elif vo < 0.2 and vp > 0.5: verdict = "prop"
        if verdict: how = "rule"
        # (2) listen again: transcribe only this window (short, so it can neither drift nor skip a pause)
        if not verdict:
            w0, w1 = max(0.0, min(os_, ps) - 2), min(dur, max(oe, pe) + 2)
            if w1 - w0 <= 60:
                segs, _ = model.transcribe(x[int(w0 * SR):int(w1 * SR)], language=lang, beam_size=5, word_timestamps=True,
                                           condition_on_previous_text=False, vad_filter=False)
                loc = [{"w": w.word, "s": w0 + w.start, "e": w0 + w.end} for sg in segs for w in (sg.words or [])]
                sm = difflib.SequenceMatcher(a=[_norm(words[k]["w"]) for k in range(i, j)], b=[_norm(w["w"]) for w in loc], autojunk=False)
                pairs = [(i + a + q, b + q) for a, b, size in sm.get_matching_blocks() for q in range(size)]
                if len(pairs) >= max(3, 0.3 * m):
                    do = sorted(abs(loc[b]["s"] - words[k]["s"]) for k, b in pairs)[len(pairs) // 2]
                    dp = sorted(abs(loc[b]["s"] - prop[k]["s"]) for k, b in pairs)[len(pairs) // 2]
                    if dp < 1.0 and do > max(2.0, 2 * dp): verdict, how = "prop", "listen"
                    elif do < 1.0 and dp > max(2.0, 2 * do): verdict, how = "orig", "listen"
                    if verdict == "prop":  # use the fresh pass's times; spread words it lacks between their neighbours
                        times = {k: (loc[b]["s"], loc[b]["e"]) for k, b in pairs}
        # (3) tie-breaker: how well do these exact words fit the sound at each position (equal-length windows)?
        if not verdict:
            if dec is None:
                from pocketsphinx import Decoder
                dec = Decoder(samprate=SR, bestpath=False, loglevel="FATAL", beam=1e-100, wbeam=1e-80, pbeam=1e-100)
            L = max(oe - os_, pe - ps) + 1.5
            toks = [words[k]["w"].strip() for k in range(i, j)]
            fo, fp = _acoustic_fit(x, toks, os_ - 0.75, os_ - 0.75 + L, dec), _acoustic_fit(x, toks, ps - 0.75, ps - 0.75 + L, dec)
            if fo is not None and fp is not None:
                if fp > fo and fo / fp > 1.4: verdict, how = "prop", "aligner"
                elif fo > fp and fp / fo > 1.4: verdict, how = "orig", "aligner"
        if verdict == "prop":
            if times:
                known = sorted(times)
                for k in range(i, j):
                    if k in times: out[k]["s"], out[k]["e"] = round(times[k][0], 3), round(times[k][1], 3)
                lo = out[i - 1]["e"] if i > 0 else 0.0
                k = i
                while k < j:
                    if k in times: k += 1; continue
                    q = k
                    while q < j and q not in times: q += 1
                    a = out[k - 1]["e"] if k > i or i > 0 else lo
                    b = out[q]["s"] if q < n and (q in times or q >= j) else a + 0.3 * (q - k)
                    if b < a + 0.05 * (q - k): b = a + 0.05 * (q - k)
                    st = (b - a) / (q - k)
                    for z in range(k, q): out[z]["s"], out[z]["e"] = round(a + st * (z - k), 3), round(a + st * (z - k + 1), 3)
                    k = q
            else:
                for k in range(i, j): out[k] = dict(prop[k])
            rep[how] += 1
        else:
            if verdict == "orig": rep[how] += 1
            else:
                rep["kept"] += 1; rep["check"].append([round(os_, 1), round(oe, 1)])
    for q in range(1, n):  # keep order
        if out[q]["s"] < out[q - 1]["s"]:
            out[q]["s"] = out[q - 1]["s"]; out[q]["e"] = max(out[q]["e"], out[q]["s"] + 0.03)
    log(f"timing check: {rep['stretches']} disputed stretches — settled by rules {rep['rule']}, by a fresh listen {rep['listen']}, "
        f"by the aligner {rep['aligner']}; {rep['kept']} left as they were for a check" + (f" at {rep['check']}" if rep["check"] else ""))
    return out, rep


def retime(out):
    """Re-time an existing transcript in OUT (words.json + a16.wav, e.g. after notes.py restore) without changing its words:
    timing pass -> reanchor -> forced alignment. Word count and order stay the same, so studio edits keep their word indices."""
    J = json.load(open(f"{out}/words.json"))
    keep = [{k: w[k] for k in ("th", "fn", "wh") if k in w} for w in J["words"]]
    themes = None
    if os.path.exists(f"{out}/data.json"):
        themes = json.load(open(f"{out}/data.json")).get("themes")
    toks = [w["w"].strip() for w in J["words"]]
    base = [{"w": w["w"], "s": w["s"], "e": w["e"], "p": w.get("p", 1)} for w in J["words"]]
    from faster_whisper import WhisperModel
    model = WhisperModel(MODEL_DIR, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 2)
    x = load16(out)
    prop, moved = reanchor(base, anchor_pass(x, J.get("lang"), model))
    anchored, rep = arbitrate(base, prop, moved, x, model, J.get("lang"))
    json.dump(rep, open(f"{out}/timing_report.json", "w"))
    json.dump(dict(J, words=anchored), open(f"{out}/words.whisper.json", "w"))
    clean = open(f"{out}/clean.txt").read() if os.path.exists(f"{out}/clean.txt") else None
    fix(out, " ".join(toks), clean)
    D = json.load(open(f"{out}/data.json"))
    if len(D["words"]) == len(keep):  # theme tags and display forms carry over by index
        for w, k in zip(D["words"], keep):
            for f in ("th", "wh"):
                if f in k: w[f] = k[f]
            if "th" in k: w["fn"] = False
        if themes: D["themes"] = themes
        json.dump(D, open(f"{out}/data.json", "w"), separators=(",", ":"))
    return rep


# ---------------------------------------------------------------- prosody
def frames_features(x):
    """10 ms frames: f0 (Hz, nan if unvoiced), rms dB, spectral centroid (Hz). YIN, numpy only."""
    W, tmin, tmax = 1024, SR // 500, SR // 60
    L = W - tmax
    n = 1 << int(math.ceil(math.log2(W + L)))
    x = np.concatenate([x, np.zeros(W)])
    N = (len(x) - W) // HOP
    f0 = np.full(N, np.nan, np.float32); db = np.zeros(N, np.float32); cen = np.zeros(N, np.float32)
    win = np.hanning(W).astype(np.float32)
    freqs = np.fft.rfftfreq(W, 1 / SR)
    taus = np.arange(tmax + 1)
    for a in range(0, N, 3000):
        b = min(N, a + 3000)
        idx = (np.arange(a, b) * HOP)[:, None] + np.arange(W)[None, :]
        fr = x[idx]
        F = np.fft.rfft(fr, n)
        acf = np.fft.irfft(np.conj(np.fft.rfft(fr[:, :L], n)) * F, n)[:, : tmax + 1]
        c = np.concatenate([np.zeros((len(fr), 1), np.float32), np.cumsum(fr ** 2, 1)], 1)
        e0 = c[:, L][:, None]
        et = c[:, taus + L] - c[:, taus]
        d = np.maximum(e0 + et - 2 * acf, 0)
        d[:, 0] = 0
        cm = np.cumsum(d[:, 1:], 1)
        cmnd = np.ones_like(d)
        cmnd[:, 1:] = d[:, 1:] * taus[1:] / np.maximum(cm, 1e-12)
        seg = cmnd[:, tmin:tmax]
        below = seg < 0.15
        first = np.where(below.any(1), below.argmax(1), seg.argmin(1))
        # walk to local minimum
        for _ in range(6):
            nxt = np.minimum(first + 1, seg.shape[1] - 1)
            better = seg[np.arange(len(seg)), nxt] < seg[np.arange(len(seg)), first]
            first = np.where(better, nxt, first)
        ap = seg[np.arange(len(seg)), first]
        t = first + tmin
        tl, tr = np.clip(t - 1, 1, tmax), np.clip(t + 1, 1, tmax)
        yl, yc, yr = cmnd[np.arange(len(t)), tl], cmnd[np.arange(len(t)), t], cmnd[np.arange(len(t)), tr]
        den = yl - 2 * yc + yr
        shift = np.where(np.abs(den) > 1e-9, 0.5 * (yl - yr) / np.where(den == 0, 1, den), 0)
        tt = t + np.clip(shift, -1, 1)
        rms = np.sqrt(e0[:, 0] / L + 1e-12)
        db[a:b] = 20 * np.log10(rms + 1e-9)
        f = SR / tt
        f0[a:b] = np.where(ap < 0.3, f, np.nan)
        S = np.abs(np.fft.rfft(fr * win, W))
        cen[a:b] = (S * freqs).sum(1) / (S.sum(1) + 1e-9)
    floor = np.percentile(db, 15)
    f0[db < floor + 8] = np.nan
    # remove octave blips: median filter on voiced runs
    st = 12 * np.log2(f0 / np.nanmedian(f0))
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.concatenate([[np.nan] * 2, st, [np.nan] * 2])
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        med = np.nanmedian(sliding_window_view(pad, 5), axis=1)
    med[np.isnan(st)] = np.nan
    return med, db, cen, floor


def rz(v):
    v = np.asarray(v, float)
    ok = ~np.isnan(v)
    if ok.sum() < 3:
        return np.zeros_like(v)
    m = np.median(v[ok]); s = 1.4826 * np.median(np.abs(v[ok] - m)) + 1e-6
    return np.where(ok, np.clip((v - m) / s, -3, 3), 0)


def analyze(out):
    J = json.load(open(f"{out}/words.json"))
    x = load16(out)
    t0 = time.time()
    st, db, cen, floor = frames_features(x)
    nF = len(st)
    W = J["words"]
    for w in W:
        if is_filler(w["w"]):
            w["fl"] = True
    if any(w.get("fl") for w in W) and not any("wh" in w for w in W):
        for k, v in _clean_forms([w["w"].strip() for w in W], None).items():
            W[k]["wh"] = " " + v
    pitch, slope, loud, bright, stretch, contour = [], [], [], [], [], []
    act = db > floor + 8
    for k, w in enumerate(W):  # trim trailing silence that Whisper folds into word ends
        a, b = int(w["s"] * 100), min(nF, int(w["e"] * 100))
        on = np.where(act[a:b])[0]
        if len(on):
            e2 = (a + on[-1]) / 100 + 0.06
            if w["e"] - e2 > 0.15:
                w["e"] = round(max(e2, w["s"] + 0.08), 3)
    for k, w in enumerate(W):
        a, b = int(w["s"] * 100), max(int(w["s"] * 100) + 1, int(w["e"] * 100))
        a, b = min(a, nF - 1), min(b, nF)
        s = st[a:b]; ok = ~np.isnan(s)
        if ok.sum() >= 3:
            s = np.clip(s, np.median(s[ok]) - 5, np.median(s[ok]) + 5)
            pitch.append(float(np.median(s[ok])))
            tt = np.arange(len(s))[ok] / 100.0
            slope.append(float(np.clip(np.polyfit(tt, s[ok], 1)[0], -30, 30)) if ok.sum() >= 5 and tt[-1] > 0.05 else 0.0)
            bins = np.array_split(np.arange(len(s)), 6)
            c = [float(np.nanmedian(s[bb])) if np.any(ok[bb]) else np.nan for bb in bins]
            c = np.array(c); good = ~np.isnan(c)
            c = np.interp(np.arange(6), np.where(good)[0], c[good]) if good.any() else np.zeros(6)
            contour.append([round(float(v), 2) for v in c])
        else:
            pitch.append(np.nan); slope.append(0.0); contour.append([])
        p = 10 ** (db[a:b] / 10)
        loud.append(10 * math.log10(p.mean() + 1e-12))
        voiced = db[a:b] > floor + 8
        bright.append(float(np.median(cen[a:b][voiced])) if voiced.any() else np.nan)
        letters = re.sub(r"[^a-zA-Z\u00C0-\u024F]", "", w["w"]).lower()
        syl = max(1, len(re.findall(r"[aeiouy]+", letters)) or max(1, len(w["w"].strip()) // 3))
        stretch.append(math.log(max(0.04, w["e"] - w["s"]) / syl))
    pitch = np.array(pitch)
    zl, zb, zs, zp = rz(loud), rz(bright), rz(stretch), rz(pitch)
    emph = rz(zl + 0.5 * np.nan_to_num(zp) + 0.5 * zs)
    prev = 0.0
    for k, w in enumerate(W):
        w.update({"pitch": None if np.isnan(pitch[k]) else round(float(pitch[k]), 2), "slope": round(slope[k], 2),
                  "contour": contour[k], "loud": round(float(zl[k]), 2), "bright": round(float(zb[k]), 2),
                  "stretch": round(float(zs[k]), 2), "pz": round(float(zp[k]), 2), "emph": round(float(emph[k]), 2),
                  "gap": round(max(0.0, w["s"] - prev), 3)})
        prev = w["e"]
    env = letters_and_envelopes(W, st, db, floor)
    for w in W:
        w.pop("contour", None)
    data = {"version": 2, "duration": J["duration"], "lang": J.get("lang"), "words": W, "env": env}
    json.dump(data, open(f"{out}/data.json", "w"), separators=(",", ":"))
    if os.path.exists(f"{out}/concepts.json"):
        apply_concepts(out, json.load(open(f"{out}/concepts.json")))
    log(f"analyzed prosody for {len(W)} words in {time.time()-t0:.0f}s")


# ---------------------------------------------------------------- fix transcript
FILLER_RE = re.compile(r"^(u+m+|u+h+|e+r+m*|h+m+|m+h*m+|a+h+)$")
_norm = lambda s: re.sub(r"[^\w']", "", s.lower().replace("’", "'"))


def is_filler(tok):
    return bool(FILLER_RE.match(_norm(tok)))


# crude letter-to-sound rules for words missing from the CMU dictionary (good enough to align, not to pronounce)
_G2P = [("tch", "CH"), ("sch", "S K"), ("th", "TH"), ("sh", "SH"), ("ch", "CH"), ("ph", "F"), ("ng", "NG"), ("ck", "K"), ("qu", "K W"),
        ("wh", "W"), ("gh", ""), ("kn", "N"), ("wr", "R"), ("ee", "IY"), ("ea", "IY"), ("oo", "UW"), ("ou", "AW"), ("ow", "OW"),
        ("ai", "EY"), ("ay", "EY"), ("oi", "OY"), ("oy", "OY"), ("au", "AO"), ("aw", "AO"), ("ie", "IY"), ("ei", "EY"), ("oa", "OW"),
        ("tion", "SH AH N"), ("sion", "ZH AH N"), ("ture", "CH ER"), ("er", "ER"), ("ir", "ER"), ("ur", "ER"), ("ar", "AA R"), ("or", "AO R")]
_G1 = {"a": "AE", "e": "EH", "i": "IH", "o": "AA", "u": "AH", "b": "B", "d": "D", "f": "F", "h": "HH", "j": "JH", "k": "K", "l": "L",
       "m": "M", "n": "N", "p": "P", "r": "R", "s": "S", "t": "T", "v": "V", "w": "W", "x": "K S", "z": "Z", "'": ""}
_DIG = "zero one two three four five six seven eight nine".split()


def _g2p(w):
    w = re.sub(r"(.)\1+", r"\1", w)
    if len(w) > 3 and w.endswith("e") and w[-2] not in "aeiou":
        w = w[:-1]
    out, i = [], 0
    rules = sorted(_G2P, key=lambda r: -len(r[0]))
    while i < len(w):
        for g, p in rules:
            if w.startswith(g, i):
                out.append(p); i += len(g); break
        else:
            c = w[i]
            if c == "c":
                out.append("S" if i + 1 < len(w) and w[i + 1] in "eiy" else "K")
            elif c == "g":
                out.append("JH" if i + 1 < len(w) and w[i + 1] in "eiy" and i > 0 else "G")
            elif c == "y":
                out.append("Y" if i == 0 else "IY")
            elif c.isdigit():
                out.append(_DIG[int(c)].upper())  # replaced below
            else:
                out.append(_G1.get(c, ""))
            i += 1
    ph = " ".join(p for p in out if p).split()
    return " ".join(ph) or "AH"


def _dict_words(tok):
    t = tok.lower().replace("’", "'")
    out = []
    for part in re.split(r"[-–—/]+", t):
        part = re.sub(r"[^a-z0-9']", "", part).strip("'")
        if not part:
            continue
        if part.isdigit():
            out += [_DIG[int(c)] for c in part]
        else:
            out.append(part)
    return out


def _silences(x, min_len=0.25):
    fr = x[: len(x) // HOP * HOP].reshape(-1, HOP)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    quiet = db < np.percentile(db, 15) + 8
    out, s = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and s is None:
            s = i
        elif not q and s is not None:
            if i - s >= min_len * 100:
                out.append((s / 100, i / 100))
            s = None
    return out


def force_align(x, tokens, anc_s, anc_e, anchored, chunk_min=10.0, chunk_max=30.0, quiet=False):
    """Align tokens (fillers included) to 16 kHz float audio with PocketSphinx, in chunks cut at silences between anchored words.
    A chunk that fails is split at an inner silence and retried. Returns per-token (start, end) or None."""
    from pocketsphinx import Decoder
    dur = len(x) / SR
    sil = _silences(x, 0.12)

    def cut_at(k, min_gap, min_ov):  # silence between tokens k-1 and k, or None
        if not (anchored[k - 1] and anchored[k]) or is_filler(tokens[k - 1]) or is_filler(tokens[k]):
            return None
        g0, g1 = anc_e[k - 1], anc_s[k]
        if g1 - g0 < min_gap:
            return None
        best = None
        for a, b in sil:
            ov = min(b, g1) - max(a, g0)
            if ov >= min_ov and (best is None or ov > best[1]):
                best = ((max(a, g0) + min(b, g1)) / 2, ov)
        return best[0] if best else None

    strict = [(k, t) for k in range(1, len(tokens)) for t in [cut_at(k, 0.2, 0.15)] if t is not None]
    cuts, last = [(0, 0.0)], 0.0
    for k, t in strict:
        if t - last >= chunk_min and k > cuts[-1][0]:
            cuts.append((k, t)); last = t
    cuts.append((len(tokens), dur))
    dec = Decoder(samprate=SR, bestpath=False, loglevel="FATAL", beam=1e-100, wbeam=1e-80, pbeam=1e-100)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    res = [None] * len(tokens)
    stats = {"ok": 0, "fail": 0}

    def try_align(i0, i1, t0, t1):
        words, owner = [], []
        for k in range(i0, i1):
            for dw in _dict_words(tokens[k]):
                if not dec.lookup_word(dw):
                    dec.add_word(dw, _g2p(dw), True)
                words.append(dw); owner.append(k)
        if not words:
            return True
        buf = pcm[int(t0 * SR):int(t1 * SR)].tobytes()
        try:
            dec.set_align_text(" ".join(words))
            dec.start_utt(); dec.process_raw(buf, full_utt=True); dec.end_utt()
            dec.set_alignment()
            dec.start_utt(); dec.process_raw(buf, full_utt=True); dec.end_utt()
            segs = [(a.name, a.start, a.duration) for a in dec.get_alignment() if not a.name.startswith(("<", "[", "+"))]
        except Exception:
            return False
        if len(segs) != len(words):
            return False
        for (name, st, du), k in zip(segs, owner):
            s, e = t0 + st / 100, t0 + (st + du) / 100
            res[k] = (s, e) if res[k] is None else (res[k][0], e)
        return True

    def span(i0, i1, t0, t1, depth=0):
        if t1 - t0 <= chunk_max or depth >= 4:
            if try_align(i0, i1, t0, t1):
                stats["ok"] += 1; return
            if depth >= 4:
                stats["fail"] += 1; return
        mid = (t0 + t1) / 2
        inner = [(k, t) for k in range(i0 + 1, i1) for t in [cut_at(k, 0.05, 0.06)] if t is not None and t0 + 1 < t < t1 - 1]
        if not inner:
            if t1 - t0 > chunk_max and try_align(i0, i1, t0, t1):
                stats["ok"] += 1
            else:
                stats["fail"] += 1
            return
        k, t = min(inner, key=lambda kt: abs(kt[1] - mid))
        span(i0, k, t0, t, depth + 1); span(k, i1, t, t1, depth + 1)

    for (i0, t0), (i1, t1) in zip(cuts[:-1], cuts[1:]):
        span(i0, i1, t0, t1)
    if not quiet:
        log(f"forced alignment: {stats['ok']} chunks aligned, {stats['fail']} left on Whisper timing")
    return res


def _clean_forms(tokens, clean_text):
    """Display text for each token when fillers are hidden. From a cleaned transcript if given, else punctuation rules."""
    vis = [k for k, t in enumerate(tokens) if not is_filler(t)]
    wh = {}
    if clean_text:
        cl = clean_text.split()
        sm = difflib.SequenceMatcher(a=[_norm(tokens[k]) for k in vis], b=[_norm(c) for c in cl], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
                for q in range(i2 - i1):
                    wh[vis[i1 + q]] = cl[j1 + q]
    trail = lambda t: re.search(r"[.?!…,;:]+$", t).group(0) if re.search(r"[.?!…,;:]+$", t) else ""
    strength = lambda p: 3 if re.search(r"[.?!]", p) and "..." not in p else (2 if ("..." in p or "…" in p) else (1 if p else 0))
    k = 0
    while k < len(tokens):
        if not is_filler(tokens[k]):
            k += 1; continue
        j = k
        while j < len(tokens) and is_filler(tokens[j]):
            j += 1
        A = k - 1 if k > 0 else None
        B = j if j < len(tokens) else None
        if A is not None and A in wh and B is not None and B in wh:
            k = j; continue  # cleaned transcript already decided
        run_p = max((trail(tokens[q]) for q in range(k, j)), key=strength, default="")
        a_txt = wh.get(A, tokens[A]) if A is not None else ""
        a_p = trail(a_txt)
        cap = A is None or strength(a_p) == 3
        if A is not None and strength(a_p) < 3 and strength(run_p) == 3:
            wh[A] = a_txt[: len(a_txt) - len(a_p)] + run_p[:1]; cap = True
        elif A is not None and a_p == "," and strength(run_p) <= 1:
            wh[A] = a_txt[:-1]
        if cap and B is not None:
            b = wh.get(B, tokens[B])
            wh[B] = b[:1].upper() + b[1:]
        k = j
    return {k: v for k, v in wh.items() if v != tokens[k]}


def fix(out, text, clean=None):
    """Replace the transcript with TEXT (verbatim, fillers kept). Word and filler timings come from forced alignment against the audio,
    anchored by Whisper's words; fillers are flagged so captions can hide them. CLEAN (optional) supplies display text with fillers removed."""
    J = json.load(open(f"{out}/words.json"))
    anc_src = f"{out}/words.whisper.json"
    if not os.path.exists(anc_src):
        shutil.copy(f"{out}/words.json", anc_src)
    old = json.load(open(anc_src))["words"]
    toks = text.split()
    sm = difflib.SequenceMatcher(a=[_norm(w["w"]) for w in old], b=[_norm(t) for t in toks], autojunk=False)
    n = len(toks)
    anc_s, anc_e, anchored, prob = [None] * n, [None] * n, [False] * n, [1.0] * n
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for q in range(i2 - i1):
                w = old[i1 + q]; anc_s[j1 + q], anc_e[j1 + q], anchored[j1 + q], prob[j1 + q] = w["s"], w["e"], True, w.get("p", 1)
    known = [k for k in range(n) if anchored[k]]
    for k in range(n):  # interpolate unanchored tokens between anchored neighbours
        if anchored[k]:
            continue
        a = max([q for q in known if q < k], default=None); b = min([q for q in known if q > k], default=None)
        t0 = anc_e[a] if a is not None else 0.0
        t1 = anc_s[b] if b is not None else J["duration"]
        lo = a if a is not None else -1; hi = b if b is not None else n
        f0, f1 = (k - lo) / (hi - lo), (k + 1 - lo) / (hi - lo)
        anc_s[k], anc_e[k] = t0 + (t1 - t0) * f0, t0 + (t1 - t0) * f1
    try:
        al = force_align(load16(out), toks, anc_s, anc_e, anchored)
    except ImportError:
        log("pocketsphinx missing (run setup); keeping Whisper timings"); al = [None] * n
    # the aligner fits every token of a chunk into its audio; a word Whisper wrote twice can squeeze a whole stretch seconds early.
    # Anchors are now checked against a silence-skipping pass (see reanchor), so a placement far from its anchor is the aligner's error.
    far = 0
    for k in range(n):
        if al[k] and anchored[k] and abs(al[k][0] - anc_s[k]) > ALIGN_TOL:
            al[k] = None; far += 1
    if far:  # align those stretches again on their own, in the window their checked timing gives
        x16, k, again = load16(out), 0, 0
        while k < n:
            if al[k] or not anchored[k]:
                k += 1; continue
            j = k
            while j < n and not al[j] and anchored[j]:
                j += 1
            pe = next((al[q][1] for q in range(k - 1, -1, -1) if al[q]), 0.0)
            ns = next((al[q][0] for q in range(j, n) if al[q]), J["duration"])
            t0, t1 = max(pe, anc_s[k] - 0.5), min(ns, anc_e[j - 1] + 0.5)
            if t1 - t0 > 0.15 * (j - k):
                try:
                    sub = force_align(x16[int(t0 * SR):int(t1 * SR)], toks[k:j], [v - t0 for v in anc_s[k:j]], [v - t0 for v in anc_e[k:j]],
                                      anchored[k:j], quiet=True)
                except Exception:
                    sub = [None] * (j - k)
                for q, v in enumerate(sub):
                    if v and abs(v[0] + t0 - anc_s[k + q]) <= ALIGN_TOL:
                        al[k + q] = (v[0] + t0, v[1] + t0); again += 1
            k = j
        log(f"{far} words the aligner put over {ALIGN_TOL:g} s from their checked timing; {again} re-aligned on their own, the rest keep that timing")
    # rescue: a voiced stretch no aligned word covers, where Whisper heard a word that the aligner squeezed elsewhere
    x = load16(out)
    fr = x[: len(x) // HOP * HOP].reshape(-1, HOP)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    act = db > np.percentile(db, 15) + 8
    cov = np.zeros(len(act), bool)
    for v in al:
        if v:
            cov[int(v[0] * 100):int(v[1] * 100)] = True
    runs, s0 = [], None
    for i, v in enumerate(np.append(act & ~cov, False)):
        if v and s0 is None:
            s0 = i
        elif not v and s0 is not None:
            if i - s0 >= 25:
                runs.append((s0 / 100, i / 100))
            s0 = None
    rescued = 0
    for r0, r1 in runs:
        for k in range(n):
            if not (anchored[k] and al[k]) or is_filler(toks[k]):
                continue
            if min(anc_e[k], r1) - max(anc_s[k], r0) >= 0.5 * (r1 - r0) and not (al[k][0] < r1 and al[k][1] > r0):
                pe = next((al[q][1] for q in range(k - 1, -1, -1) if al[q]), 0.0)
                ns = next((al[q][0] for q in range(k + 1, n) if al[q]), 1e9)
                if pe <= r0 + 0.02 and r1 <= ns + 0.02:
                    al[k] = (r0, r1); rescued += 1
                break
    if rescued:
        log(f"moved {rescued} words onto voiced stretches Whisper heard them in")
    wh = _clean_forms(toks, clean)
    res, n_al = [], 0
    for k, t in enumerate(toks):
        s, e = al[k] if al[k] else (anc_s[k], anc_e[k])
        n_al += bool(al[k])
        w = {"w": " " + t, "s": round(s, 3), "e": round(max(e, s + 0.03), 3), "p": prob[k] if anchored[k] else 1}
        if is_filler(t):
            w["fl"] = True
        if k in wh:
            w["wh"] = " " + wh[k]
        res.append(w)
    for k in range(1, n):  # keep order monotonic
        if res[k]["s"] < res[k - 1]["s"]:
            res[k]["s"] = res[k - 1]["s"]; res[k]["e"] = max(res[k]["e"], res[k]["s"] + 0.03)
    k = 1
    while k < n:  # words left on one instant by the step above would land as a burst: spread them over the room around them
        if res[k]["s"] != res[k - 1]["s"]:
            k += 1; continue
        a, b = k - 1, k
        while b < n and res[b]["s"] == res[a]["s"]:
            b += 1
        hi = res[b]["s"] if b < n else res[a]["s"] + 0.3 * (b - a)
        lo = res[a]["s"]
        if hi - lo < 0.12 * (b - a):
            lo = max((res[a - 1]["s"] + 0.05) if a > 0 else 0.0, hi - 0.12 * (b - a))
        step = (hi - lo) / (b - a)
        if step > 0.02:
            for q in range(a, b):
                res[q]["s"] = round(lo + step * (q - a), 3); res[q]["e"] = round(max(res[q]["s"] + 0.03, min(res[q]["e"], lo + step * (q - a + 1))), 3)
        k = b
    J["words"] = res
    json.dump(J, open(f"{out}/words.json", "w"))
    log(f"transcript updated: {n} words ({sum(1 for w in res if w.get('fl'))} fillers), {n_al} placed by forced alignment")
    analyze(out)


# ---------------------------------------------------------------- render

# ---------------------------------------------------------------- outputs
def text(out):
    print(" ".join(w["w"].strip() for w in json.load(open(f"{out}/words.json"))["words"]))


def srt(out):
    W = [dict(w, w=w.get("wh", w["w"])) for w in json.load(open(f"{out}/data.json"))["words"] if not w.get("fl")]
    prev = 0.0
    for w in W:  # gaps relative to the previous visible word
        w["gap"] = max(0.0, w["s"] - prev); prev = w["e"]
    cues, cur = [], []
    txt = lambda c: " ".join(x["w"].strip() for x in c)
    for w in W:
        if cur:
            if len(txt(cur + [w])) > 84 or (re.search(r"[.?!]$", cur[-1]["w"].strip()) and len(cur) >= 4) \
               or (w["gap"] >= 2.0 and len(cur) >= 6) or w["gap"] >= 4 or w["s"] - cur[0]["s"] > 8:
                cues.append(cur); cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    f = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(round((t%1)*1000))%1000:03d}"
    lines = []
    for i, c in enumerate(cues):
        end = min(c[-1]["e"] + 0.6, cues[i + 1][0]["s"]) if i + 1 < len(cues) else c[-1]["e"] + 0.6
        body = txt(c)
        if len(body) > 42:
            ws = body.split(); k = min(range(1, len(ws)), key=lambda k: abs(len(" ".join(ws[:k])) - len(" ".join(ws[k:]))))
            body = " ".join(ws[:k]) + "\n" + " ".join(ws[k:])
        lines.append(f"{i+1}\n{f(c[0]['s'])} --> {f(end)}\n{body}\n")
    open(f"{out}/captions.srt", "w").write("\n".join(lines))
    log(f"wrote {out}/captions.srt ({len(cues)} cues)")


def load_params(path):
    if not path:
        return {}
    if os.path.exists(path):
        raw = open(path).read()
    else:
        raw = path
    raw = raw.strip()
    if raw.startswith("voicecap"):
        raw = raw[raw.index("{"):]
    return json.loads(raw)


def player(out, params=None, title="Voice captions"):
    d = f"{out}/player"; os.makedirs(d, exist_ok=True)
    shutil.copy(f"{out}/audio.m4a", f"{d}/audio.mp4"); shutil.copy(f"{out}/data.json", d)
    html = open(os.path.join(HERE, "player.html")).read()
    html = html.replace("/*ENGINE*/", open(ENGINE).read())
    html = html.replace("/*INITIAL_PARAMS*/{}", json.dumps(load_params(params))).replace("__TITLE__", title.replace("<", ""))
    open(f"{d}/index.html", "w").write(html)
    log(f"player ready: {d}/index.html (+ audio.mp4 {os.path.getsize(d+'/audio.mp4')/1e6:.1f} MB, data.json {os.path.getsize(d+'/data.json')/1e6:.2f} MB)")


RENDER_JS = r"""
let scene, cv, ctx, MEAS, QP = 24;
async function vcInit(data, P) {
  const fams = Object.keys(VC.FONTS);
  await Promise.all(fams.flatMap((f) => [100, 400, 700, 900].map((w) => document.fonts.load(`${w} 40px "${f}"`))));
  const m = new OffscreenCanvas(8, 8).getContext("2d");
  MEAS = (t, fam, w, em) => { if (!t) return 0; m.font = `${w} ${em}px "${fam}"`; return m.measureText(t).width; };
  scene = VC.buildScene(data, P, MEAS);
  cv = new OffscreenCanvas(scene.W, scene.H); ctx = cv.getContext("2d");
  const ok = document.fonts.check(`400 40px "${scene.P.font}"`);
  return { W: scene.W, H: scene.H, fontOk: ok, phrases: scene.phrases.length, lines: scene.lines.length };
}
async function vcChunk(f0, n, fps, bitrate) {
  const out = []; let err = null;
  const enc = new VideoEncoder({ output: (c) => { const b = new Uint8Array(c.byteLength); c.copyTo(b); out.push(b); }, error: (e) => { err = String(e); } });
  const base = { codec: scene.W * scene.H > 2073600 ? "avc1.640032" : "avc1.640028", width: scene.W, height: scene.H, framerate: fps, avc: { format: "annexb" } };
  const qcfg = Object.assign({ bitrateMode: "quantizer" }, base);
  const useQ = (await VideoEncoder.isConfigSupported(qcfg)).supported;
  enc.configure(useQ ? qcfg : Object.assign({ bitrate, bitrateMode: "variable" }, base));
  for (let i = 0; i < n; i++) {
    VC.draw(ctx, scene, (f0 + i) / fps);
    const fr = new VideoFrame(cv, { timestamp: Math.round(((f0 + i) * 1e6) / fps), duration: Math.round(1e6 / fps) });
    enc.encode(fr, useQ ? { keyFrame: i % (fps * 10) === 0, avc: { quantizer: QP } } : { keyFrame: i % (fps * 10) === 0 }); fr.close();
    while (enc.encodeQueueSize > 6) await new Promise((r) => setTimeout(r, 0));
  }
  await enc.flush(); enc.close();
  if (err) throw new Error(err);
  let len = 0; for (const b of out) len += b.length;
  const all = new Uint8Array(len); let o = 0; for (const b of out) { all.set(b, o); o += b.length; }
  let s = ""; for (let i = 0; i < all.length; i += 0x8000) s += String.fromCharCode.apply(null, all.subarray(i, i + 0x8000));
  return btoa(s);
}
async function vcFrame(t) { VC.draw(ctx, scene, t); const b = await cv.convertToBlob({ type: "image/png" }); const u = new Uint8Array(await b.arrayBuffer()); let s = ""; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); }
"""


THUMB_JS = r"""
async function vcThumb(data, TH, P, scale) {
  const fams = Object.keys(VC.FONTS);
  await Promise.all(fams.flatMap((f) => [100, 400, 700, 900].map((w) => document.fonts.load(`${w} 40px "${f}"`))));
  const m = new OffscreenCanvas(8, 8).getContext("2d");
  const meas = (t, fam, w, em) => { if (!t) return 0; m.font = `${w} ${em}px "${fam}"`; return m.measureText(t).width; };
  const sc = VC.buildThumb(data, TH, P, meas);
  const c = new OffscreenCanvas(Math.round(sc.W * scale), Math.round(sc.H * scale)), x = c.getContext("2d");
  x.setTransform(scale, 0, 0, scale, 0, 0); VC.drawThumb(x, sc);
  const b = await c.convertToBlob({ type: "image/png" }), u = new Uint8Array(await b.arrayBuffer());
  let s = ""; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return { png: btoa(s), W: c.width, H: c.height, heard: sc.heard, total: sc.total, font: sc.P.font, fontOk: document.fonts.check(`400 40px "${sc.P.font}"`) };
}
"""


def _render_page(out, extra=""):
    faces = "\n".join(
        f'@font-face{{font-family:"{fam}";src:url("file://{os.path.join(FONT_DIR, os.path.basename(p))}");font-weight:100 1000;}}'
        for fam, p in FONT_FILES.items())
    page = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{faces}</style></head><body><script>{open(ENGINE).read()}</script><script>{RENDER_JS}{extra}</script></body></html>"
    path = f"{out}/render_page.html"; open(path, "w").write(page)
    return path


def _browser(fn):
    import asyncio
    from playwright.async_api import async_playwright

    async def go():
        async with async_playwright() as p:
            b = await p.chromium.launch(executable_path=chrome_path(), args=["--allow-file-access-from-files"])
            try:
                pg = await b.new_page()
                errors = []
                pg.on("pageerror", lambda e: errors.append(str(e)))
                return await fn(pg, errors)
            finally:
                await b.close()
    return asyncio.run(go())


def thumb(out, spec, dest=None, scale=2.0, data_path=None):
    """The studio's thumbnail as a PNG. SPEC: {"thumb": edits.json "thumb", "params": the video look}; the same engine draws it."""
    S = load_params(spec)
    D = json.load(open(data_path or f"{out}/data.json"))
    if "words" not in D and "data" in D:
        D = D["data"]
    dest = dest or f"{out}/thumbnail.png"
    page = _render_page(out, THUMB_JS)

    async def fn(pg, errors):
        await pg.goto("file://" + page)
        r = await pg.evaluate("([d,t,p,s]) => vcThumb(d,t,p,s)", [D, S.get("thumb") or {}, S.get("params") or {}, scale])
        if errors:
            raise RuntimeError("; ".join(errors[:3]))
        return r
    r = _browser(fn)
    open(dest, "wb").write(base64.b64decode(r.pop("png")))
    if not r.get("fontOk"):
        log(f"warning: {r.get('font')} did not load; run setup")
    log(f"wrote {dest}  {r['W']}x{r['H']}  {os.path.getsize(dest)/1e6:.2f} MB  ({r['heard']} of {r['total']} words heard in the recording)")
    return dest


def frames(out, params, times, prefix):
    """PNG stills at given times (seconds) — for checking a look without rendering video."""
    P = load_params(params); data = json.load(open(f"{out}/data.json")); page = _render_page(out)

    async def fn(pg, errors):
        await pg.goto("file://" + page)
        info = await pg.evaluate("([d,p]) => vcInit(d,p)", [data, P])
        paths = []
        for t in times:
            b = await pg.evaluate("(t) => vcFrame(t)", t)
            path = f"{prefix}_{t:.1f}.png"; open(path, "wb").write(base64.b64decode(b)); paths.append(path)
        if errors:
            log("page errors:", errors[:3])
        return info, paths
    info, paths = _browser(fn)
    log("frames", info, *paths)
    return paths


def render(out, params=None, start=0.0, dur=None, dest=None, fps=30, abr="128k", chunk=60.0, bitrate=2_500_000, audio=None):
    """Draws every frame with the same engine as the player (headless Chrome), encodes H.264 in resumable chunks, muxes audio."""
    P = load_params(params); data = json.load(open(f"{out}/data.json"))
    total = data["duration"]
    dur = min(dur or total, total - start)
    tag = "preview" if dur < total - 0.5 else "full"
    dest = dest or f"{out}/voicecap_{tag}.mp4"
    json.dump(P, open(f"{out}/params.used.json", "w"), indent=1)
    key = hashlib.md5((json.dumps(P, sort_keys=True) + str(os.path.getmtime(f"{out}/data.json")) + f"{fps}{start}{dur}{chunk}{bitrate}"
                       + open(ENGINE).read() + RENDER_JS).encode()).hexdigest()[:8]
    cdir = f"{out}/chunks_{key}"; os.makedirs(cdir, exist_ok=True)
    nframes = int(round(dur * fps)); per = int(chunk * fps); n = max(1, math.ceil(nframes / per))
    f_start = int(round(start * fps))
    page = _render_page(out)
    t0 = time.time()

    async def fn(pg, errors):
        await pg.goto("file://" + page)
        info = await pg.evaluate("([d,p]) => vcInit(d,p)", [data, P])
        log("scene", json.dumps(info))
        if not info.get("fontOk"):
            log("warning: font did not load; check ~/.cache/voicecap/fonts")
        done = 0
        for i in range(n):
            part = f"{cdir}/c{i:04d}.h264"
            cnt = min(per, nframes - i * per)
            if os.path.exists(part + ".ok"):
                done += cnt; continue
            b64 = await pg.evaluate("([a,b,c,d]) => vcChunk(a,b,c,d)", [f_start + i * per, cnt, fps, bitrate])
            open(part, "wb").write(base64.b64decode(b64)); open(part + ".ok", "w").close()
            done += cnt
            el = time.time() - t0
            log(f"render {100*done/nframes:5.1f}%  ({done/max(el,1e-3):.0f} fps, ~{(nframes-done)/max(done/max(el,1e-3),1)/60:.1f} min left)")
            if errors:
                raise RuntimeError("; ".join(errors[:3]))
    _browser(fn)
    allp = f"{cdir}/all.h264"
    with open(allp, "wb") as o:
        for i in range(n):
            with open(f"{cdir}/c{i:04d}.h264", "rb") as f:
                shutil.copyfileobj(f, o)
    log("muxing audio…")
    sh(["ffmpeg", "-v", "error", "-y", "-r", str(fps), "-f", "h264", "-i", allp, "-ss", str(start), "-t", str(dur),
        "-i", audio or f"{out}/master.flac", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-bsf:v", f"h264_metadata=tick_rate={2 * fps}",
        "-c:a", "aac", "-b:a", abr, "-ar", "48000",
        "-t", str(dur), "-movflags", "+faststart", dest])
    os.remove(allp)
    log(f"wrote {dest}  {os.path.getsize(dest)/1e6:.1f} MB  in {(time.time()-t0)/60:.1f} min")
    return dest


# ---------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("setup")
    r = sp.add_parser("run"); r.add_argument("audio"); r.add_argument("--out", required=True)
    r.add_argument("--lang"); r.add_argument("--prompt"); r.add_argument("--quality", default="accurate", choices=["accurate", "fast", "high"])
    r.add_argument("--no-normalize", action="store_true")
    f = sp.add_parser("fix"); f.add_argument("dir"); f.add_argument("--text", required=True); f.add_argument("--clean")
    a = sp.add_parser("analyze"); a.add_argument("dir")
    sp.add_parser("retime").add_argument("dir")
    c = sp.add_parser("concepts"); c.add_argument("dir"); c.add_argument("--file", required=True)
    v = sp.add_parser("render"); v.add_argument("dir"); v.add_argument("--params"); v.add_argument("--start", type=float, default=0)
    v.add_argument("--dur", type=float); v.add_argument("--out"); v.add_argument("--fps", type=int, default=30); v.add_argument("--abr", default="128k")
    v.add_argument("--audio", help="sound for the video (default DIR/master.flac); notes.py passes the noise-reduced version")
    fr = sp.add_parser("frames"); fr.add_argument("dir"); fr.add_argument("--params"); fr.add_argument("--times", required=True); fr.add_argument("--prefix", default="/tmp/vcframe")
    th = sp.add_parser("thumb"); th.add_argument("dir"); th.add_argument("--spec", required=True, help='{"thumb": ..., "params": ...} or a file with it')
    th.add_argument("--out"); th.add_argument("--scale", type=float, default=2.0); th.add_argument("--data", help="captions.json or data.json (default DIR/data.json)")
    pl = sp.add_parser("player"); pl.add_argument("dir"); pl.add_argument("--params"); pl.add_argument("--title", default="Voice captions")
    sp.add_parser("text").add_argument("dir"); sp.add_parser("srt").add_argument("dir")
    A = ap.parse_args()
    if A.cmd == "setup":
        setup()
    elif A.cmd == "run":
        prepare(A.audio, A.out, not A.no_normalize); transcribe(A.out, A.lang, A.prompt, A.quality)
        if A.quality != "fast":  # forced alignment: words and fillers get their real onsets (see fix)
            fix(A.out, " ".join(w["w"].strip() for w in json.load(open(f"{A.out}/words.json"))["words"]))
        else:
            analyze(A.out)
    elif A.cmd == "fix":
        fix(A.dir, open(A.text).read(), open(A.clean).read() if A.clean else None)
    elif A.cmd == "analyze":
        analyze(A.dir)
    elif A.cmd == "retime":
        retime(A.dir)
    elif A.cmd == "concepts":
        spec = json.load(open(A.file)); shutil.copy(A.file, f"{A.dir}/concepts.json") if os.path.abspath(A.file) != os.path.abspath(f"{A.dir}/concepts.json") else None
        apply_concepts(A.dir, spec)
    elif A.cmd == "render":
        render(A.dir, A.params, A.start, A.dur, A.out, A.fps, A.abr, audio=A.audio)
    elif A.cmd == "frames":
        frames(A.dir, A.params, [float(x) for x in A.times.split(",")], A.prefix)
    elif A.cmd == "thumb":
        thumb(A.dir, A.spec, A.out, A.scale, A.data)
    elif A.cmd == "player":
        player(A.dir, A.params, A.title)
    elif A.cmd == "text":
        text(A.dir)
    elif A.cmd == "srt":
        srt(A.dir)


if __name__ == "__main__":
    main()
