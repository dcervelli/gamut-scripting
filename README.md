# gamut-scripting

The scripts that take [gamut](https://github.com/dcervelli/gamut)'s
pictures: one script per picture in its `user-docs/screenshots/`, so that a
picture can be taken again after the interface changes and come out the
same size, in the same place, showing the same thing. What each one shows
is the script.

| script | picture |
| --- | --- |
| `main_screenshot` | a photograph zoomed in three steps and panned to the summit, with the minimap |
| `animated` | a GIF opened paused, then played through once with the transport bar |
| `pixel_grid` | the grid on, the wheel rolled over the stag until the grid is at single pixels, then Space |
| `info` | an elevation model in turbo with the information panel up, at 50% |
| `compare` | the three rasters of one mountain flipped through, the wheel rolled into the crater on the way |
| `false_color` | the hillshade held over the crater, `r` pressed through the four color maps |
| `fuzzy_finder` | Ctrl+P over a directory of several hundred pictures: one chosen by a few letters, one by its number |

```sh
./main_screenshot                       # ~/git/gamut/user-docs/screenshots/main_screenshot.jpg
GAMUT=~/build/gamut ./compare           # with another binary
SCREENSHOTS=/tmp/shots ./false_color    # to another directory
```

Three things are the environment's to say, each with a default:

| variable | what | default |
| --- | --- | --- |
| `GAMUT` | the binary to drive | `~/git/gamut/target/release/gamut` |
| `SCREENSHOTS` | where the pictures go | `~/git/gamut/user-docs/screenshots` |
| `FILMS` | where the recordings go before they are GIFs | `films/` here, ignored by git |

The pictures they open are not in this repository: `~/git/mora`,
`~/Downloads/stellated-dodecahedron.gif`, `~/Downloads/0-winding-road.webp`
and a directory of bird plates. Each script takes another path as its first
argument.

## What a script does

[`lib.sh`](lib.sh) is what the scripts share, and it speaks only Hyprland.
The compositor has to do three things the program cannot do for itself:

- **Leave the window at the size asked for.** `--size` is a request, and a
  tiling layout ignores it. `open` starts the program through `hl.exec_cmd`
  with a rule set that floats and centers the window at exactly that size,
  and at full opacity: Omarchy's default rules make every window slightly
  translucent, which would blend whatever is behind it into the picture.
- **Say where the window is.** `hyprctl clients` reports the window's
  position and size in logical pixels, and `grim -g` captures that rectangle
  at the monitor's own scale. On a monitor at scale 1.6 a 1000×600 window
  comes out as a 1600×960 image.
- **Type into it.** `wtype` presses keys on a virtual keyboard, and they go
  to whichever window has focus. Focus follows the pointer, so the pointer
  is put in the window before anything is typed.

`keys` presses one key per `wtype` call, and the reason is worth knowing
before changing it. `wtype` builds its keymap as it goes: each new keysym is
added and the whole keymap sent to the compositor again, which forwards it to
the focused window. A key pressed under the new keymap before the window has
read it is interpreted under the old one, and `wtype -k plus -k Up` reaches
the program as something other than `+` and `Up`. One keysym per process is
one keymap per process, and every key lands as itself.

The pointer is placed by `cursor`, which goes out of the window and back in
rather than straight to the point, because a warp within the window sends
the window no motion event: the readout of wherever the pointer last was
over the picture would stay in the bar, and the wheel would turn about the
old place. Leaving and entering are events, and the entering is also what
gives the window the keyboard. `cursor` checks that it did, and when it did
not — the desk's own mouse moved, a window came up over the spot — falls
back on the compositor's focus dispatch, which warps the pointer to the
window's center, and then leaves and enters again. `keys` and `press` make
the same check before they send anything; one run of `fuzzy_finder` before
that check typed its query into a browser's print dialog. Between shots the
pointer is parked on the middle of the top bar, the one place it shows in
nothing.

`close` kills the window and then waits for the compositor to forget it.
The next window can be given the same address, and `open` tells the new
window from the ones already open by address, so a script that opens twice
in a row would otherwise take the second window for the first.

## A device of our own

`wtype` has keys and no pointer, and Hyprland can warp the pointer but not
press its buttons or turn its wheel. What the wheel does — zoom about the
pointer — and what a drag does are half the program, so
[`device.py`](device.py) is a mouse of its own: a device registered through
`/dev/uinput` for as long as one command runs, sending wheel notches or a
held button and motion, then taken away again. It uses nothing outside
Python's standard library; the ioctl numbers and the event record are
written out from the kernel's own headers. Omarchy gives the user write
access to `/dev/uinput` through an ACL, which is what makes this possible
without root. `wheel` and `drag` in `lib.sh` call it, and `record NAME
cursor` keeps the pointer in the film for a recording where the pointer is
the point.

It is a keyboard too, for the bindings `wtype` cannot reach. A binding in
gamut's `app/input.rs` is matched either by what the key says (`Char("+")`)
or by where it is (`Position(KeyCode::Digit2)`, which is how `Shift+2` is
50% on any layout). `wtype` types a keysym under a keymap of its own, at a
keycode it chose, so the window sees the right character at the wrong
position; a key from the device is the real keycode read under the real
keymap, and matches either way. `press shift+2` in `lib.sh` is that. `keys`
stays on `wtype` for everything else, because a keysym is what a binding by
character wants and does not depend on the desk's layout.

The pointer is placed first with `cursor`, and `fitted W H X Y` says where
image pixel X, Y of a W×H image is in the layout while the image is fitted
to the window — the same sum gamut's `chrome::content_area` and
`View::fit_zoom` do, redone in awk, so that a script can put the pointer on
a feature of the picture by its own coordinates.

## A recording

`record` starts `gpu-screen-recorder` on the same rectangle, at 60 frames a
second, and waits for the `.ts` file it writes beside the film with its
first frame's wall-clock time. That is the clock the film is cut by:
`since_record` says how long after the first frame something was done, and
`gif` takes a start and a length in those seconds. `animated` reads the
start before it presses `Return` and the length from the file's own frame
delays, so the GIF is one loop of the file from the moment play was
pressed, and loops where the file does. `cut` stops the recorder with
`SIGINT`, which is how it is told to finish the file rather than drop it.

`gif` is ffmpeg's two-pass GIF — a palette from the whole clip, then the
frames dithered against it, each frame only the rectangle that changed —
at 25 frames a second and 800 pixels wide.

## What the scripts are not

They are not tests, and they do not run in CI. They open a window on
whatever workspace is active and type into it, so they want a desk with
someone at it who is not typing anything else — the keys go to whichever
window has focus, and the focus check is a remedy, not a guarantee. The
window the screenshot shows wears the desktop's theme, as the program
always does, so a picture taken on a different theme is a different
picture.
