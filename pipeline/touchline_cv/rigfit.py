"""Fit the match-wide pitch calibration (rig rays <-> pitch metres) and check it.

Uses every pitch keypoint detected on a rig keyframe. Two lessons from
Leeming v La Fammia are built in:

  * Errors are judged as angles seen from the camera, not metres on the
    pitch: at a grazing angle a 1-degree pointing error is many metres, so a
    metre threshold rejects good points.
  * The pitch model mixes up the two penalty boxes (mirror labels). Box
    keypoints are tested under both their own and their mirrored label and
    take whichever the geometry supports.

The first fit uses the keypoints that proved stable (near box and centre
circle / halfway line, whichever box is consistent); the rest are then
re-labelled and the fit repeated.

    python -m touchline_cv.rigfit OUT_DIR
Output: OUT_DIR/rig_G.npy (3x3, rig ray-plane -> pitch metres) and rigfit.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from .pitch import LENGTH, VERTICES
from .rig import rays

THRESH = 0.035  # ~2 degrees in the ray plane: about the spread of a stable keypoint
CENTRE = list(range(13, 17)) + [30, 31]
LEFT = list(range(0, 13))
RIGHT = list(range(17, 30))


def mirror_index():
    """Keypoint index -> index of the same marking at the other end."""
    m = {}
    for i, (x, y) in enumerate(VERTICES):
        d = np.hypot(VERTICES[:, 0] - (LENGTH - x), VERTICES[:, 1] - y)
        j = int(np.argmin(d))
        if d[j] < 1e-6:
            m[i] = j
    return m


def ang_err(Hpr, k, r):
    """Ray-plane distance between where vertex k should appear and the observed ray."""
    v = np.c_[VERTICES[k], np.ones(len(k))] @ Hpr.T
    p = v[:, :2] / v[:, 2:]
    return np.hypot(*(p - r).T)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    args = ap.parse_args()
    out = Path(args.out)
    kf = np.load(out / "rig.npz")["keyframes"]
    n = len(kf)
    params = np.r_[kf[:, 2:5].ravel(), np.log(kf[:, 5])]
    pos = {int(f): i for i, f in enumerate(kf[:, 0])}
    kp = np.load(out / "pitch.npz")["keypoints"]
    obs = [(pos[int(f)], x, y, int(k)) for f, _t, k, x, y, c in kp if int(f) in pos]
    idx = np.array([o[0] for o in obs])
    u = np.array([[o[1], o[2]] for o in obs])
    ks = np.array([o[3] for o in obs])
    r = rays(params, n, 960.0, 540.0, idx, u)
    mir = mirror_index()

    # Which box is stable? Try a seed fit with centre + each box, keep the better one.
    best = None
    for name, box in (("left", LEFT), ("right", RIGHT)):
        sel = np.isin(ks, CENTRE + box)
        if sel.sum() < 12:
            continue
        H, mask = cv2.findHomography(VERTICES[ks[sel]], r[sel], cv2.RANSAC, THRESH)
        if H is None:
            continue
        share = float(mask.mean())
        if best is None or share > best[2]:
            best = (name, H, share)
    if best is None:
        raise SystemExit("Not enough pitch keypoints to calibrate.")
    seed_box, Hpr, seed_share = best

    # Relabel: each keypoint takes its own or its mirrored label, whichever fits.
    k_fixed = ks.copy()
    e_own = ang_err(Hpr, ks, r)
    mk = np.array([mir.get(int(k), int(k)) for k in ks])
    e_mir = ang_err(Hpr, mk, r)
    swap = (e_mir < e_own) & (e_mir < THRESH)
    k_fixed[swap] = mk[swap]

    # Refit on points that agree with the seed (after relabelling), not on everything:
    # far-box mislabels are the majority and would outvote the good points.
    inl = ang_err(Hpr, k_fixed, r) < THRESH
    H2, _ = cv2.findHomography(VERTICES[k_fixed[inl]], r[inl], 0)
    inl = ang_err(H2, k_fixed, r) < THRESH
    e = ang_err(H2, k_fixed, r)
    G = np.linalg.inv(H2)  # ray plane -> pitch metres
    v = np.c_[r, np.ones(len(r))] @ G.T
    pm = v[:, :2] / v[:, 2:]
    em = np.hypot(*(pm - VERTICES[k_fixed]).T)

    def grp(sel):
        return {"n": int(sel.sum()), "inlier_share": round(float(inl[sel].mean()), 3) if sel.sum() else None,
                "median_deg": round(float(np.degrees(np.median(e[sel]))), 2) if sel.sum() else None,
                "median_m_inliers": round(float(np.median(em[sel & inl])), 2) if (sel & inl).sum() else None}

    # Time split: seed on the earlier keyframes only, test on the later ones.
    half = idx < n // 2
    seed = half & np.isin(k_fixed, CENTRE + (LEFT if seed_box == "left" else RIGHT))
    Ht, _ = cv2.findHomography(VERTICES[k_fixed[seed]], r[seed], cv2.RANSAC, THRESH)
    test = ~half & np.isin(k_fixed, CENTRE + (LEFT if seed_box == "left" else RIGHT))
    et = ang_err(Ht, k_fixed[test], r[test])
    report = {
        "keypoints": int(len(ks)), "seed_box": seed_box, "seed_inlier_share": round(seed_share, 3),
        "relabelled_mirror": int(swap.sum()), "inlier_share": round(float(inl.mean()), 3),
        "left box": grp(np.isin(k_fixed, LEFT)), "centre": grp(np.isin(k_fixed, CENTRE)), "right box": grp(np.isin(k_fixed, RIGHT)),
        "time_split_test": {"median_deg": round(float(np.degrees(np.median(et))), 2), "share_within_threshold": round(float(np.mean(et < THRESH)), 3)},
    }
    np.save(out / "rig_G.npy", G)
    (out / "rigfit.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
