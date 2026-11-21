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

## Limits
Web apps on iPhone can't record with the screen locked, so the app keeps the screen awake while recording. Uploads happen while the app is open.
