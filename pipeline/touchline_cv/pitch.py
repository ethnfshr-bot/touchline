"""Pitch registration: map screen pixels to pitch coordinates.

Detects pitch landmarks (32 keypoints: corners, box corners, penalty spots,
halfway line and centre circle) with the Roboflow `sports` pitch model
(MIT code; weights trained with Ultralytics, AGPL-3.0), fits a homography with
RANSAC so mislabelled points are outvoted, and stores one per sampled second.

Pitch coordinates are metres: x along the length (0 at the left goal line),
y across (0 at the far touchline). The markings use regulation dimensions
(16.5 m penalty box, 5.5 m goal box, spot at 11 m, 9.15 m centre circle).
Roboflow's own template uses a 20.15 m penalty box, which made box keypoints
contradict each other by 3-4 m and broke almost every fit. Overall length and
width vary by ground (default 105 x 68 m); only corner and halfway-line points
depend on them.

    python -m touchline_cv.pitch VIDEO --out OUT_DIR [--every 1.0]
Output: OUT_DIR/pitch.npz with arrays
    keypoints [frame, t, k, x, y, conf]       every detected keypoint
    homog     [frame, t, inliers, err_px, h00..h22]  screen -> pitch metres
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

MODELS = Path(__file__).resolve().parents[1] / "models"

LENGTH, WIDTH = 105.0, 68.0
_PB_W, _PB_L, _GB_W, _GB_L, _CC_R, _PS = 40.32, 16.5, 18.32, 5.5, 9.15, 11.0


def vertices(LENGTH: float = LENGTH, WIDTH: float = WIDTH) -> np.ndarray:
    """Keypoint positions in metres, in the model's keypoint order (0-based)."""
    return np.array([
    (0, 0), (0, (WIDTH - _PB_W) / 2), (0, (WIDTH - _GB_W) / 2), (0, (WIDTH + _GB_W) / 2),
    (0, (WIDTH + _PB_W) / 2), (0, WIDTH), (_GB_L, (WIDTH - _GB_W) / 2), (_GB_L, (WIDTH + _GB_W) / 2),
    (_PS, WIDTH / 2), (_PB_L, (WIDTH - _PB_W) / 2), (_PB_L, (WIDTH - _GB_W) / 2), (_PB_L, (WIDTH + _GB_W) / 2),
    (_PB_L, (WIDTH + _PB_W) / 2), (LENGTH / 2, 0), (LENGTH / 2, WIDTH / 2 - _CC_R), (LENGTH / 2, WIDTH / 2 + _CC_R),
    (LENGTH / 2, WIDTH), (LENGTH - _PB_L, (WIDTH - _PB_W) / 2), (LENGTH - _PB_L, (WIDTH - _GB_W) / 2),
    (LENGTH - _PB_L, (WIDTH + _GB_W) / 2), (LENGTH - _PB_L, (WIDTH + _PB_W) / 2), (LENGTH - _PS, WIDTH / 2),
    (LENGTH - _GB_L, (WIDTH - _GB_W) / 2), (LENGTH - _GB_L, (WIDTH + _GB_W) / 2), (LENGTH, 0),
    (LENGTH, (WIDTH - _PB_W) / 2), (LENGTH, (WIDTH - _GB_W) / 2), (LENGTH, (WIDTH + _GB_W) / 2),
    (LENGTH, (WIDTH + _PB_W) / 2), (LENGTH, WIDTH), (LENGTH / 2 - _CC_R, WIDTH / 2), (LENGTH / 2 + _CC_R, WIDTH / 2),
    ], dtype=np.float64)


VERTICES = vertices()


def fit_homography(pts_img: np.ndarray, idx: np.ndarray, thresh_m: float = 1.5):
    """Screen -> pitch homography from keypoints. Returns (H, inliers, rms_err_m) or None.

    Needs at least 4 points that aren't all on one line.
    """
    if len(idx) < 4:
        return None
    dst = VERTICES[idx]
    # Degenerate if every point lies on (nearly) one pitch line.
    if np.linalg.matrix_rank(np.c_[dst, np.ones(len(dst))], tol=1.0) < 3:
        return None
    H, mask = cv2.findHomography(pts_img.astype(np.float64), dst, cv2.RANSAC, thresh_m)
    if H is None:
        return None
    inl = mask.ravel().astype(bool)
    if inl.sum() < 4 or np.linalg.matrix_rank(np.c_[dst[inl], np.ones(inl.sum())], tol=1.0) < 3:
        return None
    proj = cv2.perspectiveTransform(pts_img[inl].reshape(-1, 1, 2).astype(np.float64), H).reshape(-1, 2)
    err = float(np.sqrt(np.mean(np.sum((proj - dst[inl]) ** 2, axis=1))))
    return H, int(inl.sum()), err


def to_pitch(H: np.ndarray, x: float, y: float) -> tuple[float, float]:
    v = H @ np.array([x, y, 1.0])
    return float(v[0] / v[2]), float(v[1] / v[2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--every", type=float, default=1.0, help="seconds between samples")
    ap.add_argument("--min-conf", type=float, default=0.5)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(MODELS / "rf-pitch.pt"))
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, int(round(args.every * fps)))

    kps, homs = [], []
    f = 0
    while f < total:
        ok = cap.grab()
        if not ok:
            break
        if f % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            t = f / fps
            r = model.predict(frame, imgsz=1280, conf=0.3, verbose=False)[0]
            if r.keypoints is not None and len(r.keypoints):
                xy = r.keypoints.xy[0].cpu().numpy()
                cf = r.keypoints.conf[0].cpu().numpy()
                good = (cf >= args.min_conf) & ~((xy[:, 0] == 0) & (xy[:, 1] == 0))
                for k in np.where(good)[0]:
                    kps.append([f, t, k, xy[k, 0], xy[k, 1], cf[k]])
                fit = fit_homography(xy[good], np.where(good)[0])
                if fit:
                    H, n, err = fit
                    homs.append([f, t, n, err, *H.ravel()])
            if (f // step) % 600 == 0:
                print(f"{f / total:6.1%}  homographies so far: {len(homs)}", flush=True)
        f += 1
    cap.release()
    np.savez_compressed(out / "pitch.npz", keypoints=np.array(kps).reshape(-1, 6), homog=np.array(homs).reshape(-1, 13))
    info = {"samples": total // step, "homographies": len(homs), "share": round(len(homs) / max(1, total // step), 3),
            "median_err_m": round(float(np.median([h[3] for h in homs])), 2) if homs else None}
    (out / "pitch.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
