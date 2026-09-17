#!/bin/sh
# What every screenshot script in this directory does the same way: open a
# gamut window of a known size where the compositor will leave it alone, drive
# it with keys, capture exactly its rectangle, and close it again.
#
# Only Hyprland is spoken here. Its Lua API places and focuses the window,
# `wtype` types into it, and `grim` captures the region it reports. The capture
# is in device pixels, so a monitor at scale 1.6 gives a 1200x800 window as a
# 1920x1280 image, which is what the README's pictures are.
#
# A script sources this file, then:
#
#   open 1200 800 images/mora    the window, focused, with its first file shown
#   keys plus plus plus Up       the keys to press, one argument each
#   settle                       wait for a pan or zoom to land
#   shoot main_screenshot.jpg    into $SCREENSHOTS
#   close
#
# or, for a recording, `record x.mp4` and `cut` around the keys, and
# `gif "$film" x.gif` afterwards. The recording is gpu-screen-recorder's,
# into $FILMS, and the GIF is ffmpeg's, into $SCREENSHOTS. A GIF that
# flips between stills is `still a.png`, `still b.png`, and
# `flipbook x.gif 2 "$a" "$b"`.
#
# Three things are the environment's to say, each with a default:
#
#   GAMUT         the binary to drive        ~/git/gamut/target/release/gamut
#   SCREENSHOTS   where the pictures go      ~/git/gamut/user-docs/screenshots
#   FILMS         where the recordings go    films/ beside this file, ignored by git
#
# The window opens on whatever workspace is active, so the script is for a
# desk someone is sitting at, not for CI. Keep your hands off the keyboard
# while it runs: the keys go to whichever window is focused.

set -eu

ROOT=$(cd "$(dirname "$0")" && pwd)
CLASS=com.dcervelli.gamut
GAMUT=${GAMUT:-$HOME/git/gamut/target/release/gamut}
SCREENSHOTS=${SCREENSHOTS:-$HOME/git/gamut/user-docs/screenshots}
FILMS=${FILMS:-$ROOT/films}

for tool in hyprctl jq wtype grim magick gpu-screen-recorder ffmpeg python3; do
    command -v "$tool" >/dev/null || { echo "$tool is not installed" >&2; exit 1; }
done
[ -x "$GAMUT" ] || { echo "no gamut binary at $GAMUT; build one, or set GAMUT" >&2; exit 1; }
[ -d "$SCREENSHOTS" ] || { echo "no directory at $SCREENSHOTS to put the pictures in; set SCREENSHOTS" >&2; exit 1; }

# Whatever a script that stopped early left behind: a window it was
# driving, a recorder it had started.
cleanup() {
    [ -z "${RECORDER:-}" ] || kill -INT "$RECORDER" 2>/dev/null || true
    [ -z "${WINDOW:-}" ] || kill "$(window pid)" 2>/dev/null || true
}
trap cleanup EXIT

# Every gamut window the compositor knows, one address per line.
gamut_windows() {
    hyprctl clients -j | jq -r --arg class "$CLASS" '.[] | select(.class == $class) | .address'
}

# One field of the window this script opened: "title", "pid", or the
# geometry as "x y w h".
window() {
    hyprctl clients -j | jq -r --arg address "$WINDOW" "
        .[] | select(.address == \$address) | $(case $1 in
            geometry) echo '"\(.at[0]) \(.at[1]) \(.size[0]) \(.size[1])"' ;;
            *) echo ".$1" ;;
        esac)"
}

# Open gamut at W by H logical pixels on the rest of the arguments, floating
# and centered so that the layout neither tiles nor resizes it, at full
# opacity so that whatever is behind it stays out of the picture. Returns
# once the first file is on screen and the window has the keyboard.
open() {
    width=$1
    height=$2
    shift 2

    before=" $(gamut_windows | tr '\n' ' ') "
    command="$GAMUT --size $width $height"
    for path; do
        command="$command $(shell_quote "$path")"
    done
    set -- $(placement "$width" "$height")
    hyprctl eval "hl.exec_cmd($(lua_quote "$command"), {
        float = true, size = \"$width $height\", move = { \"$1\", \"$2\" }, opacity = \"1 1\",
    })" >/dev/null

    # The new window is the one that was not there before.
    WINDOW=
    for _ in $(seq 50); do
        WINDOW=$(gamut_windows | while read -r candidate; do
            case "$before" in *" $candidate "*) ;; *) echo "$candidate" ;; esac
        done | head -1)
        [ -n "$WINDOW" ] && break
        sleep 0.1
    done
    [ -n "$WINDOW" ] || { echo "gamut's window never appeared" >&2; exit 1; }

    loaded

    # Focus follows the pointer, so the pointer goes in first; the keys
    # would otherwise land in whatever it was over.
    park
    sleep 0.3
}

