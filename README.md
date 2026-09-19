# Gemini Snap

A tiny **macOS menu bar app**: press a shortcut, it screenshots your whole screen,
sends it to Google Gemini, and shows just the answer in a small movable popup in the
bottom-right corner. Queue up several screenshots and get all the answers in a row.

Menu bar circle: 🔴 idle · 🟡 Gemini is working · 🟢 answer ready
(a number next to it = screenshots waiting in the batch)

> macOS only (Apple Silicon or Intel). Needs Python 3.9+.

## Install

1. Get a **free** Gemini API key: https://aistudio.google.com/apikey
2. Download this repo (green **Code** button → Download ZIP, or `git clone`).
3. Start it:
   - double-click `run.command` (first time: right-click → Open), or
   - in Terminal: `bash run.command`

   The first run creates a virtual environment and installs the dependencies.
4. Click the circle in the menu bar → **Set Gemini API Key…** and paste your key.
5. When macOS asks, allow **Screen Recording** for Terminal
   (System Settings → Privacy & Security → Screen Recording), then restart the app.
   Without it the screenshot is just your wallpaper.

## Shortcuts

| Shortcut | Action |
|---|---|
| ⌥⌘1 | Screenshot now and answer |
| ⌥⌘3 | Add a screenshot to the batch |
| ⌥⌘4 | Send the batch, get all answers in a row |
| ⌥⌘5 | Clear the batch |
| ⌥⌘2 | Hide / show the popup |

Drag the popup by its top strip to move it. Answers are final answers only, no explanations.

## Settings

Stored in `~/.gemini_snap_v2/config.json` (created after you set your key). You can edit:
`model` (default `gemini-2.5-flash`; try `gemini-flash-latest` if you get "model not found"),
`prompt_single`, `prompt_batch`, and the hotkeys (e.g. `"hotkey_capture": "cmd+shift+1"`).
Your API key stays on your machine and is never part of this repo.

## Troubleshooting

- **Screenshot is only wallpaper** → Screen Recording permission missing (step 5).
- **A shortcut does nothing** → another app uses it; change it in the config file.
- **Rate limit error** → the free tier is limited; wait a minute.

MIT licensed.
