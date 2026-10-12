"""Rotating-camera model for Veo follow-cam video, solved over the whole match.

A Veo follow-cam frame is a virtual pinhole view from a fixed point: only its
rotation R and focal length f change. A pixel u maps to a ray in the fixed
"rig" frame:   r = R^T K^-1 u,   K = [[f,0,cx],[0,f,cy],[0,0,1]].
The pitch is a plane, so rays map to pitch metres by ONE homography G for the
whole match. That turns calibration into: (1) solve R, f for keyframes by
bundle adjustment of feature matches (sequential + long-range loop closures,
so errors don't accumulate), (2) fit G from all pitch keypoints of the match
with RANSAC.

    python -m touchline_cv.rig VIDEO OUT_DIR [--every 2] [--from 100 --to 6500]
Output: OUT_DIR/rig.npz with keyframes [frame, t, rx, ry, rz, f] and G (3x3).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.spatial.transform import Rotation

W_SMALL = 960
PTS_PER_PAIR = 40


def features(video, times, persons_by_frame, scale):
    sift = cv2.SIFT_create(nfeatures=1500)
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    out = []
    for t in times:
        f = int(round(t * fps / 30)) * 30  # pitch samples sit on multiples of 30 frames
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, frame = cap.read()
        if not ok:
            out.append((f, t, None, None))
            continue
        g = cv2.cvtColor(cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        mask = np.full(g.shape, 255, np.uint8)
        for x1, y1, x2, y2 in persons_by_frame.get(f, []):
            mask[max(0, int(y1 * scale) - 3) : int(y2 * scale) + 3, max(0, int(x1 * scale) - 3) : int(x2 * scale) + 3] = 0
        kp, des = sift.detectAndCompute(g, mask)
        pts = np.array([k.pt for k in kp], np.float32) / scale if kp else None
        out.append((f, t, pts, des))
    return out


def match(a, b, flann, min_inliers=30):
    if a[3] is None or b[3] is None or len(a[3]) < 20 or len(b[3]) < 20:
        return None
    m = flann.knnMatch(a[3], b[3], k=2)
    good = [p[0] for p in m if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(good) < min_inliers:
        return None
    pa = a[2][[g.queryIdx for g in good]]
    pb = b[2][[g.trainIdx for g in good]]
    H, mask = cv2.findHomography(pa, pb, cv2.RANSAC, 3.0)
    if H is None or mask.sum() < min_inliers:
        return None
    inl = mask.ravel().astype(bool)
    return H, pa[inl], pb[inl]


def K(f, cx, cy):
    return np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])


def init_from_chain(n, pair_H, cx, cy, f0):
    """Initial rotations by chaining sequential pairwise homographies."""
    R = [np.eye(3)]
    for i in range(1, n):
        H = pair_H.get((i - 1, i))
        if H is None:
            R.append(R[-1].copy())
            continue
        Ka = Kb = K(f0, cx, cy)
        Rab = np.linalg.inv(Kb) @ H @ Ka
        U, _, Vt = np.linalg.svd(Rab)
        Rab = U @ Vt
        if np.linalg.det(Rab) < 0:
            Rab = -Rab
        R.append(Rab @ R[-1])  # R_b = R_ab R_a
    return R


def project(params, n, cx, cy, ia, ib, ua):
    rv = params[: 3 * n].reshape(n, 3)
    f = np.exp(params[3 * n :])
    Ra = Rotation.from_rotvec(rv[ia]).as_matrix()
    Rb = Rotation.from_rotvec(rv[ib]).as_matrix()
    x = np.c_[(ua[:, 0] - cx) / f[ia], (ua[:, 1] - cy) / f[ia], np.ones(len(ua))]
    ray = np.einsum("nji,nj->ni", Ra, x)  # R_a^T x
    cam = np.einsum("nij,nj->ni", Rb, ray)  # R_b ray
    return np.c_[f[ib] * cam[:, 0] / cam[:, 2] + cx, f[ib] * cam[:, 1] / cam[:, 2] + cy]


def solve(n, pairs, R0, f0, cx, cy, max_nfev=60):
    ia = np.concatenate([np.full(len(p[2]), p[0]) for p in pairs])
    ib = np.concatenate([np.full(len(p[2]), p[1]) for p in pairs])
    ua = np.vstack([p[2] for p in pairs])
    ub = np.vstack([p[3] for p in pairs])
    x0 = np.r_[np.vstack([Rotation.from_matrix(r).as_rotvec() for r in R0]).ravel(), np.full(n, np.log(f0))]

    def resid(p):
        return (project(p, n, cx, cy, ia, ib, ua) - ub).ravel()

    m = len(ua)
    S = lil_matrix((2 * m, 4 * n), dtype=np.int8)
    rows = np.arange(m)
    for cam_idx in (ia, ib):
        for k in range(3):
            S[2 * rows, 3 * cam_idx + k] = 1
            S[2 * rows + 1, 3 * cam_idx + k] = 1
        S[2 * rows, 3 * n + cam_idx] = 1
        S[2 * rows + 1, 3 * n + cam_idx] = 1
    r0 = np.abs(resid(x0))
    sol = least_squares(resid, x0, jac_sparsity=S, loss="huber", f_scale=3.0, x_scale="jac", max_nfev=max_nfev, verbose=0)
    r1 = np.abs(sol.fun)
    return sol.x, float(np.median(r0)), float(np.median(r1))


def forward_vectors(params, n):
    rv = params[: 3 * n].reshape(n, 3)
    return np.array([Rotation.from_rotvec(r).as_matrix().T @ [0, 0, 1.0] for r in rv])


def loop_candidates(params, n, max_angle_deg=25.0, min_gap=8, per_frame=4, rng=None):
    """Pairs of keyframes far apart in time but facing the same way (per the current solution)."""
    fwd = forward_vectors(params, n)
    cosmax = np.cos(np.radians(max_angle_deg))
    out = []
    for i in range(n):
        d = fwd @ fwd[i]
        cand = [j for j in np.where(d >= cosmax)[0] if j < i - min_gap]
        if not cand:
            continue
        if len(cand) > per_frame:
            # Spread choices across time so loops tie distant parts of the match together.
            cand = [cand[k] for k in np.linspace(0, len(cand) - 1, per_frame).astype(int)]
        out.extend((int(j), i) for j in cand)
    return out


def predicted_error(params, n, cx, cy, i, j, pa, pb):
    """Median pixel error of matched points under the current solution."""
    p = project(params, n, cx, cy, np.full(len(pa), i), np.full(len(pa), j), pa)
    return float(np.median(np.hypot(*(p - pb).T)))


def rays(params, n, cx, cy, idx, u):
    rv = params[: 3 * n].reshape(n, 3)
    f = np.exp(params[3 * n :])
    R = Rotation.from_rotvec(rv[idx]).as_matrix()
    x = np.c_[(u[:, 0] - cx) / f[idx], (u[:, 1] - cy) / f[idx], np.ones(len(u))]
    r = np.einsum("nji,nj->ni", R, x)
    return r[:, :2] / r[:, 2:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--every", type=float, default=2.0)
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=1e9)
    ap.add_argument("--loop-every", type=int, default=30, help="keyframes between loop-closure landmarks (0 = none)")
    ap.add_argument("--max-nfev", type=int, default=200)
    ap.add_argument("--loop-tolerance", type=float, default=60.0, help="max median px error for a loop closure to be trusted")
    args = ap.parse_args()
    out = Path(args.out)
    t_start = time.time()

    cap = cv2.VideoCapture(args.video)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    cx, cy = width / 2, height / 2
    times = np.arange(max(0.0, args.t0), min(dur - 1, args.t1), args.every)

    persons_by_frame = {}
    tr = out / "tracks.npz"
    if tr.exists():
        for row in np.load(tr)["persons"]:
            persons_by_frame.setdefault(int(row[0]), []).append(row[3:7])
    feats = features(args.video, times, persons_by_frame, W_SMALL / width)
    n = len(feats)
    print(f"features: {n} keyframes in {time.time() - t_start:.0f}s", flush=True)

    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=40))
    rng = np.random.default_rng(0)
    pairs, pair_H = [], {}

    def add(i, j):
        r = match(feats[i], feats[j], flann)
        if r is None:
            return False
        H, pa, pb = r
        if len(pa) > PTS_PER_PAIR:
            sel = rng.choice(len(pa), PTS_PER_PAIR, replace=False)
            pa, pb = pa[sel], pb[sel]
        pairs.append((i, j, pa, pb))
        pair_H[(i, j)] = H
        return True

    for i in range(1, n):
        for d in (1, 2, 3):
            if i - d >= 0:
                add(i - d, i)
    seq = len(pairs)
    print(f"pairs: {seq} sequential, {time.time() - t_start:.0f}s", flush=True)

    f0 = width / (2 * np.tan(np.radians(60) / 2))  # ~60 degree horizontal field of view to start
    R0 = init_from_chain(n, pair_H, cx, cy, f0)
    params, before, after = solve(n, pairs, R0, f0, cx, cy, args.max_nfev)
    print(f"sequential solve: median residual {before:.1f}px -> {after:.2f}px, {time.time() - t_start:.0f}s", flush=True)

    # Loop closures: only between keyframes facing the same way, and only if the
    # matches agree with the sequential solution (false matches are far off).
    loops = rejected = 0
    if args.loop_every > 0:
        for j, i in loop_candidates(params, n, per_frame=max(1, 60 // args.loop_every), rng=rng):
            r = match(feats[j], feats[i], flann)
            if r is None:
                continue
            _, pa, pb = r
            if predicted_error(params, n, cx, cy, j, i, pa, pb) > args.loop_tolerance:
                rejected += 1
                continue
            if len(pa) > PTS_PER_PAIR:
                sel = rng.choice(len(pa), PTS_PER_PAIR, replace=False)
                pa, pb = pa[sel], pb[sel]
            pairs.append((j, i, pa, pb))
            loops += 1
        print(f"loop closures: {loops} accepted, {rejected} rejected, {time.time() - t_start:.0f}s", flush=True)
        if loops:
            R1 = [Rotation.from_rotvec(r).as_matrix() for r in params[: 3 * n].reshape(n, 3)]
            f1 = float(np.exp(np.median(params[3 * n :])))
            params, b2, after = solve(n, pairs, R1, f1, cx, cy, args.max_nfev)
            print(f"solve with loops: {b2:.2f}px -> {after:.2f}px, {time.time() - t_start:.0f}s", flush=True)

    rv = params[: 3 * n].reshape(n, 3)
    f = np.exp(params[3 * n :])
    kf = np.c_[[x[0] for x in feats], [x[1] for x in feats], rv, f]
    np.savez_compressed(out / "rig.npz", keyframes=kf)
    info = {"keyframes": n, "pairs_sequential": seq, "loop_closures": loops, "residual_px_before": round(before, 2),
            "residual_px_after": round(after, 2), "focal_px_median": round(float(np.median(f)), 1), "seconds": round(time.time() - t_start)}
    (out / "rig.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
