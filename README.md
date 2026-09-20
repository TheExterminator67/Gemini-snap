# Gemini Snap

Press a shortcut, it screenshots your whole screen, sends it to Google Gemini, and shows
**just the answer** in a small movable popup in the bottom-right corner. Queue up several
screenshots and get all the answers in a row. Works on **macOS** and **Windows**.

Status circle: red = idle, yellow = Gemini is working, green = answer ready
(a number next to it = screenshots waiting in the batch).
It lives in the menu bar on Mac and in the system tray on Windows.

First, get a **free** Gemini API key (each person needs their own): https://aistudio.google.com/apikey
Then download this repo (green **Code** button -> Download ZIP, or `git clone`).

## Easiest: download the ready-made app (no Python needed)

Go to the **Releases** page of this repo and download:

- **Windows:** `GeminiSnap-Windows.exe` - double-click it. If Windows says "protected your PC",
  click **More info** -> **Run anyway** (the app isn't code-signed).
- **Mac (Apple Silicon):** `GeminiSnap-Mac.zip` - unzip, then **right-click GeminiSnap -> Open** the
  first time. Allow **Screen Recording** for GeminiSnap when asked (System Settings ->
  Privacy & Security), then quit and reopen it. Intel Macs: use the Python method below.

Then set your API key from the menu bar / tray circle. Shortcuts are listed below.

## Or run from source

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
