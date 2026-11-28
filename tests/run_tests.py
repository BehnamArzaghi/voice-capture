#!/usr/bin/env python3
"""Browser tests for the Library (index.html) and the caption studio (studio.html).

  python3 tests/run_tests.py            all tests; screenshots go to tests/shots/
  python3 tests/run_tests.py themes     only the named groups (library, looks, follow, themes, words, phrasing, cards, requests, thumb, sound)

Needs Playwright for Python and the Chrome that `tools/vc.py setup` installs. Exits non-zero when a check fails.
"""
import asyncio, json, os, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

C = H.Check()
STUDIO = "window.__studio && window.__studio.scene && document.querySelectorAll('#words span').length > 50"


async def open_studio(p, base, w=1440, h=900, mobile=False):
    b, pg, errs = await H.page(p, w, h, mobile)
    await pg.goto(f"{base}/studio.html?id={H.AID}")
    await pg.wait_for_function(STUDIO, timeout=30000)
    return b, pg, errs


async def t_library(p, base):
    lib = os.path.join(tempfile.mkdtemp(), "library.json")
    json.dump({"v": 1, "items": {"LIBONLY000000000000000000000000": {"rev": 1, "title": "Summary only in library.json", "duration": 300}}}, open(lib, "w"))
    H.LIBJSON = lib
    for name, w, h, mob in (("desk", 1470, 900, False), ("phone", 390, 844, True)):
        b, pg, errs = await H.page(p, w, h, mob)
        await pg.goto(f"{base}/index.html#library")
        await pg.wait_for_timeout(600)
        if not await pg.evaluate("document.getElementById('tab-library').classList.contains('on')"):
            await pg.click("#tabs button[data-t=library]")
        await pg.wait_for_selector("#libBody .item", timeout=15000); await pg.wait_for_timeout(300)
        names = await pg.eval_on_selector_all("#libBody .item .name", "e => e.map(x => x.textContent)")
        C("Summary only in library.json" in names, f"library {name}: title read from library.json", names)
        C(any("Test walk" in n for n in names), f"library {name}: title read from the file description", names)
        C(await pg.eval_on_selector_all("#libBody .badge.b-wait", "e => e.length") == 1, f"library {name}: unprocessed recording marked waiting")
        await pg.screenshot(path=f"{H.OUT}/library_{name}.png")
        C(not errs, f"library {name}: no page errors", errs); await b.close()
    H.LIBJSON = ""
    # a large imported recording: the Library offers to split it into byte parts for Claude, and they join back exactly
    H.BIG = os.urandom(2_500_123); H.PARTUPS.clear()
    b, pg, errs = await H.page(p, 390, 844, True)
    await pg.add_init_script("window.VC_CONFIG = {partLimit: 1000000}")
    await pg.goto(f"{base}/index.html#library"); await pg.wait_for_selector("#bigCard", timeout=15000); await pg.wait_for_timeout(300)
    C(await pg.eval_on_selector_all("#libBody .badge.b-err", "e => e.map(x => x.textContent)") == ["Too large"], "library: a recording over the limit in a folder inside the inbox is marked too large")
    await pg.screenshot(path=f"{H.OUT}/library_big.png")
    await pg.click("[data-lib=split]"); await pg.wait_for_function("!document.getElementById('bigCard')", timeout=20000)
    ups = sorted(H.PARTUPS, key=lambda x: int(x["appProperties"]["part"]))
    import hashlib
    C(len(ups) == 3 and all(x["appProperties"]["partOf"] == "BIGREC" and x["parents"] == ["PARTS"] for x in ups)
      and b"".join(x["body"] for x in ups) == H.BIG and ups[0]["appProperties"]["sha256"] == hashlib.sha256(H.BIG).hexdigest(),
      "library: the recording is uploaded as byte parts that join back exactly", [(x["name"], x["size"]) for x in ups])
    C(not await pg.query_selector("#libBody .badge.b-err"), "library: once its parts are in Drive it waits for Claude like any recording")
    d = tempfile.mkdtemp(); paths = []
    for x in reversed(ups): pth = os.path.join(d, x["name"]); open(pth, "wb").write(x["body"]); paths.append(pth)
    r = subprocess.run([sys.executable, os.path.join(H.REPO, "tools", "join_parts.py"), os.path.join(d, "out.m4a"), *paths, "--sha256", ups[0]["appProperties"]["sha256"]], capture_output=True, text=True)
    C(r.returncode == 0 and open(os.path.join(d, "out.m4a"), "rb").read() == H.BIG, "library: join_parts.py rebuilds the original from byte parts", r.stdout + r.stderr)
    n = len(H.PARTUPS); await pg.evaluate("window.__vc.Lib.load()"); await pg.wait_for_timeout(600)
    C(len(H.PARTUPS) == n, "library: parts already in Drive are not uploaded again")
    C(not errs, "library: no page errors while splitting", errs); await b.close()
    H.BIG = None; H.PARTUPS.clear()


