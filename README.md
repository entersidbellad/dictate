# Dictate — local Wispr Flow clone for macOS

Hold **Right ⌘**, speak, release — your words are transcribed **entirely on-device** (NVIDIA Parakeet via MLX) and pasted into whatever app has focus. No subscription, no cloud, no audio ever leaves your Mac.

## Install

```sh
git clone <this-repo-url>
cd dictate
./install.sh
```

This sets up a `wispr` terminal command, a menu-bar `Dictate.app` in `~/Applications`, and optionally a login item — all generated for wherever you cloned the repo, so it works regardless of your username or folder layout. Re-run `install.sh` anytime (e.g. after moving the folder) to regenerate everything.

## Ways to start it

- **`wispr`** — type this in any terminal. Safe to run twice; a second copy exits immediately and says so.
- **Dictate.app** — in `~/Applications`; double-click, or `open -a Dictate`. Menu-bar only, no Dock icon.
- **Auto-start at login** — answer yes when `install.sh` asks, or run it again and opt in. Remove anytime with `rm ~/Library/LaunchAgents/com.dictate.app.plist`.

## Voice commands

Dictate a command instead of text (must be the entire utterance, so normal sentences can never trigger them):

| Say | Does |
|---|---|
| "Scratch that" / "Undo that" / "Delete that" | Undoes your last dictation (⌘Z in the target app; works within 2 min, same app) |
| "Make it formal / casual / polite / shorter / longer" | Rewrites your last dictation in place |
| "Rewrite it as bullet points" | Turns your last dictation into a list |
| "Add *word* to my dictionary" | Teaches Dictate a name/term |

Command detection is regex-based (deterministic) — unknown phrases like "make it work by Friday" are inserted as normal text.

## Personal dictionary

Words in `~/.config/dictate/dictionary.txt` (one per line, or added by voice) get two treatments: the cleanup LLM is told to prefer those spellings, and a deterministic pass enforces your exact casing (`mlx` → `MLX`, `siddharth` → `Siddharth`) on every insertion.

## Per-app tone matching

With **Match App Tone** on (default), cleanup adapts to where you're dictating: casual in Messages/Slack/Discord/WhatsApp/Telegram, formal in Mail/Outlook/Word/Pages, neutral elsewhere. Edit the bundle-ID sets in [commands.py](src/dictate/commands.py) to customize.

## AI Cleanup

When **AI Cleanup** is checked in the menu (default on), transcripts pass through a local Qwen 2.5 3B model (via mlx-lm) that removes filler words (um, uh), false starts, and applies self-corrections — "move it to Tuesday no wait Wednesday" becomes "move it to Wednesday". Adds ~0.5–1 s. Toggle it off in the menu for raw, fastest insertion; the setting persists in `~/.config/dictate/config.json`.

## Running from source (skip if you used install.sh)

```sh
uv sync
uv run dictate
```

First run downloads the Parakeet model (~1.2 GB, cached in `~/.cache/huggingface`) and, if AI Cleanup is on, the Qwen cleanup model (~1.7 GB). After that everything is offline.

### Permissions (one-time)

Grant these to **the app you launch `dictate` from** (Terminal, iTerm, Ghostty, …) in **System Settings → Privacy & Security**:

| Permission | Why |
|---|---|
| Microphone | record your speech (macOS prompts automatically) |
| Input Monitoring | detect the Right ⌘ hotkey globally |
| Accessibility | synthesize the ⌘V keystroke that inserts text |

Restart `dictate` after granting. If the hotkey does nothing, Input Monitoring is the usual culprit.

## The cat 🐈

While you hold Right ⌘, an animated ginger kitten appears at the bottom-center of the screen and lip-syncs to your voice (mouth opens with your mic level). When you release, it looks up and thinks (animated thought bubble) while transcription runs, then fades away once your text is inserted. Toggle via **Show Cat** in the menu. Preview anytime with `uv run python scripts/cat_demo.py`. The overlay is click-through and floats above full-screen apps.

