"""Team shape and territory from player tracking in pitch coordinates.

Once a second, for each team's visible outfield players (keepers and referees
fall outside the two shirt-colour clusters), in that team's own frame
(attacking towards x = LENGTH):

    height      average distance of the team from its own goal line (m)
    width       spread across the pitch, 10th-90th percentile of y (m)
    depth       spread along the pitch, 10th-90th percentile of x (m)
    area        area of the convex hull around the players (m^2): compactness
    line        distance of the deepest outfield player from their own goal (m):
                how high the defensive line holds

Seconds are labelled by possession (team with a player within POSSESSION_M of
the ball) so shape can be compared in and out of possession. A follow-cam only
shows part of the pitch, so a second is used only when at least MIN_VISIBLE
outfield players of that team are on screen, and coverage is reported
alongside every number.

    python -m touchline_cv.positional OUT_DIR --us ... --them ... --pitch ... --balls ...
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull

from .analyze import assign_teams, load
from .geometry import PitchMapper, camera_motion, on_pitch
from .pitch import LENGTH, WIDTH
from .shots import attacking_dirs, ball_track, player_positions

MIN_VISIBLE = 7
POSSESSION_M = 3.0


def shape(xs: np.ndarray, ys: np.ndarray) -> dict:
    out = {
        "height": float(np.mean(xs)),
        "width": float(np.percentile(ys, 90) - np.percentile(ys, 10)),
        "depth": float(np.percentile(xs, 90) - np.percentile(xs, 10)),
        "line": float(np.min(xs)),
    }
    try:
        out["area"] = float(ConvexHull(np.c_[xs, ys]).volume)
    except Exception:  # collinear or too few points
        out["area"] = float("nan")
    return out


def per_second(players, track, halves, kickoffs, times, fps):
    ball_at = {int(r[0]): (r[2], r[3]) for r in track}
    step = max(1, int(round(fps)))
    frames = sorted(players)
    rows = []
    for f in frames[::step]:
        t = times.get(f)
        if t is None:
            continue
        half = max(0, sum(1 for k in kickoffs if t >= k) - 1)
        dirs = halves[min(half, len(halves) - 1)]
        lst = players[f]
        # Possession: nearest team player to the ball, if close enough.
        poss = None
        b = ball_at.get(f)
        if b is not None and lst:
            best = min(lst, key=lambda p: np.hypot(p[2] - b[0], p[3] - b[1]))
            if np.hypot(best[2] - b[0], best[3] - b[1]) <= POSSESSION_M:
                poss = best[0]
        row = {"t": t, "half": half + 1, "poss": poss}
        if b is not None:
            row["ball_x_us"] = b[0] if dirs["us"] > 0 else LENGTH - b[0]
        for side in ("us", "them"):
            pts = [(p[2], p[3]) for p in lst if p[0] == side]
            if len(pts) < MIN_VISIBLE:
                continue
            xs = np.array([x if dirs[side] > 0 else LENGTH - x for x, _ in pts])
            ys = np.array([y for _, y in pts])
            row[side] = shape(xs, ys)
        rows.append(row)
    return rows


def summarise(rows):
    def agg(side, state=None):
        sel = [r[side] for r in rows if side in r and (state is None or r["poss"] == state)]
        if not sel:
            return None
        keys = ("height", "width", "depth", "area", "line")
        return {k: round(float(np.nanmedian([s[k] for s in sel])), 1) for k in keys} | {"seconds": len(sel)}

    out = {"seconds_analysed": len(rows)}
    for side, other in (("us", "them"), ("them", "us")):
        out[side] = {
            "overall": agg(side),
            "in_possession": agg(side, side),
            "out_of_possession": agg(side, other),
            "coverage": round(sum(1 for r in rows if side in r) / max(1, len(rows)), 3),
        }
    bx = [r["ball_x_us"] for r in rows if "ball_x_us" in r]
    if bx:
        bx = np.array(bx)
        out["territory_us_frame"] = {
            "defensive_third": round(float(np.mean(bx < LENGTH / 3)), 3),
            "middle_third": round(float(np.mean((bx >= LENGTH / 3) & (bx < 2 * LENGTH / 3))), 3),
            "attacking_third": round(float(np.mean(bx >= 2 * LENGTH / 3)), 3),
            "seconds": int(len(bx)),
        }
    poss = [r["poss"] for r in rows if r["poss"]]
    if poss:
        out["possession_share_us"] = round(poss.count("us") / len(poss), 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--us", required=True)
    ap.add_argument("--them", required=True)
    ap.add_argument("--pitch", required=True)
    ap.add_argument("--balls", required=True)
    ap.add_argument("--kickoffs", type=float, nargs="+", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    D = load(out)
    team, _ = assign_teams(D["persons"], args.us, args.them)
    mapper = PitchMapper(Path(args.pitch), camera_motion(Path(args.pitch).parent, D["camera"]), D["fps"])
    players = player_positions(D["persons"], team, mapper)
    times = {int(r[0]): float(r[1]) for r in D["camera"]}
    halves = attacking_dirs(players, times, args.kickoffs)
    track = ball_track(np.load(args.balls)["balls"], mapper, D["fps"])
    rows = per_second(players, track, halves, args.kickoffs, times, D["fps"])
    summary = summarise(rows)
    (out / "positional.json").write_text(json.dumps({"summary": summary, "per_second": rows}, default=float))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
