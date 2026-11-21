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

## Limits
Web apps on iPhone can't record with the screen locked, so the app keeps the screen awake while recording. Uploads happen while the app is open.