# Where on the focused monitor a W by H window goes, in logical pixels
# from the monitor's corner: centered in what the bars leave, as the
# `center` rule would put it, then moved to the nearest logical pixel that
# is also a whole device pixel.
#
# On a monitor at scale 1.6 a logical pixel is 1.6 device pixels, and only
# every fifth position lands on a whole one. Centered under a 26-pixel bar,
# a 600-high window starts at device row 620.8, and both grim and the
# recorder then start their capture on row 620, which is not the window
# but Hyprland's border around it: blue while the window has focus,
# translucent gray while it does not, and half a second of fade between,
# so it changes color every time the pointer goes out and comes back. The
# recorder's is a full row of it, and the GIF, which builds its palette
# from what changes between frames, makes that row flicker.
placement() {
    hyprctl monitors -j | jq -r '.[] | select(.focused) |
        "\(.width) \(.height) \(.scale) \(.reserved | join(" "))"' |
    awk -v w="$1" -v h="$2" '
        # The whole logical pixel nearest P at which SCALE times the
        # pixel is whole too.
        function aligned(p, scale,   d, sign, q, f) {
            for (d = 0; d <= 50; d++)
                for (sign = 1; sign >= -1; sign -= 2) {
                    q = int(p + 0.5) + sign * d
                    f = q * scale - int(q * scale + 0.5)
                    if (f < 1e-6 && f > -1e-6) return q
                }
            return int(p + 0.5)
        }
        # width height scale, then the reserved left top right bottom.
        {
            print aligned($4 + ($1 / $3 - $4 - $6 - w) / 2, $3),
                  aligned($5 + ($2 / $3 - $5 - $7 - h) / 2, $3)
        }'
}

# Wait for the file on its way to be on screen: the title says "loading"
# until it is. For after a step to another file, as well as for `open`.
loaded() {
    for _ in $(seq 100); do
        case "$(window title)" in loading*) sleep 0.1 ;; *) break ;; esac
    done
}

# Put the pointer at a point in the compositor's layout, in logical pixels,
# and make sure the window has the keyboard once it is there.
#
# It goes out of the window and back in rather than straight there: a warp
# inside the window sends the window no motion, so the readout of wherever
# the pointer last was over the picture would stay in the bar, and the
# wheel would turn about the old place. Leaving and entering are events,
# and the entering is what gives the window focus, since focus follows the
# pointer.
#
# Whether it did is checked, because it does not always: the desk's own
# mouse may have moved meanwhile, or a window may have come up over the
# spot. The fallback is the compositor's own focus dispatch, which warps
# the pointer to the window's center as a side effect, and then the same
# leave and enter again to put it back where it was asked for.
cursor() {
    CURSOR_X=$1
    CURSOR_Y=$2
    set -- $(window geometry)
    for attempt in 1 2 3; do
        warp $(($1 - 8)) $(($2 - 8))
        sleep 0.1
        warp "$CURSOR_X" "$CURSOR_Y"
        sleep 0.2
        focused && return
        hyprctl eval "hl.dispatch(hl.dsp.focus({ window = hl.get_window(\"address:$WINDOW\") }))" >/dev/null
        sleep 0.2
    done
    echo "the window would not take focus" >&2
    exit 1
}

warp() {
    hyprctl eval "hl.dispatch(hl.dsp.cursor.move({ x = $1, y = $2 }))" >/dev/null
}

