"""Animated cat overlay: lip-syncs to mic level while recording, thinks while
transcribing, then fades away.

Rendering has two modes:
- Sprite mode: if `assets/cat_idle.png`, `cat_talk.png`, and `cat_think.png`
  exist (transparent PNGs), they are drawn with frame-swapped lip-sync and
  squash-and-stretch. Drop in any art style you like.
- Vector mode (built-in fallback): a drawn ginger tabby kitten with green
  eyes and pink paws. Used whenever sprites are missing or unreadable.

All AppKit work is dispatched to the main thread internally, so every public
method is safe to call from any thread. The window is borderless, transparent,
click-through, and floats above everything on all Spaces.
"""

import math
from pathlib import Path

import objc
from AppKit import (
    NSAnimationContext,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSCompositingOperationSourceOver,
    NSImage,
    NSScreen,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowStyleMaskBorderless,
)
from Foundation import NSMakeRect, NSOperationQueue, NSZeroRect

SIZE = 230
STATUS_WINDOW_LEVEL = 25  # NSStatusWindowLevel

ASSETS_DIR = Path(__file__).parent / "assets"
FRAME_NAMES = ("idle", "talk", "think")
# mic RMS above this reads as "speaking" → open-mouth frame
TALK_THRESHOLD = 0.012


def select_frame(mode: str, level: float) -> str:
    """Pure frame-selection logic (unit-tested)."""
    if mode == "thinking":
        return "think"
    return "talk" if level > TALK_THRESHOLD else "idle"


def load_frames() -> dict | None:
    """Load sprite frames; None if any is missing/unreadable (→ vector cat)."""
    frames = {}
    for name in FRAME_NAMES:
        path = ASSETS_DIR / f"cat_{name}.png"
        if not path.is_file():
            return None
        img = NSImage.alloc().initWithContentsOfFile_(str(path))
        if img is None:
            return None
        frames[name] = img
    return frames


def _on_main(fn) -> None:
    NSOperationQueue.mainQueue().addOperationWithBlock_(fn)


class CatView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(CatView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.mode = "listening"  # or "thinking"
        self.level = 0.0
        self.phase = 0.0
        self.frames = load_frames()
        return self

    # ---- drawing helpers ----

    @staticmethod
    def _fill_oval(x, y, w, h, color):
        color.setFill()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x, y, w, h)).fill()

    @staticmethod
    def _fill_triangle(p1, p2, p3, color):
        color.setFill()
        path = NSBezierPath.bezierPath()
        path.moveToPoint_(p1)
        path.lineToPoint_(p2)
        path.lineToPoint_(p3)
        path.closePath()
        path.fill()

    def _draw_thought_bubbles(self, cx, cy):
        white = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.98, 0.98, 0.98, 0.95)
        visible = 1 + int(self.phase * 2.0) % 3
        bubbles = [(cx + 58, cy + 68, 5.0), (cx + 74, cy + 88, 7.0), (cx + 92, cy + 110, 10.0)]
        for i in range(visible):
            bx, by, r = bubbles[i]
            self._fill_oval(bx - r, by - r, 2 * r, 2 * r, white)

    def drawRect_(self, rect):
        if self.frames is not None:
            self._draw_sprite_cat()
        else:
            self._draw_vector_cat()

    # ---- sprite mode ----

    def _draw_sprite_cat(self):
        thinking = self.mode == "thinking"
        bob = math.sin(self.phase * (1.5 if thinking else 3.0)) * 3.0
        frame = self.frames[select_frame(self.mode, self.level)]

        # squash & stretch with voice: taller + slightly narrower when loud
        stretch = 0.0 if thinking else min(self.level * 1.2, 0.07)
        w = SIZE * 0.88 * (1.0 - stretch * 0.5)
        h = SIZE * 0.88 * (1.0 + stretch)
        dest = NSMakeRect((SIZE - w) / 2.0, 6.0 + bob, w, h)
        frame.drawInRect_fromRect_operation_fraction_(
            dest, NSZeroRect, NSCompositingOperationSourceOver, 1.0
        )
        if thinking:
            self._draw_thought_bubbles(SIZE / 2.0 - 20, SIZE / 2.0 - 20 + bob)

    # ---- vector mode (ginger tabby fallback, styled after the reference) ----

    def _draw_vector_cat(self):
        ginger = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.93, 0.55, 0.22, 1)
        stripe = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.82, 0.42, 0.13, 1)
        cream = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.99, 0.93, 0.82, 1)
        pink = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.62, 0.68, 1)
        green = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.22, 0.72, 0.35, 1)
        dark = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.12, 0.12, 0.14, 1)
        white = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.97, 0.97, 0.97, 1)
        mouth_red = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.62, 0.2, 0.22, 1)
        whisker = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 1.0, 1.0, 0.9)

        thinking = self.mode == "thinking"
        bob = math.sin(self.phase * (1.5 if thinking else 3.0)) * 2.5
        cx, cy = SIZE / 2.0, 100.0 + bob

        # front paws (pink toes like the reference)
        self._fill_oval(cx - 44, cy - 92, 34, 22, ginger)
        self._fill_oval(cx + 10, cy - 92, 34, 22, ginger)
        for px in (cx - 40, cx - 27, cx + 14, cx + 27):
            self._fill_oval(px, cy - 92, 11, 10, pink)

        # ears (outer + inner)
        self._fill_triangle((cx - 52, cy + 26), (cx - 44, cy + 82), (cx - 8, cy + 48), ginger)
        self._fill_triangle((cx + 52, cy + 26), (cx + 44, cy + 82), (cx + 8, cy + 48), ginger)
        self._fill_triangle((cx - 44, cy + 36), (cx - 38, cy + 68), (cx - 16, cy + 46), pink)
        self._fill_triangle((cx + 44, cy + 36), (cx + 38, cy + 68), (cx + 16, cy + 46), pink)

        # head with cream muzzle patch and tabby stripes
        self._fill_oval(cx - 60, cy - 52, 120, 108, ginger)
        self._fill_oval(cx - 34, cy - 52, 68, 52, cream)
        stripe.setStroke()
        for i, (sx, sw) in enumerate(((-26, 14), (-7, 14), (12, 14))):
            p = NSBezierPath.bezierPath()
            p.setLineWidth_(5.0)
            p.moveToPoint_((cx + sx, cy + 54 - abs(i - 1) * 4))
            p.lineToPoint_((cx + sx + sw / 2, cy + 38))
            p.stroke()

        # big green eyes, blink every ~4s
        blinking = (self.phase % 4.0) < 0.18
        for ex in (cx - 27, cx + 27):
            if blinking:
                dark.setStroke()
                p = NSBezierPath.bezierPath()
                p.setLineWidth_(2.5)
                p.moveToPoint_((ex - 10, cy + 12))
                p.lineToPoint_((ex + 10, cy + 12))
                p.stroke()
            else:
                self._fill_oval(ex - 13, cy - 1, 26, 30, white)
                self._fill_oval(ex - 10, cy + 1, 20, 24, green)
                pupil_dy = 9 if thinking else 4  # look up while thinking
                self._fill_oval(ex - 4, cy + 4 + pupil_dy, 9, 12, dark)
                self._fill_oval(ex - 1, cy + 12 + pupil_dy, 4, 4, white)  # sparkle

        # nose
        self._fill_triangle((cx - 6, cy - 6), (cx + 6, cy - 6), (cx, cy - 14), pink)

        # whiskers
        whisker.setStroke()
        for side in (-1, 1):
            for i, dy in enumerate((-2, -9, -16)):
                p = NSBezierPath.bezierPath()
                p.setLineWidth_(1.5)
                p.moveToPoint_((cx + side * 24, cy + dy - 4))
                p.lineToPoint_((cx + side * 66, cy + dy + (4 - 4 * i)))
                p.stroke()

        # mouth
        if thinking:
            dark.setStroke()
            p = NSBezierPath.bezierPath()
            p.setLineWidth_(2.5)
            p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
                (cx, cy - 16), 8.0, 200.0, 340.0
            )
            p.stroke()
            self._draw_thought_bubbles(cx, cy)
        else:
            # lip-sync: mouth opens with voice level
            opening = 3.0 + min(self.level * 260.0, 32.0)
            self._fill_oval(cx - 14, cy - 30 - opening / 2, 28, opening, mouth_red)


