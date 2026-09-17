//! Renders the Mandelbrot set to a PNG, zooming in one step per second until Ctrl+C.

use std::env;
use std::fs::File;
use std::io::BufWriter;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::thread;
use std::time::{Duration, Instant};

const WIDTH: usize = 1024;
const HEIGHT: usize = 1024;

/// Supersampling factor per axis (2 => 4 samples per pixel).
const SAMPLES: usize = 2;

/// Point we zoom toward: a spiral in the "seahorse valley" of the set.
const CENTER_RE: f64 = -0.743_643_887_037_158_7;
const CENTER_IM: f64 = 0.131_825_904_205_311_97;

/// Half-width of the complex-plane window in the first frame.
const START_HALF_SPAN: f64 = 1.5;
/// Window shrink per frame.
const ZOOM_PER_FRAME: f64 = 0.8;
/// Below this span f64 runs out of mantissa and the image turns to mush, so we
/// start over from the beginning.
const MIN_HALF_SPAN: f64 = 2.0e-15;

const FRAME_INTERVAL: Duration = Duration::from_secs(1);

fn main() -> ExitCode {
    let mut args = env::args_os().skip(1);
    let Some(out) = args.next() else {
        eprintln!("usage: mandelbrot <output.png>");
        return ExitCode::FAILURE;
    };
    if args.next().is_some() {
        eprintln!("usage: mandelbrot <output.png>");
        return ExitCode::FAILURE;
    }
    let out = PathBuf::from(out);

    let threads = thread::available_parallelism().map_or(1, |n| n.get());
    println!(
        "Rendering {WIDTH}x{HEIGHT} to {} on {threads} threads. Press Ctrl+C to quit.",
        out.display()
    );

    let mut pixels = vec![0u8; WIDTH * HEIGHT * 3];
    let mut half_span = START_HALF_SPAN;

    loop {
        let started = Instant::now();
        let max_iter = iteration_budget(half_span);

        render(&mut pixels, half_span, max_iter, threads);
        if let Err(e) = write_png(&out, &pixels) {
            eprintln!("error writing {}: {e}", out.display());
            return ExitCode::FAILURE;
        }

        println!(
            "span {:.3e}  zoom {:>9.3e}x  iter {max_iter:>6}  {:>6.0} ms",
            half_span * 2.0,
            START_HALF_SPAN / half_span,
            started.elapsed().as_secs_f64() * 1000.0
        );

        half_span *= ZOOM_PER_FRAME;
        if half_span < MIN_HALF_SPAN {
            println!("hit the limit of f64 precision; restarting the zoom");
            half_span = START_HALF_SPAN;
        }

        if let Some(rest) = FRAME_INTERVAL.checked_sub(started.elapsed()) {
            thread::sleep(rest);
        }
    }
}

/// Deeper zooms need more iterations to keep the filaments from filling in.
fn iteration_budget(half_span: f64) -> u32 {
    let zoom = START_HALF_SPAN / half_span;
    (300.0 + 260.0 * zoom.log10()) as u32
}

fn render(pixels: &mut [u8], half_span: f64, max_iter: u32, threads: usize) {
    let scale = 2.0 * half_span / WIDTH as f64;
    let sub = scale / SAMPLES as f64;
    let top_left_re = CENTER_RE - half_span;
    let top_left_im = CENTER_IM + half_span;

    let rows_per_band = HEIGHT.div_ceil(threads);
    thread::scope(|s| {
        for (band, chunk) in pixels.chunks_mut(rows_per_band * WIDTH * 3).enumerate() {
            let y0 = band * rows_per_band;
            s.spawn(move || {
                for (row, out_row) in chunk.chunks_mut(WIDTH * 3).enumerate() {
                    let y = y0 + row;
                    for (x, px) in out_row.chunks_mut(3).enumerate() {
                        let (mut r, mut g, mut b) = (0.0f64, 0.0, 0.0);
                        for sy in 0..SAMPLES {
                            for sx in 0..SAMPLES {
                                let cr = top_left_re
                                    + x as f64 * scale
                                    + (sx as f64 + 0.5) * sub;
                                let ci = top_left_im
                                    - y as f64 * scale
                                    - (sy as f64 + 0.5) * sub;
                                let (sr, sg, sb) = color(escape(cr, ci, max_iter));
                                r += sr;
                                g += sg;
                                b += sb;
                            }
                        }
                        let n = (SAMPLES * SAMPLES) as f64;
                        px[0] = to_srgb(r / n);
                        px[1] = to_srgb(g / n);
                        px[2] = to_srgb(b / n);
                    }
                }
            });
        }
    });
}

