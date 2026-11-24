# Voice capture: notes for Claude

Behnam Arzaghi's voice recorder and caption studio. It is an iPhone web app on GitHub Pages (https://behnamarzaghi.github.io/voice-capture/). Google Drive and Notion are its backend, and the Python pipeline in `tools/` does the processing. Read `README.md` for how it works. This file covers how to work on it.

## Writing for Behnam
- Plain declarative prose. No first-person phrasing ("I think", "I'll"), no praise, no exclamation marks. UI text follows the same rules.
- Claims about what a thinker or text holds are checked against a source, or marked "[unverified — from training data]". This applies to glossary definitions too.
- He works mostly from an iPhone, and sometimes from a desktop browser. Every feature must work on a phone.

## Layout
| Path | What |
|---|---|
| `index.html`, `app.js` | Recorder and Library tabs |
| `studio.html` | Caption studio: Look, Voice (themes), Motion and Words tabs; word sheet; term sheet |
| `engine.js` | Caption engine. The studio and the video renderer share it, so changes show in both |
| `shared.js` | `VCDrive`: Drive helpers used by both pages |
| `sw.js` | Service worker. **Bump `CACHE` (vc-shell-vN) whenever a shipped file changes** |
| `tools/notes.py` | Pipeline commands: prepare, apply, retime, glossary, tag, publish, render (see its docstring) |
| `tools/vc.py` | Analysis, alignment and rendering (headless Chrome running `engine.js`) |
| `tools/notion_batch.py` | Many Notion updates in one command (needs `NOTION_TOKEN`; desktop runs) |
| `tests/` | Browser tests (Playwright) and pipeline checks, on a synthetic recording |

## Test before every push
```bash
python3 tests/test_tools.py        # pipeline checks, a few seconds
python3 tests/run_tests.py         # browser tests, about 1 minute; screenshots in tests/shots/
python3 tests/run_tests.py themes  # one group: library, looks, follow, themes, cards, requests
```
- The tests serve the repo locally and stand in for Google Drive with local files. They need Playwright for Python and a Chrome or Chromium: `python3 tools/notes.py setup` installs them, or `pip install playwright && playwright install chromium`.
- Look at the screenshots for anything visual. Check both a phone viewport (390×844) and a desktop one (1440×900).
- Personal data (real captions, audio, transcripts) never goes in the repo, which is public. To try a real recording, point the `CAPS`, `AUDIO` and `AID` environment variables at files outside it.

## Commit and push
- Push straight to `main`; GitHub Pages deploys in about a minute. In Claude's cloud workspace, use `git -c push.negotiate=true push origin HEAD:main`.
- Keep commit messages short. In the body, say what changed for Behnam.
- End the message with the attribution lines the session asks for (Co-Authored-By and Claude-Session).
- After a change to shipped files: bump `sw.js`, run the tests, push. Tell him to pull to refresh in the app.

## Data contracts (keep backward compatible)
- `Captions/<audio id>.captions.json`: `{audioId, title, rev, duration, notion, listen, video, remap, data}`. `data` holds `words` (w, s, e, p, fl, fn, th, emph, pitch, ...), `env`, `themes`, `themeColors` and `terms`. Raise `rev` only when the words change (`notes.py apply`), and store an index remap when it does.
- `Captions/library.json`: `{items: {id: {rev, title, duration, notion, videoId, videoAt, srtId}}}`. The Library reads this, and also each file's Drive description (older runs); whichever is newer wins.
- `Captions/glossary.json`: a copy of the Notion Glossary. `updatedAt` marks which studio requests are done.
- `Studio/<id>.edits.json`, written by the studio: `{base, params, fixes, render, glossary}`.
  - `params.thEdits` maps a word index to a theme name, with `""` for no theme. Older edits use numeric indices.
  - `params.thOff` lists hidden themes. Like `edits` and `thEdits`, it belongs to the recording and is never saved in a look.
- `Studio/looks.json`: saved looks.

## Where things live
- Drive (account behnam@uni.minerva.edu): folder "Voice Notes Inbox" `151MROBuPUjVyZ_im8uOH4qT6pNw0-oC5`, with Captions `1TBs6zCDELTV4K249mr8mdL4qc8Qq0EGP`, Listening copies `1pQU1la_Ufv3bJMuziN4oPV3qzcgq4YaS`, Studio and Parts.
- Notion data sources:
  - Voice Notes `41af7a0a-73cb-81ac-97af-000bbb3d1008`
  - Glossary `421f7a0a-73cb-81a1-9853-000b5d8bd43c`
  - Substack Articles `5ed7680b-e340-4b05-b2dc-dc74130bc60e`
  - Task List `cae389a6-de1d-48a6-9d44-fc5ecbfdd6b9`
- Processing a recording follows the `process-voice-notes` skill in his account. Code changes belong here, in the repo.

## Gotchas
- iOS web apps can't record with the screen locked. Keep the screen-awake behavior.
- In Claude's cloud workspace, the shell can't reach googleapis.com or api.notion.com, so Drive and Notion go through the connectors there. On a desktop, Google Drive for desktop and `notion_batch.py` replace most connector calls (see README, "Running on a desktop").
- The Drive connector downloads at most 10 MB per file; recordings over 9 MB also arrive as `Parts/`.
- Theme colors come from Notion color names (`themeColors`). `engine.js` turns each name into a color that reads on the chosen palette.
