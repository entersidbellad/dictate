"""Menu bar app wiring the hotkey, recorder, transcriber, cleaner, and inserter."""

import fcntl
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

import rumps
from AppKit import NSWorkspace
from Foundation import NSOperationQueue

from . import cleaner as cleaner_mod
from . import transcriber as transcriber_mod
from .cleaner import Cleaner
from .commands import (
    REWRITE_STYLES,
    TONE_INSTRUCTIONS,
    add_to_dictionary,
    apply_dictionary_casing,
    extract_list_request,
    extract_style_request,
    load_dictionary,
    parse_command,
    tone_for_bundle,
)
from .hotkey import HoldHotkey
from .inserter import insert_text, secure_input_active, undo_in_frontmost
from .overlay import CatOverlay
from .permissions import ensure_permissions
from .recorder import MAX_SECONDS, SAMPLE_RATE, Recorder
from .transcriber import Transcriber, maybe_go_offline

IDLE = "🎤"
RECORDING = "🔴"
BUSY = "⏳"
FAILED = "⚠️"

SOUND_START = "/System/Library/Sounds/Pop.aiff"
SOUND_STOP = "/System/Library/Sounds/Blow.aiff"
SOUND_ERROR = "/System/Library/Sounds/Basso.aiff"

CONFIG_PATH = Path.home() / ".config" / "dictate" / "config.json"
LOCK_PATH = Path.home() / ".cache" / "dictate.lock"
_lock_handle = None  # keeps the single-instance flock alive for process lifetime

# a dictation queued longer than this is dropped rather than pasted into
# whatever window happens to be focused much later
STALE_SECONDS = 60

# "scratch that" / "make it ..." only act on an insertion newer than this
SCRATCH_WINDOW_SECONDS = 120


def _frontmost_bundle_id() -> str | None:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.bundleIdentifier() if app is not None else None


def _ensure_homebrew_path() -> None:
    """parakeet-mlx shells out to ffmpeg; launchd's default PATH lacks Homebrew."""
    current = os.environ.get("PATH", "").split(":")
    for p in ("/opt/homebrew/bin", "/usr/local/bin"):
        if p not in current and os.path.isdir(p):
            os.environ["PATH"] = p + ":" + os.environ.get("PATH", "")


def _is_stale(enqueued_at: float, now: float, limit: float = STALE_SECONDS) -> bool:
    return now - enqueued_at > limit


def _play(sound: str) -> None:
    subprocess.Popen(
        ["afplay", sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def _load_config() -> dict:
    try:
        config = json.loads(CONFIG_PATH.read_text())
        if not isinstance(config, dict):
            raise ValueError("config is not a dict")
        config.setdefault("cleanup", True)
        return config
    except Exception:
        return {"cleanup": True}


def _save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config))


