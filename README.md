# gamut-scripting

The scripts that take [gamut](https://github.com/dcervelli/gamut)'s
pictures, and the pictures themselves: one script per picture in
`screenshots/`, so that a picture can be taken again after the interface
changes and come out the same size, in the same place, showing the same
thing. What each one shows is the script. gamut's README links to the
pictures here rather than carrying them, so taking one again and pushing it
is what changes the picture there.

| script | picture |
| --- | --- |
| `main_screenshot` | a photograph zoomed in three steps and panned to the summit, with the minimap |
| `animated` | a GIF opened paused, then played through once with the transport bar |
| `pixel_grid` | the grid on, the wheel rolled over the stag until the grid is at single pixels, then Space |
| `pixel_copy` | the grid on and the wheel rolled into the mountain, the dot at the head of the readout hovered and pressed, Hex chosen, and Ctrl+. over the picture |
| `open_in` | the photograph with the open button in the left strip pressed and the "Open in…" menu of what this desk will open it in standing beside it |
| `info` | an elevation model in turbo with the information panel up, at 50% |
| `compare` | the three rasters of one mountain flipped through, the wheel rolled into the crater on the way |
| `false_color` | the hillshade held over the crater, `r` pressed through the four color maps |
| `fuzzy_finder` | Ctrl+P over a directory of several hundred pictures: one chosen by a few letters, one by its number |
| `themes` | the photograph with the information panel open, on Tokyo Night, then on Gruvbox once the desk is switched to it, the two stills flipped between every two seconds |
| `histogram` | the photograph with the histogram opened from its button, the black and white handles on the band each dragged a fifth of the way in, and `w` held for a second to paint the clipped pixels |
| `ui` | the directory of the mountain's four rasters, the pointer held on the counter at the head of the top bar for its tooltip, the help button at the foot of the right strip pressed and the table of keys scrolled to its end over three seconds, Esc, and the button at the end of the top bar pressed to hide the interface |
| `mandelbrot` | a PNG that a program rewrites every second, one step further into the Mandelbrot set, watched for ten seconds: zoomed four steps into the middle and panned once around it partway, then Space |
| `region` | a web page's screenshot, `x` pressed and a box dragged out ten pixels loose around the wordmark, the wheel turned five notches in over the handle on its left edge, the handle clicked and Right pressed until the edge meets the first letter, the picture dragged to bring the top, right and bottom handles into view in turn and each brought in the same way, then Ctrl+C and Ctrl+V, so that the copy is pasted and shown, cut to the pixel |
| `performance` | a fresh terminal and the window it opens, side by side: `gamut --timing` on a 443 MB Swiss map typed at the prompt, Return, and the timing marks arriving on the left as the map comes up on the right |

```sh
./main_screenshot                       # screenshots/main_screenshot.jpg
GAMUT=~/build/gamut ./compare           # with another binary
SCREENSHOTS=/tmp/shots ./false_color    # to another directory
./all                                   # every one of them, in the order above
```

Three things are the environment's to say, each with a default:

| variable | what | default |
| --- | --- | --- |
| `GAMUT` | the binary to drive | `~/git/gamut/target/release/gamut` |
| `SCREENSHOTS` | where the pictures go | `screenshots/` here |
| `FILMS` | where the recordings go before they are GIFs | `films/` here, ignored by git |

The pictures they open are in `images/`: the four rasters of one mountain
in `images/mora`, several hundred bird plates in `images/birds`, and the
GIF and the stag beside them. Each script takes another path as its first
argument. `mandelbrot` opens no picture of ours: the program that draws its
picture is the Rust crate in [`mandelbrot-zoom/`](mandelbrot-zoom/), which
the script builds if `cargo build --release` has not been run there
already, or `MANDELBROT` names another binary. `performance` opens one too
big to keep here, the 14000×9600 raster of a Swiss 1:50000 map sheet at
`~/Downloads/swiss-map-raster50_2007_285_krel_2.5_2056.tif`, and wants
that or another file as its argument.

## What a script does

[`lib.sh`](lib.sh) is what the scripts share, and it speaks only Hyprland.
The compositor has to do three things the program cannot do for itself:

- **Leave the window at the size asked for.** `--size` is a request, and a
  tiling layout ignores it. `open` starts the program through `hl.exec_cmd`
  with a rule set that floats the window at exactly that size, and at full
  opacity: Omarchy's default rules make every window slightly translucent,
  which would blend whatever is behind it into the picture.
- **Put it on a device pixel.** `hyprctl clients` reports the window's
  position and size in logical pixels, and `grim -g` captures that rectangle
  at the monitor's own scale. On a monitor at scale 1.6 a 1000×600 window
  comes out as a 1600×960 image, but only every fifth logical position is a
  whole device pixel, and a window centered under the bar starts at device
  row 620.8: the first captured row is then Hyprland's border, which is blue
  while the window has focus, gray while it does not, and a half-second fade
  between whenever the pointer leaves and comes back. In a film that row
  flickers. `placement` centers the window as the `center` rule would and
  then moves it to the nearest position that is whole at the monitor's
  scale, so every captured pixel is the window's own.
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

## Two windows

`performance` has a terminal beside the window, since what it shows is what
`--timing` prints. Each window of the pair is where `open` would put one
window of their combined size, and each is 500 wide, so both start on a
whole device pixel, and both are given `border_size = 0`: the border is
drawn outside the window's rectangle, over whatever is next to it, so
two windows flush against each other would each wear a stripe of the
other's. `spawn` is what `open` does for gamut, for any command and class
— here ghostty, as a process of its own, on a shell with no rc file and a
bare prompt whose PATH begins with a directory holding the binary under
test as `gamut`. The window that shell starts cannot be handed rules by
`hl.exec_cmd`, so `rule` sets a named window rule for the run, and turns
it off when the script ends, whichever way. `FRAME` says what `record`
captures when it is not the one window's rectangle, and `text` types the
command line at the prompt: through the device's keyboard, as `press`
does, because a terminal reads a capital as its letter with Shift held,
and under wtype's one-level keymap Shift changes nothing. The command is
typed before the recording starts, so the film is Return, the window, and
the numbers.

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
without root. `wheel`, `drag` and `click` in `lib.sh` call it, and `record
NAME cursor` keeps the pointer in the film for a recording where the pointer
is the point.

`glide` moves the pointer through it too, for a film where the pointer's
way to a button is part of the picture and `cursor`'s leap out of the
window and back is not, and for a tooltip, which the program shows only
over a pointer that arrived by motion. The compositor accelerates motion
from a mouse, so that a unit of motion carries a distance that depends on
the pace it comes at; `device.py` has Hyprland give this device alone a
flat profile, through the Lua API's `hl.device`, at a sensitivity that
makes every unit exactly a quarter of a logical pixel however fast it is
sent. Where the pointer is then is arithmetic: where it was when the
device was made, asked of the compositor once, plus the units sent over
four. A glide is the units that take it to its mark, at a pace of sixteen
pixels a frame taken over the move — eased, so that it sets off and stops
gently as a hand does — and it lands within an eighth of a pixel. `drag_to`
is the same with the button held.

The pointer's place is a fraction, and `hyprctl cursorpos` cuts the
fraction off; the Lua API has it whole, and since `hyprctl eval` prints
nothing a script returns and only what it raises, `device.py` raises the
position and reads it off the error. It is read once, when the device is
made, and once more at the end, to check the sum; asked after each action
it would be a pause between them.

Where the pointer is and where the window has it are two things. The
compositor tells the window of a motion only when the whole logical pixel
the pointer is in changes, and then tells it the exact place of that
event; a last move of less than a pixel is not heard, and the window has
the pointer wherever it last crossed from one pixel into the next — up to
a pixel from where it stopped, which at a zoom under 100% is most of an
image pixel. So every glide ends on a move the window must hear: its last
two pixels are one step, sent as one event, which crosses a pixel's edge
along whichever axis it mostly goes and lands on the mark. `place` is the
same motion under a name for where the pixel under the pointer is what
matters, the two ends of the drag that draws `region`'s box.

A drag has its own trouble at the other end. A toolkit takes a press for a
click until the pointer has gone some pixels from it, and the motion of
the frame that decides it is not part of the drag; a stroke that sets off
at speed loses its first several pixels that way. So `drag_to` creeps the
first ten pixels a couple of units at a time, past the toolkit's distance,
before it moves at its pace, and what the deciding frame loses is a
fraction of a pixel.

`region` asks the program, before the film starts, which pixels it takes
the two placed corners of the box to be over — `Ctrl+Shift+.` copies the
coordinate, and the clipboard is read back — and counts the presses that
tighten each edge from its answer, in case its sums and the script's
differ by a pixel. The toast that says the coordinate was copied is gone
before the recorder starts.

Several of the device's actions are done as one hand's `gesture`, the
device made once and the actions given to it in a row, separated by `--`:
the glide to a handle, the click that takes it, the drag that brings the
next part of the picture into view, the arrows that bring the edge in, a
`rest` where a hand would pause. The whole of `region`'s film is one such
gesture, planned on the script's own model of the view, which the exact
motion lets it trust: a device made for each stage was most of a second
of the pointer sitting still between them. A pan too long for one stroke
inside the window is broken into two or three.

What the window makes of a click or a drag is decided a frame at a time,
so the device gives it two frames where the order of things matters: after
a glide, before the click or press there, since a click on a handle is a
click on whichever handle the window last drew the pointer over; and after
the button comes up, before the pointer moves on, since a click counts only
if the pointer is still on the widget in that frame, and motion in the
frame a drag is released is taken as part of the drag.

The desk hides the pointer when a key is pressed, and tells the window it
has left, which takes down whatever was up because the pointer was over
something — a tooltip, a region's measurements. `keep_pointer` turns that
off for the run, through the compositor's Lua config, and `cleanup` puts
it back however it was.

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

`mandelbrot` is a recording of the file under the window changing and the
window following, first as it was opened and then under a pan and zoom of
its own: three seconds in, `+` four times and a turn of the arrows around
the middle, which is where the renderer is heading, and each frame that
lands meanwhile comes up under the same view, since a file of the same
size keeps it; then Space fits the whole picture again. The renderer writes a 1024×1024 frame into
`$FILMS` every second, each to a temporary file renamed over the last, so
the window's watch — a `stat` every quarter second, acted on once the file
has held still for one — never reads a half-written frame. It draws its
first frame in milliseconds and the window takes a second or so to open,
so the script holds the renderer with `SIGSTOP` after that first frame and
lets it go with `SIGCONT` once the recorder is running, and every take
begins on the whole set. Ten seconds is nine steps of the zoom, at 0.8 a
step.

`themes` has no recording. Its two frames are `still`, which is `shoot`
losslessly into `$FILMS`, and `flipbook` puts them together with
ImageMagick, each held for the seconds given, at the window's own size.
The window is opened once: gamut watches the desktop's palette file and
retints itself when Omarchy rewrites it, so the second still is the same
window a few seconds later. The script switches the desk's theme with
`omarchy-theme-set` and puts it back on whatever it was, however it ends.

## What the scripts are not

They are not tests, and they do not run in CI. They open a window on
whatever workspace is active and type into it, so they want a desk with
someone at it who is not typing anything else — the keys go to whichever
window has focus, and the focus check is a remedy, not a guarantee. The
window the screenshot shows wears the desktop's theme, as the program
always does, so a picture taken on a different theme is a different
picture.
