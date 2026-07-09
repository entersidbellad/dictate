"""Hold-Right-Cmd state machine, driven directly (no real listener)."""

from pynput import keyboard

from dictate import hotkey as hotkey_mod
from dictate.hotkey import HoldHotkey

A_KEY = keyboard.KeyCode.from_char("a")


class Spy:
    def __init__(self) -> None:
        self.starts = 0
        self.finishes: list[bool] = []

    def on_start(self) -> None:
        self.starts += 1

    def on_finish(self, cancelled: bool) -> None:
        self.finishes.append(cancelled)


def make(monkeypatch, times: list[float]):
    it = iter(times)
    monkeypatch.setattr(hotkey_mod.time, "monotonic", lambda: next(it))
    spy = Spy()
    hk = HoldHotkey(spy.on_start, spy.on_finish)
    return hk, spy


def test_quick_tap_is_cancelled(monkeypatch):
    hk, spy = make(monkeypatch, [0.0, 0.1])
    hk._on_press(keyboard.Key.cmd_r)
    hk._on_release(keyboard.Key.cmd_r)
    assert spy.starts == 1
    assert spy.finishes == [True]


def test_long_hold_is_accepted(monkeypatch):
    hk, spy = make(monkeypatch, [0.0, 1.0])
    hk._on_press(keyboard.Key.cmd_r)
    hk._on_release(keyboard.Key.cmd_r)
    assert spy.starts == 1
    assert spy.finishes == [False]


def test_combo_with_other_key_is_cancelled(monkeypatch):
    hk, spy = make(monkeypatch, [0.0, 2.0])
    hk._on_press(keyboard.Key.cmd_r)
    hk._on_press(A_KEY)  # user was doing Cmd+A
    hk._on_release(keyboard.Key.cmd_r)
    assert spy.finishes == [True]


def test_release_without_press_is_ignored(monkeypatch):
    hk, spy = make(monkeypatch, [])
    hk._on_release(keyboard.Key.cmd_r)
    hk._on_release(A_KEY)
    assert spy.starts == 0
    assert spy.finishes == []


def test_repeated_press_events_start_once(monkeypatch):
    hk, spy = make(monkeypatch, [0.0, 1.0])
    hk._on_press(keyboard.Key.cmd_r)
    hk._on_press(keyboard.Key.cmd_r)
    hk._on_release(keyboard.Key.cmd_r)
    assert spy.starts == 1
    assert spy.finishes == [False]


def test_other_keys_alone_do_nothing(monkeypatch):
    hk, spy = make(monkeypatch, [])
    hk._on_press(A_KEY)
    hk._on_release(A_KEY)
    assert spy.starts == 0
    assert spy.finishes == []
