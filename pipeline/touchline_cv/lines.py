"""White pitch-line extraction for line-based calibration.

No learned labels: pitch lines are thin, bright, low-saturation ridges on
grass. Steps:
  1. pitch area: the largest connected grass region with its holes filled
     (removes sky, trees, fences; keeps line pixels and players inside it);
  2. ridge strength: white top-hat on lightness at two scales (thin far lines,
     wider near lines), thresholded against local contrast;
  3. shape: keep elongated connected pieces only (drops flags, cones, shirts,
     bibs), optionally masking out person boxes.

    python -m touchline_cv.lines VIDEO 150 500 700 --out out/bench/lines.jpg
"""

from __future__ import annotations

import argparse

import cv2
import numpy as np


def pitch_area(hsv: np.ndarray) -> np.ndarray:
    g = ((hsv[..., 0] >= 28) & (hsv[..., 0] <= 95) & (hsv[..., 1] >= 45) & (hsv[..., 2] >= 50)).astype(np.uint8)
    g = cv2.morphologyEx(g, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(g, connectivity=4)
    if n <= 1:
        return g
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    area = (lab == big).astype(np.uint8)
    # Fill holes (lines, players) by flood-filling the background from the borders.
    inv = 1 - area
    h, w = area.shape
    ff = inv.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    for x in range(0, w, 50):
        for y in (0, h - 1):
            if ff[y, x]:
                cv2.floodFill(ff, mask, (x, y), 0)
    for y in range(0, h, 50):
        for x in (0, w - 1):
            if ff[y, x]:
                cv2.floodFill(ff, mask, (x, y), 0)
    return np.maximum(area, ff)  # ff now holds only enclosed holes


def line_mask(frame_bgr: np.ndarray, person_boxes=None, min_len=25, min_elong=4.0) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    L = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    area = pitch_area(hsv)
    # Shrink the pitch area a little so its boundary (fence line, tree line) isn't picked up.
    area = cv2.erode(area, np.ones((5, 5), np.uint8))
    th_small = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    th_big = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    th_wide = cv2.morphologyEx(L, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (27, 27)))
    ridge = np.maximum(np.maximum(th_small, th_big), th_wide * 0.8)
    # Local contrast: grass texture varies across the pitch, so threshold relative to it.
    local = cv2.blur(np.abs(L - cv2.blur(L, (31, 31))), (31, 31))
    cand = (ridge > np.maximum(4.0, 1.3 * local)) & (hsv[..., 1] < 120) & (area > 0)
    cand = cand.astype(np.uint8)
    if person_boxes is not None:
        for x1, y1, x2, y2 in np.asarray(person_boxes, int):
            cand[max(0, y1 - 4) : y2 + 4, max(0, x1 - 4) : x2 + 4] = 0
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 8:
            continue
        ys, xs = np.where(lab[stats[i, 1] : stats[i, 1] + stats[i, 3], stats[i, 0] : stats[i, 0] + stats[i, 2]] == i)
        pts = np.c_[xs, ys].astype(np.float32)
        (_, _), (w, h), _ = cv2.minAreaRect(pts)
        length, width = max(w, h), max(1.0, min(w, h))
        keep[i] = length >= min_len and length / width >= min_elong
    return keep[lab].astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("times", nargs="+", type=float)
    ap.add_argument("--out", default="out/bench/lines.jpg")
    args = ap.parse_args()
    cap = cv2.VideoCapture(args.video)
    tiles = []
    for t in args.times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, f = cap.read()
        if not ok:
            continue
        m = line_mask(f)
        vis = f.copy()
        vis[m > 0] = (255, 0, 255)
        cv2.putText(vis, f"{t:.0f}s", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)
        tiles.append(cv2.resize(vis, (960, 540)))
    while len(tiles) % 2:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(args.out, np.vstack([np.hstack(tiles[i : i + 2]) for i in range(0, len(tiles), 2)]), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(args.out)


if __name__ == "__main__":
    main()