async def t_looks(p, base):
    b, pg, errs = await open_studio(p, base)
    await pg.click("#palettes [data-v=Cobalt]"); await pg.click("#fonts [data-v='Fraunces']"); await pg.wait_for_timeout(200)
    await pg.click("#saveBtn"); await pg.wait_for_timeout(400)
    await pg.fill("#lookName", "Walk notes"); await pg.click("#lookSave"); await pg.wait_for_timeout(600)
    saved = lambda: pg.eval_on_selector_all("#presets .preset.saved", "e => e.map(x => x.querySelector('b').textContent + (x.classList.contains('on') ? ' [on]' : ''))")
    C(await saved() == ["Walk notes [on]"], "looks: saved look appears and is marked in use", await saved())
    C(await pg.inner_text("#saveBtn") == "Saved ✓", "looks: Save button shows the look is saved")
    await pg.click("#palettes [data-v=Pistachio]"); await pg.wait_for_timeout(200)
    C(await saved() == ["Walk notes"], "looks: changing a setting leaves the saved look")
    await pg.click("#presets .preset.saved"); await pg.wait_for_timeout(200)
    C(await pg.evaluate("window.__studio.P.palette") == "Cobalt", "looks: tapping the saved look applies it")
    await pg.click("#presets .preset.saved .more"); await pg.wait_for_timeout(300); await pg.click("#lookDel"); await pg.wait_for_timeout(300)
    C(await saved() == [], "looks: delete removes it")
    await pg.click("#toast .toast-act"); await pg.wait_for_timeout(300)
    C(len(await saved()) == 1, "looks: Undo brings it back")
    C(any('"looks"' in s for s in H.SAVES), "looks: looks.json written to Drive")
    C(not errs, "looks: no page errors", errs); await b.close()


async def t_follow(p, base):
    for name, w, h, mob in (("desk", 1470, 860, False), ("phone", 390, 844, True)):
        b, pg, errs = await open_studio(p, base, w, h, mob)
        await pg.wait_for_function("document.getElementById('au').duration > 0", timeout=30000)
        await pg.click("#tabs button[data-t=words]")
        await pg.evaluate("() => { const a = document.getElementById('au'); a.currentTime = 40; a.play(); }")
        await pg.wait_for_timeout(2500)
        st = await pg.evaluate("() => { const el = document.querySelector('#words span.cur'); return {cur: !!el, follow: __studio.follow} }")
        C(st["cur"] and st["follow"], f"follow {name}: the playing word is marked and followed", st)
        if mob: await pg.evaluate("() => { window.dispatchEvent(new Event('touchmove')); window.scrollBy(0, -400); }")
        else: await pg.mouse.move(w * 0.8, h * 0.6); await pg.mouse.wheel(0, -500)
        await pg.wait_for_timeout(1500)
        C(not await pg.evaluate("__studio.follow") and "on" in await pg.get_attribute("#follow", "class"), f"follow {name}: scrolling stops following and shows the button")
        await pg.click("#follow"); await pg.wait_for_timeout(800)
        C(await pg.evaluate("__studio.follow"), f"follow {name}: the button resumes following")
        C(not errs, f"follow {name}: no page errors", errs); await b.close()


