"""A synthetic recording for the browser tests: no personal data (the repo is public).

make() writes tests/.fixture/: sample.m4a (a hummed tone, not speech), sample.captions.json (words timed along it, with the
voice envelope, fillers and glossary tags) and glossary.json (a few themes and terms; one definition marked verified).
"""
import base64, json, math, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, ".fixture")
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

AID = "TESTREC0000000000000000000000000"
TEXT = """Okay, so this morning I want to start with creativity, um, because creativity is where the whole account begins.
Whitehead calls the final real things actual occasions, and each actual occasion is a little act of becoming.
The process by which the many data grow together is called concrescence, and concrescence ends in one new occasion.
Uh, so the many become one, and are increased by one. That is the axiom underneath it, the presupposition that
everything else leans on. Deleuze would object to starting from the one, and Deleuze and Guattari offer the rhizome
instead, a network where any point connects to any other. Hmm, a Buddhist reading might say the same thing about
emptiness, that nothing stands on its own. So creativity, again, is not a thing but a way things go on happening.
Let me read the passage once more, slowly, and then, um, try to say it in my own words. The axiom is that becoming
comes first. The presupposition is that experience goes all the way down. And the rhizome is a picture of thinking
without a trunk. Okay. That is enough for one walk."""

GLOSSARY_ROWS = [
    {"Term": "creativity", "Theme": "Re-enchantment", "Status": "Accepted", "Forms": "", "Definition": "Whitehead: the ultimate principle by which the many become one.", "Source": "A. N. Whitehead, Process and Reality (1929), Part I, ch. 2", "Verified": "__YES__", "url": "https://www.notion.so/00000000000000000000000000000001"},
    {"Term": "actual occasion", "Theme": "Re-enchantment", "Status": "Suggested", "Forms": "actual occasions", "Definition": "Whitehead: a momentary drop of experience.", "Source": "Process and Reality [unverified — from training data]", "Verified": "__NO__", "url": "https://www.notion.so/00000000000000000000000000000002"},
    {"Term": "concrescence", "Theme": "Re-enchantment", "Status": "Suggested", "Forms": "", "Definition": "Many data growing together into one.", "Source": "Process and Reality [unverified — from training data]", "Verified": "__NO__", "url": "https://www.notion.so/00000000000000000000000000000003"},
    {"Term": "Whitehead", "Theme": "Re-enchantment", "Status": "Suggested", "Forms": "Wifehead", "Definition": "A. N. Whitehead, process philosopher.", "Source": "[unverified — from training data]", "Verified": "__NO__", "url": ""},
    {"Term": "axiom", "Theme": "Contingency of knowing", "Status": "Suggested", "Forms": "axioms", "Definition": "A starting assumption.", "Source": "[unverified — from training data]", "Verified": "__NO__", "url": ""},
    {"Term": "presupposition", "Theme": "Contingency of knowing", "Status": "Suggested", "Forms": "", "Definition": "What a claim takes for granted.", "Source": "[unverified — from training data]", "Verified": "__NO__", "url": ""},
    {"Term": "Deleuze", "Theme": "Re-enchantment", "Status": "Suggested", "Forms": "", "Definition": "Gilles Deleuze, philosopher.", "Source": "[unverified — from training data]", "Verified": "__NO__", "url": ""},
    {"Term": "Buddhist", "Theme": "Religion & theology", "Status": "Suggested", "Forms": "", "Definition": "Of the Buddha's teaching.", "Source": "[unverified — from training data]", "Verified": "__NO__", "url": ""},
]
FILLERS = {"um,", "uh,", "hmm,", "um", "uh"}
FUNC = set("a an the of to and or is are be in on at by it that this so as for with not but".split())


def make():
    import notes  # tools/notes.py: glossary building and tagging, the same code the pipeline runs
    os.makedirs(OUT, exist_ok=True)
    words, t = [], 1.0
    for tok in TEXT.split():
        fl = tok.lower() in FILLERS
        n = len(tok.strip(".,"))
        dur = (0.45 if fl else 0.12 + 0.045 * n)
        gap = 0.5 if words and words[-1]["w"].endswith((".", "?")) else 0.06
        t += gap
        bare = tok.lower().strip(".,?")
        words.append({"w": " " + tok, "s": round(t, 3), "e": round(t + dur, 3), "p": 0.4 if bare == "wifehead" else 0.95,
                      "pitch": round(math.sin(t / 3) * 1.5, 2), "slope": round(math.cos(t) * 4, 2), "loud": round(math.sin(t * 1.7), 2),
                      "stretch": round(dur * 2 - 0.6, 2), "emph": round(math.sin(t * 2.3) * 2, 2), "gap": round(gap, 2),
                      "fn": fl or bare in FUNC, **({"fl": True} if fl else {})})
        t += dur
    dur = round(t + 2.0, 3); hz = 50; frames = int(dur * hz)
    loud = bytearray(frames); pitch = bytearray(frames)
    for w in words:
        for f in range(int(w["s"] * hz), min(frames, int(w["e"] * hz))):
            loud[f] = int(120 + 100 * abs(math.sin(f / 7))); pitch[f] = int(128 + 90 * math.sin(f / 40))
    data = {"version": 2, "duration": dur, "lang": "en", "words": words,
            "env": {"hz": hz, "loud": base64.b64encode(bytes(loud)).decode(), "pitch": base64.b64encode(bytes(pitch)).decode()}}
    G = notes.build_glossary(GLOSSARY_ROWS)
    notes.tag_data(data, G)
    cap = {"audioId": AID, "title": "Test walk: creativity, concrescence and the rhizome", "recordedAt": "2026-01-01", "duration": dur,
           "rev": 1, "listen": None, "video": None, "remap": None, "notion": "https://www.notion.so/00000000000000000000000000000009", "v": 1, "data": data}
    paths = {"captions": os.path.join(OUT, "sample.captions.json"), "audio": os.path.join(OUT, "sample.m4a"), "glossary": os.path.join(OUT, "glossary.json")}
    json.dump(cap, open(paths["captions"], "w"))
    json.dump(G, open(paths["glossary"], "w"), ensure_ascii=False)
    if not os.path.exists(paths["audio"]) or os.path.getmtime(paths["audio"]) < os.path.getmtime(__file__):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=170:duration={dur}", "-af", "tremolo=f=3:d=0.6",
                        "-ac", "1", "-c:a", "aac", "-b:a", "32k", paths["audio"]], check=True)
    return dict(paths, aid=AID, title=cap["title"], duration=dur)


if __name__ == "__main__":
    print(json.dumps(make(), indent=1))