**Custom cat art**: drop three transparent PNGs into `src/dictate/assets/` — `cat_idle.png` (mouth closed), `cat_talk.png` (mouth open), `cat_think.png` (looking up) — and restart. The overlay switches to your sprites automatically (frame-swap lip-sync + squash-and-stretch); if any file is missing or unreadable it falls back to the built-in drawn kitten. Generate them with any AI image tool (e.g. "Pixar-style ginger tabby kitten, front facing, mouth open, transparent background").

## Usage

- **Hold Right ⌘** → pop sound, menu bar shows 🔴, speak.
- **Release** → transcription runs (⏳), text is pasted at your cursor.
- Quick taps (<0.3 s) and Right-⌘ shortcuts (e.g. ⌘C with the right key) are ignored.
- The menu bar item shows the last transcription; **Quit** exits.

## Safety & privacy

- **Fully offline**: once the model is cached, `HF_HUB_OFFLINE=1` is set before any Hugging Face code loads — the app makes zero network requests. Audio and transcripts never leave your Mac.
- **Password fields are protected**: when macOS secure input is active (a password field has focus), recording and insertion are blocked (`🔒` in the menu).
- **Clipboard is preserved in full**: the entire pasteboard — text, images, files — is snapshotted and restored after pasting, and only if you haven't copied something new in the meantime.
- **Clipboard managers won't log dictations**: transcripts are written with the `org.nspasteboard.ConcealedType` marker, which well-behaved clipboard managers skip.
- **Failed pastes are surfaced**: if ⌘V can't be synthesized (Accessibility missing), the menu tells you and leaves the text on the clipboard so you can paste manually.
- **Bounded recording**: capture stops after 5 minutes even if the key stays held; long recordings are transcribed in overlapping chunks.
- Audio is briefly written to a temp WAV with `0600` permissions and deleted immediately after transcription.

Notes:
- English only (Parakeet TDT 0.6B). For multilingual, swap `MODEL_ID` in `src/dictate/transcriber.py` for an mlx-community Whisper model and adjust accordingly.

## Testing

```sh
uv run pytest -m "not slow"   # unit tests: fast, offline, no keystrokes/mic
uv run pytest                 # + model integration tests (needs cached models)
```

The suite covers the hotkey state machine, recorder cap, clipboard snapshot/restore, secure-input blocking, offline-mode logic, temp-file hygiene, single-instance lock, config corruption, the launchd-PATH regression (ffmpeg reachability), and LLM cleanup guards — including a deterministic anti-prompt-injection sanity check on cleanup output (`output_is_sane` in [cleaner.py](src/dictate/cleaner.py)): if the model obeys an instruction embedded in your speech instead of cleaning it, the raw transcript is inserted instead.

Manual end-to-end checklist (once per setup change): dictate into Notes with cleanup on and off; copy an image, dictate, verify the image still pastes afterward; focus a password field and confirm 🔒 blocks recording; run `wispr` twice and confirm the second exits.

## Known limitations

- The ⌘V keystroke uses ANSI keycode 9 ('v'); non-QWERTY hardware layouts may need a different keycode.
- The menu bar shows your last transcription — visible during screen shares.
- Moving or renaming the project folder breaks `wispr` and Dictate.app (both point at `.venv` by absolute path) — re-run `./install.sh` after moving it.
- Dictation is English-only; the cleanup guard assumes cleanup shouldn't invent words, so heavy rephrasing is (deliberately) rejected.

## How it works

```
pynput (Right ⌘ down/up) → sounddevice records 16 kHz mono
  → parakeet-mlx transcribes on a worker thread
  → clipboard swap + synthesized ⌘V pastes into the frontmost app
```

Source layout: [app.py](src/dictate/app.py) (menu bar + wiring), [hotkey.py](src/dictate/hotkey.py), [recorder.py](src/dictate/recorder.py), [transcriber.py](src/dictate/transcriber.py), [inserter.py](src/dictate/inserter.py).
