"""失败样本分析：找出 val/test 上"为什么错"，并把每张失败图画出来

分类规则（IoU 阈值 0.5，类别必须一致）：
    漏检   GT 框没有任何预测与之 IoU>=0.5
    误检   预测框没有任何 GT 与之 IoU>=0.5
    框偏移 匹配上了但 IoU 在 0.3~0.5
    类别混淆 位置对得上（IoU>=0.5）却报了另一个类名

输出：
    docs/failure_cases.png    一张总图（最多 8 个失败样本，绿=GT，红=预测）
    docs/failure_cases.json   每个失败样本的明细（含人工归因 reason）

用法:
    python analyze_failures.py
"""
import os
import glob
import json

import cv2
import numpy as np
from ultralytics import YOLO

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
CONF = 0.25
IOU_MATCH = 0.5
IOU_WEAK = 0.3
IOU_GOOD = 0.75      # 达到这个才算"框贴合"；低于它计入失败样本（对应 mAP@0.5:0.95 的失分）

# 人工归因（看图后填写；key = 图片名#序号）
REASONS = {
}


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def read_gt(path):
    lp = os.path.join("data/labels", os.path.basename(path).rsplit(".", 1)[0] + ".txt")
    if not os.path.exists(lp):
        return []
    img = cv2.imread(path)
    h, w = img.shape[:2]
    out = []
    for line in open(lp):
        p = line.split()
        if len(p) != 5:
            continue
        c, cx, cy, bw, bh = int(float(p[0])), *[float(v) for v in p[1:]]
        out.append({"cls": c,
                    "bbox": [(cx - bw / 2) * w, (cy - bh / 2) * h,
                             (cx + bw / 2) * w, (cy + bh / 2) * h]})
    return out


def main():
    model = YOLO("models/best.pt")
    names = [os.path.basename(x.strip()) for x in open("data/splits/test.txt") if x.strip()]
    names += [os.path.basename(x.strip()) for x in open("data/splits/val.txt") if x.strip()]
    paths = [os.path.join("data/images", n) for n in names]

    cases = []
    for p in paths:
        if not os.path.exists(p):
            continue
        gt = read_gt(p)
        r = model.predict(p, imgsz=640, conf=CONF, verbose=False)[0]
        preds = [{"cls": int(b.cls[0]), "conf": float(b.conf[0]),
                  "bbox": [float(v) for v in b.xyxy[0].tolist()]} for b in r.boxes]

        used = set()
        for g in gt:
            best_i, best_iou = None, 0.0
            for i, pr in enumerate(preds):
                if i in used:
                    continue
                v = iou(g["bbox"], pr["bbox"])
                if v > best_iou:
                    best_i, best_iou = i, v
            if best_i is None or best_iou < IOU_WEAK:
                cases.append({"image": os.path.basename(p), "type": "miss",
                              "cls": g["cls"], "iou": round(best_iou, 3),
                              "gt": g["bbox"], "pred": None})
            else:
                used.add(best_i)
                pr = preds[best_i]
                if pr["cls"] != g["cls"] and best_iou >= IOU_MATCH:
                    cases.append({"image": os.path.basename(p), "type": "class",
                                  "cls": g["cls"], "pred_cls": pr["cls"],
                                  "iou": round(best_iou, 3),
                                  "gt": g["bbox"], "pred": pr["bbox"]})
                elif best_iou < IOU_GOOD:
                    cases.append({"image": os.path.basename(p), "type": "shift",
                                  "cls": g["cls"], "iou": round(best_iou, 3),
                                  "gt": g["bbox"], "pred": pr["bbox"]})
        for i, pr in enumerate(preds):
            if i in used:
                continue
            cases.append({"image": os.path.basename(p), "type": "false_pos",
                          "cls": pr["cls"], "conf": round(pr["conf"], 3),
                          "gt": None, "pred": pr["bbox"], "iou": 0.0})

    # 每个失败样本配一张图（同图多处失败只取第一条）
    seen = set()
    picks = []
    for c in cases:
        key = c["image"]
        if key in seen:
            continue
        seen.add(key)
        picks.append(c)
    picks = picks[:8]

    tiles = []
    for idx, c in enumerate(picks):
        img = cv2.imread(os.path.join("data/images", c["image"]))
        h, w = img.shape[:2]
        scale = 420.0 / w
        img = cv2.resize(img, (420, int(h * scale)))
        if c.get("gt"):
            b = [int(v * scale) for v in c["gt"]]
            cv2.rectangle(img, (b[0], b[1]), (b[2], b[3]), (0, 255, 0), 2)
            cv2.putText(img, "GT " + CLASSES[c["cls"]], (b[0], max(b[1] - 5, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
        if c.get("pred"):
            b = [int(v * scale) for v in c["pred"]]
            cv2.rectangle(img, (b[0], b[1]), (b[2], b[3]), (0, 0, 255), 2)
            lab = "P " + (CLASSES[c["pred_cls"]] if "pred_cls" in c else CLASSES[c["cls"]])
            if "conf" in c:
                lab += f" {c['conf']:.2f}"
            cv2.putText(img, lab, (b[0], min(b[3] + 14, img.shape[0] - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)
        caption = f"#{idx+1} {c['type']}  IoU={c.get('iou', 0):.2f}"
        if c.get("pred_cls") is not None:
            caption += f"  GT={CLASSES[c['cls']]}/P={CLASSES[c['pred_cls']]}"
        cv2.rectangle(img, (0, img.shape[0] - 22), (img.shape[1], img.shape[0]),
                      (20, 20, 20), -1)
        cv2.putText(img, caption, (4, img.shape[0] - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (255, 255, 255), 1)
        c["reason"] = REASONS.get(f"{c['image']}#{idx+1}", "")
        tiles.append((c, img))

    if tiles:
        th = max(t[1].shape[0] for t in tiles)
        cols = 4
        rows = (len(tiles) + cols - 1) // cols
        sheet = np.zeros((rows * th, cols * 420, 3), np.uint8)
        for k, (_, im) in enumerate(tiles):
            r, cc = divmod(k, cols)
            sheet[r * th:r * th + im.shape[0], cc * 420:cc * 420 + im.shape[1]] = im
        os.makedirs("docs", exist_ok=True)
        cv2.imwrite("docs/failure_cases.png", sheet)
        print(f"[ok] docs/failure_cases.png  ({len(tiles)} cases)")

    with open("docs/failure_cases.json", "w") as f:
        json.dump({"conf": CONF, "iou_match": IOU_MATCH, "total_failures": len(cases),
                   "picked": [t[0] for t in tiles],
                   "all": cases}, f, indent=1)
    by_type = {}
    for c in cases:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    print(f"[failures] total={len(cases)} by type={by_type}")
    print("[ok] docs/failure_cases.json")


if __name__ == "__main__":
    main()
