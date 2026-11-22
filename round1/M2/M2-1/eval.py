"""M2-1 评测脚本：读人工标注，跑检测，输出 eval.csv 与摘要表。

标注文件 labels.csv（逗号分隔，表头固定）：
    key,state,cx,cy
    normal.png,Red,1389,816        # 图片目录模式：key=文件名
    120,Red,1389,816               # 视频模式：key=帧号
    60,none,,                      # 该帧没有灯：state=none，cx/cy 留空

用法：
    python3 eval.py --source videos/test.mp4 --ann labels.csv --out eval.csv
    python3 eval.py --source results/ --ann labels.csv --out eval.csv

指标：
    状态准确率、混淆矩阵（Red/Yellow/Green/none）、中心误差 P50/P95、
    漏检率（有灯判 none）、误检率（无灯判有灯）。

注意：检测阈值与 detect.py 保持一致（同一组 H/S/V 区间），改动时两边一起改。
"""
import argparse
import csv
import os
import sys
from collections import Counter

import cv2
import numpy as np

# ---- 与 detect.py 完全一致的阈值 ----
H_RED1 = ((0, 120, 70), (10, 255, 255))
H_RED2 = ((170, 120, 70), (180, 255, 255))
H_YELLOW = ((20, 100, 100), (35, 255, 255))
H_GREEN = ((40, 70, 70), (90, 255, 255))
AREA_MIN, AREA_MAX = 100, 50000
STATES = ["Red", "Yellow", "Green", "none"]


def _mask_ranges(hsv, lo, hi):
    return cv2.inRange(hsv, np.array(lo), np.array(hi))


def analyze(frame):
    """返回 (state, cx, cy, area, radius)；state ∈ Red/Yellow/Green/none。"""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    masks = {
        "Red": _mask_ranges(hsv, *H_RED1) + _mask_ranges(hsv, *H_RED2),
        "Yellow": _mask_ranges(hsv, *H_YELLOW),
        "Green": _mask_ranges(hsv, *H_GREEN),
    }
    kernel = np.ones((5, 5), np.uint8)

    def best(mask):
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        max_area, best_cnt = 0, None
        for c in contours:
            a = cv2.contourArea(c)
            if a > max_area:
                max_area, best_cnt = a, c
        if best_cnt is not None and AREA_MIN < max_area < AREA_MAX:
            (x, y), r = cv2.minEnclosingCircle(best_cnt)
            return float(x), float(y), max_area, float(r)
        return None

    for name in ("Red", "Yellow", "Green"):        # 优先级：红 > 黄 > 绿
        hit = best(masks[name])
        if hit is not None:
            return (name, hit[0], hit[1], hit[2], hit[3])
    return ("none", None, None, 0.0, 0.0)


def load_labels(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            st = (r["state"] or "").strip()
            if not st:
                continue
            cx = float(r["cx"]) if r.get("cx") not in (None, "") else None
            cy = float(r["cy"]) if r.get("cy") not in (None, "") else None
            rows.append(dict(key=r["key"].strip(), state=st, cx=cx, cy=cy))
    return rows


def frames_from_source(source, stride):
    """返回 {key: frame}；目录模式 key=文件名，视频模式 key=帧号(字符串)。"""
    if os.path.isdir(source):
        out = {}
        for name in sorted(os.listdir(source)):
            if name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                img = cv2.imread(os.path.join(source, name))
                if img is not None:
                    out[name] = img
        return out

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"打不开视频: {source}")
    out, idx = {}, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            out[str(idx)] = frame
        idx += 1
    cap.release()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="视频文件或图片目录")
    ap.add_argument("--ann", required=True, help="人工标注 labels.csv")
    ap.add_argument("--out", default="eval.csv")
    ap.add_argument("--stride", type=int, default=1, help="视频抽帧步长（与标注一致）")
    args = ap.parse_args()

    frames = frames_from_source(args.source, args.stride)
    labels = load_labels(args.ann)
    print(f"[eval] source={args.source} 可用帧={len(frames)} 标注={len(labels)}")

    rows = []
    errs = []
    miss = fp = 0
    conf = Counter()
    for lb in labels:
        key = lb["key"]
        if key not in frames:
            print(f"[eval] 跳过（源里没有这一帧）: {key}")
            continue
        st, cx, cy, area, r = analyze(frames[key])
        ok = (st == lb["state"])
        conf[(lb["state"], st)] += 1
        if lb["state"] != "none" and st == "none":
            miss += 1
        if lb["state"] == "none" and st != "none":
            fp += 1
        e = None
        if lb["cx"] is not None and lb["cy"] is not None and cx is not None:
            e = float(np.hypot(cx - lb["cx"], cy - lb["cy"]))
            errs.append(e)
        rows.append(dict(key=key, gt=lb["state"], pred=st, ok=int(ok),
                         gt_cx=lb["cx"], gt_cy=lb["cy"],
                         pred_cx=round(cx, 1) if cx is not None else "",
                         pred_cy=round(cy, 1) if cy is not None else "",
                         area=round(area, 0), radius=round(r, 1),
                         center_err_px=round(e, 2) if e is not None else ""))

    n = len(rows)
    if n == 0:
        print("[eval] 没有可评测的帧，检查 --source / --ann 的 key 是否对得上")
        sys.exit(1)

    acc = sum(r["ok"] for r in rows) / n
    has_light = [r for r in rows if r["gt"] != "none"]
    print("\n===== 摘要表 =====")
    print(f"标注帧数           : {n}")
    print(f"状态准确率         : {acc * 100:.1f}%  ({sum(r['ok'] for r in rows)}/{n})")
    if has_light:
        print(f"漏检率（有灯判none）: {miss / len(has_light) * 100:.1f}%  ({miss}/{len(has_light)})")
    no_light = [r for r in rows if r["gt"] == "none"]
    if no_light:
        print(f"误检率（无灯判有灯）: {fp / len(no_light) * 100:.1f}%  ({fp}/{len(no_light)})")
    if errs:
        print(f"中心误差 P50 / P95 : {np.percentile(errs, 50):.2f} / {np.percentile(errs, 95):.2f} px"
              f"   (n={len(errs)})")
    else:
        print("中心误差 P50 / P95 : 无（标注里没有中心坐标）")

    print("\n混淆矩阵（行=真值, 列=预测）")
    print("        " + "".join(f"{s:>8}" for s in STATES))
    for gt in STATES:
        if not any(conf[(gt, p)] for p in STATES):
            continue
        print(f"{gt:>8}" + "".join(f"{conf[(gt, p)]:>8}" for p in STATES))

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n[eval] 逐帧结果 -> {args.out}")


if __name__ == "__main__":
    main()
