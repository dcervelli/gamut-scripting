#!/usr/bin/env python3
"""A mouse and a keyboard that are not there, through /dev/uinput.

wtype has keys but no pointer, and Hyprland can warp the pointer but not press
its buttons or turn its wheel, so what the wheel and a drag do — zooming about
the pointer, panning by hand — cannot be recorded without a device of our
own. This registers one with the kernel for as long as the command runs,
sends the events, and takes it away again. Nothing but the standard library:
the ioctls and the event record are spelled out here from linux/uinput.h and
linux/input.h.

It has keys as well, for the bindings wtype cannot reach. wtype types a
keysym under a keymap of its own, at whatever keycode it chose for it, and
a binding on a key's position — Shift+2 for 50%, matched by the key being
the second digit and not by what it says — never sees the key it wants.
A key from here is the real keycode, read under the real keymap.

    device.py wheel N [S]      N notches: positive is away from the hand, which zooms in;
                               spread evenly over S seconds rather than sent at once
    device.py glide X Y        the pointer moved, with no button held, until it is at X, Y,
                               which may be fractions of a logical pixel
    device.py place X Y        the pointer put at X, Y to the hundredth of a pixel, and the
                               window told so
    device.py drag DX DY       the left button held while the pointer moves DX, DY
    device.py drag_to X Y [placed]
                               the left button held while the pointer glides to X, Y —
                               and is placed there, if asked, before it is let go
    device.py click            the left button pressed and released
    device.py key CHORD        a key by its position, with modifiers: 2, shift+2, ctrl+shift+c

/dev/uinput has to be writable by the user; Omarchy grants that through an
ACL, and `getfacl /dev/uinput` says whether it has.
"""

import fcntl
import os
import struct
import subprocess
import sys
import time

# linux/input-event-codes.h
EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
SYN_REPORT = 0
REL_X, REL_Y, REL_WHEEL, REL_WHEEL_HI_RES = 0x00, 0x01, 0x08, 0x0B
BTN_LEFT = 0x110

# The keys a chord can name, by their evdev codes.
KEYS = {
    "esc": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9,
    "9": 10, "0": 11, "minus": 12, "equal": 13, "backspace": 14, "tab": 15,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23,
    "o": 24, "p": 25, "leftbrace": 26, "rightbrace": 27, "enter": 28,
    "leftctrl": 29, "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35,
    "j": 36, "k": 37, "l": 38, "semicolon": 39, "apostrophe": 40, "grave": 41,
    "leftshift": 42, "backslash": 43, "z": 44, "x": 45, "c": 46, "v": 47,
    "b": 48, "n": 49, "m": 50, "comma": 51, "dot": 52, "slash": 53,
    "rightshift": 54, "leftalt": 56, "space": 57, "up": 103, "pageup": 104,
    "left": 105, "right": 106, "end": 107, "down": 108, "pagedown": 109,
}
MODIFIERS = {"shift": "leftshift", "ctrl": "leftctrl", "alt": "leftalt"}

# linux/uinput.h, with the _IO macros already applied: 'U' is 0x55, and
# uinput_setup is an input_id (four u16), an 80-byte name and a u32.
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405C5503
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_RELBIT = 0x40045566

# libinput's notion of a notch, for REL_WHEEL_HI_RES.
NOTCH = 120

# How long the compositor takes to notice a device that has just appeared,
# and to drain what it sent before it goes.
SETTLE = 0.25

# How near its mark a glide leaves the pointer, in logical pixels.
TOLERANCE = 0.2

# What the compositor's acceleration makes of a move at `move`'s pace: a
# move of the whole distance lands this much past its mark, so a glide
# asks for this fraction of what is left and lands short instead. Short is
# the safe side: a pointer that overshoots the window during a drag is a
# pointer the window sees leave, and a drag it sees end.
ACCELERATION = 1.24

# How near its mark `place` has to get the pointer, and the units of motion
# it sends for the last step, with how far they carry: three units after a
# rest go one pixel and a little, so the step always crosses into a new
# pixel, which is what makes the window hear of it. Measured on the way,
# since the compositor's acceleration decides it; this is the first guess.
PLACED = 0.03
STEP = 3
STEP_CARRIES = 1.006

