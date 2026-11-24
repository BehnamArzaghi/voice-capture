# Voice capture

A one-button voice recorder for iPhone that saves straight to a Google Drive folder ("Voice Notes Inbox" by default), where the voice-caption studio picks recordings up.

- Records with the phone's microphone; every 4 seconds of audio is written to the phone as it's recorded, so a crash or closed app loses at most a few seconds.
- Uploads to Google Drive with resumable uploads; a dropped connection picks up where it left off.
- Works offline; recordings wait on the phone until there's signal and a Google sign-in.
- Asks Google only for access to files this app creates (`drive.file`).

## Setup
1. Google Cloud: create a project, enable the Google Drive API, set up Google Auth Platform (External, Testing, add yourself as a test user), and create a **Web application** client with
   - Authorized JavaScript origin: `https://behnamarzaghi.github.io`
   - Authorized redirect URI: `https://behnamarzaghi.github.io/voice-capture/`
2. Put the client ID in `config.js` (or paste it in the app's Settings).
3. Open the site in Safari → Share → **Add to Home Screen**. Open it from the Home Screen, tap Settings → Connect Google Drive.

For one-tap recording, turn on Settings → "Start recording when the app opens"; tapping the Home Screen icon then starts recording.

## Long recordings: the Parts folder
Claude's Google Drive connector downloads at most 10 MB per file (about 10 minutes at the default quality). So after a recording over 9 MB reaches Drive in full, the app also uploads it as pieces under 9 MB into `Voice Notes Inbox/Parts`, named "… · part 2 of 4.m4a".

- iPhone recordings are fragmented MP4: a header, then one fragment every ~4 s. Each piece is the header plus a run of whole fragments, so every piece plays on its own.
- The original is part 1 followed by every later part without its header, byte for byte. Each part's description and `appProperties` carry the header length and the SHA-256 of the original.
- `tools/join_parts.py OUT.m4a PART… --sha256 HEX` rebuilds and verifies the original; parts can be given in any order.

## Library and caption studio
The Library tab lists the recordings in Drive. After Claude processes them ("process my voice notes" in Claude), each one has captions you can tune in the studio (`studio.html`): look, voice mapping, motion, word corrections and a render request. Everything is saved to Drive:

- `Captions/<audio id>.captions.json`: written by Claude (words, timings, voice analysis). The file description holds a short JSON summary (rev, title, Notion link, video id) for the Library.
- `Captions/<audio id>.mp4` and `.srt`: rendered videos, made when the studio asks for one.
- `Studio/<audio id>.edits.json`: written by the app (look, corrections, render request, thumbnail). Claude re-times corrected words, raises `rev`, and includes an index remap so emphasis edits carry over.
- `Studio/<audio id>.thumbnail.png`: the thumbnail, when saved to Drive from the Thumbnail tab.
- `Listening copies/<audio id>.light.m4a` and `.full.m4a`: noise-reduced copies. Each file's description holds `{snr, rec, level}`, and `library.json` repeats `noise: {snr, rec}`.
- `Captions/vocabulary.txt`: names and terms given to the transcriber; corrected words and hard-to-spell glossary terms are added.
- `Captions/library.json`: the Library's summary of every captions file (title, rev, Notion link, video); written by `notes.py publish`.
- `Captions/glossary.json`: a copy of the Notion **Glossary** database (themes with their Notion colors; terms with forms, definition, source, status, verified). Claude refreshes it on each run.

## Noise reduction
Recordings made while driving or walking in wind carry steady background noise. Claude makes two noise-reduced copies of each recording, using RNNoise (Valin, 2018; through ffmpeg's `arnndn`, with a model trained for speech under recording noise):
- **Light:** most of the noise removed, some room sound kept.
- **Full:** also removes the steady hiss left after the first pass.

Both copies are brought back up to an even speaking level, and are saved as `Listening copies/<audio id>.light.m4a` and `.full.m4a`. Claude's Drive connector takes about 3 MB per upload, so a longer copy goes up in byte parts (`.full.m4a.p1of3`, ...), and the studio joins them back into the original file. Claude measures how far the voice stands above the background (in dB, between words) and recommends a level: Full below 8 dB, Light below 16 dB, the original above that. On the noisiest test recordings the noise between words fell by about 10 dB with Full, and transcription agreed with the existing transcript as well or better.

In the studio, **Sound** (top of the Voice tab) switches between Original, Light and Full while playing; a dot marks the recommended level. The choice is saved with the recording, and rendered videos use it. New recordings are cleaned when they are processed. A very noisy one (estimated before transcription) is transcribed and analyzed from the Full copy, so the voice-driven type follows the voice rather than the wind.

## Thumbnails
The studio's Thumbnail tab makes a still title card for the video, drawn by the same engine as the captions. It starts from the recording's title, split at the first colon into title and subtitle, and uses the video's look until a look control in the tab changes it. From then on it keeps its own look: the same looks, saved looks, colors, typefaces, placements, formats (16:9, 9:16, 1:1, 4:5) and voice and meaning settings as the captions, plus title and subtitle size, case (including Title Case) and a divider.

Words of the title that are heard in the recording borrow the loudness and pitch of the moment they are spoken, so weight, size, lift and lean work as they do in the video; Melody line turns the divider into the tune of the title as it was said. Glossary terms take their theme's color. Tap a word on the image (or in the tab's word list) to emphasize it, quiet it or change its theme; edits stay with the word when the text changes.

Save image exports a PNG at twice the video frame (3840 × 2160 for 16:9). On a phone it opens the share sheet (Save Image, Save to Files); on a computer it downloads. Save to Drive writes `Studio/<audio id>.thumbnail.png`. The text, look and word edits are saved in the recording's `edits.json` (`thumb`), and `tools/notes.py thumb WORK/ID EDITS.json` draws the same image in the pipeline.

## Themes and the glossary
Theme colors come from Notion: the Glossary database's Theme options (the same ten as Substack Articles) keep their Notion color in every recording, adjusted for contrast on each palette. When Claude processes a note it tags the glossary's terms in the transcript (`notes.py tag`), and suggests themes for the note's Notion row when a theme is heard at least 4 times, or 3 times across 2 different terms.

In the studio, the Voice tab lists the themes heard in the recording: tap one (or a term) to jump to its next mention, or hide a theme's color. Tap any word to tag it: ‹ › widen the selection to a phrase; choose a theme for this place, the whole recording, or the glossary (Claude adds the term to Notion on its next run). Terms Claude suggested are underlined with dashes in Words; Accept or Reject them from the word or term sheet. These requests are saved in the recording's `edits.json` (`glossary`), and Claude applies them in Notion. Definition cards show a term's definition in the video where it is first heard, only for definitions marked Verified in Notion; unchecked definitions carry an "unverified" label in the studio.

The Library needs read access to Drive files the app didn't create (`drive.readonly`), because the captions are written by Claude. Keep this the only GitHub Pages site on the account: every Pages site under the same `*.github.io` address shares the browser storage that holds the sign-in token.

## Processing tools
`tools/notes.py` runs the local steps of processing (transcription with forced alignment, captions, listening copy for Notion, applying corrections, glossary tagging, rendering); `tools/vc.py` is the caption engine's Python side and shares `engine.js` with the studio.

Caption timing is checked against a second, silence-skipping transcription pass: on long recordings with pauses, a single whole-recording pass can slide its timestamps by up to ~20 s. `notes.py retime AUDIO CAPTIONS.json` repairs captions made before this check (Nov 23, 2026) without changing their words, so studio edits still fit.

## Optional: running on a computer
The standard setup is fully in the cloud. A Claude chat in the "Voice Capture" project does the work through its Google Drive and Notion connectors, and a nightly scheduled task processes new recordings. Nothing needs to be installed. The steps below are an optional speed-up for bulk work on one computer, and nothing depends on them.

**Google Drive for desktop.** Install it (https://www.google.com/drive/download/), sign in as the Drive account the app uses, and make "Voice Notes Inbox" available on the computer: either mirror My Drive, or stream it and set the folder to "Available offline". Then `notes.py publish CAPTIONS.json ... --drive-dir "<path to Voice Notes Inbox>"` writes the captions, `glossary.json`, `vocabulary.txt` and `library.json` straight into `Captions/`. Drive syncs them as updates to the existing files. The app looks files up by name and uses the newest, so nothing needs trashing, and no file descriptions are needed because the Library reads `library.json`. New recordings and studio edits appear in the same folder as ordinary files.

**Notion integration token.** At https://www.notion.so/profile/integrations, create an internal integration and copy its token. Then share the Voice Notes and Glossary databases with it: open each database, then the ••• menu, then Connections. With `NOTION_TOKEN` set, `python3 tools/notion_batch.py changes.json` applies many property updates (themes, glossary status, relations) in one command. Writing note pages (transcripts, TL;DRs) still goes through Claude's Notion connector.

**Tools.** Python 3.10+, ffmpeg, and `python3 tools/notes.py setup` (speech model, aligner, fonts; it needs Chrome or `playwright install chromium`). The scheduled nightly run stays in the cloud unless it is set to require this computer, which must then be awake.

## Tests
`python3 tests/test_tools.py` (pipeline checks) and `python3 tests/run_tests.py` (browser tests for the Library and studio). Both use a synthetic recording, so no personal data is in the repo. See `CLAUDE.md`.

## Desktop
On screens 1000 px and wider the studio uses two columns (stage and player on the left, the Look / Voice / Motion / Words panels on the right) and the Library shows recordings in a grid. In the Words tab the transcript follows the playing word until you scroll it yourself; a button brings you back.

## Limits
Web apps on iPhone can't record with the screen locked, so the app keeps the screen awake while recording. Uploads happen while the app is open.
