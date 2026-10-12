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


def find_kickoffs(sec, min_sep=0.6, still=0.3, moving=0.6, hold_s=4):
    # Thresholds from Leeming v La Fammia: before the 2:25 kick-off, stillness
    # ~0.2 then 0.6-1.1 within two seconds. Team separation on screen is only
    # 0.64-0.75 over the full match because benches and spectators in similar
    # colours dilute it, so the separation bar is low and other checks
    # (centre markings in view, timing relative to the breaks) do the filtering.
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


CALM_ACTIVITY = 0.36  # 2-minute median below this: a break, not play
CALM_WINDOW_S = 120
MIN_BREAK_RUN_S = 240


def calm_mask(sec):
    """Boolean per second: inside a spell of low movement (2-minute rolling median).

    In Leeming v La Fammia, play runs at 0.4-0.6 per-minute median movement and
    half-time at 0.24-0.33; short stoppages don't survive a 2-minute median.
    """
    act = np.nan_to_num(sec[:, 4], nan=0.0)
    w = CALM_WINDOW_S
    pad = np.pad(act, w // 2, mode="edge")
    med = np.array([np.median(pad[i : i + w]) for i in range(len(act))])
    return med < CALM_ACTIVITY


def breaks(times, calm, min_len=MIN_BREAK_RUN_S):
    """(start, end) of calm spells at least min_len seconds long."""
    out, start = [], None
    for t, c in zip(times, calm):
        if c and start is None:
            start = t
        elif not c and start is not None:
            if t - start >= min_len:
                out.append((float(start), float(t)))
            start = None
    if start is not None and times[-1] - start >= min_len:
        out.append((float(start), float(times[-1])))
    return out


GOAL_MIN_PAUSE_S = 30


def pre_kickoff_pause(sec, t, quiet=0.35):
    """Seconds of low movement (10-second rolling median) just before a kick-off.

    Leeming v La Fammia: the two half kick-offs followed pauses of 105 s and
    53 s; set-piece false alarms and doubtful candidates 0-29 s.
    """
    times = sec[:, 0]
    act = np.nan_to_num(sec[:, 4])
    i = int(np.searchsorted(times, t))
    j = i
    while j > 10 and np.median(act[j - 10 : j]) < quiet:
        j -= 1
    return float(times[min(i, len(times) - 1)] - times[j])


def centre_in_view(frame, keypoints, window_frames=90, min_points=2):
    """True if the pitch model saw centre markings (halfway line / centre circle)
    near this frame; None if no keypoint data. These markings are read reliably."""
    if keypoints is None:
        return None
    near = keypoints[np.abs(keypoints[:, 0] - frame) <= window_frames]
    centre = np.isin(near[:, 2].astype(int), [13, 14, 15, 16, 30, 31])
    if not len(near):
        return False
    return bool(centre.sum() >= min_points)


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


def phases(sec, kicks, persons, team, mapper=None, balls=None, keypoints=None):
    times = sec[:, 0]
    end = float(times[-1])
    calm = calm_mask(sec)
    # A calm spell running to the end of the video counts even if short: the
    # recording usually stops a minute or two after the final whistle.
    brks = breaks(times, calm)
    tail = breaks(times, calm, min_len=45)
    if tail and tail[-1][1] >= end - 1 and tail[-1] not in brks:
        brks.append(tail[-1])

    # centre_in_view() proved unreliable as a filter on Leeming v La Fammia (it
    # rejected the real second-half kick-off), so kick-offs are judged by timing.
    valid, rejected = list(kicks), []
    if not valid:
        return {"error": "no kick-offs found"}

    k1 = valid[0][0]
    result = {"k1": k1}
    after1 = [b for b in brks if b[0] > k1 + MIN_HALF_S]
    k2 = None
    if after1:
        ht = max(after1, key=lambda b: b[1] - b[0])
        if ht[1] < end - 1:  # a break before the end of the video, not the end itself
            result["ht"] = ht[0]
            later = [t for t, _ in valid if t >= ht[0]]
            if later:
                k2 = later[0]
                result["k2"] = k2
    start2 = k2 if k2 is not None else k1
    after2 = [b for b in brks if b[0] > start2 + MIN_HALF_S]
    result["ft"] = after2[0][0] if after2 else end
    result["breaks"] = [[round(a, 1), round(b, 1)] for a, b in brks]

    halves = [(k1, result.get("ht", result["ft"]))]
    if k2 is not None:
        halves.append((k2, result["ft"]))
    goals, possible = [], []
    for t, f in valid:
        if t in (k1, k2):
            continue
        if not any(a < t < b - 30 for a, b in halves):
            rejected.append({"t": t, "reason": "outside play (break or after full time)"})
            continue
        # After a goal there's a celebration and a walk back before the restart;
        # set pieces restart within seconds. Below the bar: listed, not counted.
        pause = pre_kickoff_pause(sec, t)
        if pause < GOAL_MIN_PAUSE_S:
            possible.append({"t": t, "pause_s": round(pause), "scored_by": {"us": "them", "them": "us"}.get(kicker_side(f, persons, team, balls))})
            continue
        spot = ball_on_spot(f, balls, mapper)
        if spot is False:
            rejected.append({"t": t, "reason": "ball not on centre spot"})
            continue
        side = kicker_side(f, persons, team, balls)
        goals.append({"t": t, "scored_by": {"us": "them", "them": "us"}.get(side), "ball_on_spot": spot})
    result["goals"] = goals
    result["possible_goals"] = possible
    result["rejected_kickoffs"] = rejected
    result["all_kickoffs"] = [k[0] for k in kicks]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--us", required=True)
    ap.add_argument("--them", required=True)
    ap.add_argument("--pitch", help="pitch.npz: its keypoints confirm the centre is in view at a kick-off")
    ap.add_argument("--calibrated", action="store_true", help="also trust pitch.npz homographies (centre-spot ball check)")
    ap.add_argument("--balls", help="balls.npz for the conceding-team check")
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
    keypoints = None
    if args.pitch and Path(args.pitch).exists():
        keypoints = np.load(args.pitch)["keypoints"]
        if args.calibrated:
            from .geometry import PitchMapper, camera_motion

            mapper = PitchMapper(Path(args.pitch), camera_motion(Path(args.pitch).parent, D["camera"]), D["fps"])
    if args.balls and Path(args.balls).exists():
        balls = np.load(args.balls)["balls"]
    result = phases(sec, kicks, D["persons"], team, mapper, balls, keypoints)
    (out / "phases.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
