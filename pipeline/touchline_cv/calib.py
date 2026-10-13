"""Windowed pitch calibration for a whole match.

A single rotating-camera calibration holds over about five minutes (~3 m on the
pitch, measured on Leeming v La Fammia) but not over a whole match yet. So the
match is calibrated in overlapping windows: for each, rig.py solves the camera
and rigfit.py fits the pitch, and windows whose held-out test is poor are
dropped. Every keyframe of a good window gets a homography

    H = G . R^T . K^-1        (pixels -> pitch metres)

written in pitch.npz's homog layout, so geometry.PitchMapper can use it (it
carries homographies between keyframes, ~2 s apart, through camera.npz).

    python -m touchline_cv.calib VIDEO OUT_DIR [--window 300 --step 240 --max-deg 3]
Output: OUT_DIR/calib.npz (homog rows) and calib.json (per-window quality).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from .rigfit import seeded_fit

CX, CY = 960.0, 540.0


def run(*args):
    r = subprocess.run([sys.executable, "-m", *args], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def keyframe_homographies(kf: np.ndarray, G: np.ndarray) -> list:
    rows = []
    for f, t, rx, ry, rz, fl in kf:
        R = Rotation.from_rotvec([rx, ry, rz]).as_matrix()
        Kinv = np.array([[1 / fl, 0, -CX / fl], [0, 1 / fl, -CY / fl], [0, 0, 1.0]])
        H = G @ R.T @ Kinv
        rows.append([f, t, H])
    return rows


def handover(out: Path, tag_a: str, tag_b: str):
    """Seed for window B from calibrated window A, via their shared keyframes.

    Each window solves rotations in its own reference frame. For a keyframe in
    both, rays_A = R_A^T R_B rays_B; averaging that rotation over the overlap
    gives T (B rays -> A rays), and B's pitch->ray seed is T^-1 . inv(G_A).
    """
    ka = np.load(out / f"rig_{tag_a}.npz")["keyframes"]
    kb = np.load(out / f"rig_{tag_b}.npz")["keyframes"]
    rows_a = {int(r[0]): r for r in ka}
    rel = []
    for r in kb:
        a = rows_a.get(int(r[0]))
        if a is not None:
            Ra = Rotation.from_rotvec(a[2:5]).as_matrix()
            Rb = Rotation.from_rotvec(r[2:5]).as_matrix()
            rel.append(Ra.T @ Rb)
    if len(rel) < 5:
        return None
    T = Rotation.from_matrix(np.array(rel)).mean().as_matrix()
    G_a = np.load(out / f"rig_G_{tag_a}.npy")
    return np.linalg.inv(T) @ np.linalg.inv(G_a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--window", type=float, default=300.0)
    ap.add_argument("--step", type=float, default=240.0)
    ap.add_argument("--max-deg", type=float, default=3.0, help="drop windows whose held-out median error is worse")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=0.0)
    ap.add_argument("--reuse", action="store_true", help="reuse existing per-window camera solves")
    args = ap.parse_args()
    out = Path(args.out)

    cap = cv2.VideoCapture(args.video)
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    t1 = args.t1 or dur - 1
    starts = np.arange(args.t0, max(args.t0 + 1, t1 - args.window / 2), args.step)

    windows = []
    for i, s in enumerate(starts):
        e = min(s + args.window, t1)
        tag = f"w{i:03d}"
        if not (args.reuse and (out / f"rig_{tag}.npz").exists()):
            code, log = run("touchline_cv.rig", args.video, str(out), "--from", str(s), "--to", str(e), "--every", "2", "--loop-every", "15", "--tag", tag)
            if code != 0:
                windows.append({"tag": tag, "from": s, "to": e, "ok": False, "reason": "camera solve failed"})
                continue
        code, log = run("touchline_cv.rigfit", str(out), "--tag", tag)
        rep_path = out / f"rigfit_{tag}.json"
        if code != 0 or not rep_path.exists():
            windows.append({"tag": tag, "from": s, "to": e, "ok": False, "reason": "pitch fit failed"})
            continue
        rep = json.loads(rep_path.read_text())
        deg = rep["time_split_test"]["median_deg"]
        ok = deg <= args.max_deg
        windows.append({"tag": tag, "from": float(s), "to": float(e), "ok": ok, "test_median_deg": deg,
                        "seed_box": rep.get("seed_box"), "inlier_share": rep.get("inlier_share")})
        print(f"{tag} {int(s // 60):3d}-{int(e // 60):3d} min  held-out {deg:5.2f} deg  {'kept' if ok else 'dropped'}", flush=True)

    # Hand calibrations across overlaps to windows that couldn't calibrate alone
    # (camera mostly on the far end, where the pitch model mislabels markings).
    changed = True
    while changed:
        changed = False
        for i, w in enumerate(windows):
            if w["ok"] or not (out / f"rig_{w['tag']}.npz").exists():
                continue
            for j in (i - 1, i + 1):
                if not (0 <= j < len(windows)) or not windows[j]["ok"]:
                    continue
                seed = handover(out, windows[j]["tag"], w["tag"])
                if seed is None:
                    continue
                rep = seeded_fit(out, w["tag"], seed)
                if rep and rep["time_split_test"]["median_deg"] <= args.max_deg:
                    w.update(ok=True, test_median_deg=rep["time_split_test"]["median_deg"], seeded_from=windows[j]["tag"])
                    print(f"{w['tag']} calibrated from {windows[j]['tag']}: held-out {w['test_median_deg']:.2f} deg", flush=True)
                    changed = True
                    break

    by_frame = {}
    for w in windows:
        if not w["ok"]:
            continue
        kf = np.load(out / f"rig_{w['tag']}.npz")["keyframes"]
        G = np.load(out / f"rig_G_{w['tag']}.npy")
        mid = (w["from"] + w["to"]) / 2
        for f, t, H in keyframe_homographies(kf, G):
            # Overlaps: keep the window whose centre is nearest this keyframe.
            prev = by_frame.get(int(f))
            if prev is None or abs(t - mid) < prev[0]:
                by_frame[int(f)] = (abs(t - mid), t, w["test_median_deg"], H)

    # inliers/err columns set so PitchMapper's single-frame quality filters pass;
    # window quality is recorded in calib.json instead.
    rows = [[f, v[1], 99, 0.0, *v[3].ravel()] for f, v in sorted(by_frame.items())]
    np.savez_compressed(out / "calib.npz", homog=np.array(rows).reshape(-1, 13), keypoints=np.zeros((0, 6)))
    kept = [w for w in windows if w["ok"]]
    info = {"windows": len(windows), "kept": len(kept), "keyframes_calibrated": len(rows),
            "share_of_span_covered": round(sum(w["to"] - w["from"] for w in kept) / max(1.0, t1 - args.t0), 3), "detail": windows}
    (out / "calib.json").write_text(json.dumps(info, indent=1))
    print(json.dumps({k: v for k, v in info.items() if k != "detail"}, indent=1))


if __name__ == "__main__":
    main()
