"""Write an automatic tags file for the Touchline app from pipeline results.

Combines phases.json (kick-offs, half-time, full-time, goals) and
shots_v2.json (shots with pitch locations). A goal is matched to the scoring
team's most recent shot in the GOAL_LOOKBACK_S seconds before the restart;
that shot becomes a goal. Goals with no matching shot can't be placed on the
pitch, so they're listed under generator.unplaced_goals instead of guessed.

    python -m touchline_cv.export OUT_DIR --video NAME.mp4 [--out FILE]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__

GOAL_LOOKBACK_S = 90


def build(phases: dict, shots: list, video_name: str, shape: dict | None = None) -> dict:
    events = [
        {"vt": s["vt"], "team": s["team"], "type": "shot", "x": s["x"], "y": s["y"], "conf": 0.5}
        for s in shots
    ]
    unplaced = []
    for g in phases.get("goals", []):
        side = g.get("scored_by")
        cands = [e for e in events if e["team"] == side and 0 < g["t"] - e["vt"] <= GOAL_LOOKBACK_S]
        if side and cands:
            max(cands, key=lambda e: e["vt"])["type"] = "goal"
        else:
            unplaced.append(g)
    sync = {k: round(float(phases[k]), 2) for k in ("k1", "k2", "ht", "ft") if phases.get(k) is not None}
    out = {
        "app": "touchline-auto",
        "schema": 1,
        "video": {"name": video_name},
        "sync": sync,
        "events": sorted(events, key=lambda e: e["vt"]),
        "generator": {"tool": "touchline-pipeline", "version": __version__, "unplaced_goals": unplaced},
    }
    if shape:
        out["shape"] = shape
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--video", required=True, help="video file name, as the user will load it")
    ap.add_argument("--out", help="output file (default OUT_DIR/touchline-auto.json)")
    args = ap.parse_args()
    d = Path(args.out_dir)
    phases = json.loads((d / "phases.json").read_text())
    shots = json.loads((d / "shots_v2.json").read_text())["shots"] if (d / "shots_v2.json").exists() else []
    shape = json.loads((d / "positional.json").read_text())["summary"] if (d / "positional.json").exists() else None
    auto = build(phases, shots, Path(args.video).name, shape)
    dest = Path(args.out) if args.out else d / "touchline-auto.json"
    dest.write_text(json.dumps(auto, indent=1))
    print(f"{dest}: {len(auto['events'])} events, sync {auto['sync']}")


if __name__ == "__main__":
    main()
