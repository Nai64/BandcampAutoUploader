![Bandcamp Auto Uploader](screenshots/screenshot1.png)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License MIT">
  <img src="https://img.shields.io/badge/Version-0.2.15-blue?style=for-the-badge" alt="Version 0.2.15">
</p>

<h1 align="center">Bandcamp Auto Uploader</h1>

<p align="center">
  <strong>Upload your music to Bandcamp in bulk — no Pro account needed.</strong><br>
  Drag in a folder of audio files, review the tracks, and upload. That's it.<br>
  <sub>Forked from <a href="https://github.com/7x11x13">7x11x13</a>'s original work.</sub>
</p>

<p align="center">
  <sub>Works with FLAC, WAV, AIFF, MP3, MOD, XM · Only lossy formats (MP3) are converted to FLAC · Pulls tags from metadata</sub>
</p>

---

## Quick Start

1. **Download the app** — grab the latest `BandcampAutoUploaderGUI.exe` from the [Releases page](https://github.com/Nai64/BandcampAutoUploader/releases). No Python installation needed.
2. **Launch it** — the upload window opens immediately.
3. **Log in** — click the **Artists** button. The app finds your Bandcamp login from Chrome, Firefox, Edge, or other browsers and shows your artist pages.
4. **Pick an artist** — select which Bandcamp page to upload to.
5. **Drag in an album folder** — drop a folder with your audio files onto the window. The app reads track titles, artist names, cover art, and more from your files' metadata.
6. **Upload** — click the **Upload** button and the app does the rest (cover art, tracks, album info).

> Your settings, prices, and preferences are saved automatically to `Documents\Bandcamp Auto Uploader\config.json`.

---

## What You Can Do

| Feature | What it means for you |
|---|---|
| **Bulk upload** | Upload whole albums at once instead of one track at a time in a browser |
| **Any audio format** | FLAC, WAV, AIFF, MP3, MOD, XM — lossy formats (MP3) are converted to FLAC; lossless files (FLAC, WAV, AIFF) and tracker modules (MOD, XM) are uploaded as-is (FFmpeg required for conversion) |
| **Cover art auto-detect** | Finds cover images in your album folder, or extracts them from audio tags |
| **Browser login** | Reads your Bandcamp session from Chrome, Firefox, Edge, Brave, Opera, Vivaldi, and more |
| **Track management** | Reorder tracks, edit metadata, lock/unlock, randomize, undo/redo — right-click any track |
| **Album templates** | Save your common album settings (prices, tags, descriptions) as presets |
| **CSRF auto-refresh** | If your session expires mid-upload, the app refreshes it and retries automatically |
| **Notifications** | Get a toast when uploads complete (or for errors) |

---

## How It Works (the short version)

1. The app grabs your Bandcamp login from your browser's cookies — **your credentials never leave your computer**.
2. It authenticates with Bandcamp's standard artist edit interface (the same one you use in a browser).
3. Lossy formats (MP3) are converted to FLAC 16-bit 44.1 kHz (Bandcamp's preferred format) via FFmpeg. Lossless files (FLAC, WAV, AIFF) go through as-is.
4. Cover art is uploaded, then tracks are uploaded with their metadata.
5. Everything lands on your Bandcamp artist page — done.

---

## FAQ

### Do I need a Pro account?
**No.** This works with any free Bandcamp artist account.

### Will I get banned?
The tool uses your own browser session and respects rate limits — it looks just like normal browser usage. Use it responsibly.

### Why does it need my browser cookies?
It reads your Bandcamp login session from your browser to authenticate. Cookies are never sent anywhere except to bandcamp.com.

### Upload got a 403 error?
Click the **Artists** button to re-authenticate. The app will re-scan your browsers for a fresh session.

### What audio formats are supported and which get converted?
FLAC, WAV, AIFF, and MP3. Only lossy formats (MP3) are converted to FLAC 16-bit 44.1 kHz before upload. Lossless files (FLAC, WAV, AIFF) are uploaded without re-encoding. FFmpeg is required for MP3 conversion.

### What if I don't use a supported browser?
You can upload a `cookies.txt` file instead. The CLI (`bc-upload`) guides you through this.

## Third-party licenses

- [Azure ttk theme](https://github.com/rdbende/Azure-ttk-theme) by rdbende is bundled under the MIT License.
- [TKinterModernThemes](https://github.com/RobertJN64/TKinterModernThemes) by Robert Nies is used for Sun-Valley theme support under the MIT License. TKinterModernThemes credits the included Sun-Valley theme work to [rdbende](https://github.com/rdbende).

## Need Help?

- [Browse open issues](https://github.com/Nai64/BandcampAutoUploader/issues)