async def t_themes(p, base):
    for name, w, h, mob in (("desk", 1440, 900, False), ("phone", 390, 844, True)):
        H.SAVES.clear()
        b, pg, errs = await open_studio(p, base, w, h, mob)
        await pg.click("#tabs [data-t=voice]"); await pg.wait_for_timeout(300)
        rows = await pg.eval_on_selector_all("#themes .th .go span:first-of-type", "e => e.map(x => x.textContent)")
        C(rows[:1] == ["Re-enchantment"], f"themes {name}: most-heard theme listed first", rows)
        chips = await pg.eval_on_selector_all("#themes .term", "e => e.map(x => x.firstChild.textContent)")
        C({"creativity", "concrescence", "axiom"} <= set(chips), f"themes {name}: terms listed under their themes", chips)
        await (await pg.query_selector("#themes .th")).scroll_into_view_if_needed(); await pg.screenshot(path=f"{H.OUT}/themes_{name}.png")
        await pg.click("#themes [data-go]"); await pg.wait_for_timeout(300)
        C(await pg.evaluate("document.getElementById('au').currentTime") > 1 and "Re-enchantment" in await pg.inner_text("#toast"), f"themes {name}: tapping a theme jumps to a mention")
        await pg.click("#themes .term >> text=concrescence"); await pg.wait_for_timeout(300)
        body = await pg.inner_text("#sheetBody")
        C("Many data growing together" in body and "UNVERIFIED" in body.upper(), f"themes {name}: term sheet shows the definition and the unverified label")
        await pg.screenshot(path=f"{H.OUT}/term_{name}.png")
        await pg.click("#sheetBody [data-tc=accept]"); await pg.wait_for_timeout(400)
        C(await pg.evaluate("window.__studio.GL.some(g => g.op === 'accept' && g.term === 'concrescence')"), f"themes {name}: Accept makes a glossary request")
        await pg.click("#tNext"); await pg.wait_for_timeout(200)
        C((await pg.inner_text("#sheetBody .row .muted")).startswith("2 of 2"), f"themes {name}: term sheet steps through mentions")
        await pg.click("#tDone")
        await pg.click("#tabs [data-t=words]"); await pg.wait_for_timeout(300)
        C(await pg.eval_on_selector_all("#words span.sug", "e => e.length") > 0, f"themes {name}: suggested terms are underlined in Words")
        i = await pg.evaluate("window.__studio.data.words.findIndex(w => /^rhizome/i.test(w.w.trim()))")
        await pg.evaluate(f"window.__studio.openWord({i})"); await pg.wait_for_timeout(300)
        await pg.click("#foldTheme summary"); await pg.wait_for_timeout(150)
        await pg.click("#scopeSeg [data-v=gloss]"); await pg.wait_for_timeout(150)
        await pg.click('#thRow [data-v="Re-enchantment"]'); await pg.wait_for_timeout(500)
        n = await pg.evaluate("Object.values(window.__studio.P.thEdits).filter(v => v === 'Re-enchantment').length")
        C(n == 2, f"themes {name}: + Glossary tags every mention of the word", n)
        C(await pg.evaluate("window.__studio.GL.some(g => g.op === 'add' && g.term === 'rhizome')"), f"themes {name}: + Glossary makes an add request")
        await pg.screenshot(path=f"{H.OUT}/word_{name}.png")
        await pg.click("#scopeSeg [data-v=here]"); await pg.click("#selR"); await pg.wait_for_timeout(200)
        C(len((await pg.inner_text("#sheetBody .sel-row .w")).split()) == 2, f"themes {name}: + Next word widens the selection to a phrase")
        C(await pg.evaluate("document.getElementById('foldTheme').open"), f"themes {name}: the Theme section stays open while tagging")
        await pg.click("#newTh"); await pg.fill("#newThIn", "Process philosophy"); await pg.click("#newThSave"); await pg.wait_for_timeout(500)
        C(await pg.inner_text("#thRow .chip.on") == "Process philosophy", f"themes {name}: a new theme can be created and applied")
        await pg.click("#closeS"); await pg.click("#tabs [data-t=voice]"); await pg.wait_for_timeout(200)
        await pg.click("#themes [data-eye]"); await pg.wait_for_timeout(400)
        C(await pg.evaluate("window.__studio.P.thOff[0]") == "Re-enchantment", f"themes {name}: Hide turns a theme's color off")
        await pg.evaluate("window.__studio.flush()"); await pg.wait_for_timeout(400)
        body = next((s for s in reversed(H.SAVES) if '"audioId"' in s), "")
        doc = json.loads(body[body.index('{"v":1,"audioId"'):body.rindex("}") + 1]) if body else {}
        C({g["op"] for g in doc.get("glossary", [])} == {"accept", "add", "newTheme"}, f"themes {name}: glossary requests saved in edits.json", doc.get("glossary"))
        C(not errs, f"themes {name}: no page errors", errs); await b.close()


