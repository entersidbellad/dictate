"""Pasteboard snapshot/restore and insert flow. The user's real clipboard is
snapshotted before each test and restored after; no real keystrokes are ever
posted (CGEvent posting is monkeypatched out)."""

import pytest
from AppKit import NSPasteboard, NSPasteboardItem, NSPasteboardTypeString

from dictate import inserter as inserter_mod
from dictate.inserter import (
    CONCEALED_TYPE,
    _restore,
    _snapshot,
    insert_text,
    secure_input_active,
)

CUSTOM_TYPE = "com.sid.dictate.test-data"


@pytest.fixture(autouse=True)
def preserve_user_clipboard():
    pb = NSPasteboard.generalPasteboard()
    saved = _snapshot(pb)
    yield pb
    _restore(pb, saved)


@pytest.fixture(autouse=True)
def no_real_side_effects(monkeypatch):
    monkeypatch.setattr(inserter_mod, "_press_cmd_v", lambda: None)
    monkeypatch.setattr(inserter_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(inserter_mod, "accessibility_granted", lambda: True)
    monkeypatch.setattr(inserter_mod, "secure_input_active", lambda: False)


def write_multi_type_item(pb):
    item = NSPasteboardItem.alloc().init()
    item.setString_forType_("hello", NSPasteboardTypeString)
    item.setData_forType_(b"\x00\x01binary".decode("latin1").encode(), CUSTOM_TYPE)
    pb.clearContents()
    pb.writeObjects_([item])


def test_snapshot_restore_roundtrip_multi_type(preserve_user_clipboard):
    pb = preserve_user_clipboard
    write_multi_type_item(pb)
    snap = _snapshot(pb)

    pb.clearContents()
    other = NSPasteboardItem.alloc().init()
    other.setString_forType_("something else", NSPasteboardTypeString)
    pb.writeObjects_([other])

    _restore(pb, snap)
    assert pb.pasteboardItems()[0].stringForType_(NSPasteboardTypeString) == "hello"
    assert bytes(pb.pasteboardItems()[0].dataForType_(CUSTOM_TYPE)) == bytes(
        snap[0][dict((t, i) for i, (t, _) in enumerate(snap[0]))[CUSTOM_TYPE]][1]
    )


def test_insert_restores_original_clipboard(preserve_user_clipboard, monkeypatch):
    pb = preserve_user_clipboard
    write_multi_type_item(pb)
    assert insert_text("dictated words") == "ok"
    # original clipboard is back
    assert pb.pasteboardItems()[0].stringForType_(NSPasteboardTypeString) == "hello"


def test_transcript_is_concealed_while_staged(preserve_user_clipboard, monkeypatch):
    pb = preserve_user_clipboard
    seen = {}

    def spy_paste():
        item = pb.pasteboardItems()[0]
        seen["text"] = item.stringForType_(NSPasteboardTypeString)
        seen["concealed"] = item.stringForType_(CONCEALED_TYPE)

    monkeypatch.setattr(inserter_mod, "_press_cmd_v", spy_paste)
    insert_text("secret dictation")
    assert seen["text"] == "secret dictation"
    assert seen["concealed"] is not None  # marker present for clipboard managers


def test_user_copy_during_paste_is_not_clobbered(preserve_user_clipboard, monkeypatch):
    pb = preserve_user_clipboard
    write_multi_type_item(pb)

    def paste_then_user_copies():
        item = NSPasteboardItem.alloc().init()
        item.setString_forType_("user copied this mid-paste", NSPasteboardTypeString)
        pb.clearContents()
        pb.writeObjects_([item])

    monkeypatch.setattr(inserter_mod, "_press_cmd_v", paste_then_user_copies)
    insert_text("dictated")
    # the user's newer copy must survive; no restore over it
    assert (
        pb.pasteboardItems()[0].stringForType_(NSPasteboardTypeString)
        == "user copied this mid-paste"
    )


def test_secure_input_blocks_insertion(monkeypatch):
    monkeypatch.setattr(inserter_mod, "secure_input_active", lambda: True)
    assert "blocked" in insert_text("password123")


def test_missing_accessibility_leaves_text_on_clipboard(
    preserve_user_clipboard, monkeypatch
):
    pb = preserve_user_clipboard
    monkeypatch.setattr(inserter_mod, "accessibility_granted", lambda: False)
    status = insert_text("fallback text")
    assert "⌘V" in status
    assert pb.pasteboardItems()[0].stringForType_(NSPasteboardTypeString) == (
        "fallback text"
    )


def test_empty_text_is_noop():
    assert insert_text("") == "Heard nothing"


def test_secure_input_probe_returns_bool():
    assert isinstance(secure_input_active(), bool)
