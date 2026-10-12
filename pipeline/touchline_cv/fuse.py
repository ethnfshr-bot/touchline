"""Fused pitch calibration: one homography per sampled second from all pitch
keypoints detected within +/- WINDOW_S seconds, brought into that frame
through the camera motion.

Single-frame calibrations rest on 5-9 keypoints bunched in one part of the
image; they fit those points to ~0.3 m but are ~3 m out elsewhere in the
frame (measured: a calibration carried to a frame seconds away misses that
frame's own keypoints by ~3 m). Pooling keypoints over a window spreads them
across the pitch as the camera pans, and RANSAC outvotes mislabelled ones.

    python -m touchline_cv.fuse OUT_DIR [--window 10] [--evaluate]
Output: OUT_DIR/fused.npz with array homog [frame, t, inliers, err_m, h00..h22]
(same layout as pitch.npz, so geometry.PitchMapper can use either).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from .pitch import VERTICES

WINDOW_S = 10.0
RANSAC_M = 1.5
MIN_POINTS = 8


def cumulative(camera_H: np.ndarray):
    """frames, pos, and C[i]: frame i coords -> frame 0 coords."""
    frames = camera_H[:, 0].astype(int)
    C = np.empty((len(frames), 3, 3))
    C[0] = np.eye(3)
    for i in range(1, len(frames)):
        M = camera_H[i, 3:].reshape(3, 3)
        C[i] = C[i - 1] @ np.linalg.inv(M)
    return frames, {int(f): i for i, f in enumerate(frames)}, C


def fuse_at(target, samples, pos, C, window_frames, exclude_self=False):
    """Fit a pitch homography for frame `target` from keypoints in nearby samples.

    samples: frame -> (img_pts (n,2), vertex_idx (n,))
    """
    it = pos[target]
    Cinv = np.linalg.inv(C[it])
    src, dst = [], []
    for f, (pts, idx) in samples.items():
        if abs(f - target) > window_frames or (exclude_self and f == target) or f not in pos:
            continue
        T = Cinv @ C[pos[f]]  # frame f coords -> target coords
        v = np.c_[pts, np.ones(len(pts))] @ T.T
        src.append(v[:, :2] / v[:, 2:])
        dst.append(VERTICES[idx])
    if not src:
        return None
    src, dst = np.vstack(src), np.vstack(dst)
    if len(src) < MIN_POINTS or np.linalg.matrix_rank(np.c_[dst, np.ones(len(dst))], tol=1.0) < 3:
        return None
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_M)
    if H is None:
        return None
    inl = mask.ravel().astype(bool)
    if inl.sum() < MIN_POINTS:
        return None
    p = cv2.perspectiveTransform(src[inl].reshape(-1, 1, 2), H).reshape(-1, 2)
    return H, int(inl.sum()), float(np.sqrt(np.mean(np.sum((p - dst[inl]) ** 2, axis=1))))


def kp_err(H, pts, idx):
    v = np.c_[pts, np.ones(len(pts))] @ H.T
    p = v[:, :2] / v[:, 2:]
    return float(np.median(np.hypot(*(p - VERTICES[idx]).T)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--window", type=float, default=WINDOW_S)
    ap.add_argument("--evaluate", action="store_true", help="leave-one-out accuracy on frames with good single-frame fits")
    args = ap.parse_args()
    out = Path(args.out)
    pz = np.load(out / "pitch.npz")
    cam = np.load(out / "camera.npz")["H"]
    frames, pos, C = cumulative(cam)
    fps = 1 / np.median(np.diff(cam[:, 1]))
    window_frames = int(args.window * fps) * int(np.median(np.diff(frames)))

    samples = {}
    for f, _t, k, x, y, _c in pz["keypoints"]:
        samples.setdefault(int(f), ([], []))
        samples[int(f)][0].append((x, y))
        samples[int(f)][1].append(int(k))
    samples = {f: (np.array(p), np.array(i)) for f, (p, i) in samples.items() if f in pos}
    times = dict(zip(frames.tolist(), cam[:, 1].tolist()))

    if args.evaluate:
        h = pz["homog"]
        good = h[(h[:, 2] >= 5) & (h[:, 3] <= 1.0)]
        errs = []
        for r in good:
            f = int(r[0])
            if f not in samples or f not in pos:
                continue
            fit = fuse_at(f, samples, pos, C, window_frames, exclude_self=True)
            if fit:
                errs.append(kp_err(fit[0], *samples[f]))
        errs = np.array(errs)
        print(json.dumps({"window_s": args.window, "frames_tested": int(len(errs)), "median_m": round(float(np.median(errs)), 2),
                          "p75_m": round(float(np.percentile(errs, 75)), 2), "share_under_2m": round(float(np.mean(errs < 2)), 3)}, indent=1))
        return

    rows = []
    for f in sorted(samples):
        fit = fuse_at(f, samples, pos, C, window_frames)
        if fit:
            H, n, err = fit
            rows.append([f, times[f], n, err, *H.ravel()])
    arr = np.array(rows).reshape(-1, 13)
    np.savez_compressed(out / "fused.npz", homog=arr)
    info = {"seconds_with_keypoints": len(samples), "fused": len(rows), "median_rms_m": round(float(np.median(arr[:, 3])), 2) if len(rows) else None}
    (out / "fused.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
