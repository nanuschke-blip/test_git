"""在 val/test 上算出混淆矩阵的**数值**（题面表 4 要求"混淆矩阵里体现为多少"）

做法：按 IoU>=0.5、类别必须一致才算命中；对每个 GT 找 IoU 最大的预测，
统计 (GT 类, 预测类) 计数，另外把"没有预测对上"记为背景（miss），
"预测没对上任何 GT"也记背景（false positive）。

输出 docs/confusion_counts.json
"""
import os
import json

import cv2
import numpy as np
from ultralytics import YOLO

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
BG = "background"
CONF = 0.25
IOU_MATCH = 0.5


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def read_gt(path):
    lp = os.path.join("data/labels", os.path.basename(path).rsplit(".", 1)[0] + ".txt")
    img = cv2.imread(path)
    h, w = img.shape[:2]
    out = []
    for line in open(lp):
        p = line.split()
        if len(p) != 5:
            continue
        c = int(float(p[0]))
        cx, cy, bw, bh = [float(v) for v in p[1:]]
        out.append({"cls": c, "bbox": [(cx - bw / 2) * w, (cy - bh / 2) * h,
                                       (cx + bw / 2) * w, (cy + bh / 2) * h]})
    return out


def main():
    model = YOLO("models/best.pt")
    names = []
    for split in ("test", "val"):
        names += [os.path.basename(x.strip()) for x in
                  open(f"data/splits/{split}.txt") if x.strip()]

    mat = {g: {p: 0 for p in CLASSES + [BG]} for g in CLASSES + [BG]}
    for n in names:
        p = os.path.join("data/images", n)
        if not os.path.exists(p):
            continue
        gt = read_gt(p)
        r = model.predict(p, imgsz=640, conf=CONF, verbose=False)[0]
        preds = [{"cls": int(b.cls[0]), "bbox": [float(v) for v in b.xyxy[0].tolist()]}
                 for b in r.boxes]
        used = set()
        for g in gt:
            best_i, best_iou = None, 0.0
            for i, pr in enumerate(preds):
                if i in used:
                    continue
                v = iou(g["bbox"], pr["bbox"])
                if v > best_iou:
                    best_i, best_iou = i, v
            if best_i is not None and best_iou >= IOU_MATCH:
                used.add(best_i)
                mat[CLASSES[g["cls"]]][CLASSES[preds[best_i]["cls"]]] += 1
            else:
                mat[CLASSES[g["cls"]]][BG] += 1
        for i in range(len(preds)):
            if i not in used:
                mat[BG][CLASSES[preds[i]["cls"]]] += 1

    os.makedirs("docs", exist_ok=True)
    with open("docs/confusion_counts.json", "w") as f:
        json.dump({"images": len(names), "conf": CONF, "iou_match": IOU_MATCH,
                   "matrix": mat}, f, indent=1)

    print(f"[confusion] {len(names)} images (val+test), IoU>={IOU_MATCH}")
    print("GT \\ Pred " + " ".join(f"{c[:6]:>7s}" for c in CLASSES + [BG]))
    for g in CLASSES + [BG]:
        row = " ".join(f"{mat[g][p]:7d}" for p in CLASSES + [BG])
        print(f"{g:10s} {row}")
    print("[ok] docs/confusion_counts.json")


if __name__ == "__main__":
    main()
