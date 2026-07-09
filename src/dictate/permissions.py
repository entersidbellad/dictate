"""Programmatic macOS permission checks/requests via TCC's own APIs.

Requesting through the official APIs makes macOS register the correct
responsible app (Terminal, Dictate.app, ...) in the permission lists itself —
no manual '+' button hunting.
"""

import ctypes

_cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_ax = ctypes.CDLL(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")

_KIOHID_LISTEN_EVENT = 1

_ax.AXIsProcessTrusted.restype = ctypes.c_bool
_iokit.IOHIDCheckAccess.restype = ctypes.c_uint32
_iokit.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
_iokit.IOHIDRequestAccess.restype = ctypes.c_bool
_iokit.IOHIDRequestAccess.argtypes = [ctypes.c_uint32]


def accessibility_granted() -> bool:
    return bool(_ax.AXIsProcessTrusted())


def input_monitoring_granted() -> bool:
    return _iokit.IOHIDCheckAccess(_KIOHID_LISTEN_EVENT) == 0


def request_accessibility() -> None:
    """Pop the system Accessibility dialog (registers this app in the list)."""
    _ax.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
    _ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
    _cf.CFDictionaryCreate.restype = ctypes.c_void_p
    _cf.CFDictionaryCreate.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    prompt_key = ctypes.c_void_p.in_dll(_ax, "kAXTrustedCheckOptionPrompt")
    true_val = ctypes.c_void_p.in_dll(_cf, "kCFBooleanTrue")
    key_cb = (ctypes.c_char * 1).in_dll(_cf, "kCFTypeDictionaryKeyCallBacks")
    val_cb = (ctypes.c_char * 1).in_dll(_cf, "kCFTypeDictionaryValueCallBacks")
    keys = (ctypes.c_void_p * 1)(prompt_key)
    vals = (ctypes.c_void_p * 1)(true_val)
    opts = _cf.CFDictionaryCreate(
        None, keys, vals, 1, ctypes.byref(key_cb), ctypes.byref(val_cb)
    )
    _ax.AXIsProcessTrustedWithOptions(opts)


def request_input_monitoring() -> None:
    _iokit.IOHIDRequestAccess(_KIOHID_LISTEN_EVENT)


def ensure_permissions() -> list[str]:
    """Request whatever is missing; return the list of missing permission names."""
    missing = []
    if not accessibility_granted():
        missing.append("Accessibility")
        request_accessibility()
    if not input_monitoring_granted():
        missing.append("Input Monitoring")
        request_input_monitoring()
    return missing
