"""Analyse a whole match in one go: video in, automatic tags file out.

Runs every pass in order, skipping any whose output already exists (so an
interrupted run picks up where it stopped), then writes
<video name>.touchline-auto.json next to the video, ready to add in the app.

    python -m touchline_cv.analyse VIDEO --us navy --them red
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Plain colour names a coach would type, mapped to typical shirt colours.
COLOURS = {
    "navy": "#1b2a4a", "blue": "#1f4fa8", "sky": "#6cabdd", "lightblue": "#6cabdd", "red": "#c8102e",
    "maroon": "#6d1a2a", "claret": "#7a263a", "white": "#f2f2f2", "black": "#151515", "green": "#1f7a3a",
    "yellow": "#f2d21b", "gold": "#d4a017", "orange": "#f07820", "purple": "#5b2a86", "grey": "#8a8a8a",
    "gray": "#8a8a8a", "pink": "#e75480",
}

PASSES = [
    ("track", "tracks.npz", "Finding and following players"),
    ("camera", "camera.npz", "Measuring camera movement"),
    ("pitch", "pitch.npz", "Finding pitch markings"),
    ("ballpass", "balls.npz", "Finding the ball"),
]


def colour(c: str) -> str:
    c = c.strip().lower().replace(" ", "")
    if c.startswith("#") and len(c) == 7:
        return c
    if c in COLOURS:
        return COLOURS[c]
    raise SystemExit(f"Unknown colour '{c}'. Use one of: {', '.join(sorted(COLOURS))}, or a hex code like #1b2a4a.")


def run(module: str, *args: str):
    cmd = [sys.executable, "-m", f"touchline_cv.{module}", *args]
    r = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1])
    if r.returncode != 0:
        raise SystemExit(f"Step '{module}' failed (exit {r.returncode}).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--us", required=True, help="your shirt colour: a name (navy, red, ...) or hex")
    ap.add_argument("--them", required=True, help="opposition shirt colour")
    ap.add_argument("--work", help="folder for intermediate files (default: next to the video)")
    args = ap.parse_args()

    video = Path(args.video).resolve()
    us, them = colour(args.us), colour(args.them)
    work = Path(args.work) if args.work else video.with_suffix("").parent / (video.stem + ".touchline")
    work.mkdir(parents=True, exist_ok=True)

    for i, (module, output, label) in enumerate(PASSES, 1):
        if (work / output).exists():
            print(f"[{i}/6] {label}: already done")
            continue
        print(f"[{i}/6] {label}...", flush=True)
        run(module, str(video), "--out", str(work))

    print("[5/6] Detecting kick-offs, half-time, full-time and goals...", flush=True)
    # No --pitch: follow-cam calibration isn't reliable yet (see README, Accuracy).
    run("phases", str(work), "--us", us, "--them", them, "--balls", str(work / "balls.npz"))
    # Shots and team shape need a reliable pitch calibration, which follow-cam
    # footage doesn't have yet. They stay off rather than produce wrong numbers;
    # run touchline_cv.shots / .positional by hand to experiment.
    print("[6/6] Shots and team shape: not available yet for follow-cam video (see README).", flush=True)
    for stale in ("shots_v2.json", "positional.json"):
        (work / stale).unlink(missing_ok=True)
    dest = video.with_name(video.stem + ".touchline-auto.json")
    run("export", str(work), "--video", video.name, "--out", str(dest))
    print(f"\nDone. In Touchline, open the match, load this video, then press 'Add automatic tags' and choose:\n  {dest}")


if __name__ == "__main__":
    main()