# Move the pointer to a point in the layout the way a hand would: as
# motion, from wherever it is, through device.py. For a film with the
# pointer in it, where `cursor` would be seen to jump out of the window and
# back; and for a tooltip, which wants the pointer to have arrived rather
# than appeared. Only for a point inside the window, which keeps the
# keyboard throughout.
glide() {
    CURSOR_X=$1
    CURSOR_Y=$2
    python3 "$ROOT/device.py" glide "$1" "$2"
}

focused() {
    [ "$(hyprctl activewindow -j | jq -r .address)" = "$WINDOW" ]
}

# Before a key is sent: the window still has the keyboard, or gets it back
# with the pointer put where it last was.
keyboard() {
    focused || cursor "$CURSOR_X" "$CURSOR_Y"
}

# Where in the layout image pixel X, Y of a W by H image is while the image
# is fitted to the window: the picture is centered in the area the four
# bars leave, at whichever of the two scales fits all of it in.
#
#   cursor $(fitted 6016 3384 960 2150)
fitted() {
    set -- "$1" "$2" "$3" "$4" $(window geometry) $(scale)
    awk -v W="$1" -v H="$2" -v X="$3" -v Y="$4" \
        -v wx="$5" -v wy="$6" -v ww="$7" -v wh="$8" -v scale="$9" -v bar=30 'BEGIN {
        vw = (ww - 2 * bar) * scale; vh = (wh - 2 * bar) * scale
        zoom = vw / W; if (vh / H < zoom) zoom = vh / H
        x = (vw - W * zoom) / 2 + X * zoom; y = (vh - H * zoom) / 2 + Y * zoom
        printf "%d %d\n", wx + bar + x / scale, wy + bar + y / scale
    }'
}

# Device pixels to the logical one on the monitor the window is on.
scale() {
    monitor=$(window monitor)
    hyprctl monitors -j | jq -r --argjson id "$monitor" '.[] | select(.id == $id) | .scale'
}

# Turn the wheel N notches under the pointer, positive away from the hand,
# which zooms in about it; drag the left button DX, DY logical pixels from
# where the pointer is; and click the left button where the pointer is. All
# three are a device of our own: see device.py.
wheel() {
    python3 "$ROOT/device.py" wheel "$1"
}

drag() {
    python3 "$ROOT/device.py" drag "$1" "$2"
}

click() {
    python3 "$ROOT/device.py" click
}

# Press a key by its position rather than by what it says — `shift+2` for
# 50%, `ctrl+shift+c` — through the same device, for the bindings that are
# matched on the key's position and that wtype's own keymap cannot reach.
press() {
    keyboard
    for chord; do
        python3 "$ROOT/device.py" key "$chord"
    done
}

# Press keys, one argument each, named as xkb names them: `plus`, `Up`,
# `space`, `bracketright`, `c`, and `C` for the capital. Modifiers go in
# front, joined with dashes: `ctrl-c`, `ctrl-shift-period`.
#
# One wtype call per key, because wtype grows its keymap as it meets new
# keysyms and sends the compositor each revision, and a key pressed under a
# keymap the window has not read yet lands as whatever that keycode was
# under the last one.
keys() {
    keyboard
    for key; do
        mods=
        while :; do
            case $key in
                ctrl-*|shift-*|alt-*) mods="$mods ${key%%-*}"; key=${key#*-} ;;
                *) break ;;
            esac
        done
        held=
        released=
        for mod in $mods; do
            held="$held -M $mod"
            released="-m $mod $released"
        done
        wtype $held -k "$key" $released
        sleep 0.05
    done
}

# Long enough for a pan or a zoom to reach where it was going: a move takes
# motion::DURATION, 200 ms, and the frame after it is what is wanted.
settle() {
    sleep 0.5
}

# Put the pointer where it shows in nothing: the middle of the top bar,
# between the title and the readout. Over the picture it would put a pixel
# readout in the bottom bar, over a button a tooltip, and outside the
# window it would take the keyboard with it, since focus follows it.
park() {
    set -- $(window geometry)
    cursor $(($1 + $3 / 2)) $(($2 + 15))
}

# Capture the window's rectangle as a JPEG, under the name given, in
# $SCREENSHOTS.
shoot() {
    park
    set -- "$SCREENSHOTS/$1" $(window geometry)
    grim -g "$2,$3 ${4}x$5" -t jpeg -q 92 "$1"
    echo "$1"
}

