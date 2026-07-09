"""Diagnose macOS permissions for Dictate.

Prints the live trust status the OS reports for this process (which is what
actually matters — not what the Settings list appears to show), and unless
CHECK_ONLY=1 is set, triggers the official system prompts so the right app
gets registered in the permission lists.
"""

import ctypes
import os
import sys

cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
ax = ctypes.CDLL(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")

check_only = os.environ.get("CHECK_ONLY") == "1"

print(f"python binary : {sys.executable}")

# ---- Accessibility ----
ax.AXIsProcessTrusted.restype = ctypes.c_bool
trusted = ax.AXIsProcessTrusted()
print(f"Accessibility : {'GRANTED' if trusted else 'NOT GRANTED'}")

if not trusted and not check_only:
    # AXIsProcessTrustedWithOptions with the prompt option: pops the system
    # dialog and adds the responsible app to the Accessibility list
    ax.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
    ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
    cf.CFDictionaryCreate.restype = ctypes.c_void_p
    cf.CFDictionaryCreate.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    prompt_key = ctypes.c_void_p.in_dll(ax, "kAXTrustedCheckOptionPrompt")
    true_val = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
    key_cb = (ctypes.c_char * 1).in_dll(cf, "kCFTypeDictionaryKeyCallBacks")
    val_cb = (ctypes.c_char * 1).in_dll(cf, "kCFTypeDictionaryValueCallBacks")
    keys = (ctypes.c_void_p * 1)(prompt_key)
    vals = (ctypes.c_void_p * 1)(true_val)
    opts = cf.CFDictionaryCreate(
        None, keys, vals, 1, ctypes.byref(key_cb), ctypes.byref(val_cb)
    )
    ax.AXIsProcessTrustedWithOptions(opts)
    print("  -> requested Accessibility (check for a system dialog)")

# ---- Input Monitoring ----
KIOHID_LISTEN_EVENT = 1
iokit.IOHIDCheckAccess.restype = ctypes.c_uint32
iokit.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
status = iokit.IOHIDCheckAccess(KIOHID_LISTEN_EVENT)
names = {0: "GRANTED", 1: "DENIED", 2: "NOT YET ASKED"}
print(f"InputMonitoring: {names.get(status, status)}")

if status != 0 and not check_only:
    iokit.IOHIDRequestAccess.restype = ctypes.c_bool
    iokit.IOHIDRequestAccess.argtypes = [ctypes.c_uint32]
    granted = iokit.IOHIDRequestAccess(KIOHID_LISTEN_EVENT)
    print(f"  -> requested Input Monitoring (check for a system dialog); granted={granted}")

if trusted and status == 0:
    print("\nAll good — dictate should work. Run: uv run dictate")
else:
    print(
        "\nAfter approving any dialogs / flipping toggles, fully quit Terminal"
        " (Cmd+Q), reopen, and run this script again."
    )