/// Returns the smooth (fractional) escape iteration, or `None` for points that
/// never escaped.
fn escape(cr: f64, ci: f64, max_iter: u32) -> Option<f64> {
    // The main cardioid and the period-2 bulb are the two big interior regions;
    // testing them directly saves running max_iter on a large share of pixels.
    let q = (cr - 0.25) * (cr - 0.25) + ci * ci;
    if q * (q + (cr - 0.25)) <= 0.25 * ci * ci {
        return None;
    }
    if (cr + 1.0) * (cr + 1.0) + ci * ci <= 0.0625 {
        return None;
    }

    // Escape radius of 2 is enough for correctness; a larger one makes the
    // smoothing term below far less banded.
    const BAILOUT: f64 = 65536.0;
    let (mut zr, mut zi) = (0.0f64, 0.0f64);
    let (mut zr2, mut zi2) = (0.0f64, 0.0f64);

    // Periodicity check: interior orbits settle into a cycle, so bail out once
    // the orbit stops moving away from a periodically refreshed reference.
    let (mut oldr, mut oldi) = (0.0f64, 0.0f64);
    let mut period = 0u32;
    let mut period_limit = 20u32;

    for i in 0..max_iter {
        zi = 2.0 * zr * zi + ci;
        zr = zr2 - zi2 + cr;
        zr2 = zr * zr;
        zi2 = zi * zi;

        let mag2 = zr2 + zi2;
        if mag2 > BAILOUT {
            let nu = (mag2.ln() / 2.0 / std::f64::consts::LN_2).log2();
            return Some(i as f64 + 1.0 - nu);
        }

        if zr == oldr && zi == oldi {
            return None;
        }
        period += 1;
        if period > period_limit {
            period = 0;
            period_limit *= 2;
            oldr = zr;
            oldi = zi;
        }
    }
    None
}

/// Cosine palette (after Inigo Quilez): a smooth, cyclic blue -> gold -> white ramp.
fn color(escape: Option<f64>) -> (f64, f64, f64) {
    let Some(n) = escape else {
        return (0.0, 0.0, 0.0);
    };
    // sqrt compresses the fast-growing outer bands so the cycle stays readable
    // as the iteration count climbs.
    let t = n.max(0.0).sqrt() * 0.155;
    let tau = std::f64::consts::TAU;
    (
        0.5 + 0.5 * (tau * (t + 0.00)).cos(),
        0.5 + 0.5 * (tau * (t + 0.15)).cos(),
        0.5 + 0.5 * (tau * (t + 0.30)).cos(),
    )
}

fn to_srgb(linear: f64) -> u8 {
    (linear.clamp(0.0, 1.0) * 255.0 + 0.5) as u8
}

/// Writes via a sibling temp file and renames, so a viewer watching the output
/// never sees a half-written frame (and Ctrl+C can't leave a truncated PNG).
fn write_png(path: &Path, pixels: &[u8]) -> std::io::Result<()> {
    let tmp = path.with_extension("png.tmp");
    {
        let file = File::create(&tmp)?;
        let mut encoder = png::Encoder::new(BufWriter::new(file), WIDTH as u32, HEIGHT as u32);
        encoder.set_color(png::ColorType::Rgb);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header()?;
        writer.write_image_data(pixels)?;
        writer.finish()?;
    }
    std::fs::rename(&tmp, path)
}
