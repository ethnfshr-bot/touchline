"""Match phases from player tracking: kick-offs, half-time, full-time, goals.

Kick-offs are the anchor. Before a kick-off both teams stand still, each in
its own half; then everyone moves at once. The first kick-off of each half
starts that half; every other kick-off is a restart after a goal, conceded by
the team kicking off. Half-time is the longest spell without play.

The conceding team (the one kicking off) is found on screen: the team of the
player nearest the ball. With a reliable pitch calibration (--pitch), goal
restarts must also have the ball on the centre spot. Follow-cam calibration
isn't reliable yet, so the video tool doesn't pass --pitch for now.

    python -m touchline_cv.phases OUT_DIR --us "#1b2a4a" --them "#c8102e" \
        [--pitch OUT_DIR/pitch.npz --balls OUT_DIR/balls.npz]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.svm import LinearSVC

from .analyze import apply, assign_teams, load, motion_matrices

PLAY_ACTIVITY = 0.45  # player-heights/second: above this, play is (probably) on
MIN_BREAK_S = 300  # half-time lasts at least 5 minutes
MIN_HALF_S = 15 * 60
CENTRE_SPOT_RADIUS_M = 4.0


def per_second(persons, team, motion, fps):
    """One row per second: [t, separation, n_us, n_them, activity, frame].

    separation  how cleanly a straight line splits the two teams on screen (0.5-1)
    activity    median camera-compensated player speed, in player-heights/second
    """
    frames = sorted(motion)
    by_frame = {}
    for row in persons:
        side = team.get(int(row[2]))
        if side in ("us", "them"):
            by_frame.setdefault(int(row[0]), []).append((row, side))

    prev_pos, speeds = {}, {}
    for f in frames:
        M = motion[f]
        cur, sp = {}, []
        for row, _side in by_frame.get(f, []):
            tid = int(row[2])
            x, y, h = (row[3] + row[5]) / 2, row[6], max(row[6] - row[4], 8.0)
            cur[tid] = (x, y)
            if tid in prev_pos:
                px, py = apply(M, *prev_pos[tid])
                sp.append(np.hypot(x - px, y - py) * fps / h)
        speeds[f] = sp
        prev_pos = cur

    step = max(1, int(round(fps)))
    rows = []
    for i in range(0, len(frames), step):
        f = frames[i]
        items = by_frame.get(f, [])
        t = items[0][0][1] if items else f / (fps * 2)
        sides = np.array([s == "us" for _, s in items], dtype=bool)
        n_us, n_them = int(sides.sum()), int((~sides).sum())
        sep = 0.5
        if n_us >= 6 and n_them >= 6:
            X = np.array([[(r[3] + r[5]) / 2, r[6]] for r, _ in items]) / 1000.0
            clf = LinearSVC(C=10.0, dual=False).fit(X, sides)
            sep = float((clf.predict(X) == sides).mean())
        window = [s for g in frames[i : i + step] for s in speeds.get(g, [])]
        act = float(np.median(window)) if window else np.nan
        rows.append([t, sep, n_us, n_them, act, f])
    return np.array(rows)


def find_kickoffs(sec, min_sep=0.75, still=0.3, moving=0.6, hold_s=4):
    # Thresholds tuned on the first kick-off of Leeming v La Fammia (2:25):
    # stillness ~0.2, then 0.6-1.1 within two seconds; separation 0.78-0.87
    # because bench and spectators in similar colours dilute it.
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
                kicks.append((float(sec[j - 1, 0]), int(sec[j - 1, 5])))
                i = j + 30  # no two kick-offs within 30 s
                continue
        i = max(j, i + 1)
    return kicks


def play_mask(sec, window=15):
    """Boolean per second: play is on (rolling median activity, both teams present)."""
    act = np.nan_to_num(sec[:, 4], nan=0.0)
    pad = np.pad(act, window // 2, mode="edge")
    med = np.array([np.median(pad[i : i + window]) for i in range(len(act))])
    return (med >= PLAY_ACTIVITY) & (sec[:, 2] >= 4) & (sec[:, 3] >= 4)


def longest_gap(times, mask, lo, hi):
    """Longest run of no-play seconds within [lo, hi): (start_t, end_t)."""
    best, start = (None, None), None
    for t, on in zip(times, mask):
        if t < lo or t >= hi:
            continue
        if not on and start is None:
            start = t
        elif on and start is not None:
            if best[0] is None or t - start > best[1] - best[0]:
                best = (start, t)
            start = None
    return best


def kicker_side(frame, persons, team, balls, window=8):
    """Team kicking off: the team of the player nearest the ball on screen, just
    before the kick-off. Works without pitch calibration.

    The ball is taken as the detection nearest the midpoint between the two
    teams' centroids (the centre spot sits between them), which ignores spare
    balls beside the pitch. Distances are in player-heights. Returns None if unclear.
    """
    if balls is None:
        return None
    votes = {"us": 0, "them": 0}
    for f in range(frame - window * 2, frame + 1, 2):
        rows = [r for r in persons[persons[:, 0] == f] if team.get(int(r[2])) in ("us", "them")]
        cand = balls[(balls[:, 0] == f) & (balls[:, 6] >= 0.15)]
        if len(rows) < 8 or not len(cand):
            continue
        feet = np.array([((r[3] + r[5]) / 2, r[6]) for r in rows])
        sides = [team[int(r[2])] for r in rows]
        mid = np.mean([feet[[s == side for s in sides]].mean(axis=0) for side in ("us", "them") if side in sides], axis=0)
        bc = np.c_[(cand[:, 2] + cand[:, 4]) / 2, (cand[:, 3] + cand[:, 5]) / 2]
        ball = bc[np.argmin(np.hypot(*(bc - mid).T))]
        heights = np.array([r[6] - r[4] for r in rows])
        d = np.hypot(*(feet - ball).T) / np.maximum(heights, 8)
        i = int(np.argmin(d))
        if d[i] <= 1.5:
            votes[sides[i]] += 1
    if votes["us"] == votes["them"]:
        return None
    return max(votes, key=votes.get)


def ball_on_spot(frame, balls, mapper, fps_frames=30):
    """True/False if the ball was seen near the centre spot around this frame; None if unknown."""
    if mapper is None or balls is None:
        return None
    from .pitch import LENGTH, WIDTH

    near = balls[(np.abs(balls[:, 0] - frame) <= fps_frames) & (balls[:, 6] >= 0.15)]
    seen = False
    for f, _t, x1, y1, x2, y2, _c in near:
        p = mapper.to_pitch(int(f), (x1 + x2) / 2, (y1 + y2) / 2)
        if p is None:
            continue
        seen = True
        if np.hypot(p[0] - LENGTH / 2, p[1] - WIDTH / 2) <= CENTRE_SPOT_RADIUS_M:
            return True
    return False if seen else None


def phases(sec, kicks, persons, team, mapper=None, balls=None):
    times = sec[:, 0]
    mask = play_mask(sec)
    if not kicks:
        return {"error": "no kick-offs found"}
    k1, f1 = kicks[0]
    end = float(times[-1])
    gap = longest_gap(times, mask, k1 + MIN_HALF_S, end)
    result = {"k1": k1}
    k2 = None
    if gap[0] is not None and gap[1] - gap[0] >= MIN_BREAK_S:
        result["ht"] = gap[0]
        after = [k for k in kicks if k[0] >= gap[1] - 60]
        if after:
            k2 = after[0]
            result["k2"] = k2[0]
    # Full time: last play second after the second half starts (or after k1).
    start2 = k2[0] if k2 else k1
    on = [t for t, m in zip(times, mask) if m and t > start2]
    if on:
        result["ft"] = float(on[-1])
    halves = [(k1, result.get("ht", result.get("ft", end)))]
    if k2:
        halves.append((k2[0], result.get("ft", end)))
    goals, rejected = [], []
    for t, f in kicks:
        if t == k1 or (k2 and t == k2[0]):
            continue
        if not any(a < t < b for a, b in halves):
            continue
        spot = ball_on_spot(f, balls, mapper)
        if spot is False:
            rejected.append({"t": t, "reason": "ball not on centre spot"})
            continue
        side = kicker_side(f, persons, team, balls)
        goals.append({"t": t, "scored_by": {"us": "them", "them": "us"}.get(side), "ball_on_spot": spot})
    result["goals"] = goals
    result["rejected_kickoffs"] = rejected
    result["all_kickoffs"] = [k[0] for k in kicks]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--us", required=True)
    ap.add_argument("--them", required=True)
    ap.add_argument("--pitch", help="pitch.npz for centre-spot checks")
    ap.add_argument("--balls", help="balls.npz for centre-spot checks")
    args = ap.parse_args()

    out = Path(args.out)
    D = load(out)
    team, _ = assign_teams(D["persons"], args.us, args.them)
    motion = motion_matrices(D["camera"])
    sec = per_second(D["persons"], team, motion, D["fps"])
    np.save(out / "per_second.npy", sec)
    kicks = find_kickoffs(sec)
    mapper = None
    # Ball detections: the dedicated ball pass if given, else the tracking pass's own.
    balls = D["balls"]
    if args.pitch:
        from .geometry import PitchMapper, camera_motion

        mapper = PitchMapper(Path(args.pitch), camera_motion(Path(args.pitch).parent, D["camera"]), D["fps"])
    if args.balls:
        balls = np.load(args.balls)["balls"]
    result = phases(sec, kicks, D["persons"], team, mapper, balls)
    (out / "phases.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
