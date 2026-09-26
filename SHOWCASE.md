# The showcase film

A 30–40 second recording of the whole desktop for a Reddit post, ending on
Omarchy's theme menu re-theming everything including gamut. Unlike every other
script here, this one films the monitor rather than the window, because what it
is arguing is that gamut belongs on this desk.

Everything below was decided in an earlier session. Verify the open questions
at the end before writing code; do not relitigate the decisions.

## Decisions already taken

- **Deliver 1920×1080.** Reddit's player tops out there; above it you are
  handing the quality decision to their transcoder.
- **Record the monitor at native 3840×2160 and keep that as the master.** Do
  not let the recorder scale (`-s`). The 2:1 headroom is what pays for the
  punch-ins.
- **Set the recorded output to scale 2 for the take**, restoring the live value
  on exit.
- **Window 1400×800 logical.** See the arithmetic below.
- **Wide throughout, tighten once on the info panel, punch out for the theme
  swap.** No punch-in at the opening.
- **End on the opening theme**, so the loop is wide→wide on the same palette.
- Beat count is deliberately long at this stage. Trim later; the `trim`
  column says what goes first.

## Why scale 2, and why a 1400×800 window

Both monitors are 3840×2160. At the live scale of 1.6 the logical desktop is
2400×1350, so delivering 1080p would render one logical pixel as 0.8 video
pixels — half the density of the window films in `films/`, which capture a
1000×600 logical window at 1600×960 device and ship it native.

At scale 2 the logical desktop is exactly 1920×1080, the delivery grid. One
logical pixel is one video pixel, rendered at 2× and downsampled 2:1, so text
comes out sharper than any native-1080p capture. Scale 2 is an integer, so
every logical pixel is a whole device pixel and `placement()`'s alignment nudge
becomes a no-op — the half-pixel border flicker it exists to prevent cannot
happen.

Window size follows from wanting the wide shot to already be legible:

| window (logical) | video px in the wide shot | vs. the existing films |
| --- | --- | --- |
| 1000×600 | 1000×600 | 63% |
| **1400×800** | **1400×800** | **88%** |
| 1500×850 | 1500×850 | 94% |

1400×800 leaves 260 logical px of wallpaper on each side and 254 below the bar
— enough desktop, gaps and bar to make the point — while landing within ~12% of
the density the README's films already ship. That is why the opening does not
need a punch-in: there is no legibility problem to solve, and punching in early
would spend the one reveal on nothing, make two thirds of the film look like
the window-cropped films that already exist, and break the wide→wide loop.

## Recording

Record `HDMI-A-1` and drive the script from a terminal on `DP-2`, so the thing
typing the keys is off camera. This is the one advantage the dual-head setup
gives that the window films never needed.

Leave the panel at 120 Hz — an exact 2× of 60, so constant-frame-rate sampling
lands evenly. Stay in SDR: the output is on the `srgb` preset with
`sdrMaxLuminance 80`, and there is no HDR path to Reddit anyway. Do not use the
`hevc_hdr` / `av1_hdr` encoders.

### Scale switch

The live scale and the config disagree — `~/.config/hypr/monitors.lua` says
`scale = 1.25` and `GDK_SCALE = 1`, while the compositor is live at 1.6. So
**read the live value from `hyprctl monitors -j` and restore to that**; do not
read the config, and do not assume 1.6 either. Save on entry, restore on exit
however the run ends, the way `performance` turns its window rule back off.

Two candidate commands, neither tested on Hyprland 0.56.2 with the Lua config:

```sh
hyprctl keyword monitor "HDMI-A-1,3840x2160@119.88,<position>,2"
hyprctl eval 'hl.monitor({ output = "HDMI-A-1", mode = "3840x2160@119.88", position = "<pos>", scale = 2 })'
```

The `eval` form matches how `lib.sh` already reaches the Lua API for
`hl.window_rule`. Find out which one takes before building on it. Note that
monitor positions are `auto`, so changing the scale will reflow them — re-read
`hyprctl monitors` after the switch rather than caching positions from before.

### Capture

`lib.sh`'s `record` already takes a rectangle in logical pixels through
`FRAME`, and the recorder scales to device pixels itself, so no library change
is needed:

```sh
FRAME="$mx $my $mw $mh"      # the monitor's logical rect, global coords, from hyprctl monitors
record showcase.mp4 cursor   # cursor must be visible throughout
```

`gpu-screen-recorder -w HDMI-A-1` would capture the output directly and is
slightly cleaner, but needs a small change to `record`. Either is fine.

`record` hardcodes `-k h264`. At 4K60 with `-q ultra` that is acceptable for a
scratch master; switching the master to `-k hevc` would hold quality at a
smaller size if you want to touch it.

### Window placement at scale 2

Logical monitor 1920×1080, bar reserving 26 at the top (**read `reserved` from
`hyprctl monitors` at record time — the bar's logical height may not be the
same at a different scale**). A 1400×800 window centred in what the bar leaves:

