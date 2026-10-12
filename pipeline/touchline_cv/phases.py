"""Match phases from player tracking: kick-offs, half-time, full-time, goals.

Kick-offs are the anchor. Before a kick-off both teams stand still, each
entirely in its own half; then everyone moves at once. Apart from the first
kick-off of each half, every kick-off is a restart after a goal, conceded by
the team kicking off.

    python -m touchline_cv.phases OUT_DIR --us "#1b2a4a" --them "#c8102e"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.svm import LinearSVC

from .analyze import apply, assign_teams, load, motion_matrices


def per_second(persons, team, motion, fps):
    """One row per second: [t, separation, n_us, n_them, activity, kicker_side_hint].

    separation  how cleanly a straight line splits the two teams on screen (0.5-1)
    activity    median camera-compensated player speed, in player-heights/second
    """
    frames = sorted(motion)
    idx = {f: i for i, f in enumerate(frames)}
    by_frame = {}
    for row in persons:
        side = team.get(int(row[2]))
        if side in ("us", "them"):
            by_frame.setdefault(int(row[0]), []).append((row, side))

    prev_pos = {}
    speeds = {}  # frame -> list of speeds
    for f in frames:
        M = motion[f]
        cur = {}
        sp = []
        for row, _side in by_frame.get(f, []):
            tid = int(row[2])
            x, y, h = (row[3] + row[5]) / 2, row[6], max(row[6] - row[4], 8.0)
            cur[tid] = (x, y, h)
            if tid in prev_pos:
                px, py = apply(M, prev_pos[tid][0], prev_pos[tid][1])
                sp.append(np.hypot(x - px, y - py) * fps / h)
        speeds[f] = sp
        prev_pos = cur

    step = max(1, int(round(fps)))
    rows = []
    for i in range(0, len(frames), step):
        f = frames[i]
        items = by_frame.get(f, [])
        t = items[0][0][1] if items else f / fps
        sides = np.array([s == "us" for _, s in items])
        n_us, n_them = int(sides.sum()), int((~sides).sum())
        sep = 0.5
        if n_us >= 6 and n_them >= 6:
            X = np.array([[(r[3] + r[5]) / 2, r[6]] for r, _ in items]) / 1000.0
            clf = LinearSVC(C=10.0, dual=False).fit(X, sides)
            sep = float((clf.predict(X) == sides).mean())
        window = [s for g in frames[i : i + step] for s in speeds.get(g, [])]
        act = float(np.median(window)) if window else np.nan
        rows.append([t, sep, n_us, n_them, act])
    return np.array(rows)


def find_kickoffs(sec, min_sep=0.75, still=0.3, moving=0.6, hold_s=4):
    # Thresholds tuned on the first kick-off of Leeming v La Fammia (2:25):
    # stillness ~0.2, then 0.6-1.1 within two seconds; separation 0.78-0.87
    # because bench and spectators in similar colours dilute it.
    """Kick-off = end of a >= hold_s spell of clean separation and stillness,
    followed within 5 s by general movement."""
    kicks = []
    n = len(sec)
    i = 0
    while i < n:
        j = i
        while j < n and sec[j, 1] >= min_sep and sec[j, 4] <= still and sec[j, 2] >= 6 and sec[j, 3] >= 6:
            j += 1
        if j - i >= hold_s:
            after = sec[j : j + 5, 4]
            if len(after) and np.nanmax(after) >= moving:
                kicks.append(float(sec[j - 1, 0]))
                i = j + 30  # no two kick-offs within 30 s
                continue
        i = max(j, i + 1)
    return kicks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--us", required=True)
    ap.add_argument("--them", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    D = load(out)
    team, _ = assign_teams(D["persons"], args.us, args.them)
    motion = motion_matrices(D["camera"])
    sec = per_second(D["persons"], team, motion, D["fps"])
    np.save(out / "per_second.npy", sec)
    kicks = find_kickoffs(sec)
    result = {"kickoffs_video_seconds": kicks}
    (out / "phases.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
