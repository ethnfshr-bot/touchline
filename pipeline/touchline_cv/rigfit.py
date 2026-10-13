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

from .pitch import VERTICES, vertices
from .rig import rays

THRESH = 0.035  # ~2 degrees in the ray plane: about the spread of a stable keypoint
CENTRE = list(range(13, 17)) + [30, 31]
LEFT = list(range(0, 13))
RIGHT = list(range(17, 30))


def mirror_index():
    """Keypoint index -> index of the same marking at the other end."""
    m = {}
    length = VERTICES[24, 0]  # far corner (length, 0): follows a fitted pitch size
    for i, (x, y) in enumerate(VERTICES):
        d = np.hypot(VERTICES[:, 0] - (length - x), VERTICES[:, 1] - y)
        j = int(np.argmin(d))
        if d[j] < 1e-6:
            m[i] = j
    return m


def ang_err(Hpr, k, r):
    """Ray-plane distance between where vertex k should appear and the observed ray."""
    v = np.c_[VERTICES[k], np.ones(len(k))] @ Hpr.T
    p = v[:, :2] / v[:, 2:]
    return np.hypot(*(p - r).T)


def size_search(ks, r, stable_box):
    """Estimate pitch length and width: the size whose markings the rays agree with best.

    Penalty boxes, the centre circle and the spot are regulation size everywhere;
    only corner and halfway-line positions depend on the pitch's length and width.
    Returns (length, width, inliers, median_err).
    """
    box = LEFT if stable_box == "left" else RIGHT
    sel = np.isin(ks, CENTRE + box)
    best = None
    for L in np.arange(90.0, 111.0, 1.0):
        for W in np.arange(55.0, 76.0, 1.0):
            V = vertices(L, W)
            H, mask = cv2.findHomography(V[ks[sel]], r[sel], cv2.RANSAC, THRESH)
            if H is None:
                continue
            v = np.c_[V[ks[sel]], np.ones(sel.sum())] @ H.T
            e = np.hypot(*(v[:, :2] / v[:, 2:] - r[sel]).T)
            n_in, med = int((e < THRESH).sum()), float(np.median(e[e < THRESH])) if (e < THRESH).any() else 1.0
            if best is None or (n_in, -med) > (best[2], -best[3]):
                best = (float(L), float(W), n_in, med)
    return best


def load_window(out: Path, tag: str = ""):
    """Rays and keypoint labels for a rig solve: (kf, idx, ks, r, n)."""
    sfx = f"_{tag}" if tag else ""
    rz = np.load(out / f"rig{sfx}.npz")
    kf = rz["keyframes"]
    k1 = float(rz["k1"]) if "k1" in rz.files else 0.0
    n = len(kf)
    params = np.r_[kf[:, 2:5].ravel(), np.log(kf[:, 5])]
    pos = {int(f): i for i, f in enumerate(kf[:, 0])}
    kp = np.load(out / "pitch.npz")["keypoints"]
    obs = [(pos[int(f)], x, y, int(k)) for f, _t, k, x, y, c in kp if int(f) in pos]
    idx = np.array([o[0] for o in obs], dtype=int)
    u = np.array([[o[1], o[2]] for o in obs]).reshape(-1, 2)
    ks = np.array([o[3] for o in obs], dtype=int)
    r = rays(params, n, 960.0, 540.0, idx, u, k1) if len(obs) else np.zeros((0, 2))
    return kf, idx, ks, r, n


def refine(Hpr, ks, r, use, thresholds=(THRESH,)):
    """From a pitch->ray homography, relabel mirror-confused box keypoints, keep
    the points that agree, and refit; repeated for each threshold in turn
    (coarse to fine), so a rough starting calibration can be pulled in.
    Returns (Hpr, labels, inliers) or None."""
    mir = mirror_index()
    mk = np.array([mir.get(int(k), int(k)) for k in ks])
    k = ks.copy()
    for th in thresholds:
        e_own, e_mir = ang_err(Hpr, ks, r), ang_err(Hpr, mk, r)
        k = ks.copy()
        swap = (e_mir < e_own) & (e_mir < th)
        k[swap] = mk[swap]
        inl = use & (ang_err(Hpr, k, r) < th)
        if inl.sum() < 8 or np.linalg.matrix_rank(np.c_[VERTICES[k[inl]], np.ones(inl.sum())], tol=1.0) < 3:
            return None
        H2, _ = cv2.findHomography(VERTICES[k[inl]], r[inl], cv2.RANSAC, th)
        if H2 is None:
            return None
        Hpr = H2
    return Hpr, k, use & (ang_err(Hpr, k, r) < THRESH)


# Coarse-to-fine thresholds for a handed-over seed: wide enough to accept a
# ~10 degree seed error, narrow enough to reject ~45 degree mirror mislabels.
SEED_STEPS = (0.25, 0.15, 0.08, 0.05, THRESH)


def seeded_fit(out: Path, tag: str, Hpr_seed: np.ndarray):
    """Fit a window starting from a calibration handed over by a neighbouring
    window, instead of from its own (possibly too few) trustworthy keypoints.
    Writes rig_G_<tag>.npy and rigfit_<tag>.json; returns the report or None."""
    kf, idx, ks, r, n = load_window(out, tag)
    if len(ks) < 8:
        return None
    every = np.ones(len(ks), bool)
    res = refine(Hpr_seed, ks, r, every, SEED_STEPS)
    if res is None:
        return None
    res2 = refine(res[0], ks, r, every) or res
    H2, k, inl = res2
    # Held-out check: refit from the seed with the first half only, test the
    # second half's centre markings (the most reliably labelled).
    half = idx < n // 2
    r1 = refine(Hpr_seed, ks, r, half, SEED_STEPS)
    test = ~half & np.isin(k, CENTRE)
    if test.sum() < 5:
        test = ~half & np.isin(k, CENTRE + LEFT)
    if r1 is None or test.sum() < 5:
        return None
    et = ang_err(r1[0], k[test], r[test])
    report = {"seeded": True, "keypoints": int(len(ks)), "inlier_share": round(float(inl.mean()), 3),
              "relabelled_mirror": int((k != ks).sum()),
              "time_split_test": {"median_deg": round(float(np.degrees(np.median(et))), 2), "share_within_threshold": round(float(np.mean(et < THRESH)), 3)}}
    np.save(out / f"rig_G_{tag}.npy", np.linalg.inv(H2))
    (out / f"rigfit_{tag}.json").write_text(json.dumps(report, indent=1))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--tag", default="", help="read rig_<tag>.npz, write rig_G_<tag>.npy")
    ap.add_argument("--fit-size", action="store_true", help="estimate the pitch's length and width instead of assuming 105 x 68")
    args = ap.parse_args()
    global VERTICES
    out = Path(args.out)
    sfx = f"_{args.tag}" if args.tag else ""
    kf, idx, ks, r, n = load_window(out, args.tag)
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
    size = None
    if args.fit_size:
        size = size_search(ks, r, seed_box)
        VERTICES = vertices(size[0], size[1])
        sel = np.isin(ks, CENTRE + (LEFT if seed_box == "left" else RIGHT))
        Hpr, _ = cv2.findHomography(VERTICES[ks[sel]], r[sel], cv2.RANSAC, THRESH)
        mir = mirror_index()

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
    if size:
        report["pitch_size_m"] = {"length": size[0], "width": size[1]}
        np.save(out / f"rig_size{sfx}.npy", np.array(size[:2]))
    np.save(out / f"rig_G{sfx}.npy", G)
    (out / f"rigfit{sfx}.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
