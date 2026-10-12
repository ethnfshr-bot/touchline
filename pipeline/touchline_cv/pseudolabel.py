"""Build a ball/person training set from match videos, without hand labelling.

A large "teacher" model scans short bursts of consecutive frames at high
resolution (tiled). Ball candidates are kept only when they form a plausible
track across the burst, after compensating for camera motion:
  - moving chains of >= MIN_CHAIN frames are kept anywhere;
  - static chains are kept only next to an outfield player (a ball at a
    player's feet), which rejects bottles, cones and bibs near the bench.
Person boxes come from the teacher's full-frame pass.

Output is a YOLO-format dataset: <out>/images/{train,val}, <out>/labels/{train,val}.

    python -m touchline_cv.pseudolabel VIDEO [VIDEO ...] --out pipeline/out/balldata
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from .track import CameraMotion

PERSON, BALL = 0, 32
MIN_CHAIN = 5
TILE = 1280
OVERLAP = 256


def tiles(w, h, size=TILE, overlap=OVERLAP):
    step = size - overlap
    xs = list(range(0, max(w - size, 0) + 1, step))
    ys = list(range(0, max(h - size, 0) + 1, step))
    if xs[-1] + size < w:
        xs.append(w - size)
    if ys[-1] + size < h:
        ys.append(h - size)
    return [(x, y) for y in ys for x in xs]


def teacher_frame(model, frame, ball_conf=0.05):
    """Persons from a full-frame pass; ball candidates from tiles."""
    h, w = frame.shape[:2]
    r = model.predict(frame, imgsz=1920, conf=0.3, classes=[PERSON], verbose=False)[0]
    persons = r.boxes.xyxy.cpu().numpy()
    crops = [frame[y : y + TILE, x : x + TILE] for x, y in tiles(w, h)]
    offs = tiles(w, h)
    balls = []
    for res, (ox, oy) in zip(model.predict(crops, imgsz=TILE, conf=ball_conf, classes=[BALL], verbose=False), offs):
        for b, c in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy()):
            balls.append([b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy, float(c)])
    return persons, np.array(balls).reshape(-1, 5)


def link_chains(cands, motions, gate=60.0):
    """Greedy linking of ball candidates across a burst.

    cands[i]: (n_i, 5) boxes in frame i; motions[i]: 3x3 mapping frame i-1 -> i.
    Returns chains as lists of (frame_index, candidate_index).
    """
    chains = []
    active = []  # (chain, last_xy in its frame coords)
    for i, boxes in enumerate(cands):
        centres = (boxes[:, :2] + boxes[:, 2:4]) / 2 if len(boxes) else np.zeros((0, 2))
        used = set()
        nxt = []
        for chain, (lx, ly) in active:
            if i > 0:
                v = motions[i] @ np.array([lx, ly, 1.0])
                lx, ly = v[0], v[1]
            if len(centres):
                d = np.hypot(centres[:, 0] - lx, centres[:, 1] - ly)
                d[list(used)] = np.inf
                j = int(np.argmin(d))
                if d[j] <= gate:
                    used.add(j)
                    chain.append((i, j))
                    nxt.append((chain, tuple(centres[j])))
                    continue
            chains.append(chain)
        for j in range(len(centres)):
            if j not in used:
                nxt.append(([(i, j)], tuple(centres[j])))
        active = nxt
    chains.extend(c for c, _ in active)
    return chains


def chain_is_ball(chain, cands, motions, persons):
    if len(chain) < MIN_CHAIN:
        return False
    # Camera-compensated travel over the chain.
    (i0, j0), (i1, j1) = chain[0], chain[-1]
    p = (cands[i0][j0, :2] + cands[i0][j0, 2:4]) / 2
    for k in range(i0 + 1, i1 + 1):
        v = motions[k] @ np.array([p[0], p[1], 1.0])
        p = v[:2]
    q = (cands[i1][j1, :2] + cands[i1][j1, 2:4]) / 2
    if np.hypot(*(q - p)) > 6.0:
        return True
    # Static: only next to a player's feet.
    ppl = persons[i1]
    if len(ppl) == 0:
        return False
    feet = np.stack([(ppl[:, 0] + ppl[:, 2]) / 2, ppl[:, 3]], 1)
    hgt = ppl[:, 3] - ppl[:, 1]
    d = np.hypot(feet[:, 0] - q[0], feet[:, 1] - q[1]) / np.maximum(hgt, 8)
    return bool(d.min() < 0.6)


def yolo_line(cls, box, w, h):
    x1, y1, x2, y2 = box[:4]
    return f"{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--teacher", default="yolo11x.pt")
    ap.add_argument("--every", type=float, default=12.0, help="seconds between bursts")
    ap.add_argument("--burst", type=int, default=10, help="consecutive sampled frames per burst")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--keep", type=int, default=2, help="frames saved per burst")
    ap.add_argument("--val-share", type=float, default=0.15)
    args = ap.parse_args()

    out = Path(args.out)
    for split in ("train", "val"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
    model = YOLO(args.teacher)
    rng = random.Random(0)
    stats = {"bursts": 0, "frames": 0, "ball_labels": 0, "frames_without_ball": 0}

    for video in args.videos:
        stem = Path(video).stem[:40]
        cap = cv2.VideoCapture(video)
        src_fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        stride = max(1, round(src_fps / args.fps))
        for start in range(0, total - args.burst * stride, int(args.every * src_fps)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            frames, cands, persons, motions = [], [], [], []
            cam = CameraMotion(w)
            for k in range(args.burst * stride):
                ok = cap.grab()
                if not ok:
                    break
                if k % stride:
                    continue
                ok, fr = cap.retrieve()
                if not ok:
                    break
                ppl, balls = teacher_frame(model, fr)
                a, b, tx, ty, _ = cam.update(fr, ppl)
                motions.append(np.array([[a, -b, tx], [b, a, ty], [0, 0, 1.0]]))
                frames.append(fr)
                cands.append(balls)
                persons.append(ppl)
            if len(frames) < args.burst:
                continue
            stats["bursts"] += 1
            chains = link_chains(cands, motions)
            ball_of = {}
            for ch in chains:
                if chain_is_ball(ch, cands, motions, persons):
                    for i, j in ch:
                        if i not in ball_of or cands[i][j, 4] > ball_of[i][4]:
                            ball_of[i] = cands[i][j]
            # Save a few frames per burst, preferring ones with a confirmed ball.
            order = sorted(range(len(frames)), key=lambda i: (i not in ball_of, rng.random()))
            split = "val" if rng.random() < args.val_share else "train"
            for i in order[: args.keep]:
                name = f"{stem}_{start + i * stride:07d}"
                cv2.imwrite(str(out / "images" / split / f"{name}.jpg"), frames[i], [cv2.IMWRITE_JPEG_QUALITY, 92])
                lines = [yolo_line(1, p, w, h) for p in persons[i]]
                if i in ball_of:
                    lines.append(yolo_line(0, ball_of[i], w, h))
                    stats["ball_labels"] += 1
                else:
                    stats["frames_without_ball"] += 1
                (out / "labels" / split / f"{name}.txt").write_text("\n".join(lines) + "\n")
                stats["frames"] += 1
            if stats["bursts"] % 25 == 0:
                print(json.dumps(stats), flush=True)
        cap.release()

    (out / "data.yaml").write_text(
        f"path: {out.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: ball\n  1: person\n"
    )
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
