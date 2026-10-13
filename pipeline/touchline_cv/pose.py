"""Find where the Veo camera stands, from the white pitch lines alone.

The camera is physically fixed beside the pitch; only its virtual view turns
and zooms (solved per keyframe by rig.py, in the rig's own reference frame).
So the whole pitch calibration is 6 numbers: camera position (x, y, height)
in pitch metres and the rotation Q from the rig frame to the pitch frame.
They're found by maximising how many detected white-line pixels (lines.py)
lie on the projected pitch markings, over keyframes spread through a window.
No pitch-keypoint labels are used, so mislabelled markings can't mislead it.

Pitch frame: x along the length (0 = left goal line), y across (0 = far
touchline, WIDTH = near touchline, camera side), z up.

    python -m touchline_cv.pose VIDEO OUT_DIR --tag d000 [--keyframes 24]
Writes rig_G_<tag>_pose.npy (ray plane -> pitch metres, like rig_G) and pose_<tag>.json.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from .lineref import CX, CY, SCALE, TRUNC, pitch_polylines
from .lines import line_mask
from .pitch import LENGTH, WIDTH
from .rig import distort

W_HALF, H_HALF = int(1920 * SCALE), int(1080 * SCALE)


def world_to_cam_basis(yaw, tilt, roll):
    """Rotation taking pitch-frame vectors to the rig frame (rig z = forward, y = down)."""
    # Nominal view: from the near side looking towards the far touchline (-y),
    # level. Rows are the camera axes in pitch coordinates: forward z_c = -y,
    # down y_c = -z, and right x_c = y_c x z_c = -x (a proper rotation, det +1).
    # The pitch model is symmetric end-to-end, so which goal is "x = 0" doesn't
    # affect the fit.
    base = np.array([[-1.0, 0, 0], [0, 0, -1], [0, -1, 0]])
    return Rotation.from_euler("zxy", [roll, tilt, yaw], degrees=True).as_matrix() @ base


def ray_plane_to_pitch(Wc: np.ndarray, C: np.ndarray) -> np.ndarray:
    """G: rig ray-plane (x/z, y/z, 1) -> pitch metres, for camera at C with world->rig rotation Wc."""
    # A rig ray d maps to world direction Wc^T d; it meets z=0 at C + t Wc^T d, t = -C_z / (Wc^T d)_z.
    # As a projective map on d: X ~ C_z * (Wc^T d)_xy - (Wc^T d)_z * C_xy  over  -(Wc^T d)_z.
    A = Wc.T
    G = np.vstack([C[2] * A[0] - C[0] * A[2], C[2] * A[1] - C[1] * A[2], -A[2]])
    return G


CENTRE_KEYS = [13, 14, 15, 16, 30, 31]  # halfway line ends and circle crossings, circle sides
KP_SIGMA_PX = 20.0
KP_WEIGHT = 1.0


def keypoint_score(Ginv, frames_kp, k1):
    """Soft agreement of projected centre markings with detected ones (0-1).

    Centre markings were the stable ones (~2 degrees); they pin the scale and
    the far side, which the lines alone leave loose (only near lines are
    detected reliably)."""
    if not frames_kp:
        return 0.0
    from .pitch import VERTICES

    vals = []
    for R, f, obs in frames_kp:
        K = np.array([[f, 0, CX], [0, f, CY], [0, 0, 1.0]])
        M = K @ R @ Ginv
        for k, u, v in obs:
            p = M @ np.r_[VERTICES[k], 1.0]
            if p[2] <= 1e-6:
                vals.append(0.0)
                continue
            q = distort((p[:2] / p[2])[None], CX, CY, k1)[0]
            vals.append(float(np.exp(-((np.hypot(q[0] - u, q[1] - v) / KP_SIGMA_PX) ** 2))))
    return float(np.mean(vals))


def score(params, frames, polys, k1, frames_kp=None):
    x, y, h, yaw, tilt, roll = params
    if h <= 1 or h > 25:
        return 0.0
    Wc = world_to_cam_basis(yaw, tilt, roll)
    G = ray_plane_to_pitch(Wc, np.array([x, y, h]))
    try:
        Ginv = np.linalg.inv(G)
    except np.linalg.LinAlgError:
        return 0.0
    kp = keypoint_score(Ginv, frames_kp, k1) if frames_kp else 0.0
    tot = 0.0
    for R, f, pts in frames:
        K = np.array([[f, 0, CX], [0, f, CY], [0, 0, 1.0]])
        M = K @ R @ Ginv
        canvas = np.full((H_HALF, W_HALF), 255, np.uint8)
        for p in polys:
            v = np.c_[p, np.ones(len(p))] @ M.T
            ok = v[:, 2] > 1e-6
            if ok.sum() < 2:
                continue
            q = distort(v[ok, :2] / v[ok, 2:], CX, CY, k1) * SCALE
            inside = (np.abs(q[:, 0]) < 4 * W_HALF) & (np.abs(q[:, 1]) < 4 * H_HALF)
            if inside.sum() > 1:
                cv2.polylines(canvas, [np.round(q[inside]).astype(np.int32)], False, 0, 1)
        dt = cv2.distanceTransform(canvas, cv2.DIST_L2, 3)
        d = dt[pts[:, 1], pts[:, 0]]
        tot += float(np.mean(np.exp(-np.minimum(d / 2.5, 10.0) ** 2)))  # soft "near a line" share
    return tot / len(frames) + KP_WEIGHT * kp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--keyframes", type=int, default=24)
    args = ap.parse_args()
    out = Path(args.out)
    rz = np.load(out / f"rig_{args.tag}.npz")
    kf = rz["keyframes"]
    k1 = float(rz["k1"]) if "k1" in rz.files else 0.0
    polys = pitch_polylines()
    persons = {}
    tr = out / "tracks.npz"
    if tr.exists():
        for row in np.load(tr)["persons"]:
            persons.setdefault(int(row[0]), []).append(row[3:7])

    cap = cv2.VideoCapture(args.video)
    frames = []
    for i in np.linspace(0, len(kf) - 1, args.keyframes * 2).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(kf[i, 0]))
        ok, frame = cap.read()
        if not ok:
            continue
        m = cv2.resize(line_mask(frame, persons.get(int(kf[i, 0]))), (W_HALF, H_HALF), interpolation=cv2.INTER_NEAREST)
        ys, xs = np.nonzero(m)
        if len(xs) < 80:
            continue
        pts = np.c_[xs, ys]
        if len(pts) > 1500:
            pts = pts[np.random.default_rng(0).choice(len(pts), 1500, replace=False)]
        frames.append((Rotation.from_rotvec(kf[i, 2:5]).as_matrix(), kf[i, 5], pts))
        if len(frames) >= args.keyframes:
            break
    print(f"{len(frames)} keyframes with lines", flush=True)

    # Centre-marking detections on all keyframes of the window.
    kp = np.load(out / "pitch.npz")["keypoints"]
    by_f = {}
    for f_, _t, k, u, v, c in kp:
        if int(k) in CENTRE_KEYS:
            by_f.setdefault(int(f_), []).append((int(k), u, v))
    frames_kp = [(Rotation.from_rotvec(r[2:5]).as_matrix(), r[5], by_f[int(r[0])]) for r in kf if int(r[0]) in by_f]
    print(f"{sum(len(o) for _, _, o in frames_kp)} centre-marking detections on {len(frames_kp)} keyframes", flush=True)

    # Coarse grid: camera beside the near touchline, a few metres up; any yaw.
    grid = list(itertools.product([35.0, 52.5, 70.0], [WIDTH + 3, WIDTH + 10], [4.0, 8.0], np.arange(-180, 180, 15.0), [-20.0, -10.0, 10.0, 20.0], [0.0]))
    scored = sorted(((score(p, frames, polys, k1, frames_kp), p) for p in grid), reverse=True)
    print(f"grid best {scored[0][0]:.3f} at {np.round(scored[0][1], 1).tolist()}", flush=True)
    best = (scored[0][0], np.array(scored[0][1]))
    for s0, p0 in scored[:6]:
        r = minimize(lambda p: -score(p, frames, polys, k1, frames_kp), np.array(p0), method="Powell",
                     options={"xtol": 0.05, "ftol": 1e-4, "maxfev": 1500})
        if -r.fun > best[0]:
            best = (-r.fun, r.x)
    s, p = best
    Wc = world_to_cam_basis(*p[3:])
    G = ray_plane_to_pitch(Wc, p[:3])
    np.save(out / f"rig_G_{args.tag}_pose.npy", G)
    Ginv = np.linalg.inv(G)
    rep = {"score": round(float(s), 3), "line_share": round(float(score(p, frames, polys, k1)), 3), "centre_marking_agreement": round(keypoint_score(Ginv, frames_kp, k1), 3), "camera_m": {"x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "height": round(float(p[2]), 1)},
           "angles_deg": {"yaw": round(float(p[3]), 1), "tilt": round(float(p[4]), 1), "roll": round(float(p[5]), 1)}, "keyframes": len(frames)}
    (out / f"pose_{args.tag}.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