async def t_words(p, base):
    """The word sheet: ‹ › step between words, Enter saves a correction and closes, Emphasis and Theme start folded."""
    pick = """() => { const S = __studio, W = S.data.words, inT = new Set();
      (S.data.terms || []).forEach(t => t.occ.forEach(([a, n]) => { for (let q = a; q < a + n; q++) inT.add(q); }));
      const ok = (q) => q >= 0 && q < W.length && !W[q].fl && W[q].w.trim();
      const step = (q, d) => { q += d; while (q >= 0 && q < W.length && !ok(q)) q += d; return q; };
      for (let i = 10; i < W.length - 10; i++) { const a = step(i, -1), b = step(i, 1); if (ok(i) && ![a, i, b].some(q => inT.has(q))) return [a, i, b]; } }"""
    for name, w, h, mob in (("desk", 1440, 900, False), ("phone", 390, 844, True)):
        b, pg, errs = await open_studio(p, base, w, h, mob)
        await pg.click("#tabs [data-t=words]"); await pg.wait_for_timeout(300)
        a, i, n = await pg.evaluate(pick)
        word = lambda q: pg.evaluate(f"__studio.data.words[{q}].w.trim()")
        shown = lambda: pg.inner_text("#sheetBody .sel-row .w")
        is_open = lambda: pg.evaluate("document.getElementById('sheet').classList.contains('on')")
        folded = lambda: pg.evaluate("!document.getElementById('foldEmph').open && !document.getElementById('foldTheme').open")
        await pg.evaluate(f"__studio.openWord({i})"); await pg.wait_for_timeout(350)
        C(await folded(), f"words {name}: Emphasis and Theme start folded")
        C(await pg.inner_text("#foldEmph .val") == "Auto", f"words {name}: the folded Emphasis row shows its setting")
        await pg.screenshot(path=f"{H.OUT}/wordsheet_{name}.png")
        await pg.click("#wNext"); await pg.wait_for_timeout(250)
        C(await shown() == await word(n), f"words {name}: › moves to the next word", [await shown(), await word(n)])
        C(await pg.evaluate(f"document.getElementById('w{n}').classList.contains('insel') && !document.getElementById('w{i}').classList.contains('insel')"), f"words {name}: only the new word is marked")
        await pg.click("#wPrev"); await pg.click("#wPrev"); await pg.wait_for_timeout(250)
        C(await shown() == await word(a), f"words {name}: ‹ moves to the previous word", [await shown(), await word(a)])
        await pg.keyboard.press("ArrowRight"); await pg.wait_for_timeout(250)
        C(await shown() == await word(i), f"words {name}: the → key moves to the next word", [await shown(), await word(i)])
        await pg.click("#foldTheme summary"); await pg.click('#thRow [data-v="Re-enchantment"]'); await pg.wait_for_timeout(500)
        C(await pg.evaluate("document.getElementById('foldTheme').open"), f"words {name}: an opened section stays open after a change")
        C("Re-enchantment" in await pg.inner_text("#foldTheme .val"), f"words {name}: the Theme row shows the new theme")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(250)
        C(not await is_open(), f"words {name}: Esc closes the sheet")
        await pg.evaluate(f"__studio.openWord({i})"); await pg.wait_for_timeout(300)
        C(await folded(), f"words {name}: sections are folded again when the sheet reopens")
        orig = await word(i)
        await pg.fill("#fixIn", "Testword"); await pg.press("#fixIn", "Enter"); await pg.wait_for_timeout(500)
        st = await pg.evaluate(f"() => ({{fix: __studio.fixes[{i}], span: document.getElementById('w{i}').textContent, focus: document.activeElement.id}})")
        C(not await is_open() and st["fix"] == "Testword" and st["span"] == "Testword", f"words {name}: Enter saves the correction and closes the sheet", st)
        C(st["focus"] != "fixIn", f"words {name}: closing drops focus from the field (the phone keyboard goes away)")
        await pg.screenshot(path=f"{H.OUT}/wordsheet_saved_{name}.png")
        await pg.click("#toast .toast-act"); await pg.wait_for_timeout(500)
        st = await pg.evaluate(f"() => ({{has: {i} in __studio.fixes, span: document.getElementById('w{i}').textContent}})")
        C(not st["has"] and st["span"] == orig, f"words {name}: Undo in the message brings the word back", st)
        await pg.evaluate(f"__studio.openWord({i})"); await pg.wait_for_timeout(300)
        await pg.press("#fixIn", "Enter"); await pg.wait_for_timeout(300)
        C(not await is_open() and not await pg.evaluate(f"{i} in __studio.fixes"), f"words {name}: Enter on an unchanged word just closes")
        await pg.evaluate(f"__studio.openWord({i})"); await pg.wait_for_timeout(300)
        await pg.click("#fixDel"); await pg.wait_for_timeout(500)
        C(not await is_open() and await pg.evaluate(f"__studio.fixes[{i}]") == "", f"words {name}: Remove word saves and closes too")
        await pg.click("#toast .toast-act"); await pg.wait_for_timeout(400)
        C(not await pg.evaluate(f"{i} in __studio.fixes"), f"words {name}: Undo restores a removed word")
        await pg.evaluate("window.__studio.flush()"); await pg.wait_for_timeout(400)
        C(not errs, f"words {name}: no page errors", errs); await b.close()


