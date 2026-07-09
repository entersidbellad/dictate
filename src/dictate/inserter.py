"""Insert text into the frontmost app: full-pasteboard swap + synthesized Cmd+V.

Safety properties:
- The entire pasteboard (all types: text, images, files) is snapshotted and
  restored, not just plain text.
- The transcript is written with the "concealed" marker so well-behaved
  clipboard managers don't record dictations.
- The snapshot is only restored if the pasteboard hasn't changed since we
  wrote the transcript — if the user copies something in the meantime, we
  never clobber it.
- If secure input is active (a password field is focused), insertion is
  refused entirely.
- The Cmd+V keystroke is posted via Quartz CGEvent, which needs only the
  Accessibility permission (no Apple Events / Automation grant, unlike
  osascript). If Accessibility is missing, the transcript is left on the
  clipboard and the failure is reported.
"""

import ctypes
import threading
import time

from AppKit import NSPasteboard, NSPasteboardItem, NSPasteboardTypeString
from Foundation import NSOperationQueue, NSThread
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

from .permissions import accessibility_granted

# clipboard managers skip items carrying this type (nspasteboard.org convention)
CONCEALED_TYPE = "org.nspasteboard.ConcealedType"

# ANSI keyboard keycodes (assumes ANSI/QWERTY layout)
_KEYCODE_V = 9
_KEYCODE_Z = 6

_carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")


def secure_input_active() -> bool:
    """True when macOS secure input is on (e.g. a password field has focus)."""
    return bool(_carbon.IsSecureEventInputEnabled())


def _on_main_sync(fn):
    """Run pasteboard work on the main thread (NSPasteboard promise
    fulfillment from background threads is unsafe). Direct call when already
    on the main thread — which is also what pytest exercises."""
    if NSThread.isMainThread():
        return fn()
    result = {}
    done = threading.Event()

    def block():
        try:
            result["value"] = fn()
        finally:
            done.set()

    NSOperationQueue.mainQueue().addOperationWithBlock_(block)
    if not done.wait(3.0):
        raise RuntimeError("main thread unavailable for pasteboard operation")
    return result["value"]


def _press_cmd_key(keycode: int) -> None:
    down = CGEventCreateKeyboardEvent(None, keycode, True)
    CGEventSetFlags(down, kCGEventFlagMaskCommand)
    up = CGEventCreateKeyboardEvent(None, keycode, False)
    CGEventSetFlags(up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, down)
    CGEventPost(kCGHIDEventTap, up)


def _press_cmd_v() -> None:
    _press_cmd_key(_KEYCODE_V)


def undo_in_frontmost() -> bool:
    """Post Cmd+Z to the frontmost app (for 'scratch that'). False if blocked."""
    if not accessibility_granted() or secure_input_active():
        return False
    _press_cmd_key(_KEYCODE_Z)
    return True


def _snapshot(pb) -> list[list[tuple[str, object]]]:
    items = []
    for item in pb.pasteboardItems() or []:
        entry = []
        for t in item.types():
            data = item.dataForType_(t)
            if data is not None:
                entry.append((t, data))
        if entry:
            items.append(entry)
    return items


def _restore(pb, items: list[list[tuple[str, object]]]) -> None:
    pb.clearContents()
    restored = []
    for entry in items:
        pi = NSPasteboardItem.alloc().init()
        for t, data in entry:
            pi.setData_forType_(data, t)
        restored.append(pi)
    if restored:
        pb.writeObjects_(restored)


def insert_text(text: str) -> str:
    """Paste `text` into the frontmost app. Returns "ok" or a status message."""
    if not text:
        return "Heard nothing"
    if secure_input_active():
        return "🔒 Secure field focused — insertion blocked"

    def stage():
        pb = NSPasteboard.generalPasteboard()
        saved = _snapshot(pb)
        item = NSPasteboardItem.alloc().init()
        item.setString_forType_(text, NSPasteboardTypeString)
        item.setString_forType_("", CONCEALED_TYPE)
        pb.clearContents()
        pb.writeObjects_([item])
        return saved, pb.changeCount()

    saved, our_change = _on_main_sync(stage)

    if not accessibility_granted():
        # leave the transcript on the clipboard as a fallback
        return "⚠️ Paste failed (grant Accessibility) — text is on clipboard, press ⌘V"

    time.sleep(0.05)  # let the pasteboard settle before pasting
    _press_cmd_v()

    # give the target app time to read the pasteboard before restoring it
    time.sleep(0.5)

    def restore_if_unchanged():
        pb = NSPasteboard.generalPasteboard()
        if pb.changeCount() == our_change:
            _restore(pb, saved)

    _on_main_sync(restore_if_unchanged)
    return "ok"
