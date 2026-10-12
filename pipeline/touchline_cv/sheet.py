"""Contact sheet of frames around a moment, for checking detections by eye.

    python -m touchline_cv.sheet VIDEO 512.4 [--before 2 --after 3 --n 8] [--out sheet.jpg]
"""

from __future__ import annotations

import argparse

import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("t", type=float, help="video seconds")
    ap.add_argument("--before", type=float, default=2.0)
    ap.add_argument("--after", type=float, default=3.0)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--width", type=int, default=640, help="width of each tile")
    ap.add_argument("--out", default="sheet.jpg")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    tiles = []
    for ts in np.linspace(args.t - args.before, args.t + args.after, args.n):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, ts) * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h = int(frame.shape[0] * args.width / frame.shape[1])
        tile = cv2.resize(frame, (args.width, h), interpolation=cv2.INTER_AREA)
        label = f"{int(ts // 60)}:{ts % 60:05.2f}"
        cv2.putText(tile, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4)
        cv2.putText(tile, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        tiles.append(tile)
    cap.release()
    cols = 2
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i : i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(args.out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(args.out)


if __name__ == "__main__":
    main()
