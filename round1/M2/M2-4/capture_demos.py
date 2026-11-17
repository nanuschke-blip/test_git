"""从追踪结果里自动挑出考核要求的几个关键画面，存成 results/demo_*.png

挑选逻辑全部基于 results/track_log.json（不靠手工截屏，换视频可复现）：
    demo_1_multitarget  同帧存活航迹最多的一帧
    demo_2_crossing     两条航迹框重叠度最高的一帧（没有重叠就退化成“最近距离”并如实标注）
    demo_3_occlusion    预测帧数 k 最大的一帧（黄色虚线 PREDICTED 最明显）
    demo_4_reentry      目标消失后又出现、且被分配了新 ID 的那一帧
    demo_5_static       最长静止航迹的中间帧

用法:
    python capture_demos.py
"""
import os
import json

import cv2
import numpy as np

LOG = "results/track_log.json"
VIDEO = "results/tracked.mp4"      # 用已经画好框的追踪视频截图，保证截图和视频一致
FALLBACK_VIDEO = "videos/my_scene.mp4"
OUT_DIR = "results"


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def pick(log):
    frames = log["frames"]
    picks = {}

    # 1) 多目标并行：存活航迹最多的帧（跳过片头 10 s，避免挑到刚开机那几帧）
    cand = [f for f in frames if f["frame"] >= 300] or frames
    best = max(cand, key=lambda f: len(f["boxes"]))
    picks["demo_1_multitarget"] = (best["frame"],
                                   f"multi-target: {len(best['boxes'])} tracks alive")

    # 2) 交叉/重叠：两条框 IoU 最大；否则最近中心距离
    bi, bd = None, 1e9
    bframe = frames[0]["frame"]
    for f in frames:
        ids = list(f["boxes"].keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = f["boxes"][ids[i]], f["boxes"][ids[j]]
                v = iou(a, b)
                if bi is None or v > bi[0]:
                    bi = (v, f["frame"], ids[i], ids[j])
                ca, cb = center(a), center(b)
                d = ((ca[0] - cb[0]) ** 2 + (ca[1] - cb[1]) ** 2) ** 0.5
                if d < bd:
                    bd, bframe = d, f["frame"]
    if bi and bi[0] > 0.35:
        picks["demo_2_crossing"] = (bi[1],
                                    f"two targets overlapping, IoU={bi[0]:.2f} "
                                    f"(ID {bi[2]} / ID {bi[3]})")
    elif bi:
        picks["demo_2_crossing"] = (bi[1],
                                    f"closest approach, boxes overlap IoU={bi[0]:.2f} "
                                    f"(ID {bi[2]} / ID {bi[3]})")
    else:
        picks["demo_2_crossing"] = (bframe, f"closest approach: {bd:.0f} px between two targets")

    # 3) 遮挡预测：k 最大的预测帧（跳过开头 15 s，避免抓到刚开机那段）
    MIN_T = 450
    bestk, bestf = -1, None
    for f in frames:
        if f["frame"] < MIN_T:
            continue
        for tid, box, k in f["predicted"]:
            if k > bestk:
                bestk, bestf = k, (f["frame"], tid)
    if bestf is None:                      # 退化：不限制时间
        for f in frames:
            for tid, box, k in f["predicted"]:
                if k > bestk:
                    bestk, bestf = k, (f["frame"], tid)
    if bestf:
        picks["demo_3_occlusion"] = (bestf[0],
                                     f"occluded: ID {bestf[1]} predicted for {bestk} frames "
                                     f"(dashed = PREDICTED, max_age=10)")

    # 4) 目标重入：新 ID 出生时与近期死亡的同类航迹位置重合（同样跳过开头）
    deaths = log["deaths"]
    reentry = None
    for b in log["births"]:
        if b["frame"] < MIN_T:
            continue
        cand = [d for d in deaths if d["cls"] == b["cls"]
                and 0 < b["frame"] - d["frame"] <= 90]
        if not cand:
            continue
        d = max(cand, key=lambda x: x["frame"])
        if iou(b["bbox"], d["bbox"]) > 0.1:
            reentry = (b["frame"], b["id"], d["id"], b["frame"] - d["frame"])
            break
    if reentry:
        picks["demo_4_reentry"] = (reentry[0],
                                   f"re-entry: old ID {reentry[2]} lost, new ID {reentry[1]} "
                                   f"issued after {reentry[3]} frames (ID never reused)")

    # 5) 静止目标：滑动窗口找"中心几乎不动"的最长连续段（允许 5 帧以内的检测断档）
    per_id = {}
    for f in frames:
        for tid, box in f["boxes"].items():
            per_id.setdefault(tid, []).append((f["frame"], box))
    best = None
    for tid, seq in per_id.items():
        fs = [f for f, _ in seq]
        cs = np.array([center(b) for _, b in seq])
        i = 0
        while i < len(seq):
            j = i
            while j + 1 < len(seq):
                if fs[j + 1] - fs[j] > 5:
                    break
                if np.linalg.norm(cs[j + 1] - cs[i]) > 12.0:
                    break
                j += 1
            span = fs[j] - fs[i] + 1
            drift = float(np.linalg.norm(cs[j] - cs[i]))
            if best is None or span > best[0]:
                best = (span, fs[i], fs[j], tid, drift)
            i = j + 1 if j > i else i + 1
    if best and best[0] >= 60:
        span, f0, f1, tid, drift = best
        picks["demo_5_static"] = ((f0 + f1) // 2,
                                  f"static target ID {tid}: {span} frames "
                                  f"({span / 30.0:.1f} s), drift {drift:.1f} px")
    return picks


def annotate(img, line1, line2):
    h, w = img.shape[:2]
    bar = 74
    canvas = np.zeros((h + bar, w, 3), np.uint8)
    canvas[:h] = img
    cv2.rectangle(canvas, (0, h), (w, h + bar), (24, 24, 24), -1)
    cv2.putText(canvas, line1, (14, h + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.72,
                (80, 240, 80), 2, cv2.LINE_AA)
    cv2.putText(canvas, line2, (14, h + 58), cv2.FONT_HERSHEY_SIMPLEX, 0.56,
                (230, 230, 230), 1, cv2.LINE_AA)
    return canvas


def main():
    with open(LOG) as f:
        log = json.load(f)
    picks = pick(log)
    src = VIDEO if os.path.exists(VIDEO) else FALLBACK_VIDEO
    cap = cv2.VideoCapture(src)
    print(f"[info] reading frames from {src}")
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, (fi, desc) in sorted(picks.items()):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fi))
        ok, img = cap.read()
        if not ok:
            print(f"[warn] cannot read frame {fi} for {name}")
            continue
        out = os.path.join(OUT_DIR, f"{name}.png")
        cv2.imwrite(out, annotate(img, name.replace("_", " "), f"{desc}   |   frame {fi}"))
        print(f"[ok] {out}  frame={fi}  {desc}")
    cap.release()

    with open(os.path.join(OUT_DIR, "demo_picks.json"), "w") as f:
        json.dump({k: {"frame": int(v[0]), "desc": v[1]} for k, v in picks.items()},
                  f, indent=1)


if __name__ == "__main__":
    main()