async def t_phrasing(p, base):
    """Phrases follow pauses (default) or syntax: a long pause mid-sentence splits a phrase only in the first."""
    b, pg, errs = await open_studio(p, base)
    run = """(args) => {
      const [texts, P] = args; let t = 0;
      const words = texts.map(([w, gap]) => { t += gap; const o = { w: ' ' + w, s: t, e: t + 0.3, gap, p: 1 }; t += 0.3; return o; });
      const sc = VC.buildScene({ words, duration: t + 1 }, P, (c, f, wt, s) => s * 0.5 * [...c].length);
      return sc.placement === 'page' ? sc.lines.map(L => (L.para ? '¶' : '') + L.words.map(w => w.text).join(' '))
                                     : sc.phrases.map(ph => ph.words.map(w => w.text).join(' '));
    }"""
    talk = [["So", 0], ["the", .1], ["thing", .1], ["is...", .1], ["that", 3.0], ["creativity", .1], ["begins.", .1],
            ["Whitehead", .5], ["calls", .1], ["it", .1], ["concrescence.", .1]]
    pause = await pg.evaluate(run, [talk, {}])
    C(pause == ["So the thing is...", "that creativity begins.", "Whitehead calls it concrescence."], "phrasing: Pauses splits at a long pause mid-sentence", pause)
    syn = await pg.evaluate(run, [talk, {"phrasing": "syntax"}])
    C(syn == ["So the thing is... that creativity begins.", "Whitehead calls it concrescence."], "phrasing: Syntax keeps a sentence whole across its pauses", syn)
    low = await pg.evaluate(run, [talk, {"phrasing": "syntax", "preset": "Score", "punct": False}])
    C(len(low) == 2 and low[1].startswith("whitehead"), "phrasing: Syntax reads the transcript even when a look lowercases it and hides punctuation", low)
    long = [[x, .1] for x in "When the many become one, the novel entity arises from them all.".split()]
    cut = await pg.evaluate(run, [long, {"phrasing": "syntax", "maxLines": 1}])
    C(cut[0] == "When the many become one," and " ".join(cut) == " ".join(x for x, _ in long), "phrasing: a sentence too long for the screen splits at its comma", cut)
    page = await pg.evaluate(run, [talk, {"phrasing": "syntax", "preset": "Manuscript"}])
    C(not any(L.startswith("¶") for L in page), "phrasing: on a Page, Syntax starts no paragraph mid-sentence", page)
    page = await pg.evaluate(run, [talk, {"preset": "Manuscript"}])
    C(any(L.startswith("¶that") for L in page), "phrasing: on a Page, Pauses starts a paragraph at the long pause", page)
    # the control
    for name, w, h, mob in (("desk", 1440, 900, False), ("phone", 390, 844, True)):
        if mob: await b.close(); b, pg, errs = await open_studio(p, base, w, h, mob)
        await pg.click("#tabs [data-t=motion]"); await pg.wait_for_timeout(200)
        n0 = await pg.evaluate("__studio.scene.phrases.length")
        C(await pg.is_visible("#s-pauseBreak"), f"phrasing {name}: the pause slider shows with Pauses")
        await pg.click("#phrasing [data-v=syntax]"); await pg.wait_for_timeout(500)
        st = await pg.evaluate("() => ({p: __studio.P.phrasing, n: __studio.scene.phrases.length})")
        C(st["p"] == "syntax" and st["n"] > 0, f"phrasing {name}: Syntax applies to the captions", [n0, st])
        C(not await pg.is_visible("#s-pauseBreak") and "Each sentence" in await pg.inner_text("#phrasingNote"), f"phrasing {name}: the pause slider gives way to a note")
        await (await pg.query_selector("#phrasing")).scroll_into_view_if_needed(); await pg.screenshot(path=f"{H.OUT}/phrasing_{name}.png")
        await pg.click("#undo"); await pg.wait_for_timeout(300)
        C(await pg.evaluate("__studio.P.phrasing") == "pause", f"phrasing {name}: Undo goes back to Pauses")
    await pg.click("#phrasing [data-v=syntax]"); await pg.wait_for_timeout(300)
    await pg.evaluate("window.__studio.flush()"); await pg.wait_for_timeout(400)
    body = next((s for s in reversed(H.SAVES) if '"audioId"' in s), "")
    doc = json.loads(body[body.index('{"v":1,"audioId"'):body.rindex("}") + 1]) if body else {}
    C((doc.get("params") or {}).get("phrasing") == "syntax", "phrasing: the choice is saved with the look in edits.json", doc.get("params"))
    C(not errs, "phrasing: no page errors", errs); await b.close()


async def t_cards(p, base):
    b, pg, errs = await open_studio(p, base)
    await pg.click("#tabs [data-t=voice]"); await pg.click('#cards [data-v="1"]'); await pg.wait_for_timeout(400)
    cards = await pg.evaluate("window.__studio.scene.cards.map(c => c.term)")
    C(cards == ["creativity"], "cards: only verified definitions become cards", cards)
    t = await pg.evaluate("window.__studio.scene.cards[0].s") + 1.2
    await pg.evaluate(f"document.getElementById('au').currentTime = {t}"); await pg.wait_for_timeout(600)
    await (await pg.query_selector("#stage")).screenshot(path=f"{H.OUT}/card.png")
    C(not errs, "cards: no page errors", errs); await b.close()


