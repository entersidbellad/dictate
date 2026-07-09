"""Hold-Right-Cmd detection.

Recording starts on key-down so no speech is missed. On key-up the hold is
either accepted or cancelled: taps shorter than MIN_HOLD_SECONDS and holds
where another key was pressed (the user was doing a Cmd+... shortcut) are
cancelled.
"""

import time
from collections.abc import Callable

from pynput import keyboard

MIN_HOLD_SECONDS = 0.3


class HoldHotkey:
    def __init__(
        self,
        on_start: Callable[[], None],
        on_finish: Callable[[bool], None],
    ) -> None:
        """on_finish receives cancelled=True when the hold should be discarded."""
        self._on_start = on_start
        self._on_finish = on_finish
        self._held_since: float | None = None
        self._cancelled = False
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()

    def _on_press(self, key) -> None:
        if key == keyboard.Key.cmd_r:
            if self._held_since is None:
                self._held_since = time.monotonic()
                self._cancelled = False
                self._on_start()
        elif self._held_since is not None:
            # another key while Right Cmd is down: it's a shortcut, not dictation
            self._cancelled = True

    def _on_release(self, key) -> None:
        if key != keyboard.Key.cmd_r or self._held_since is None:
            return
        held = time.monotonic() - self._held_since
        self._held_since = None
        cancelled = self._cancelled or held < MIN_HOLD_SECONDS
        self._on_finish(cancelled)
