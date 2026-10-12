"""Shot detection in pitch coordinates (v2).

A shot is: the ball leaves a player's feet fast (>= MIN_SPEED m/s, sustained),
from within SHOT_RANGE metres of the goal that player's team is attacking,
on a path that would cross that goal line within GOAL_MOUTH_SLACK metres of
the goal centre (on target, or a near miss).

    python -m touchline_cv.shots OUT_DIR --pitch PITCH_NPZ --balls BALLS_NPZ \
        --us "#1b2a4a" --them "#c8102e" --kickoffs 145 [3200]

Writes OUT_DIR/shots_v2.json with shots in video time and Touchline's
0-100 pitch frame (acting team attacking towards x = 100).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .analyze import assign_teams, load
from .geometry import PitchMapper, camera_motion, on_pitch
from .pitch import LENGTH, WIDTH

MIN_CONF = 0.15
MIN_SPEED = 12.0  # m/s at the kick
SUSTAIN_SPEED = 8.0  # m/s on the next detection
MAX_SPEED = 45.0  # anything faster is two different detections
KICK_RADIUS = 2.5  # m from the kicker's feet
KICK_LOOKBACK_S = 0.8
SHOT_RANGE = 35.0  # m from goal centre
GOAL_MOUTH_SLACK = 12.0  # m either side of goal centre where the path crosses the line
COOLDOWN_S = 3.0


def player_positions(persons, team, mapper):
    """frame -> list of (side, track_id, px, py) in pitch metres."""
    out = {}
    for row in persons:
        side = team.get(int(row[2]))
        if side not in ("us", "them"):
            continue
        f = int(row[0])
        p = mapper.to_pitch(f, (row[3] + row[5]) / 2, row[6])
        if on_pitch(p):
            out.setdefault(f, []).append((side, int(row[2]), p[0], p[1]))
    return out


def attacking_dirs(players, times, kickoffs):
    """Per half: 'us'/'them' -> +1 if attacking towards x = LENGTH, else -1."""
    bounds = list(kickoffs) + [1e12]
    halves = []
    for h in range(len(kickoffs)):
        xs = {"us": [], "them": []}
        for f, lst in players.items():
            if bounds[h] <= times[f] < bounds[h + 1]:
                for side, _tid, px, _py in lst:
                    xs[side].append(px)
        mu, mt = np.median(xs["us"]) if xs["us"] else 60, np.median(xs["them"]) if xs["them"] else 60
        halves.append({"us": 1 if mu < mt else -1, "them": 1 if mt < mu else -1, "us_x": round(float(mu), 1), "them_x": round(float(mt), 1)})
    return halves


def ball_track(balls, mapper, fps):
    """Best on-pitch ball per frame, preferring continuity. Rows [frame, t, px, py, conf]."""
    by_frame = {}
    for f, t, x1, y1, x2, y2, c in balls:
        if c < MIN_CONF:
            continue
        p = mapper.to_pitch(int(f), (x1 + x2) / 2, (y1 + y2) / 2)
        if on_pitch(p, margin=1.0):
            by_frame.setdefault(int(f), []).append((t, p[0], p[1], c))
    track, last = [], None
    for f in sorted(by_frame):
        cands = by_frame[f]
        pick = max(cands, key=lambda r: r[3])
        if last is not None:
            dt = (f - last[0]) / (fps * 2)  # sampled every 2 source frames at 15 fps
            gate = MAX_SPEED * max(dt, 1 / fps) + 2.0
            near = [r for r in cands if np.hypot(r[1] - last[2], r[2] - last[3]) <= gate]
            if near:
                pick = max(near, key=lambda r: r[3])
        track.append([f, pick[0], pick[1], pick[2], pick[3]])
        last = (f, pick[0], pick[1], pick[2])
    return np.array(track).reshape(-1, 5)


def detect(track, players, halves, kickoffs, fps):
    shots, last_t = [], -1e9
    for i in range(1, len(track) - 1):
        f0, t0, x0, y0, _ = track[i - 1]
        f1, t1, x1, y1, _ = track[i]
        dt = t1 - t0
        if dt <= 0 or dt > 3.5 / fps or t1 - last_t < COOLDOWN_S:
            continue
        vx, vy = (x1 - x0) / dt, (y1 - y0) / dt
        speed = float(np.hypot(vx, vy))
        if not (MIN_SPEED <= speed <= MAX_SPEED):
            continue
        f2, t2, x2, y2, _ = track[i + 1]
        dt2 = t2 - t1
        if 0 < dt2 <= 3.5 / fps:
            s2 = np.hypot(x2 - x1, y2 - y1) / dt2
            if s2 < SUSTAIN_SPEED or s2 > MAX_SPEED:
                continue
        elif speed < MIN_SPEED * 1.3:
            continue
        # Kicker: nearest outfield player to the ball just before it took off.
        kicker = None
        for j in range(i - 1, -1, -1):
            if track[i - 1, 1] - track[j, 1] > KICK_LOOKBACK_S:
                break
            fj, _, bx, by, _ = track[j]
            best = min(players.get(int(fj), []), key=lambda p: np.hypot(p[2] - bx, p[3] - by), default=None)
            if best and np.hypot(best[2] - bx, best[3] - by) <= KICK_RADIUS:
                kicker = best
                break
        if not kicker:
            continue
        side = kicker[0]
        half = max(0, sum(1 for k in kickoffs if t0 >= k) - 1)
        d = halves[min(half, len(halves) - 1)][side]
        gx = LENGTH if d > 0 else 0.0
        if np.hypot(gx - x0, WIDTH / 2 - y0) > SHOT_RANGE:
            continue
        if np.sign(vx) != np.sign(gx - x0) or abs(vx) < 1e-6:
            continue
        y_cross = y0 + vy * (gx - x0) / vx
        if abs(y_cross - WIDTH / 2) > GOAL_MOUTH_SLACK:
            continue
        # Touchline frame: acting team attacks towards x = 100.
        tx, ty = (x0 / LENGTH * 100, y0 / WIDTH * 100) if d > 0 else ((LENGTH - x0) / LENGTH * 100, (WIDTH - y0) / WIDTH * 100)
        shots.append({
            "vt": round(float(t0), 2), "team": side, "track_id": kicker[1], "speed_mps": round(speed, 1),
            "x": round(float(tx), 1), "y": round(float(ty), 1), "dist_m": round(float(np.hypot(gx - x0, WIDTH / 2 - y0)), 1),
            "y_cross_m": round(float(y_cross - WIDTH / 2), 1),
        })
        last_t = t1
    return shots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--pitch", required=True)
    ap.add_argument("--balls", required=True)
    ap.add_argument("--us", required=True)
    ap.add_argument("--them", required=True)
    ap.add_argument("--kickoffs", type=float, nargs="+", required=True, help="video seconds of each half's kick-off")
    args = ap.parse_args()

    out = Path(args.out)
    D = load(out)
    team, _ = assign_teams(D["persons"], args.us, args.them)
    motion = camera_motion(Path(args.pitch).parent, D["camera"])
    mapper = PitchMapper(Path(args.pitch), motion, D["fps"])
    players = player_positions(D["persons"], team, mapper)
    times = {int(r[0]): float(r[1]) for r in D["camera"]}
    halves = attacking_dirs(players, times, args.kickoffs)
    balls = np.load(args.balls)["balls"]
    track = ball_track(balls, mapper, D["fps"])
    shots = detect(track, players, halves, args.kickoffs, D["fps"])
    mapped = sum(1 for f in times if mapper.homography(f) is not None)
    summary = {
        "frames_with_pitch_mapping": round(mapped / max(1, len(times)), 3),
        "ball_frames_on_pitch": int(len(track)),
        "ball_coverage": round(len(track) / max(1, len(times)), 3),
        "halves": halves,
        "shots": {k: sum(1 for s in shots if s["team"] == k) for k in ("us", "them")},
    }
    (out / "shots_v2.json").write_text(json.dumps({"summary": summary, "shots": shots}, indent=1))
    print(json.dumps(summary, indent=1))
    k0 = args.kickoffs[0]
    for s in shots:
        m = s["vt"] - k0
        print(f"  {s['team']:5s} vt={s['vt']:7.1f}  match {int(m // 60):02d}:{int(m % 60):02d}  {s['speed_mps']:5.1f} m/s  {s['dist_m']:5.1f} m out  crosses {s['y_cross_m']:+5.1f} m")


if __name__ == "__main__":
    main()