async def t_requests(p, base):
    ed = os.path.join(tempfile.mkdtemp(), "edits.json")
    json.dump({"v": 1, "audioId": H.AID, "base": 1, "params": {"preset": "Typewriter", "thEdits": {"3": "Soul-making"}}, "fixes": {}, "render": None,
               "glossary": [{"op": "accept", "term": "Whitehead", "at": 1000}, {"op": "reject", "term": "axiom", "at": 9e15}]}, open(ed, "w"))
    H.EDITS = ed
    b, pg, errs = await open_studio(p, base)
    C(await pg.evaluate("JSON.stringify(window.__studio.GL.map(g => g.term))") == '["axiom"]', "requests: ones older than glossary.json are treated as done")
    C(await pg.evaluate("window.__studio.data.words.filter(w => w.th != null && /axiom/i.test(w.w)).length") == 0, "requests: a pending Reject untags the term")
    C(await pg.evaluate("window.__studio.scene.themes[window.__studio.scene.words.find(w => w.i === 3).th]") == "Soul-making", "requests: theme edits by name apply")
    C(not errs, "requests: no page errors", errs); await b.close()
    H.EDITS = ""


async def t_thumb(p, base):
    for name, w, h, mob in (("desk", 1440, 900, False), ("phone", 390, 844, True)):
        H.SAVES.clear()
        b, pg, errs = await open_studio(p, base, w, h, mob)
        await pg.click("#tabs [data-t=thumb]"); await pg.wait_for_timeout(500)
        st = await pg.evaluate("() => ({on: document.body.classList.contains('thumb'), t: __studio.TH.title, s: __studio.TH.subtitle, n: __studio.tscene.words.length, W: __studio.tscene.W, H: __studio.tscene.H})")
        C(st["on"] and st["t"] == "Test walk" and st["s"].startswith("creativity"), f"thumb {name}: starts from the recording title, split at the colon", st)
        C("3840 × 2160" in await pg.inner_text("#thumbInfo"), f"thumb {name}: exports at 3840 × 2160")
        await pg.fill("#tTitle", "Creativity and the rhizome"); await pg.wait_for_timeout(400)
        heard = await pg.evaluate("__studio.tscene.words.filter(w => w.part === 't' && w.src != null).map(w => w.text)")
        C(heard == ["Creativity", "and", "the", "rhizome"], f"thumb {name}: title words found where they are spoken", heard)
        await pg.screenshot(path=f"{H.OUT}/thumb_{name}.png")
        await pg.click("#tPalettes [data-v=Ink]"); await pg.wait_for_timeout(300)
        st = await pg.evaluate("() => ({f: __studio.TH.follow, tp: __studio.TH.look.palette, vp: __studio.P.palette})")
        C(st["f"] is False and st["tp"] == "Ink" and st["vp"] != "Ink", f"thumb {name}: its own look leaves the video's look alone", st)
        await pg.click('#tPresets [data-tl="video"]'); await pg.wait_for_timeout(300)
        C(await pg.evaluate("__studio.TH.follow && __studio.tscene.P.palette === __studio.P.palette"), f"thumb {name}: Video's look follows the captions again")
        await pg.click("#tPresets [data-tl='p:Poster']"); await pg.wait_for_timeout(400)
        C(await pg.evaluate("__studio.tscene.P.font") == "Bricolage Grotesque", f"thumb {name}: a built-in look applies")
        k = await pg.evaluate("__studio.tscene.words.findIndex(w => w.text === 'rhizome')")
        wt0 = await pg.evaluate(f"__studio.tscene.words[{k}].chars[0].wt")
        await pg.click(f"#tWords span[data-k='{k}']"); await pg.wait_for_timeout(300)
        await pg.click("#tedSeg [data-v=emph]"); await pg.wait_for_timeout(500)
        st = await pg.evaluate(f"() => ({{e: __studio.TH.edits['rhizome#0'], wt: __studio.tscene.words[{k}].chars[0].wt}})")
        C(st["e"] == "emph" and st["wt"] > wt0, f"thumb {name}: Emphasize makes the word heavier", st)
        await pg.click('#tthRow [data-v="Re-enchantment"]'); await pg.wait_for_timeout(500)
        C(await pg.evaluate("__studio.TH.thEdits['rhizome#0']") == "Re-enchantment", f"thumb {name}: a word can take a theme")
        await pg.screenshot(path=f"{H.OUT}/thumb_word_{name}.png")
        await pg.click("#tDone"); await pg.wait_for_timeout(200)
        await pg.fill("#tTitle", "The rhizome, again"); await pg.wait_for_timeout(400)
        C(await pg.evaluate("__studio.tscene.words.find(w => w.key === 'rhizome#0').emph"), f"thumb {name}: an edit stays with its word when the text changes")
        await pg.click("#undo"); await pg.wait_for_timeout(400)
        C(await pg.evaluate("__studio.TH.title") == "Creativity and the rhizome", f"thumb {name}: Undo restores the earlier text")
        box = await pg.evaluate(f"() => {{ const s = __studio.tscene, w = s.words.find(x => x.text === 'Creativity'), r = document.getElementById('cv').getBoundingClientRect(); return {{x: r.left + (w.x + w.width / 2) / s.W * r.width, y: r.top + (w.base - w.S * 0.3) / s.H * r.height}}; }}")
        await pg.mouse.click(box["x"], box["y"]); await pg.wait_for_timeout(300)
        C("Creativity" in await pg.inner_text("#sheetBody .w"), f"thumb {name}: tapping a word on the image opens it")
        await pg.click("#tDone")
        await pg.click("#tAspect [data-v='9:16']"); await pg.wait_for_timeout(400)
        C(await pg.evaluate("[__studio.tscene.W, __studio.tscene.H]") == [1080, 1920], f"thumb {name}: 9:16 format")
        if not mob:
            async with pg.expect_download() as dl:
                await pg.click("#thumbSave")
            d = await dl.value; path = os.path.join(tempfile.mkdtemp(), d.suggested_filename); await d.save_as(path)
            from PIL import Image
            C(d.suggested_filename == "creativity-and-the-rhizome-thumbnail.png" and Image.open(path).size == (2160, 3840), "thumb: Save image downloads the PNG at full size", (d.suggested_filename, Image.open(path).size))
        await pg.click("#thumbDrive"); await pg.wait_for_timeout(800)
        C(any(H.AID + ".thumbnail.png" in s and "PNG" in s for s in H.SAVES), f"thumb {name}: Save to Drive uploads the image to Studio")
        await pg.evaluate("window.__studio.flush()"); await pg.wait_for_timeout(400)
        body = next((s for s in reversed(H.SAVES) if '"audioId"' in s), "")
        doc = json.loads(body[body.index('{"v":1,"audioId"'):body.rindex("}") + 1]) if body else {}
        C((doc.get("thumb") or {}).get("title") == "Creativity and the rhizome", f"thumb {name}: text, look and edits saved in edits.json", doc.get("thumb"))
        await pg.click("#tabs [data-t=look]"); await pg.wait_for_timeout(300)
        C(not await pg.evaluate("document.body.classList.contains('thumb')") and await pg.is_visible("#renderBtn"), f"thumb {name}: leaving the tab brings the video back")
        C(not errs, f"thumb {name}: no page errors", errs); await b.close()
    # a saved thumbnail comes back when the studio opens
    ed = os.path.join(tempfile.mkdtemp(), "edits.json")
    json.dump({"v": 1, "audioId": H.AID, "base": 1, "params": {"preset": "Typewriter"}, "fixes": {}, "render": None, "glossary": [],
               "thumb": {"title": "Saved title", "subtitle": "", "follow": False, "look": {"preset": "Score"}, "edits": {"title#0": "quiet"}}}, open(ed, "w"))
    H.EDITS = ed
    # the pipeline draws the same thumbnail from edits.json (notes.py thumb)
    d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "REC")); shutil.copy(H.CAPS, os.path.join(d, "REC", "captions.json"))
    r = subprocess.run([sys.executable, os.path.join(H.REPO, "tools", "notes.py"), "thumb", os.path.join(d, "REC"), ed, "--glossary", H.GLOSSF], capture_output=True, text=True)
    from PIL import Image
    png = os.path.join(d, "REC", "thumbnail.png")
    C(r.returncode == 0 and os.path.exists(png) and Image.open(png).size == (3840, 2160), "thumb: notes.py thumb renders the saved thumbnail at 3840 × 2160", (r.stdout + r.stderr)[-300:])
    b, pg, errs = await open_studio(p, base)
    await pg.click("#tabs [data-t=thumb]"); await pg.wait_for_timeout(500)
    st = await pg.evaluate("() => ({v: document.getElementById('tTitle').value, f: __studio.tscene.P.font, q: __studio.tscene.words[1].quiet})")
    C(st == {"v": "Saved title", "f": "Fraunces", "q": True}, "thumb: a saved thumbnail is restored", st)
    C(not errs, "thumb: no page errors on restore", errs); await b.close()
    H.EDITS = ""