```
x = (1920 - 1400) / 2                = 260
y = 26 + (1080 - 26 - 800) / 2       = 153
device, relative to the output       = (520, 306) 2800×1600
```

## The curated directory

Open gamut **once**, on one directory, so the whole film is a single continuous
take with no cuts. A cut always reads as "something was hidden here". This also
makes `Ctrl+P` the actual means of navigation rather than a bolted-on beat, and
it satisfies `When::SeveralFiles`, which gates both `Ctrl+P` and `Tab` — on a
single file those bindings do not exist.

Build it at run time (symlinks under `$FILMS` or a temp dir, removed on exit)
rather than committing 800-odd links. Names fix the `]` order:

```
00-mora.jpg                        opening, bright, the thumbnail frame
01-reflection-lake-sunrise.dng     the clipping beat
<837 bird plates, their own names> the fuzzy finder's haystack
zz-1-mora-dem.tif                  gray, 4400×3760, 16-bit
zz-2-mora-hillshade.tif            gray, 4400×3760, 8-bit
zz-3-mora-relief.png               gray+alpha, 4400×3760, 8-bit
```

The 837 plates are the point of the `Ctrl+P` beat — the counter at the head of
the top bar showing ~842 files is what makes the chooser look necessary. A
directory of ten would make it look like a toy.

`zz-` keeps the rasters after every bird (some sort to `z`), adjacent and in
DEM → hillshade → relief order so `]` `]` walks them. `Ctrl+P` still finds them
on a fuzzy "dem".

Do not press `w` on a bird plate. They are on black backdrops — 17% to 57% of
pixels crushed across the sample checked — so the shadow mark would paint a
wall of blue that means nothing. On camera it would read as a rendering bug.

## The cut list

Times are targets, not measurements. The existing films are the sanity check:
`compare` runs 7.12 s for `]` `]` + wheel + `[` `[`, `fuzzy_finder` 9.87 s for
two queries, `loupe` 9.88 s, `false_color` 4.25 s.

| # | t | beat | keys | punch | trim |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.0 | `00-mora.jpg` at fit, whole desktop. The thumbnail frame. | — | 1.0× | |
| 2 | 2.5 | Wheel into the summit, `Space` back to fit | wheel, Space | 1.0× | |
| 3 | 6.5 | `]` to the sunrise raw | `]` | 1.0× | merge into 4 |
| 4 | 7.5 | `h` histogram, `w` paints the clipped pixels, hold, `w` clears | h, w, w | 1.0× | |
| 5 | 13.0 | `Ctrl+P`, a few letters of a bird's name, `Enter` | Ctrl+P, keys, Enter | 1.0× | |
| 6 | 17.5 | `l` loupe, glide onto the bird's eye, `Shift+L` once | l, L | 1.0× | |
| 7 | 21.0 | `Ctrl+P` → "dem", `Enter`, wheel into the crater | Ctrl+P, keys, Enter, wheel | 1.0× | |
| 8 | 25.0 | `]` `]` — hillshade, relief, the view held across both | `]` `]` | 1.0× | one `]` |
| 9 | 28.0 | `r` for false colour | r | 1.0× | **first to go** |
| 10 | 29.5 | `i` info panel, GeoTIFF metadata | i | 1.5× → 2.0× | |
| 11 | 33.5 | Theme menu, two swaps, back to the opening theme, hold ~2 s | Super+Shift+Ctrl+Space | 1.0× | one swap |
| | 40.5 | end | | | |

Trimming beats 9, 3 and one `]` from 8 brings it to about 33 s; dropping a
theme swap as well reaches 30.

Notes on individual beats:

- **2.** `Space` is `CycleFit`, which cycles whole → fill → actual size. After a
  wheel zoom `fit` is `None`, so the first press goes to `Fit::Whole`. One
  press is correct.
- **4.** Blocked on the gamut shader fix — see Dependencies.
- **6.** `l` is `ToggleLoupe`, `L` (shift) is `CycleMagnification`, which wraps
  through four magnifications. Keep the bird plates for this beat; the sunrise
  raw is 6 MP from a 2003 sensor and will show shadow noise under the loupe.
- **7–9.** All three rasters are single-channel, so `r` (`CycleColormap`) works
  on any of them. The colormap appears **not** to carry across `]` to a
  file not visited before — see open questions.
- **11.** The bind runs `omarchy-menu toggle theme`, so the script can spawn
  that command directly and then type letters and `Enter` with the existing
  `keys` machinery. The menu everyone recognises *and* a repeatable script.

Cut on a keystroke, never in dead air. Cut to 1.5× on the frame the info panel
appears and back to wide on the frame the theme menu appears. A cut that lands
on an action reads as emphasis; a cut between actions reads as an edit seam and
undercuts the continuous take the curated directory buys.

## Punch-in geometry

