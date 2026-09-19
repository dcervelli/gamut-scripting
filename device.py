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
                               which may be fractions of a logical pixel, and the window
                               told so
    device.py place X Y        the same; the name is for a script to say where the pixel
                               under the pointer is what matters
    device.py drag DX DY       the left button held while the pointer moves DX, DY
    device.py drag_to X Y [placed]
                               the left button held while the pointer glides to X, Y —
                               and is placed there, if asked, before it is let go
    device.py click            the left button pressed and released
    device.py key CHORD        a key by its position, with modifiers: 2, shift+2, ctrl+shift+c
    device.py rest S [T]       nothing, for S seconds, or for somewhere between S and T:
                               a hand that pauses between two things

Several of these, separated by `--`, are done in turn by the one device:
`device.py glide 400 300 -- click -- key down -- key down` is a hand that
goes somewhere, clicks and presses a key twice, and the compositor meets
the device once rather than four times. After each, where the pointer is
is printed, a line of two numbers: what a drag moved is the difference
between two of them.

Motion is sent in units, and the compositor is told to make each unit of
this device exactly a quarter of a logical pixel, at any pace: a flat
acceleration profile, for this device alone, so that the pointer's place
is arithmetic — where it started plus the units sent, over four. It is
asked of the compositor once when the device is made, and once more at
the end, to check the sum. The real mouse keeps its own acceleration.