async def t_sound(p, base):
    for name, w, h, mob in (("desk", 1440, 900, False), ("phone", 390, 844, True)):
        H.GETS.clear(); H.SAVES.clear()
        b, pg, errs = await open_studio(p, base, w, h, mob)
        await pg.wait_for_timeout(800)
        C(await pg.evaluate("__studio.REC") == "full" and await pg.evaluate("__studio.soundLevel") == "full", f"sound {name}: the recommended level plays by default")
        C(any(x.endswith("/CLEANFULL") for x in H.GETS) and not any(x.endswith("/" + H.AID) for x in H.GETS), f"sound {name}: only the cleaned copy is downloaded", H.GETS)
        await pg.click("#tabs [data-t=voice]"); await pg.wait_for_timeout(200)
        C(await pg.eval_on_selector_all("#denoise .rec", "e => e.map(x => x.dataset.v)") == ["full"], f"sound {name}: the recommended level is marked")
        await (await pg.query_selector("#denoise")).scroll_into_view_if_needed(); await pg.screenshot(path=f"{H.OUT}/sound_{name}.png")
        await pg.evaluate("() => { const a = document.getElementById('au'); a.currentTime = 20; }"); await pg.wait_for_timeout(200)
        await pg.click("#denoise [data-v=off]"); await pg.wait_for_timeout(900)
        st = await pg.evaluate("() => ({l: __studio.soundLevel, t: document.getElementById('au').currentTime, d: __studio.P.denoise})")
        C(st["l"] == "off" and abs(st["t"] - 20) < 0.6 and st["d"] == "off", f"sound {name}: Original switches the sound and keeps the place", st)
        await pg.click("#denoise [data-v=light]"); await pg.wait_for_timeout(700)
        C(await pg.evaluate("__studio.soundLevel") == "light", f"sound {name}: Light plays the light copy")
        await pg.click("#tabs [data-t=look]"); await pg.click("#presets .preset[data-p=Poster]"); await pg.wait_for_timeout(300)
        C(await pg.evaluate("__studio.P.denoise") == "light", f"sound {name}: changing the look keeps the sound choice")
        await pg.evaluate("window.__studio.flush()"); await pg.wait_for_timeout(400)
        body = next((s for s in reversed(H.SAVES) if '"audioId"' in s), "")
        doc = json.loads(body[body.index('{"v":1,"audioId"'):body.rindex("}") + 1]) if body else {}
        C((doc.get("params") or {}).get("denoise") == "light", f"sound {name}: the choice is saved with the recording", doc.get("params"))
        C(not errs, f"sound {name}: no page errors", errs); await b.close()
    lib = os.path.join(tempfile.mkdtemp(), "library.json")
    json.dump({"v": 1, "items": {H.AID: {"rev": 1, "title": "x", "noise": {"snr": 12.0, "rec": "light"}}}}, open(lib, "w"))
    H.CLEANDESC = False; H.LIBJSON = lib
    b, pg, errs = await open_studio(p, base); await pg.wait_for_timeout(600)
    C(await pg.evaluate("[__studio.REC, __studio.soundLevel]") == ["light", "light"], "sound: the noise reading can come from library.json")
    await b.close(); H.CLEANDESC = True; H.LIBJSON = ""
    H.CLEANPARTS = True; H.GETS.clear()
    b, pg, errs = await open_studio(p, base); await pg.wait_for_timeout(900)
    st = await pg.evaluate("() => ({l: __studio.soundLevel, d: document.getElementById('au').duration})")
    ref = json.load(open(H.CAPS))["duration"]
    C(st["l"] == "full" and abs((st["d"] or 0) - ref) < 1.5, "sound: a copy stored in parts is joined and plays whole", [st, ref])
    C(sorted(x[-5:] for x in H.GETS if "/PART" in x) == ["PART1", "PART2", "PART3"] and not any("OLDPART" in x for x in H.GETS),
      "sound: only the complete set of parts is downloaded", H.GETS)
    C(not errs, "sound: no page errors with parts", errs); await b.close()
    H.CLEANPARTS = False
    H.CLEANCOPIES = False
    b, pg, errs = await open_studio(p, base)
    await pg.click("#tabs [data-t=voice]"); await pg.wait_for_timeout(300)
    st = await pg.evaluate("() => ({l: __studio.soundLevel, dis: [...document.querySelectorAll('#denoise button')].map(b => b.disabled)})")
    C(st == {"l": "off", "dis": [False, True, True]}, "sound: without cleaned copies the original plays and Light and Full wait", st)
    C(not errs, "sound: no page errors without copies", errs); await b.close()
    H.CLEANCOPIES = True


GROUPS = {"library": t_library, "looks": t_looks, "follow": t_follow, "themes": t_themes, "words": t_words, "phrasing": t_phrasing, "cards": t_cards, "requests": t_requests, "thumb": t_thumb, "sound": t_sound}


async def main(names):
    base = H.serve()
    async with async_playwright() as p:
        for n in names:
            print(n); await GROUPS[n](p, base)
    print(f"\n{C.n - len(C.fails)} of {C.n} checks passed" + ("" if not C.fails else ":\n  " + "\n  ".join(C.fails)))
    sys.exit(1 if C.fails else 0)


if __name__ == "__main__":
    asyncio.run(main([a for a in sys.argv[1:] if a in GROUPS] or list(GROUPS)))