Any crop **wider than 1920 px is still a downscale** to delivery and therefore
still sharp. The sharp range is continuous from 1× to 2×; only past 2× do you
begin upscaling.

| punch | crop from the 3840×2160 master | to delivery |
| --- | --- | --- |
| 1.0× | 3840×2160 | 2:1 downscale |
| 1.5× | 2560×1440 | 1.33:1 downscale |
| 2.0× | 1920×1080 | none, 1:1 |
| 2.5× | 1536×864 | 1.25:1 **upscale — do not** |

The info panel is anchored to the window's right edge, so anchor the crop to
the window's right edge plus a margin and clamp to the frame, rather than
hardcoding. With the placement above, and taking the panel as roughly the
rightmost 300 logical px:

```
1.5×   crop=2560:1440:1280:386
2.0×   crop=1920:1080:1920:566
```

Both keep the panel comfortably inside. Recompute from the real window
rectangle; `placement()` already makes it arithmetic rather than eyeballing.

## Post

Have the script emit an **edit list** beside the master: `since_record`
timestamps paired with crop rectangles and key captions. Then the whole edit is
reproducible the way the screenshots are — re-run after the interface changes
and the same film comes out.

One pass, segments trimmed and cropped separately then concatenated, so every
segment shares output parameters:

```sh
ffmpeg -i showcase.mp4 -filter_complex "
 [0:v]trim=0:29.5,setpts=PTS-STARTPTS,scale=1920:1080:flags=area[a];
 [0:v]trim=29.5:31.5,setpts=PTS-STARTPTS,crop=2560:1440:1280:386,scale=1920:1080:flags=area[b];
 [0:v]trim=31.5:33.5,setpts=PTS-STARTPTS,crop=1920:1080:1920:566[c];
 [0:v]trim=33.5:40.5,setpts=PTS-STARTPTS,scale=1920:1080:flags=area[d];
 [a][b][c][d]concat=n=4:v=1:a=0[out]" \
 -map "[out]" -c:v libx264 -preset slow -crf 18 \
 -pix_fmt yuv420p -movflags +faststart -an reddit.mp4
```

`flags=area` rather than lanczos: at these ratios a box average is the correct
supersample and will not ring on 1 px borders or text. The 2.0× segment takes
no scale filter at all. If the result looks soft, lanczos is the alternative.

Roughly 40 s of 1080p60 at CRF 18 lands near 50 MB, well inside Reddit's
limits.

### Keystroke captions

Reddit autoplays muted, so the keys have to be visible. Do **not** install a
live overlay — neither `wshowkeys` nor `showmethekey` is installed and both
want root or an AUR build, and a live overlay would also catch
`Super+Shift+Ctrl+Space` and any stray key.

Burn them in instead. The script knows every key it presses and `since_record`
already gives exact offsets from the first frame, so log `3.42 Space` as it
goes and render with `drawtext ... enable='between(t,3.42,4.42)'`. Perfectly
timed, styled to match the theme, no new packages, no root.

## Open questions — settle these first

1. **Which scale-switch command takes** on 0.56.2 with the Lua config,
   `hyprctl keyword monitor` or `hyprctl eval hl.monitor`. Everything else
   depends on this.
2. **Does the bar's logical height stay 26 at scale 2?** Read `reserved` after
   the switch; the window placement arithmetic uses it.
3. **Does gamut follow symlinks** for the file list and the chooser? If not,
   hardlink or copy into the generated directory.
4. **What is the file list's default sort?** The naming scheme assumes name
   ascending. `file_list` drives a sort menu with Area and Descending, so the
   control exists; confirm the default.
5. **Does the colormap carry across `]`?** `app/mod.rs:1551` picks
   `Display::for_image_with` for a file with no kept settings, which suggests a
   newly visited file gets a fresh display and `r`'s colormap does **not**
   follow. This was read quickly — confirm it, because it decides whether `r`
   belongs before or after the `]` `]` in beats 8–9.
6. **Where exactly is the info panel**, in window-relative logical pixels, so
   the punch crops anchor to it properly.
7. **Does `open` place the window on the recorded monitor** when the driving
   terminal is focused on the other one? `lib.sh` opens on the focused
   workspace. This needs handling or the window lands off camera.

## Dependencies

**Beat 4 is blocked on a gamut change.** `w` (`MarkClipped`) currently paints
nothing on `images/mora/mora_reflection_lake_sunrise.dng`, because
`src/render/shaders/image.wgsl:289` requires *all three* channels to be
clipped, and the warm sun saturates red over ~1% of the frame while green
reaches white over only ~0.025%. The fix is `all()` → `any()`. A full
diagnosis, with measurements and an investigation list, was handed to a
separate session.

If that change does not land, beat 4 has to change: either drag the histogram's
black and white handles in first to manufacture clipping — which is what the
`histogram` script does, and why that film runs 15.45 s rather than four
seconds — or drop `w` and let the beat be the histogram and the pixel readout
alone.
