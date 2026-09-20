# Gemini Snap

Press a shortcut, it screenshots your whole screen, sends it to Google Gemini, and shows
**just the answer** in a small movable popup in the bottom-right corner. Queue up several
screenshots and get all the answers in a row. Works on **macOS** and **Windows**.

Status circle: red = idle, yellow = Gemini is working, green = answer ready
(a number next to it = screenshots waiting in the batch).
It lives in the menu bar on Mac and in the system tray on Windows.

First, get a **free** Gemini API key (each person needs their own): https://aistudio.google.com/apikey

## Easiest: download the ready-made app (no Python, no installing anything)

Open the **Releases** page of this repo (right side of the repo page) and download:

### Mac
- **Apple Silicon** (M1, M2, M3, M4...): `GeminiSnap-Mac-AppleSilicon.zip`
- **Intel**: `GeminiSnap-Mac-Intel.zip`

Not sure which? Apple menu -> **About This Mac**: it says "Chip: Apple M..." or "Processor: Intel".

1. Unzip it and drag **GeminiSnap** into your Applications folder.
2. The first time, macOS blocks apps that aren't from the App Store. To open it:
   - Try **right-click -> Open -> Open**. If that doesn't work (newer macOS): double-click it once,
     then go to **System Settings -> Privacy & Security**, scroll down and click **Open Anyway**.
   - Or paste this in Terminal once: `xattr -dr com.apple.quarantine /Applications/GeminiSnap.app`
3. Click the circle in the menu bar -> **Set Gemini API Key...** and paste your free key
   (https://aistudio.google.com/apikey).
4. Allow **Screen Recording** for GeminiSnap when asked (System Settings -> Privacy & Security),
   then quit and reopen it. Without it the screenshot is just your wallpaper.

### Windows
- `GeminiSnap-Windows.zip` - unzip it, open the folder and double-click `GeminiSnap.exe`.
  The app isn't code-signed, so Windows Defender / your browser may warn about it (a common false
  alarm for unsigned Python apps that take screenshots and use hotkeys). The full source is in this
  repo. If it still gets blocked, use "Run from source" below.
- Find the colored circle in the system tray (bottom-right, maybe under the ^ arrow), right-click it
  -> **Set Gemini API Key...**

Shortcuts are listed below.

## Or run from source (needs Python 3.9+, for developers)

## macOS (needs Python 3.9+)

1. Double-click `run.command` (first time: right-click -> Open), or run `bash run.command` in Terminal.
   The first run installs everything automatically.
2. Click the circle in the menu bar -> **Set Gemini API Key...** and paste your key.
3. Allow **Screen Recording** for Terminal when macOS asks
   (System Settings -> Privacy & Security), then restart the app.
   Without it the screenshot is just your wallpaper.

| Shortcut | Action |
|---|---|
| ⌥⌘1 | Screenshot now and answer |
| ⌥⌘3 | Add a screenshot to the batch |
| ⌥⌘4 | Send the batch, all answers in a row |
| ⌥⌘5 | Clear the batch |
| ⌥⌘2 | Hide / show the popup |

## Windows 10/11 (needs Python 3.9+ from python.org, tick "Add Python to PATH")

1. Double-click `run_windows.bat`. The first run installs everything automatically.
2. Find the colored circle in the system tray (bottom-right; it may be under the ^ arrow),
   right-click it -> **Set Gemini API Key...** and paste your key.

| Shortcut | Action |
|---|---|
| Ctrl+Alt+1 | Screenshot now and answer |
| Ctrl+Alt+3 | Add a screenshot to the batch |
| Ctrl+Alt+4 | Send the batch, all answers in a row |
| Ctrl+Alt+5 | Clear the batch |
| Ctrl+Alt+2 | Hide / show the popup |

Only your main monitor is captured. Right-click the tray circle -> Quit to close it.
Crashes are logged to `%USERPROFILE%\.gemini_snap_v2\error.log`.

## Using it

Drag the popup by its top strip to move it. Answers are final answers only, no explanations.
The popup hides itself while a screenshot is taken so it never shows up in the picture.

## Settings

Stored in `~/.gemini_snap_v2/config.json` (created after you set your key). You can edit
`model` (default `gemini-2.5-flash`; try `gemini-flash-latest` on "model not found"),
`prompt_single`, `prompt_batch`, and the hotkeys (Mac: `hotkey_capture` etc., e.g. `"cmd+shift+1"`;
Windows: `hk_capture` etc., e.g. `"ctrl+shift+s"`). Your API key stays on your machine and is
never part of this repo.

## Troubleshooting

- **Screenshot is only wallpaper (Mac)** -> Screen Recording permission missing.
- **A shortcut does nothing** -> another app uses it; change it in the config file.
- **Rate limit error** -> the free tier is limited; wait a minute.

MIT licensed.
