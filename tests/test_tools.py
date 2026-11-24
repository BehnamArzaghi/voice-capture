#!/usr/bin/env python3
"""Checks for the pipeline's pure steps (no speech model, no network): glossary tagging, publishing, Notion payloads.

  python3 tests/test_tools.py
"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools")); sys.path.insert(0, HERE)
import fixture, notes, notion_batch  # noqa: E402
from harness import Check  # noqa: E402

C = Check()
FX = fixture.make()
cap = json.load(open(FX["captions"])); G = json.load(open(FX["glossary"]))

# tagging: longer terms win, plurals and forms count, fillers are skipped, rejected terms are ignored
terms = {t["t"]: len(t["occ"]) for t in cap["data"]["terms"]}
C(terms.get("actual occasion") == 2, "tag: 'actual occasions' counts as the term 'actual occasion'", terms)
C(terms.get("creativity") == 3, "tag: every mention found", terms)
C(not any(w.get("th") is not None for w in cap["data"]["words"] if w.get("fl")), "tag: fillers are never tagged")
rows = [dict(r) for r in fixture.GLOSSARY_ROWS]; rows[4]["Status"] = "Rejected"
data = json.loads(json.dumps(cap["data"])); notes.tag_data(data, notes.build_glossary(rows))
C("axiom" not in {t["t"] for t in data["terms"]}, "tag: rejected terms are skipped")
stats = {"A": {"occurrences": 4, "terms": ["x"]}, "B": {"occurrences": 3, "terms": ["x", "y"]}, "C": {"occurrences": 3, "terms": ["x"]}}
C(notes.note_themes(stats) == ["A", "B"], "tag: Notion theme rule (4+, or 3+ across 2+ terms)", notes.note_themes(stats))
v = os.path.join(tempfile.mkdtemp(), "vocabulary.txt"); open(v, "w").write("# words\nWhitehead\n")
added = notes.add_vocab(v, G)
C("concrescence" in added and "Whitehead" not in added and "Wifehead" not in open(v).read(), "vocab: term names added once, forms never", added)

# publish: library.json and the Drive for desktop folder
d = tempfile.mkdtemp()
out = subprocess.run([sys.executable, os.path.join(HERE, "..", "tools", "notes.py"), "publish", FX["captions"], "--extra", FX["glossary"], "--drive-dir", d],
                     capture_output=True, text=True, env=dict(os.environ, VN_WORK=d))
lib = json.load(open(os.path.join(d, "Captions", "library.json")))
C(out.returncode == 0 and lib["items"][FX["aid"]]["title"] == FX["title"], "publish: library.json carries the summary", out.stderr[-300:])
C(os.path.exists(os.path.join(d, "Captions", FX["aid"] + ".captions.json")) and os.path.exists(os.path.join(d, "Captions", "glossary.json")),
  "publish: files written into the synced Captions folder")

# Notion payloads
C(notion_batch.value("multi_select", ["B"], {"multi_select": [{"name": "A"}]}) == {"multi_select": [{"name": "A"}, {"name": "B"}]},
  "notion: '+' adds to a multi-select")
C(notion_batch.pid("https://app.notion.com/p/421f7a0a73cb81e2bffae19bdffc3d54?pvs=204") == "421f7a0a-73cb-81e2-bffa-e19bdffc3d54", "notion: ids from URLs")

print(f"\n{C.n - len(C.fails)} of {C.n} checks passed")
sys.exit(1 if C.fails else 0)
