"""Visual demo of the cat overlay: listening (fake voice), thinking, vanish."""

import math
import time

from AppKit import NSApplication  # noqa: F401  (initializes the app context)
from Foundation import NSTimer
from PyObjCTools import AppHelper

from dictate.overlay import CatOverlay

overlay = CatOverlay()
overlay.show_listening()
t0 = time.time()
switched = False


def tick(_timer):
    global switched
    elapsed = time.time() - t0
    if elapsed < 3.5:
        # synthetic speech envelope
        level = abs(math.sin(elapsed * 5.0)) * 0.07 * (0.4 + abs(math.sin(elapsed * 1.3)))
        overlay.tick(level)
    elif elapsed < 6.5:
        if not switched:
            overlay.show_thinking()
            switched = True
        overlay.tick(0.0)
    elif elapsed < 7.5:
        overlay.hide()
        overlay.tick(0.0)
    else:
        AppHelper.stopEventLoop()


NSApplication.sharedApplication()
NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.067, True, tick)
print("Showing cat demo for ~8 seconds (bottom-right corner of screen)…")
AppHelper.runConsoleEventLoop(installInterrupt=True)
print("Demo done.")
