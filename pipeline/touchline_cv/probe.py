"""Measure off-the-shelf detection quality on a match video.

Samples frames across the video, runs YOLO person/ball detection at full
resolution and with tiling, and reports how often the ball is found. Saves a
few annotated frames to inspect by eye.

    python -m touchline_cv.probe VIDEO [--every 30] [--out pipeline/out/probe]
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


def tiles(w: int, h: int, size: int = 960, overlap: int = 160):
    """Top-left corners of overlapping square tiles covering a w x h frame."""
    step = size - overlap
    xs = list(range(0, max(w - size, 0) + 1, step))
    ys = list(range(0, max(h - size, 0) + 1, step))
    if xs[-1] + size < w:
        xs.append(w - size)
    if ys[-1] + size < h:
        ys.append(h - size)
    return [(x, y) for y in ys for x in xs]


def detect(model, frame, imgsz, conf):
    r = model.predict(frame, imgsz=imgsz, conf=conf, classes=[PERSON, BALL], verbose=False)[0]
    b = r.boxes
    return b.xyxy.cpu().numpy(), b.cls.cpu().numpy().astype(int), b.conf.cpu().numpy()


def detect_tiled_ball(model, frame, conf):
    h, w = frame.shape[:2]
    best = None
    for x, y in tiles(w, h):
        xyxy, cls, cf = detect(model, frame[y : y + 960, x : x + 960], 960, conf)
        for box, c, p in zip(xyxy, cls, cf):
            if c == BALL and (best is None or p > best[1]):
                best = (box + [x, y, x, y], float(p))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--every", type=float, default=30.0, help="seconds between sampled frames")
    ap.add_argument("--model", default="yolo11m.pt")
    ap.add_argument("--out", default="pipeline/out/probe")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.model)
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stride = int(round(args.every * fps))

    rows, t0 = [], time.time()
    for i, fidx in enumerate(range(0, n, stride)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ok, frame = cap.read()
        if not ok:
            break
        xyxy, cls, cf = detect(model, frame, 1920, 0.15)
        persons = int((cls == PERSON).sum())
        ball_full = float(cf[cls == BALL].max()) if (cls == BALL).any() else 0.0
        tb = detect_tiled_ball(model, frame, 0.10)
        rows.append({"t": fidx / fps, "persons": persons, "ball_full": ball_full, "ball_tiled": tb[1] if tb else 0.0})
        if i % 20 == 0:
            vis = frame.copy()
            for box, c in zip(xyxy.astype(int), cls):
                cv2.rectangle(vis, tuple(box[:2]), tuple(box[2:]), (0, 255, 255) if c == PERSON else (0, 0, 255), 2)
            if tb:
                bx = tb[0].astype(int)
                cv2.circle(vis, ((bx[0] + bx[2]) // 2, (bx[1] + bx[3]) // 2), 18, (255, 0, 255), 3)
            cv2.imwrite(str(out / f"frame_{int(fidx / fps):05d}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 85])

    cap.release()
    p = np.array([r["persons"] for r in rows])
    bf = np.array([r["ball_full"] > 0 for r in rows])
    bt = np.array([r["ball_tiled"] > 0 for r in rows])
    summary = {
        "frames": len(rows),
        "seconds": round(time.time() - t0, 1),
        "persons_median": float(np.median(p)),
        "ball_found_full_frame": round(float(bf.mean()), 3),
        "ball_found_tiled": round(float(bt.mean()), 3),
    }
    (out / "probe.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
