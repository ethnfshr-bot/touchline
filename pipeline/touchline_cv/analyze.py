"""Event detection from a tracks.npz produced by track.py. Fast; rerun freely.

    python -m touchline_cv.analyze OUT_DIR --us "#1b2a4a" --them "#c8102e" --kickoff 145

Writes OUT_DIR/shots.json and prints a summary. v1 detects shots only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from sklearn.cluster import KMeans

PLAYER_HEIGHT_M = 1.75


# ---------- loading ----------

def load(out: Path):
    d = np.load(out / "tracks.npz")
    meta = d["meta"]
    return {
        "fps": float(meta[0]),
        "width": int(meta[1]),
        "height": int(meta[2]),
        "persons": d["persons"],
        "balls": d["balls"],
        "camera": d["camera"],
    }


# ---------- camera ----------

def motion_matrices(camera: np.ndarray) -> dict[int, np.ndarray]:
    """frame -> 3x3 similarity mapping previous sampled frame coords to this frame."""
    out = {}
    for f, _t, a, b, tx, ty, _n in camera:
        out[int(f)] = np.array([[a, -b, tx], [b, a, ty], [0, 0, 1.0]])
    return out


def world_transforms(camera: np.ndarray) -> dict[int, np.ndarray]:
    """frame -> 3x3 mapping this frame's coords to the first frame's ("world") coords.

    Chains inverse frame-to-frame motions, so it drifts slowly; good enough for
    which-side-of-the-pitch questions over a half, not for precise positions.
    """
    T = np.eye(3)
    out = {}
    for f, _t, a, b, tx, ty, _n in camera:
        M = np.array([[a, -b, tx], [b, a, ty], [0, 0, 1.0]])
        T = T @ np.linalg.inv(M)
        out[int(f)] = T.copy()
    return out


def apply(M: np.ndarray, x: float, y: float) -> tuple[float, float]:
    v = M @ np.array([x, y, 1.0])
    return float(v[0]), float(v[1])


# ---------- teams ----------

def hex_to_lab(h: str) -> np.ndarray:
    h = h.lstrip("#")
    rgb = np.array([[[int(h[i : i + 2], 16) for i in (0, 2, 4)]]], np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[0, 0].astype(float)


def assign_teams(persons: np.ndarray, us_hex: str, them_hex: str, k: int = 4):
    """track_id -> 'us' | 'them' | 'other', from clustered shirt colours."""
    tracks, feats, weights = [], [], []
    for tid in np.unique(persons[:, 2]):
        if tid < 0:
            continue
        rows = persons[(persons[:, 2] == tid) & (persons[:, 11] >= 10)]
        if len(rows) < 8:
            continue
        tracks.append(int(tid))
        feats.append(np.median(rows[:, 8:11], axis=0))
        weights.append(len(rows))
    feats = np.array(feats)
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(feats, sample_weight=weights)
    centres = km.cluster_centers_
    sizes = np.bincount(km.labels_, weights=weights, minlength=k)

    # Match the hint colours to the two biggest clusters they're closest to.
    us_lab, them_lab = hex_to_lab(us_hex), hex_to_lab(them_hex)
    big = np.argsort(sizes)[::-1][:3]
    d_us = {c: np.linalg.norm(centres[c] - us_lab) for c in big}
    d_them = {c: np.linalg.norm(centres[c] - them_lab) for c in big}
    us_c = min(big, key=lambda c: d_us[c])
    them_c = min((c for c in big if c != us_c), key=lambda c: d_them[c])

    team = {}
    for tid, lab in zip(tracks, km.labels_):
        team[tid] = "us" if lab == us_c else "them" if lab == them_c else "other"
    info = {"centres_lab": centres.round(1).tolist(), "sizes": sizes.round().tolist(), "us_cluster": int(us_c), "them_cluster": int(them_c)}
    return team, info


# ---------- ball ----------

def ball_track(balls: np.ndarray, persons: np.ndarray, motion: dict, fps: float, min_conf: float = 0.2):
    """Best ball candidate per frame, with camera-compensated speed in rough m/s.

    Returns rows [frame, t, x, y, conf, speed_mps, vx_px, vy_px, m_per_px].
    """
    best = {}
    for f, t, x1, y1, x2, y2, c in balls:
        if c < min_conf:
            continue
        f = int(f)
        if f not in best or c > best[f][4]:
            best[f] = (f, t, (x1 + x2) / 2, (y1 + y2) / 2, c)

    by_frame = {}
    for row in persons:
        by_frame.setdefault(int(row[0]), []).append(row)

    frames = sorted(motion)
    pos = {f: i for i, f in enumerate(frames)}
    out, prev = [], None
    for f in sorted(best):
        _, t, x, y, c = best[f]
        # Scale: median height of the 3 nearest people.
        ppl = by_frame.get(f, [])
        if ppl:
            arr = np.array(ppl)
            cx, foot = (arr[:, 3] + arr[:, 5]) / 2, arr[:, 6]
            near = np.argsort(np.hypot(cx - x, foot - y))[:3]
            h = float(np.median(arr[near, 6] - arr[near, 4]))
            mpp = PLAYER_HEIGHT_M / max(h, 8.0)
        else:
            mpp = np.nan
        speed = vx = vy = np.nan
        if prev is not None and f in pos and prev[0] in pos:
            gap = pos[f] - pos[prev[0]]
            if 1 <= gap <= 3:
                # Bring the previous position into this frame's coordinates.
                px, py = prev[2], prev[3]
                for g in frames[pos[prev[0]] + 1 : pos[f] + 1]:
                    px, py = apply(motion[g], px, py)
                dt = gap / fps
                vx, vy = (x - px) / dt, (y - py) / dt
                speed = float(np.hypot(vx, vy) * mpp)
        out.append([f, t, x, y, c, speed, vx, vy, mpp])
        prev = (f, t, x, y)
    return np.array(out)


# ---------- shots ----------

def attacking_directions(persons, team, world):
    """'us'/'them' -> +1 if they attack towards increasing world x, else -1."""
    xs = {"us": [], "them": []}
    for row in persons[::5]:
        side = team.get(int(row[2]))
        T = world.get(int(row[0]))
        if side in xs and T is not None:
            xs[side].append(apply(T, (row[3] + row[5]) / 2, row[6])[0])
    mu, mt = np.median(xs["us"]), np.median(xs["them"])
    # Each team's players sit, on average, nearer the goal they defend.
    return {"us": 1 if mu < mt else -1, "them": 1 if mt < mu else -1}, {"us_median_x": mu, "them_median_x": mt}


def possessor(f, x, y, by_frame, team, mpp, radius_m=2.5):
    best, bd = None, 1e9
    for row in by_frame.get(f, []):
        side = team.get(int(row[2]))
        if side not in ("us", "them"):
            continue
        d = np.hypot((row[3] + row[5]) / 2 - x, row[6] - y) * mpp
        if d < bd:
            best, bd = (side, int(row[2])), d
    return best if bd <= radius_m else None


def detect_shots(ball, persons, team, directions, world, fps, min_speed=14.0, min_frames=2, cooldown_s=4.0):
    by_frame = {}
    for row in persons:
        by_frame.setdefault(int(row[0]), []).append(row)
    shots, last_t = [], -1e9
    n = len(ball)
    for i in range(1, n):
        f, t, x, y, c, s, vx, vy, mpp = ball[i]
        if not (s >= min_speed) or t - last_t < cooldown_s:
            continue
        # Sustained: the next min_frames-1 detections also fast.
        nxt = ball[i : i + min_frames]
        if len(nxt) < min_frames or not np.all(nxt[:, 5] >= min_speed * 0.7):
            continue
        # Who kicked it: possessor in the preceding ~0.6 s.
        who = None
        for j in range(i - 1, max(-1, i - int(0.6 * fps) - 1), -1):
            who = possessor(int(ball[j, 0]), ball[j, 2], ball[j, 3], by_frame, team, ball[j, 8])
            if who:
                break
        if not who:
            continue
        side = who[0]
        T = world.get(int(f))
        if T is None:
            continue
        # Direction of travel in world coordinates.
        wx0, _ = apply(T, x - vx / fps, y - vy / fps)
        wx1, _ = apply(T, x, y)
        towards = np.sign(wx1 - wx0) == directions[side]
        if not towards:
            continue
        shots.append({"vt": round(float(t), 2), "team": side, "speed_mps": round(float(s), 1), "frame": int(f), "x_px": round(float(x)), "y_px": round(float(y))})
        last_t = t
    return shots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--us", required=True, help="our shirt colour, hex")
    ap.add_argument("--them", required=True, help="opposition shirt colour, hex")
    ap.add_argument("--kickoff", type=float, default=0.0, help="video seconds at kick-off")
    ap.add_argument("--min-speed", type=float, default=14.0)
    args = ap.parse_args()

    out = Path(args.out)
    D = load(out)
    team, tinfo = assign_teams(D["persons"], args.us, args.them)
    motion = motion_matrices(D["camera"])
    world = world_transforms(D["camera"])
    directions, dinfo = attacking_directions(D["persons"], team, world)
    ball = ball_track(D["balls"], D["persons"], motion, D["fps"])
    shots = detect_shots(ball, D["persons"], team, directions, world, D["fps"], min_speed=args.min_speed)
    for s in shots:
        s["match_t"] = round(s["vt"] - args.kickoff, 1)

    counts = {k: sum(1 for s in shots if s["team"] == k) for k in ("us", "them")}
    summary = {
        "teams": {k: sum(1 for v in team.values() if v == k) for k in ("us", "them", "other")},
        "team_clusters": tinfo,
        "directions": directions,
        "direction_info": {k: round(float(v)) for k, v in dinfo.items()},
        "ball_frames": int(len(ball)),
        "ball_coverage": round(len(ball) / max(1, len(D["camera"])), 3),
        "shots": counts,
    }
    (out / "shots.json").write_text(json.dumps({"summary": summary, "shots": shots}, indent=1))
    print(json.dumps(summary, indent=1))
    for s in shots:
        m = s["match_t"]
        print(f"  {s['team']:5s} vt={s['vt']:7.1f}s  match {int(m // 60):02d}:{int(m % 60):02d}  {s['speed_mps']} m/s")


if __name__ == "__main__":
    main()
