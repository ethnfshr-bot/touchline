"""Camera motion pass: full frame-to-frame homographies.

A Veo camera is fixed; its follow-cam is a virtual camera that pans, tilts
and zooms within the panorama. For a camera rotating about a fixed centre,
any two frames are related by a homography, for every scene point, so
chaining frame-to-frame homographies maps any frame onto any other. That lets
a pitch calibration found on one frame be carried to frames where the pitch
markings can't be read (geometry.py).

CPU only (OpenCV), so it can run alongside GPU passes. Uses the same frame
grid as track.py.

    python -m touchline_cv.camera VIDEO --out OUT_DIR [--fps 15]
Output: OUT_DIR/camera.npz with array
    H  [frame, t, inliers, h00..h22]   maps the previous sampled frame to this one
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

SMALL = 640


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=float, default=15.0)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    stride = max(1, round(src_fps / args.fps))
    s = SMALL / width
    S, Si = np.diag([s, s, 1.0]), np.diag([1 / s, 1 / s, 1.0])

    rows, prev, t0, f = [], None, time.time(), 0
    while f < total:
        if not cap.grab():
            break
        if f % stride == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            grey = cv2.cvtColor(cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            H, n = np.eye(3), 0
            if prev is not None:
                pts = cv2.goodFeaturesToTrack(prev, maxCorners=500, qualityLevel=0.01, minDistance=7)
                if pts is not None and len(pts) >= 15:
                    nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, grey, pts, None, winSize=(21, 21), maxLevel=3)
                    good = st.ravel() == 1
                    if good.sum() >= 15:
                        Hs, mask = cv2.findHomography(pts[good], nxt[good], cv2.RANSAC, 1.5)
                        if Hs is not None:
                            H, n = Si @ Hs @ S, int(mask.sum())
            rows.append([f, f / src_fps, n, *H.ravel()])
            prev = grey
            if (f // stride) % 4500 == 0:
                done = f / total
                el = time.time() - t0
                print(f"{done:6.1%}  elapsed {el / 60:5.1f} min  eta {el / max(done, 1e-6) * (1 - done) / 60:5.1f} min", flush=True)
        f += 1
    cap.release()
    arr = np.array(rows).reshape(-1, 12)
    np.savez_compressed(out / "camera.npz", H=arr)
    info = {"frames": len(rows), "median_inliers": float(np.median(arr[:, 2])), "seconds": round(time.time() - t0, 1)}
    (out / "camera.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