class CatOverlay:
    """Thread-safe facade; lazily builds the window on the main thread."""

    def __init__(self) -> None:
        self._window = None
        self._view = None
        self.visible = False

    def _ensure_built(self) -> None:
        if self._window is not None:
            return
        screen = NSScreen.mainScreen().frame()
        rect = NSMakeRect(screen.size.width / 2 - SIZE / 2, 70, SIZE, SIZE)
        w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
        )
        w.setOpaque_(False)
        w.setBackgroundColor_(NSColor.clearColor())
        w.setLevel_(STATUS_WINDOW_LEVEL)
        w.setIgnoresMouseEvents_(True)
        w.setHasShadow_(False)
        w.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        v = CatView.alloc().initWithFrame_(NSMakeRect(0, 0, SIZE, SIZE))
        w.setContentView_(v)
        w.setAlphaValue_(0.0)
        self._window, self._view = w, v

    # ---- public API (any thread) ----

    def show_listening(self) -> None:
        def run():
            self._ensure_built()
            self._view.mode = "listening"
            self._view.level = 0.0
            self._view.phase = 0.5  # start past the blink window
            self._window.orderFrontRegardless()
            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(0.15)
            self._window.animator().setAlphaValue_(1.0)
            NSAnimationContext.endGrouping()

        self.visible = True
        _on_main(run)

    def show_thinking(self) -> None:
        def run():
            if self._view is not None:
                self._view.mode = "thinking"
                self._view.setNeedsDisplay_(True)

        _on_main(run)

    def hide(self) -> None:
        self.visible = False

        def run():
            if self._window is None:
                return
            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(0.4)
            self._window.animator().setAlphaValue_(0.0)
            NSAnimationContext.endGrouping()

        _on_main(run)

    def tick(self, level: float) -> None:
        """Advance the animation one frame (~15 fps); call from any thread."""
        if not self.visible:
            return

        def run():
            if self._view is None:
                return
            self._view.phase += 0.067
            # fast attack, slow decay, so the mouth snaps open and eases shut
            self._view.level = max(level, self._view.level * 0.72)
            self._view.setNeedsDisplay_(True)

        _on_main(run)
