"""Ball detection pass with a football-specific ball model.

On Leeming v La Fammia, the Roboflow `sports` ball model found the right ball
in ~16/24 sampled frames with ~2 wrong objects, against ~12 and ~7 for stock
YOLO11m (which mostly picked spare balls beside the pitch). See bench.py.

Samples frames on the same grid as track.py (same --fps), so rows line up
with tracks.npz by frame number.

    python -m touchline_cv.ballpass VIDEO --out OUT_DIR [--fps 15]
Output: OUT_DIR/balls.npz with array balls [frame, t, x1, y1, x2, y2, conf]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

MODELS = Path(__file__).resolve().parents[1] / "models"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--model", default=str(MODELS / "rf-ball.pt"))
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--duration", type=float, default=0.0)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.model)
    cap = cv2.VideoCapture(args.video)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stride = max(1, round(src_fps / args.fps))
    # Align to the stride so every pass samples the same absolute frames.
    first = -(-int(args.start * src_fps) // stride) * stride
    last = total if args.duration <= 0 else min(total, first + int(args.duration * src_fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, first)

    balls, t0, f = [], time.time(), first
    while f < last:
        if not cap.grab():
            break
        if (f - first) % stride == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            r = model.predict(frame, imgsz=args.imgsz, conf=0.05, verbose=False)[0]
            for b, c in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()):
                balls.append([f, f / src_fps, *b, c])
            if ((f - first) // stride) % 1800 == 0:
                done = (f - first) / max(1, last - first)
                el = time.time() - t0
                print(f"{done:6.1%}  elapsed {el / 60:5.1f} min  eta {el / max(done, 1e-6) * (1 - done) / 60:5.1f} min", flush=True)
        f += 1
    cap.release()
    np.savez_compressed(out / "balls.npz", balls=np.array(balls, dtype=np.float32).reshape(-1, 7))
    info = {"detections": len(balls), "seconds": round(time.time() - t0, 1)}
    (out / "balls.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
