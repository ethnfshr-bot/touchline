"""Line-based refinement of per-keyframe camera rotation and zoom.

Each keyframe's pixels map to the pitch by H = G . R^T . K^-1 (rig.py,
calib.py). The camera solve drifts by a few degrees over minutes, and far-end
pitch keypoints are unusable, so G alone isn't enough. Here, with G fixed, each
keyframe's rotation and focal length are adjusted so the projected pitch lines
lie on the white-line pixels detected in that frame (lines.py): a directional
chamfer distance from detected line pixels to the rendered pitch model.

    python -m touchline_cv.lineref VIDEO OUT_DIR --tag w001
Writes rig_<tag>_lines.npz (same layout as rig_<tag>.npz) and reports fit quality.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from .lines import line_mask
from .pitch import LENGTH, WIDTH
from .rig import distort

CX, CY = 960.0, 540.0
SCALE = 0.5  # work at half resolution
TRUNC = 12.0  # px (half-res): distances beyond this count as this
_PB_W, _PB_L, _GB_W, _GB_L, _CC_R, _PS = 40.32, 16.5, 18.32, 5.5, 9.15, 11.0


def pitch_polylines(L: float = LENGTH, W: float = WIDTH, step: float = 0.5) -> list[np.ndarray]:
    """Pitch markings as polylines of points in metres."""
    def seg(a, b):
        n = max(2, int(np.hypot(b[0] - a[0], b[1] - a[1]) / step))
        return np.linspace(a, b, n)

    lines = [seg((0, 0), (L, 0)), seg((0, W), (L, W)), seg((0, 0), (0, W)), seg((L, 0), (L, W)), seg((L / 2, 0), (L / 2, W))]
    for x0, s in ((0, 1), (L, -1)):
        y1, y2 = (W - _PB_W) / 2, (W + _PB_W) / 2
        lines += [seg((x0, y1), (x0 + s * _PB_L, y1)), seg((x0 + s * _PB_L, y1), (x0 + s * _PB_L, y2)), seg((x0 + s * _PB_L, y2), (x0, y2))]
        g1, g2 = (W - _GB_W) / 2, (W + _GB_W) / 2
        lines += [seg((x0, g1), (x0 + s * _GB_L, g1)), seg((x0 + s * _GB_L, g1), (x0 + s * _GB_L, g2)), seg((x0 + s * _GB_L, g2), (x0, g2))]
        # Penalty arc: the part of the 9.15 m circle round the spot outside the box.
        spot = x0 + s * _PS
        a = np.arccos((_PB_L - _PS) / _CC_R)
        th = np.linspace(-a, a, 30)
        lines.append(np.c_[spot + s * _CC_R * np.cos(th), W / 2 + _CC_R * np.sin(th)])
    th = np.linspace(0, 2 * np.pi, 120)
    lines.append(np.c_[L / 2 + _CC_R * np.cos(th), W / 2 + _CC_R * np.sin(th)])
    return lines


def project_lines(polys, G, R, f, k1, w, h):
    """Pitch polylines -> image polylines (half-res), dropping points behind the camera or far off-frame."""
    Ginv = np.linalg.inv(G)
    K = np.array([[f, 0, CX], [0, f, CY], [0, 0, 1.0]])
    M = K @ R @ Ginv  # pitch -> pixels (ideal)
    out = []
    for p in polys:
        v = np.c_[p, np.ones(len(p))] @ M.T
        ok = v[:, 2] > 1e-6
        px = v[:, :2] / np.where(ok, v[:, 2], 1)[:, None]
        px = distort(px, CX, CY, k1) * SCALE
        ok &= (px[:, 0] > -w) & (px[:, 0] < 2 * w) & (px[:, 1] > -h) & (px[:, 1] < 2 * h)
        # split at invalid points
        run = []
        for q, good in zip(px, ok):
            if good:
                run.append(q)
            elif len(run) > 1:
                out.append(np.array(run))
                run = []
            else:
                run = []
        if len(run) > 1:
            out.append(np.array(run))
    return out


def chamfer(mask_pts, polys_img, w, h):
    """Mean truncated distance (half-res px) from detected line pixels to the rendered model."""
    canvas = np.full((h, w), 255, np.uint8)
    for p in polys_img:
        cv2.polylines(canvas, [np.round(p).astype(np.int32)], False, 0, 1)
    dt = cv2.distanceTransform(canvas, cv2.DIST_L2, 3)
    d = dt[mask_pts[:, 1], mask_pts[:, 0]]
    return float(np.mean(np.minimum(d, TRUNC))), float(np.mean(d < 2.0))


def refine_keyframe(frame, G, rv, f, k1, polys, person_boxes=None):
    m = line_mask(frame, person_boxes)
    small = cv2.resize(m, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST)
    ys, xs = np.nonzero(small)
    h, w = small.shape
    if len(xs) < 60:
        return None
    pts = np.c_[xs, ys]
    if len(pts) > 3000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 3000, replace=False)]
    R0 = Rotation.from_rotvec(rv)

    def cost(x):
        R = (Rotation.from_rotvec(x[:3] * 0.01) * R0).as_matrix()
        return chamfer(pts, project_lines(polys, G, R, f * np.exp(x[3] * 0.01), k1, w, h), w, h)[0]

    c0 = cost(np.zeros(4))
    # Coarse-to-fine: Powell from the seed, then from a few perturbed starts if it's poor.
    best = minimize(cost, np.zeros(4), method="Powell", options={"xtol": 0.02, "ftol": 0.01, "maxfev": 600})
    if best.fun > 3.0:
        for start in ([3, 0, 0, 0], [-3, 0, 0, 0], [0, 3, 0, 0], [0, -3, 0, 0]):
            r = minimize(cost, np.array(start, float), method="Powell", options={"xtol": 0.02, "ftol": 0.01, "maxfev": 400})
            if r.fun < best.fun:
                best = r
    x = best.x
    R = Rotation.from_rotvec(x[:3] * 0.01) * R0
    f1 = f * np.exp(x[3] * 0.01)
    _, near = chamfer(pts, project_lines(polys, G, R.as_matrix(), f1, k1, w, h), w, h)
    return R.as_rotvec(), f1, c0, float(best.fun), near, len(xs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--every", type=int, default=1, help="refine every Nth keyframe")
    args = ap.parse_args()
    out = Path(args.out)
    rz = np.load(out / f"rig_{args.tag}.npz")
    kf = rz["keyframes"].copy()
    k1 = float(rz["k1"]) if "k1" in rz.files else 0.0
    G = np.load(out / f"rig_G_{args.tag}.npy")
    polys = pitch_polylines()
    persons = {}
    tr = out / "tracks.npz"
    if tr.exists():
        for row in np.load(tr)["persons"]:
            persons.setdefault(int(row[0]), []).append(row[3:7])
    cap = cv2.VideoCapture(args.video)
    stats = []
    for i in range(0, len(kf), args.every):
        f_idx = int(kf[i, 0])
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
        ok, frame = cap.read()
        if not ok:
            continue
        res = refine_keyframe(frame, G, kf[i, 2:5], kf[i, 5], k1, polys, persons.get(f_idx))
        if res is None:
            stats.append({"t": round(float(kf[i, 1]), 1), "lines": 0})
            continue
        rv, f1, c0, c1, near, npx = res
        stats.append({"t": round(float(kf[i, 1]), 1), "lines": npx, "before": round(c0, 2), "after": round(c1, 2), "near2px": round(near, 3)})
        if c1 < c0 and near >= 0.35:
            kf[i, 2:5], kf[i, 5] = rv, f1
    np.savez_compressed(out / f"rig_{args.tag}_lines.npz", keyframes=kf, k1=np.array(k1))
    done = [s for s in stats if s.get("lines")]
    summary = {"keyframes": len(stats), "with_lines": len(done),
               "median_before": float(np.median([s["before"] for s in done])) if done else None,
               "median_after": float(np.median([s["after"] for s in done])) if done else None,
               "share_accepted": round(float(np.mean([s["near2px"] >= 0.35 and s["after"] < s["before"] for s in done])), 3) if done else None}
    (out / f"lineref_{args.tag}.json").write_text(json.dumps({"summary": summary, "keyframes": stats}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
