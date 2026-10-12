"""Benchmark candidate models on frames from a match, for visual checking.

    python -m touchline_cv.bench pitch VIDEO 300 900 1500 ... --out out/bench
    python -m touchline_cv.bench ball  VIDEO 300 900 1500 ... --out out/bench

pitch: draws detected pitch keypoints (Roboflow sports model) on each frame.
ball:  runs every ball model on each frame and saves a strip of crops around
       each model's best detection, so hits and misses can be judged by eye.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

MODELS = Path(__file__).resolve().parents[1] / "models"


def read_frame(cap, t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    return frame if ok else None


def bench_pitch(cap, times, out):
    model = YOLO(str(MODELS / "rf-pitch.pt"))
    summary = []
    for t in times:
        frame = read_frame(cap, t)
        if frame is None:
            continue
        r = model.predict(frame, imgsz=1280, conf=0.3, verbose=False)[0]
        vis = frame.copy()
        n_good = 0
        if r.keypoints is not None and len(r.keypoints):
            xy = r.keypoints.xy[0].cpu().numpy()
            cf = r.keypoints.conf[0].cpu().numpy() if r.keypoints.conf is not None else np.ones(len(xy))
            for i, ((x, y), c) in enumerate(zip(xy, cf)):
                if c < 0.5 or (x == 0 and y == 0):
                    continue
                n_good += 1
                cv2.circle(vis, (int(x), int(y)), 9, (255, 0, 255), -1)
                cv2.putText(vis, str(i), (int(x) + 10, int(y) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.imwrite(str(out / f"pitch_{int(t):05d}.jpg"), cv2.resize(vis, (1280, 720)), [cv2.IMWRITE_JPEG_QUALITY, 85])
        summary.append({"t": t, "keypoints": n_good})
    return summary


def ball_models():
    ms = {"stock-1920": (YOLO("yolo11m.pt"), 1920, [32])}
    ms["roboflow"] = (YOLO(str(MODELS / "rf-ball.pt")), 1280, None)
    ms["amateur"] = (YOLO(str(MODELS / "amateur-ball.onnx"), task="detect"), 1280, None)
    return ms


def bench_ball(cap, times, out):
    models = ball_models()
    summary = []
    for t in times:
        frame = read_frame(cap, t)
        if frame is None:
            continue
        crops, row = [], {"t": t}
        for name, (m, size, classes) in models.items():
            r = m.predict(frame, imgsz=size, conf=0.05, classes=classes, verbose=False)[0]
            b = r.boxes
            if len(b):
                i = int(b.conf.argmax())
                x1, y1, x2, y2 = b.xyxy[i].cpu().numpy()
                cx, cy, c = (x1 + x2) / 2, (y1 + y2) / 2, float(b.conf[i])
                row[name] = [round(float(cx)), round(float(cy)), round(c, 3)]
                X0, Y0 = int(max(0, cx - 80)), int(max(0, cy - 80))
                crop = frame[Y0 : Y0 + 160, X0 : X0 + 160].copy()
                crop = cv2.resize(crop, (240, 240), interpolation=cv2.INTER_NEAREST)
                cv2.circle(crop, (int((cx - X0) * 1.5), int((cy - Y0) * 1.5)), 16, (255, 0, 255), 2)
            else:
                row[name] = None
                crop = np.zeros((240, 240, 3), np.uint8)
            cv2.putText(crop, f"{name} {row[name][2] if row[name] else '-'}", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            crops.append(crop)
        overview = cv2.resize(frame, (427, 240))
        for name, v in row.items():
            if name != "t" and v:
                cv2.circle(overview, (int(v[0] * 427 / frame.shape[1]), int(v[1] * 240 / frame.shape[0])), 6, (255, 0, 255), 2)
        cv2.imwrite(str(out / f"ball_{int(t):05d}.jpg"), np.hstack([overview] + crops), [cv2.IMWRITE_JPEG_QUALITY, 88])
        summary.append(row)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["pitch", "ball"])
    ap.add_argument("video")
    ap.add_argument("times", nargs="+", type=float)
    ap.add_argument("--out", default="out/bench")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    res = bench_pitch(cap, args.times, out) if args.mode == "pitch" else bench_ball(cap, args.times, out)
    (out / f"{args.mode}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