# Lua for Hyprland that raises the pointer's position as its error.
CURSOR_POSITION = 'local p = hl.get_cursor_pos(); error(string.format("%.4f %.4f", p.x, p.y))'


class Device:
    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(self.fd, UI_SET_KEYBIT, BTN_LEFT)
        for code in KEYS.values():
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_REL)
        for code in (REL_X, REL_Y, REL_WHEEL, REL_WHEEL_HI_RES):
            fcntl.ioctl(self.fd, UI_SET_RELBIT, code)
        setup = struct.pack("HHHH80sI", 0x03, 0x1234, 0x5678, 1, b"gamut screenshots", 0)
        fcntl.ioctl(self.fd, UI_DEV_SETUP, setup)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        time.sleep(SETTLE)

    def close(self):
        time.sleep(SETTLE)
        fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        os.close(self.fd)

    def emit(self, kind, code, value):
        # struct input_event: a timeval the kernel fills in, then type, code, value.
        os.write(self.fd, struct.pack("llHHi", 0, 0, kind, code, value))

    def sync(self):
        self.emit(EV_SYN, SYN_REPORT, 0)

    def wheel(self, notches, seconds=None):
        # As fast as a flick unless told how long to take: a slow turn, for
        # a scroll that is meant to be read on the way down, is the same
        # notches with the whole time parted out between them.
        step = 1 if notches > 0 else -1
        pause = 0.05 if seconds is None else seconds / max(1, abs(notches))
        for _ in range(abs(notches)):
            self.emit(EV_REL, REL_WHEEL, step)
            self.emit(EV_REL, REL_WHEEL_HI_RES, step * NOTCH)
            self.sync()
            time.sleep(pause)

    def move(self, dx, dy):
        # In steps, so that it is a drag rather than a jump: a pointer that
        # arrives in one event is one motion event, and a drag threshold
        # or an easing that watches the pointer's path sees nothing of it.
        steps = max(1, int(max(abs(dx), abs(dy)) / 8))
        gone = [0, 0]
        for i in range(1, steps + 1):
            to = [dx * i // steps, dy * i // steps]
            self.emit(EV_REL, REL_X, to[0] - gone[0])
            self.emit(EV_REL, REL_Y, to[1] - gone[1])
            self.sync()
            gone = to
            time.sleep(0.008)

    def glide(self, x, y):
        # Motion from a mouse is accelerated by the compositor, so a move of
        # the whole distance lands past its mark; move for the acceleration,
        # ask where the pointer got to and move what is left, which is a
        # smaller and so a slower move, until it is there. The only thing here that knows the pointer's
        # place is Hyprland, and it is asked again until it gives the same
        # answer twice, since a move is not over when its last event has
        # been written.
        #
        # The pointer's place is a fraction, and so may the mark be: at a
        # zoom where an image pixel is half a logical one, only a pointer
        # within a quarter of a pixel of its mark is over the pixel meant.
        # So once the whole pixels are covered, single units of motion —
        # each a third of a pixel or so, slow motion being slowed further —
        # take it the rest of the way, to within TOLERANCE.
        for _ in range(12):
            at = self.resting()
            dx, dy = x - at[0], y - at[1]
            if abs(dx) < 1 and abs(dy) < 1:
                break
            self.move(round(dx / ACCELERATION), round(dy / ACCELERATION))
            time.sleep(0.05)
        for _ in range(40):
            at = self.resting()
            dx, dy = x - at[0], y - at[1]
            if abs(dx) <= TOLERANCE and abs(dy) <= TOLERANCE:
                return
            step = lambda d: 0 if abs(d) <= TOLERANCE else (1 if d > 0 else -1)
            self.emit(EV_REL, REL_X, step(dx))
            self.emit(EV_REL, REL_Y, step(dy))
            self.sync()
            time.sleep(0.1)

    def place(self, x, y):
        # The window is told where the pointer is only when the whole pixel
        # it is in changes, and then it is told the exact place of the event
        # that changed it: the pointer may then creep a third of a pixel at
        # a time to anywhere within the pixel, and the window still has it
        # where it crossed in. So the mark is reached by crossing into it
        # with the last event: the pointer is warped — which sets its place
        # exactly, and which the window is not told of — to just under a
        # pixel short of the mark, rested until the acceleration has
        # forgotten it moved, and sent STEP units, which carry it a whole
        # pixel and a little, over the pixel's edge and onto the mark. How
        # far the units carry is measured from the first try, and a second
        # try uses the measure.
        carries = [STEP_CARRIES, STEP_CARRIES]
        for _ in range(4):
            start = (x - carries[0], y - carries[1])
            self.warp(*start)
            time.sleep(0.5)
            self.emit(EV_REL, REL_X, STEP)
            self.emit(EV_REL, REL_Y, STEP)
            self.sync()
            time.sleep(0.2)
            at = self.position()
            if abs(at[0] - x) <= PLACED and abs(at[1] - y) <= PLACED:
                return
            carries = [at[0] - start[0], at[1] - start[1]]
        sys.exit(f"the pointer could not be placed at {x}, {y}: it is at {at}")

    def warp(self, x, y):
        subprocess.run(
            ["hyprctl", "eval", f"hl.dispatch(hl.dsp.cursor.move({{ x = {x}, y = {y} }}))"],
            capture_output=True,
            check=True,
        )

    def resting(self):
        last = None
        while True:
            at = self.position()
            if at == last:
                return at
            last = at
            time.sleep(0.03)

    def position(self):
        # `hyprctl cursorpos` cuts the fraction off. The Lua API has it
        # whole, but `hyprctl eval` prints nothing a script returns — only
        # what it raises, so the position is raised.
        said = subprocess.run(
            ["hyprctl", "eval", CURSOR_POSITION], capture_output=True, text=True
        ).stdout
        x, y = said.split()[-2:]
        return float(x), float(y)

    def button(self, down):
        self.emit(EV_KEY, BTN_LEFT, 1 if down else 0)
        self.sync()

    def drag(self, dx, dy):
        self.button(True)
        time.sleep(0.05)
        self.move(dx, dy)
        time.sleep(0.05)
        self.button(False)

    def drag_to(self, x, y, placed=False):
        # A drag as long as a region's diagonal is accelerated like any
        # other motion and would end well past its mark; this one is a
        # glide with the button down, so it ends where it was told to —
        # and, for a drag that is to end on a given pixel of the picture,
        # `place` then puts it on the mark to the hundredth. The button
        # stays down a while after that, so that the window has drawn a
        # frame with the pointer at its mark before the frame that ends the
        # drag: a toolkit takes the drag's end from the last frame it was
        # dragging on, and a motion that arrives in the same frame as the
        # release is not part of it.
        self.button(True)
        time.sleep(0.05)
        self.glide(x, y)
        if placed:
            self.place(x, y)
        time.sleep(0.3)
        self.button(False)

    def click(self):
        self.button(True)
        time.sleep(0.05)
        self.button(False)

    def key(self, chord):
        *modifiers, key = chord.lower().split("+")
        codes = [KEYS[MODIFIERS[m]] for m in modifiers] + [KEYS[key]]
        for code in codes:
            self.emit(EV_KEY, code, 1)
            self.sync()
            time.sleep(0.02)
        for code in reversed(codes):
            self.emit(EV_KEY, code, 0)
            self.sync()
            time.sleep(0.02)


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    device = Device()
    try:
        match argv[1:]:
            case ["wheel", notches]:
                device.wheel(int(notches))
            case ["wheel", notches, seconds]:
                device.wheel(int(notches), float(seconds))
            case ["glide", x, y]:
                device.glide(float(x), float(y))
            case ["drag", dx, dy]:
                device.drag(int(dx), int(dy))
            case ["place", x, y]:
                device.place(float(x), float(y))
            case ["drag_to", x, y]:
                device.drag_to(float(x), float(y))
            case ["drag_to", x, y, "placed"]:
                device.drag_to(float(x), float(y), placed=True)
            case ["click"]:
                device.click()
            case ["key", chord]:
                device.key(chord)
            case _:
                sys.exit(__doc__)
    finally:
        device.close()


if __name__ == "__main__":
    main(sys.argv)