def _acquire_single_instance_lock() -> bool:
    global _lock_handle
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _lock_handle = open(LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


class DictateApp(rumps.App):
    def __init__(self, missing_permissions: list[str] | None = None) -> None:
        super().__init__("Dictate", title=BUSY, quit_button="Quit")
        self.config = _load_config()
        self.status_item = rumps.MenuItem("Loading model…")
        self.cleanup_item = rumps.MenuItem("AI Cleanup", callback=self._toggle_cleanup)
        self.cleanup_item.state = bool(self.config.get("cleanup", True))
        self.cat_item = rumps.MenuItem("Show Cat", callback=self._toggle_cat)
        self.cat_item.state = bool(self.config.get("cat", True))
        self.tone_item = rumps.MenuItem("Match App Tone", callback=self._toggle_tone)
        self.tone_item.state = bool(self.config.get("tone", True))
        self.menu = [self.status_item, self.cleanup_item, self.tone_item, self.cat_item]

        # state for "scratch that" / "make it ..." voice commands
        self.last_text: str | None = None
        self.last_insert_at = 0.0
        self.last_bundle: str | None = None

        self.overlay = CatOverlay()
        self._anim_timer = rumps.Timer(self._on_anim_tick, 0.067)  # ~15 fps
        self._anim_timer.start()

        self.missing_permissions = missing_permissions or []
        if self.missing_permissions:
            self.title = FAILED
            self.status_item.title = (
                f"Grant {' and '.join(self.missing_permissions)} in System"
                " Settings → Privacy & Security, then relaunch"
            )

        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.cleaner = Cleaner()
        self.jobs: queue.Queue = queue.Queue()
        self.model_failed = False
        self.hotkey = HoldHotkey(self._on_hold_start, self._on_hold_finish)

        threading.Thread(target=self._worker, daemon=True).start()
        self.hotkey.start()

    # ---- UI helpers (menu bar must be touched from the main thread) ----

    def _set_status(self, title: str, menu_text: str | None = None) -> None:
        def apply() -> None:
            self.title = title
            if menu_text is not None:
                self.status_item.title = menu_text

        NSOperationQueue.mainQueue().addOperationWithBlock_(apply)

    def _toggle_cleanup(self, item: rumps.MenuItem) -> None:
        item.state = not item.state
        self.config["cleanup"] = bool(item.state)
        _save_config(self.config)
        if item.state and not self.cleaner.loaded:
            threading.Thread(target=self._load_cleaner, daemon=True).start()

    def _toggle_cat(self, item: rumps.MenuItem) -> None:
        item.state = not item.state
        self.config["cat"] = bool(item.state)
        _save_config(self.config)
        if not item.state:
            self.overlay.hide()

    def _toggle_tone(self, item: rumps.MenuItem) -> None:
        item.state = not item.state
        self.config["tone"] = bool(item.state)
        _save_config(self.config)

    def _on_anim_tick(self, _timer) -> None:
        if self.overlay.visible:
            self.overlay.tick(self.recorder.level)

    def _load_cleaner(self) -> None:
        try:
            self.cleaner.load()
            self.cleaner.clean("warm up")  # compile kernels off the hot path
        except Exception as exc:
            print(f"Cleanup model failed to load: {exc}")
            self._set_status(IDLE, f"Cleanup unavailable: {exc}")

    # ---- hotkey callbacks (pynput listener thread) ----
    # Never let an exception escape: it would kill the key listener silently.

    def _on_hold_start(self) -> None:
        try:
            if self.model_failed or self.missing_permissions:
                return
            if secure_input_active():
                self._set_status(IDLE, "🔒 Secure field focused — dictation blocked")
                return
            self._target_bundle = _frontmost_bundle_id()
            self.recorder.start()
            self._set_status(RECORDING)
            if self.cat_item.state:
                self.overlay.show_listening()
            _play(SOUND_START)
        except Exception as exc:
            self._set_status(IDLE, f"Mic error: {exc}")

    def _on_hold_finish(self, cancelled: bool) -> None:
        try:
            audio, truncated = self.recorder.stop()
            if cancelled or len(audio) < SAMPLE_RATE * 0.3:
                self._set_status(IDLE)
                self.overlay.hide()
                return
            _play(SOUND_STOP)
            self.overlay.show_thinking()
            notice = f"Recording capped at {MAX_SECONDS // 60} min" if truncated else None
            self._set_status(BUSY, notice)
            self.jobs.put((time.monotonic(), audio, getattr(self, "_target_bundle", None)))
        except Exception as exc:
            self._set_status(IDLE, f"Error: {exc}")
            self.overlay.hide()

    # ---- transcription worker ----

    def _worker(self) -> None:
        maybe_go_offline([transcriber_mod.MODEL_ID, cleaner_mod.MODEL_ID])
        try:
            self.transcriber.load()
            # warm up MLX kernels so the first real dictation is fast
            import numpy as np

            self.transcriber.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))
        except Exception as exc:
            self.model_failed = True
            self._set_status(FAILED, f"Model failed to load: {exc}")
            print(f"Model failed to load: {exc}")
            return
        if not self.missing_permissions:
            self._set_status(IDLE, "Hold Right ⌘ and speak")
        else:
            self._set_status(FAILED)
        if self.cleanup_item.state:
            self._load_cleaner()

        while True:
            enqueued_at, audio, bundle = self.jobs.get()
            try:
                if _is_stale(enqueued_at, time.monotonic()):
                    self._set_status(IDLE, "Skipped a stale dictation (queued >60 s)")
                    continue
                raw = self.transcriber.transcribe(audio)
                if not raw:
                    self._set_status(IDLE, "Heard nothing")
                    continue
                command = parse_command(raw)
                if command is not None:
                    print(f"[command] parsed: {command[0]}")
                    self._handle_command(*command)
                    continue
                self._insert_dictation(raw, bundle)
            except Exception as exc:
                self._set_status(IDLE, f"Error: {exc}")
                print(f"Transcription error: {exc}")
            finally:
                if self.jobs.empty():
                    self.overlay.hide()  # vanish into thin air

    def _insert_dictation(self, raw: str, bundle: str | None) -> None:
        text = raw
        dictionary = load_dictionary()
        list_body = extract_list_request(raw) if self.cleanup_item.state else None
        style_req = None
        if list_body is None and self.cleanup_item.state:
            style_req = extract_style_request(raw)
        if self.cleanup_item.state:
            tone = tone_for_bundle(bundle) if self.tone_item.state else "neutral"
            body = raw
            if list_body is not None:
                body = list_body
            elif style_req is not None:
                body = style_req[1]
            text = self.cleaner.clean(
                body,
                tone_instruction=TONE_INSTRUCTIONS[tone],
                dictionary=dictionary,
            )
            if list_body is not None:
                # second pass: the rewrite prompt is the one proven to split
                # items into bullets reliably
                bullets = self.cleaner.rewrite(text, REWRITE_STYLES["bullet points"])
                if bullets:
                    text = bullets
                print(f"[dictation] bullet list: {'ok' if bullets else 'fell back'}")
            elif style_req is not None:
                styled = self.cleaner.rewrite(text, style_req[0])
                if styled:
                    text = styled
                print(f"[dictation] inline style: {'ok' if styled else 'fell back'}")
        text = apply_dictionary_casing(text, dictionary)
        status = insert_text(text)
        print(f"[dictation] insert status: {status if status != 'ok' else 'ok'}")
        if status == "ok":
            self.last_text = text
            self.last_insert_at = time.monotonic()
            self.last_bundle = bundle
            self._set_status(IDLE, f"Last: {text[:60]}")
        else:
            self._set_status(IDLE, status)

    def _scratch_blocker(self) -> str | None:
        """Why scratch/rewrite can't run right now; None when it can."""
        if self.last_text is None:
            return "no recent dictation"
        if time.monotonic() - self.last_insert_at >= SCRATCH_WINDOW_SECONDS:
            return "last dictation is older than 2 min"
        if _frontmost_bundle_id() != self.last_bundle:
            return "you're in a different app now"
        return None

    def _command_failed(self, verb: str, reason: str) -> None:
        _play(SOUND_ERROR)
        self._set_status(IDLE, f"Can't {verb}: {reason}")
        print(f"[command] {verb} refused: {reason}")  # reasons only, never content

    def _handle_command(self, kind: str, arg: str) -> None:
        if kind == "scratch":
            blocker = self._scratch_blocker()
            if blocker:
                self._command_failed("scratch", blocker)
                return
            if undo_in_frontmost():
                self.last_text = None
                self._set_status(IDLE, "Scratched that")
            else:
                self._command_failed("scratch", "permissions")
        elif kind == "rewrite":
            blocker = self._scratch_blocker()
            if blocker:
                self._command_failed("rewrite", blocker)
                return
            new = self.cleaner.rewrite(self.last_text, arg)
            print(f"[command] rewrite generated: {'ok' if new else 'nothing'}")
            if new is None or new == self.last_text:
                self._command_failed("rewrite", "model produced nothing usable")
                return
            if not undo_in_frontmost():
                self._command_failed("rewrite", "permissions")
                return
            print("[command] rewrite: undo posted")
            time.sleep(0.15)  # let the target app process the undo first
            status = insert_text(new)
            print(f"[command] rewrite insert status: {status}")
            if status == "ok":
                self.last_text = new
                self.last_insert_at = time.monotonic()
                self._set_status(IDLE, f"Rewrote: {new[:55]}")
            else:
                self._set_status(IDLE, status)
        elif kind == "dict_add":
            add_to_dictionary(arg)
            self._set_status(IDLE, f"Added “{arg}” to dictionary")


def main() -> None:
    if not _acquire_single_instance_lock():
        print("Dictate is already running (menu bar 🎤). Not starting a second copy.")
        return
    _ensure_homebrew_path()
    print("Dictate — hold Right ⌘, speak, release.")
    missing = ensure_permissions()
    if missing:
        print(
            f"Missing permissions: {', '.join(missing)} — approve the system"
            " dialogs (or enable this app in System Settings → Privacy &"
            " Security), then restart Dictate."
        )
    DictateApp(missing_permissions=missing).run()


if __name__ == "__main__":
    main()
