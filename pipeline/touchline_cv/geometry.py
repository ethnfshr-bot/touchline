"""Screen -> pitch mapping for any sampled frame.

Pitch homographies are estimated about once a second (pitch.py). For frames
in between, the nearest good homography is carried across using the
frame-to-frame camera motion from track.py:

    H_f = H_s . (motion from f to s)

Pitch coordinates are metres on the 120 x 70 template (see pitch.py).
"""

from __future__ import annotations

import bisect
from pathlib import Path

import numpy as np

from .pitch import LENGTH, WIDTH

MAX_ERR_M = 1.0  # anchor only on homographies whose keypoints fit within this
MIN_INLIERS = 5
MAX_CARRY_S = 30.0  # don't carry a homography further than this


def camera_motion(out_dir: Path, camera_similarity: np.ndarray) -> dict[int, np.ndarray]:
    """frame -> 3x3 mapping the previous sampled frame to this one.

    Prefers the full homographies from camera.py (exact for a rotating camera);
    falls back to the similarity transforms recorded by track.py.
    """
    p = Path(out_dir) / "camera.npz"
    if p.exists():
        return {int(r[0]): r[3:].reshape(3, 3) for r in np.load(p)["H"]}
    return {int(r[0]): np.array([[r[2], -r[3], r[4]], [r[3], r[2], r[5]], [0, 0, 1.0]]) for r in camera_similarity}


class PitchMapper:
    def __init__(self, pitch_npz: Path, motion: dict[int, np.ndarray], fps_sampled: float):
        d = np.load(pitch_npz)
        h = d["homog"]
        good = (h[:, 2] >= MIN_INLIERS) & (h[:, 3] <= MAX_ERR_M)
        h = h[good]
        self.sample_frames = h[:, 0].astype(int).tolist()
        self.H = {int(r[0]): r[4:].reshape(3, 3) for r in h}
        self.frames = sorted(motion)
        self.pos = {f: i for i, f in enumerate(self.frames)}
        self.M = motion
        self.max_carry = int(MAX_CARRY_S * fps_sampled)
        self.cache: dict[int, np.ndarray | None] = {}

    def homography(self, f: int) -> np.ndarray | None:
        """3x3 mapping frame f's pixels to pitch metres, or None if unknown."""
        if f in self.cache:
            return self.cache[f]
        res = None
        if f in self.pos and self.sample_frames:
            i = bisect.bisect_left(self.sample_frames, f)
            cands = [self.sample_frames[j] for j in (i - 1, i) if 0 <= j < len(self.sample_frames)]
            cands = [s for s in cands if s in self.pos and abs(self.pos[s] - self.pos[f]) <= self.max_carry]
            if cands:
                s = min(cands, key=lambda s: abs(self.pos[s] - self.pos[f]))
                T = np.eye(3)  # maps frame f coords -> frame s coords
                a, b = self.pos[f], self.pos[s]
                if b > a:
                    for k in range(a + 1, b + 1):
                        T = self.M[self.frames[k]] @ T
                elif b < a:
                    for k in range(a, b, -1):
                        T = np.linalg.inv(self.M[self.frames[k]]) @ T
                res = self.H[s] @ T
        self.cache[f] = res
        return res

    def to_pitch(self, f: int, x: float, y: float) -> tuple[float, float] | None:
        H = self.homography(f)
        if H is None:
            return None
        v = H @ np.array([x, y, 1.0])
        if abs(v[2]) < 1e-9:
            return None
        return float(v[0] / v[2]), float(v[1] / v[2])


def on_pitch(p, margin: float = 2.0) -> bool:
    return p is not None and -margin <= p[0] <= LENGTH + margin and -margin <= p[1] <= WIDTH + margin
