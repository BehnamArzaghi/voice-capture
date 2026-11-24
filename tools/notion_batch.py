#!/usr/bin/env python3
"""Many Notion property updates in one command, for runs on a computer with a Notion integration token.

  NOTION_TOKEN=secret_... python3 notion_batch.py CHANGES.json [--dry-run]

CHANGES.json is a list of changes:
  {"page": "<page id or URL>", "set": {"Theme": ["Re-enchantment"], "Status": "Accepted", "Verified": true,
                                        "Voice notes": ["<page id>", ...], "Definition": "text"}}
  {"create": "<data source id>", "set": {"Term": "rhizome", "Theme": "Re-enchantment", "Status": "Suggested"}}

Values are written according to each property's type, read from Notion: text for title / rich_text / url, a name for
select / status, a list of names for multi_select, a list of page ids for relation, true / false for checkbox, a number,
or an ISO date. A multi_select or relation value replaces the old one; prefix the property name with "+" to add to it
instead ("+Theme": ["Religion & theology"] keeps the themes already set).

Setup (once): create an internal integration at https://www.notion.so/profile/integrations, copy its token, and share the
Voice Notes and Glossary databases with it (database ... menu > Connections). Uses only the Python standard library.
"""
import json, os, re, sys, time, urllib.error, urllib.request

API, VERSION = "https://api.notion.com/v1", "2025-09-03"


def pid(x):
    m = re.findall(r"[0-9a-f]{32}|[0-9a-f-]{36}", str(x).lower())
    if not m: raise ValueError(f"not a Notion id: {x}")
    h = m[-1].replace("-", "")
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def call(method, path, body=None, tries=4):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + os.environ["NOTION_TOKEN"], "Notion-Version": VERSION,
                                          "Content-Type": "application/json"})
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and k < tries - 1:
                time.sleep(float(e.headers.get("Retry-After") or 1.5 * (k + 1))); continue
            raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:300]}")


def value(typ, v, old=None):
    """Notion API property value for type TYP; OLD (the current value) is merged in for "+" properties."""
    txt = lambda s: [{"type": "text", "text": {"content": str(s)[i:i + 2000]}} for i in range(0, max(1, len(str(s))), 2000)] if s else []
    if typ == "title": return {"title": txt(v)}
    if typ == "rich_text": return {"rich_text": txt(v)}
    if typ == "url": return {"url": v or None}
    if typ in ("select", "status"): return {typ: {"name": v} if v else None}
    if typ == "multi_select":
        names = ([o["name"] for o in (old or {}).get("multi_select", [])] if old is not None else []) + list(v or [])
        return {"multi_select": [{"name": n} for n in dict.fromkeys(names)]}
    if typ == "relation":
        ids = ([r["id"] for r in (old or {}).get("relation", [])] if old is not None else []) + [pid(x) for x in v or []]
        return {"relation": [{"id": i} for i in dict.fromkeys(ids)]}
    if typ == "checkbox": return {"checkbox": bool(v)}
    if typ == "number": return {"number": v}
    if typ == "date": return {"date": {"start": v} if v else None}
    raise ValueError(f"property type {typ} is not handled")


def build(schema, sets, current=None):
    """SCHEMA: {name: type}; CURRENT: the page's properties (for "+" merges)."""
    props = {}
    for k, v in sets.items():
        add = k.startswith("+"); name = k[1:] if add else k
        if name not in schema: raise KeyError(f"no property {name!r} (has: {', '.join(schema)})")
        props[name] = value(schema[name], v, (current or {}).get(name, {}) if add else None)
    return props


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    changes, dry = json.load(open(sys.argv[1])), "--dry-run" in sys.argv
    if not dry and not os.environ.get("NOTION_TOKEN"): sys.exit("set NOTION_TOKEN (see the setup note at the top of this file)")
    schemas, done, failed = {}, 0, []
    for ch in changes:
        try:
            if "create" in ch:
                ds = pid(ch["create"])
                if ds not in schemas:
                    schemas[ds] = {n: p["type"] for n, p in call("GET", f"/data_sources/{ds}")["properties"].items()}
                body = {"parent": {"type": "data_source_id", "data_source_id": ds}, "properties": build(schemas[ds], ch["set"])}
                if dry: print(json.dumps(body, ensure_ascii=False)); continue
                call("POST", "/pages", body)
            else:
                page = pid(ch["page"])
                if dry and "schema" in ch: print(json.dumps(build(ch["schema"], ch["set"]), ensure_ascii=False)); continue
                cur = call("GET", f"/pages/{page}")["properties"]
                body = {"properties": build({n: p["type"] for n, p in cur.items()}, ch["set"], cur)}
                if dry: print(json.dumps(body, ensure_ascii=False)); continue
                call("PATCH", f"/pages/{page}", body)
            done += 1
        except Exception as e:  # keep going; report at the end
            failed.append({"change": ch, "error": str(e)})
    print(json.dumps({"done": done, "failed": failed}, indent=1, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
