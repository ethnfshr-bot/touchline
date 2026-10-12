"""How accurate is carrying a pitch calibration through camera motion?

For pairs of directly calibrated frames, carry the first calibration to the
second frame and compare with the second's own calibration, over a grid of
on-pitch pixels. Reports the median disagreement in metres by time apart, and
how much of the match is within reach of a calibration.

    python -m touchline_cv.checkcarry OUT_DIR
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .geometry import MAX_ERR_M, MIN_INLIERS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    args = ap.parse_args()
    out = Path(args.out)
    h = np.load(out / "pitch.npz")["homog"]
    info_all = len(h)
    h = h[(h[:, 2] >= MIN_INLIERS) & (h[:, 3] <= MAX_ERR_M)]
    cam = np.load(out / "camera.npz")["H"]
    frames = cam[:, 0].astype(int)
    pos = {f: i for i, f in enumerate(frames)}
    M = [r[3:].reshape(3, 3) for r in cam]
    fps = 1 / np.median(np.diff(cam[:, 1]))

    # Cumulative transform: frame i coords -> frame 0 coords (C_i = inv(M_1..M_i)).
    C = [np.eye(3)]
    for i in range(1, len(M)):
        C.append(C[-1] @ np.linalg.inv(M[i]))

    xs, ys = np.meshgrid(np.linspace(200, 1720, 9), np.linspace(450, 1000, 6))
    grid = np.c_[xs.ravel(), ys.ravel(), np.ones(xs.size)]

    def pitch_pts(H):
        v = grid @ H.T
        return v[:, :2] / v[:, 2:]

    anchors = [(int(r[0]), r[1], r[4:].reshape(3, 3)) for r in h if int(r[0]) in pos]
    from .pitch import VERTICES

    kp = np.load(out / "pitch.npz")["keypoints"]
    kp_by = {}
    for f, _t, k, x, y, c in kp:
        kp_by.setdefault(int(f), []).append((int(k), x, y))

    def kp_err(H, f):
        """Median distance (m) between the frame's detected keypoints mapped by H and their true positions."""
        pts = kp_by.get(f, [])
        if len(pts) < 3:
            return None
        v = np.array([[x, y, 1.0] for _, x, y in pts]) @ H.T
        p = v[:, :2] / v[:, 2:]
        return float(np.median(np.hypot(*(p - VERTICES[[k for k, _, _ in pts]]).T)))

    res_kp = []
    for a in range(len(anchors)):
        fa, ta, Ha = anchors[a]
        for b in range(a + 1, min(a + 6, len(anchors))):
            fb, tb, Hb = anchors[b]
            if tb - ta > 120:
                break
            T = np.linalg.inv(C[pos[fa]]) @ C[pos[fb]]
            e_carry, e_own = kp_err(Ha @ T, fb), kp_err(Hb, fb)
            if e_carry is not None:
                res_kp.append((tb - ta, e_carry, e_own))
    res_kp = np.array(res_kp)
    res = []
    for a in range(len(anchors)):
        fa, ta, Ha = anchors[a]
        for b in range(a + 1, min(a + 6, len(anchors))):
            fb, tb, Hb = anchors[b]
            dt = tb - ta
            if dt > 120:
                break
            # frame b coords -> frame 0 -> frame a coords
            T = np.linalg.inv(C[pos[fa]]) @ C[pos[fb]]
            Hc = Ha @ T
            pa, pb = pitch_pts(Hc), pitch_pts(Hb)
            ok = (pb[:, 0] > -5) & (pb[:, 0] < 110) & (pb[:, 1] > -5) & (pb[:, 1] < 73)
            if ok.sum() < 5:
                continue
            res.append((dt, float(np.median(np.hypot(*(pa[ok] - pb[ok]).T)))))
    res = np.array(res)
    bins = [(0, 5), (5, 15), (15, 30), (30, 60), (60, 120)]
    by = {}
    for lo, hi in bins:
        sel = res[(res[:, 0] >= lo) & (res[:, 0] < hi)] if len(res) else np.zeros((0, 2))
        by[f"{lo}-{hi}s"] = {"pairs": int(len(sel)), "median_m": round(float(np.median(sel[:, 1])), 2) if len(sel) else None}
    at = np.array([a[1] for a in anchors])
    t_all = cam[:, 1]
    gap = np.min(np.abs(t_all[:, None] - at[None, :]), axis=1) if len(at) else np.full(len(t_all), np.inf)
    cover = {f"within_{s}s": round(float(np.mean(gap <= s)), 3) for s in (5, 15, 30, 60)}
    by_kp = {}
    for lo, hi in bins:
        sel = res_kp[(res_kp[:, 0] >= lo) & (res_kp[:, 0] < hi)] if len(res_kp) else np.zeros((0, 3))
        by_kp[f"{lo}-{hi}s"] = {"pairs": int(len(sel)), "carried_m": round(float(np.median(sel[:, 1])), 2) if len(sel) else None,
                                "own_fit_m": round(float(np.median(sel[:, 2])), 2) if len(sel) else None}
    summary = {"fits_total": info_all, "anchors": len(anchors), "carry_error_on_keypoints": by_kp,
               "carry_vs_own_fit_over_frame": by, "share_of_match_near_an_anchor": cover}
    (out / "checkcarry.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
