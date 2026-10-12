"""Detection + tracking pass: the expensive GPU step, run once per match.

Reads the video at a fixed sample rate, tracks people with ByteTrack, records
every ball candidate, and stores a shirt-colour descriptor per person box so
team assignment can run later without re-reading the video.

Output: <out>/tracks.npz with arrays
    meta      [fps_sampled, width, height, source_fps, stride]
    persons   [frame, t, track_id, x1, y1, x2, y2, conf, L, a, b, colour_px]
    balls     [frame, t, x1, y1, x2, y2, conf]
    camera    [frame, t, a, b, tx, ty, inliers]   motion from the previous sampled frame

    python -m touchline_cv.track VIDEO --out pipeline/out/<match> [--fps 15]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

PERSON, BALL = 0, 32  # COCO class ids


def shirt_colour(frame_bgr: np.ndarray, box) -> tuple[float, float, float, int]:
    """Median Lab colour of the torso region, ignoring grass-coloured pixels.

    Returns (L, a, b, pixel_count); pixel_count 0 means no usable pixels.
    """
    x1, y1, x2, y2 = (int(v) for v in box)
    h, w = y2 - y1, x2 - x1
    if h < 12 or w < 4:
        return 0.0, 0.0, 0.0, 0
    # Torso: from 20% to 50% of the box height, central 60% of the width.
    crop = frame_bgr[y1 + int(0.2 * h) : y1 + int(0.5 * h), x1 + int(0.2 * w) : x2 - int(0.2 * w)]
    if crop.size == 0:
        return 0.0, 0.0, 0.0, 0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    grass = (hsv[..., 0] >= 30) & (hsv[..., 0] <= 90) & (hsv[..., 1] > 40)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)[~grass]
    if len(lab) < 6:
        return 0.0, 0.0, 0.0, 0
    L, a, b = np.median(lab, axis=0)
    return float(L), float(a), float(b), int(len(lab))


class CameraMotion:
    """Frame-to-frame camera motion (pan/zoom) from background features.

    Estimates a similarity transform previous -> current sampled frame on a
    downscaled greyscale image, ignoring pixels inside person boxes.
    Returns (a, b, tx, ty) in full-resolution pixels, where
    x' = a*x - b*y + tx,  y' = b*x + a*y + ty.
    """

    def __init__(self, width: int, small: int = 640):
        self.scale = small / width
        self.prev = None

    def update(self, frame_bgr: np.ndarray, boxes: np.ndarray):
        s = self.scale
        grey = cv2.cvtColor(cv2.resize(frame_bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        mask = np.full(grey.shape, 255, np.uint8)
        for x1, y1, x2, y2 in (boxes * s).astype(int):
            mask[max(0, y1 - 4) : y2 + 4, max(0, x1 - 4) : x2 + 4] = 0
        result = (1.0, 0.0, 0.0, 0.0, 0)
        if self.prev is not None:
            prev_grey, prev_mask = self.prev
            pts = cv2.goodFeaturesToTrack(prev_grey, maxCorners=400, qualityLevel=0.01, minDistance=8, mask=prev_mask)
            if pts is not None and len(pts) >= 12:
                nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev_grey, grey, pts, None, winSize=(21, 21), maxLevel=3)
                good = st.ravel() == 1
                if good.sum() >= 12:
                    M, inl = cv2.estimateAffinePartial2D(pts[good], nxt[good], method=cv2.RANSAC, ransacReprojThreshold=2.0)
                    if M is not None:
                        a, b = M[0, 0], M[1, 0]
                        result = (float(a), float(b), float(M[0, 2] / s), float(M[1, 2] / s), int(inl.sum()))
        self.prev = (grey, mask)
        return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=float, default=15.0, help="frames per second to analyse")
    ap.add_argument("--model", default="yolo11m.pt")
    ap.add_argument("--imgsz", type=int, default=1920)
    ap.add_argument("--start", type=float, default=0.0, help="start time in seconds")
    ap.add_argument("--duration", type=float, default=0.0, help="seconds to process (0 = all)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.model)

    cap = cv2.VideoCapture(args.video)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stride = max(1, round(src_fps / args.fps))
    first = int(args.start * src_fps)
    last = total if args.duration <= 0 else min(total, first + int(args.duration * src_fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)

    motion = CameraMotion(width)
    persons, balls, camera = [], [], []
    t0 = time.time()
    fidx = first
    while fidx < last:
        ok = cap.grab()
        if not ok:
            break
        if (fidx - first) % stride == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            t = fidx / src_fps
            r = model.track(
                frame, imgsz=args.imgsz, conf=0.1, classes=[PERSON, BALL],
                persist=True, tracker="bytetrack.yaml", verbose=False,
            )[0]
            b = r.boxes
            xyxy = b.xyxy.cpu().numpy()
            cls = b.cls.cpu().numpy().astype(int)
            conf = b.conf.cpu().numpy()
            ids = b.id.cpu().numpy().astype(int) if b.id is not None else np.full(len(cls), -1)
            for box, c, p, tid in zip(xyxy, cls, conf, ids):
                if c == PERSON:
                    if p < 0.25:
                        continue
                    L, A, B, n = shirt_colour(frame, box)
                    persons.append([fidx, t, tid, *box, p, L, A, B, n])
                else:
                    balls.append([fidx, t, *box, p])
            camera.append([fidx, t, *motion.update(frame, xyxy[cls == PERSON])])
            done = (fidx - first) / max(1, last - first)
            if len(persons) and (fidx // stride) % 900 == 0:
                el = time.time() - t0
                print(f"{done:6.1%}  t={t:7.1f}s  elapsed {el / 60:5.1f} min  eta {el / max(done, 1e-6) * (1 - done) / 60:5.1f} min", flush=True)
        fidx += 1
    cap.release()

    np.savez_compressed(
        out / "tracks.npz",
        meta=np.array([src_fps / stride, width, height, src_fps, stride]),
        persons=np.array(persons, dtype=np.float32).reshape(-1, 12),
        balls=np.array(balls, dtype=np.float32).reshape(-1, 7),
        camera=np.array(camera, dtype=np.float64).reshape(-1, 7),
    )
    info = {"video": str(args.video), "seconds": round(time.time() - t0, 1), "persons": len(persons), "balls": len(balls)}
    (out / "tracks.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
