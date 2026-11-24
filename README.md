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
- `Studio/<audio id>.edits.json`: written by the app (look, corrections, render request). Claude re-times corrected words, raises `rev`, and includes an index remap so emphasis edits carry over.
- `Captions/vocabulary.txt`: names and terms given to the transcriber; corrected words and hard-to-spell glossary terms are added.
- `Captions/glossary.json`: a copy of the Notion **Glossary** database (themes with their Notion colors; terms with forms, definition, source, status, verified). Claude refreshes it on each run.

## Themes and the glossary
Theme colors come from Notion: the Glossary database's Theme options (the same ten as Substack Articles) keep their Notion color in every recording, adjusted for contrast on each palette. When Claude processes a note it tags the glossary's terms in the transcript (`notes.py tag`), and suggests themes for the note's Notion row when a theme is heard at least 4 times, or 3 times across 2 different terms.

In the studio, the Voice tab lists the themes heard in the recording: tap one (or a term) to jump to its next mention, or hide a theme's color. Tap any word to tag it: ‹ › widen the selection to a phrase; choose a theme for this place, the whole recording, or the glossary (Claude adds the term to Notion on its next run). Terms Claude suggested are underlined with dashes in Words; Accept or Reject them from the word or term sheet. These requests are saved in the recording's `edits.json` (`glossary`), and Claude applies them in Notion. Definition cards show a term's definition in the video where it is first heard, only for definitions marked Verified in Notion; unchecked definitions carry an "unverified" label in the studio.

The Library needs read access to Drive files the app didn't create (`drive.readonly`), because the captions are written by Claude. Keep this the only GitHub Pages site on the account: every Pages site under the same `*.github.io` address shares the browser storage that holds the sign-in token.

## Processing tools
`tools/notes.py` runs the local steps of processing (transcription with forced alignment, captions, listening copy for Notion, applying corrections, glossary tagging, rendering); `tools/vc.py` is the caption engine's Python side and shares `engine.js` with the studio.

Caption timing is checked against a second, silence-skipping transcription pass: on long recordings with pauses, a single whole-recording pass can slide its timestamps by up to ~20 s. `notes.py retime AUDIO CAPTIONS.json` repairs captions made before this check (Nov 23, 2026) without changing their words, so studio edits still fit.

## Desktop
On screens 1000 px and wider the studio uses two columns (stage and player on the left, the Look / Voice / Motion / Words panels on the right) and the Library shows recordings in a grid. In the Words tab the transcript follows the playing word until you scroll it yourself; a button brings you back.

## Limits
Web apps on iPhone can't record with the screen locked, so the app keeps the screen awake while recording. Uploads happen while the app is open.