/dev/uinput has to be writable by the user; Omarchy grants that through an
ACL, and `getfacl /dev/uinput` says whether it has.
"""

import fcntl
import math
import os
import random
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
SETTLE = 0.2

# Hyprland's rule for this device, by the name it lists it under: a flat
# profile, so that a unit of motion carries the same distance whatever the
# pace, and a sensitivity that makes the distance a quarter of a logical
# pixel — at 0 it is one whole pixel. Set through the Lua API before the
# device is made, and for this device alone.
PROFILE = 'hl.device({ name = "gamut-screenshots-1", accel_profile = "flat", sensitivity = -0.75 })'
UNIT = 0.25

# Logical pixels a step of a move, at a step a frame, taken over the
# move: a drag on screen that reads as a hand's, not so slow as to try
# the patience of a film. A hand sets off and stops gently, so the steps
# are not even: this much of the move follows an S-curve and the rest is
# spread evenly, which makes the first and last steps about a third of
# PACE and the middle ones a third more. At 0 every step would be PACE;
# at 1 the first and last would be nothing.
PACE = 16
EASE = 0.7

# The least a key press waits before the next, and the most: a hand does
# not press a key ten times at a metronome's beat.
KEY_GAP = (0.0, 0.02)

# The units of the step that ends a glide, two pixels: the window hears of
# the pointer only as it crosses from one whole pixel into the next, and
# then where that event landed, so a glide's last step goes far enough
# along its way to be sure of crossing an edge, and lands on the mark.
LAST = 8

# How long the window takes to have drawn a frame with the pointer where
# it is, two frames at the film's 60. A glide waits this long before
# anything is done where it ended, since a click on a handle is a click
# on whichever handle the window last drew the pointer over, and a drag's
# press is at wherever it last drew it; and the button is up this long
# before the pointer moves on, since a toolkit counts a click only if the
# pointer is still on the widget in the frame the button came up, and
# takes motion in the frame of a drag's release as part of the drag.
HEARD = 0.035

# How many steps of two units a drag creeps from its press before it sets
# off: half a pixel a step, seven and a half pixels an axis, past the six
# the toolkit takes for a click.
CREEP = 15

# Lua for Hyprland that raises the pointer's position as its error.
CURSOR_POSITION = 'local p = hl.get_cursor_pos(); error(string.format("%.4f %.4f", p.x, p.y))'


class Device:
    def __init__(self):
        subprocess.run(["hyprctl", "eval", PROFILE], capture_output=True, check=True)
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
        # Where the pointer is, asked once; every move from here is added
        # to it, since each unit is known to carry UNIT.
        self.at = list(self.resting())

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

    def move(self, ux, uy):
        # UX, UY units of motion, in steps, so that it is a drag rather than
        # a jump: a pointer that arrives in one event is one motion event,
        # and a drag threshold or an easing that watches the pointer's path
        # sees nothing of it. PACE pixels a step on average, about a step a
        # frame at the film's 60, eased in and out by EASE.
        if ux == 0 and uy == 0:
            return
        steps = max(1, int(max(abs(ux), abs(uy)) * UNIT / PACE))
        gone = [0, 0]
        for i in range(1, steps + 1):
            t = i / steps
            f = (1 - EASE) * t + EASE * t * t * (3 - 2 * t)
            to = [ux, uy] if i == steps else [round(ux * f), round(uy * f)]
            self.emit(EV_REL, REL_X, to[0] - gone[0])
            self.emit(EV_REL, REL_Y, to[1] - gone[1])
            self.sync()
            gone = to
            time.sleep(0.012)
        self.at[0] += ux * UNIT
        self.at[1] += uy * UNIT

    def units(self, x, y):
        # The units that take the pointer from where it is to X, Y: to the
        # nearest quarter of a pixel, an eighth off the mark at worst.
        return round((x - self.at[0]) / UNIT), round((y - self.at[1]) / UNIT)

    def glide(self, x, y):
        # To the mark at `move`'s pace, all but the last step, which is
        # LAST units along the way, sent as one event. The window hears of
        # the pointer only as it crosses from one whole pixel into the next,
        # and then where that event landed, so after a last move of less
        # than a pixel the window has the pointer up to a pixel from where
        # it is; the last step here is long enough to cross an edge on
        # whichever axis it mostly goes along, so the window hears it and
        # has the pointer where it stopped. A mark within the last step's
        # length is backed away from by the difference first, and a mark
        # under the pointer already is stepped away from and back.
        ux, uy = self.units(x, y)
        length = math.hypot(ux, uy)
        if length == 0:
            lx = ly = round(LAST / math.sqrt(2))
        else:
            lx, ly = round(ux * LAST / length), round(uy * LAST / length)
        self.move(ux - lx, uy - ly)
        self.emit(EV_REL, REL_X, lx)
        self.emit(EV_REL, REL_Y, ly)
        self.sync()
        self.at[0] += lx * UNIT
        self.at[1] += ly * UNIT
        time.sleep(HEARD)

    def place(self, x, y):
        # The same motion: the name is for the scripts, which say `place`
        # where the pixel under the pointer is what matters, as at the two
        # corners of `region`'s box.
        self.glide(x, y)

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
        if not down:
            time.sleep(HEARD)

    def drag(self, dx, dy):
        self.button(True)
        time.sleep(0.05)
        self.move(round(dx / UNIT), round(dy / UNIT))
        time.sleep(0.05)
        self.button(False)

    def drag_to(self, x, y, placed=False):
        # A glide with the button down, to a point in the layout rather
        # than by a distance. The glide ends with the frames the window
        # takes to draw the pointer at its mark, and the button comes up
        # after them: a toolkit takes the drag's end from the last frame it
        # was dragging on, and a motion that arrives in the same frame as
        # the release is not part of it. A drag that is to end on a given
        # pixel of the picture, which a pan could miss the last step of and
        # be none the worse, holds a while longer to be sure. The press is
        # a frame before the creep for the same reason, the other way about.
        self.button(True)
        time.sleep(0.02)
        self.creep(x, y)
        self.glide(x, y)
        if placed:
            time.sleep(0.1)
        self.button(False)

    def creep(self, x, y):
        # A toolkit takes a press for a click until the pointer has gone
        # some way from it — six logical pixels, for egui — and only then
        # for a drag, and the motion of the frame that decides it is not
        # part of the drag. A stroke that sets off at speed loses its first
        # eight pixels or so that way, and the picture ends up that much
        # short of where the pointer took it. So the first pixels are
        # covered two units at a time, half a pixel each, until the pointer
        # is well past the toolkit's distance, and what the deciding frame
        # loses is a fraction of a pixel. An axis with less than that to go
        # creeps only as far as its mark.
        ux, uy = self.units(x, y)
        sx = max(-2, min(2, ux))
        sy = max(-2, min(2, uy))
        for _ in range(CREEP):
            if sx == 0 and sy == 0:
                return
            self.emit(EV_REL, REL_X, sx)
            self.emit(EV_REL, REL_Y, sy)
            self.sync()
            self.at[0] += sx * UNIT
            self.at[1] += sy * UNIT
            ux -= sx
            uy -= sy
            sx = max(-2, min(2, ux))
            sy = max(-2, min(2, uy))
            time.sleep(0.008)

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
        time.sleep(random.uniform(*KEY_GAP))


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    actions = [[]]
    for word in argv[1:]:
        if word == "--":
            actions.append([])
        else:
            actions[-1].append(word)
    device = Device()
    try:
        for action in actions:
            match action:
                case ["wheel", notches]:
                    device.wheel(int(notches))
                case ["wheel", notches, seconds]:
                    device.wheel(int(notches), float(seconds))
                case ["glide", x, y]:
                    device.glide(float(x), float(y))
                case ["place", x, y]:
                    device.place(float(x), float(y))
                case ["drag", dx, dy]:
                    device.drag(int(dx), int(dy))
                case ["drag_to", x, y]:
                    device.drag_to(float(x), float(y))
                case ["drag_to", x, y, "placed"]:
                    device.drag_to(float(x), float(y), placed=True)
                case ["click"]:
                    device.click()
                case ["key", chord]:
                    device.key(chord)
                case ["rest", seconds]:
                    time.sleep(float(seconds))
                case ["rest", least, most]:
                    time.sleep(random.uniform(float(least), float(most)))
                case _:
                    sys.exit(__doc__)
            print("%.2f %.2f" % tuple(device.at))
        # Where the compositor says the pointer is, which the sum should
        # agree with; a difference means the profile was not applied, or
        # the pointer met the edge of a screen. Asked once at the end:
        # asked after each action it would be a pause between them.
        at = device.resting()
        if abs(at[0] - device.at[0]) > 0.05 or abs(at[1] - device.at[1]) > 0.05:
            print("the pointer is at %.2f %.2f, not %.2f %.2f as the units sent add up to"
                  % (*at, *device.at), file=sys.stderr)
    finally:
        device.close()


if __name__ == "__main__":
    main(sys.argv)