# Start recording the window's rectangle under the name given in $FILMS, an
# MP4 at 60 frames a second, and return once the first frame is down. `cut`
# stops it, and says where the film is.
# The pointer is left out of the film unless a second argument says
# `cursor`, for a recording of something the pointer does.
#
# The region is handed over in logical pixels, as `hyprctl clients` reports
# it; the recorder scales to the monitor's own pixels itself.
record() {
    park
    set -- "$FILMS/$1" "${2:-no}" $(window geometry)
    mkdir -p "$FILMS"
    rm -f "$1" "$1.ts"
    case $2 in cursor) shown=yes ;; *) shown=no ;; esac
    gpu-screen-recorder -w "${5}x$6+$3+$4" -f 60 -fm cfr -k h264 -cursor "$shown" \
        -fallback-cpu-encoding yes -write-first-frame-ts yes -o "$1" 2>"$1.log" &
    RECORDER=$!
    RECORDING=$1
    # The .ts file is written with the first frame, and says when that was.
    for _ in $(seq 100); do
        [ -s "$1.ts" ] && break
        kill -0 "$RECORDER" 2>/dev/null || { cat "$1.log" >&2; exit 1; }
        sleep 0.1
    done
    [ -s "$1.ts" ] || { echo "the recorder never wrote a frame" >&2; exit 1; }
    RECORDING_STARTED=$(awk 'NR == 2 { printf "%.6f\n", $2 / 1000000 }' "$1.ts")
}

# Seconds since the recording's first frame, for cutting the film to what
# happened after it.
since_record() {
    awk -v now="$(date +%s.%N)" -v then="$RECORDING_STARTED" 'BEGIN { printf "%.3f\n", now - then }'
}

# Stop the recording. SIGINT is how the recorder is told to finish the file
# rather than abandon it.
cut() {
    kill -INT "$RECORDER"
    wait "$RECORDER" 2>/dev/null || true
    RECORDER=
    rm -f "$RECORDING.log" "$RECORDING.ts"
    echo "$RECORDING"
}

# The recording, or the part of it from START for LENGTH seconds, as a GIF
# WIDTH pixels wide at 25 frames a second, under the name given in
# $SCREENSHOTS: a palette for the whole clip first, then the frames dithered
# against it.
#
#   gif "$film" out.gif [WIDTH] [START] [LENGTH]
gif() {
    film=$1
    out=$SCREENSHOTS/$2
    width=${3:-800}
    window=""
    [ -n "${4:-}" ] && window="-ss $4"
    [ -n "${5:-}" ] && window="$window -t $5"
    filters="fps=25,scale=$width:-1:flags=lanczos"
    ffmpeg -v error -y $window -i "$film" \
        -filter_complex "$filters,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
        -loop 0 "$out"
    echo "$out"
}

# Capture the window's rectangle losslessly, as a PNG under the name given
# in $FILMS: a frame for a GIF put together from stills rather than cut
# from a recording. `flipbook` makes the GIF.
still() {
    park
    set -- "$FILMS/$1" $(window geometry)
    mkdir -p "$FILMS"
    grim -g "$2,$3 ${4}x$5" "$1"
    echo "$1"
}

# The stills given, each held for HOLD seconds, as a GIF under the name
# given in $SCREENSHOTS, at the stills' own size.
#
#   flipbook themes.gif 2 "$first" "$second"
flipbook() {
    out=$SCREENSHOTS/$1
    hold=$2
    shift 2
    magick -delay "${hold}x1" -loop 0 "$@" "$out"
    echo "$out"
}

# Close the window, and wait until the compositor has forgotten it: the next
# window opened can be given the same address, and would then look like one
# that was already there.
close() {
    kill "$(window pid)" 2>/dev/null || true
    for _ in $(seq 50); do
        [ -z "$(window pid)" ] && break
        sleep 0.1
    done
}

# A string as a Lua literal, for the arguments hyprctl eval is handed.
lua_quote() {
    printf '"%s"' "$(printf '%s' "$1" | sed 's/[\\"]/\\&/g')"
}

# A string as one word of the shell command line Hyprland runs.
shell_quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}
