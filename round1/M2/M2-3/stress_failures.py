"""失败样本分析（压力版）：在 test 集上叠加三类扰动，找出模型真正翻车的样本

为什么需要这一步：test 集只有 6 张近景图，模型几乎全对（自然评估只有 1 个漏检），
只贴 1 张失败图既不够、也说明不了问题。题面要的是"能说出模型为什么在**这类**样本上翻车"，
所以这里按现场真实会遇到的三类退化构造压力样本：

    过曝   cv2.convertScaleAbs(alpha=1.6, beta=70)      —— 手电筒直射 / 反光
    遮挡   在 GT 框上盖住约 1/3 的方块                 —— 手指、其它物料挡住
    模糊   GaussianBlur(9) + 压暗到 0.55 倍             —— 手抖 / 逆光欠曝

判定（IoU 阈值）：
    < 0.3   漏检（完全没框住）
    0.3~0.75 框偏移（框住了但不贴合，直接对应 mAP@0.5:0.95 的失分）
    >= 0.5 但类别不同 → 类别混淆
    没有 GT 对得上的预测 → 误检
达到 0.75 才算"贴合"，否则记为失败样本。

输出：
    docs/failure_cases.png    失败样本总图（最多 8 张，绿=GT，红=预测）
    docs/failure_cases.json   明细（含人工归因 reason）

用法:
    python stress_failures.py
"""
import os
import json

import cv2
import numpy as np
from ultralytics import YOLO

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
CONF = 0.25
IOU_WEAK, IOU_MATCH, IOU_GOOD = 0.3, 0.5, 0.75

REASONS = {
    "bottle_08.jpg#1": "压暗到 0.55 倍并高斯模糊后，灰白瓶体与木桌面的对比度被抹平，边缘响应消失，"
                       "模型直接不输出框（bottle 原图只有 10 张，弱光样本更少）。",
    "bottle_08.jpg#2": "灰块盖住瓶体右侧，剩下可见部分太窄，模型没有输出任何框；"
                       "这一类遮挡超过约 40% 就整体失效。",
    "pen_04.jpg#3": "笔的中段被灰块挡住、只剩两端露出，模型给出的框 IoU 仅 0.275（<0.3 视为漏检）。"
                    "细长目标对遮挡最敏感，因为可用的形状线索本来就少。",
    "bottle_08.jpg#4": "过曝后瓶体与桌面的高光融为一体、边界消失，直接漏检——"
                       "这正是 cup/bottle 易混判断在强光下的具体表现。",
    "mouse_06.jpg#5": "鼠标被灰块切掉一半，剩下的圆顶+侧边形状更像手机的圆角矩形；"
                      "两者都是深灰色，颜色线索也同时失效，于是判成 phone（IoU 0.665）。",
    "phone_02.jpg#6": "手机屏幕大面积反光过曝成白色高光块，形状接近杯口/杯身的白色区域，"
                      "被判成 cup（IoU 0.804，位置对、类别错）。",
    "mouse_06.jpg#7": "过曝把背景白墙/门框的高光条误检成 pen（置信度仅 0.27）——"
                      "pen 类对\"细长高光\"敏感，是背景误检的主要来源。",
    "cup_08.jpg#8": "杯子右侧被灰块遮挡，框只覆盖可见的左侧部分，IoU 0.633 低于贴合阈值 0.75。"
                    "这类\"框偏移\"正是 mAP@0.5:0.95 掉分的主因（mAP@0.5 仍算命中）。",
}


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def read_gt(img_path):
    lp = os.path.join("data/labels",
                      os.path.basename(img_path).rsplit(".", 1)[0] + ".txt")
    if not os.path.exists(lp):
        return []
    img = cv2.imread(img_path)
    h, w = img.shape[:2]
    out = []
    for line in open(lp):
        p = line.split()
        if len(p) != 5:
            continue
        c = int(float(p[0]))
        cx, cy, bw, bh = [float(v) for v in p[1:]]
        out.append({"cls": c,
                    "bbox": [(cx - bw / 2) * w, (cy - bh / 2) * h,
                             (cx + bw / 2) * w, (cy + bh / 2) * h]})
    return out


def perturb(img, kind, gt):
    """返回扰动后的图；遮挡会把方块盖在 GT 框内"""
    if kind == "overexpose":
        return cv2.convertScaleAbs(img, alpha=1.6, beta=70)
    if kind == "occlude":
        out = img.copy()
        h, w = out.shape[:2]
        for g in gt:
            x1, y1, x2, y2 = [int(v) for v in g["bbox"]]
            bw, bh = max(x2 - x1, 4), max(y2 - y1, 4)
            # 盖住框的中间偏右 1/3，模拟手指从一侧伸进来
            ox1 = int(x1 + bw * 0.45)
            ox2 = int(min(x1 + bw * 1.05, w))
            oy1 = int(y1 - bh * 0.1)
            oy2 = int(min(y2 + bh * 0.1, h))
            cv2.rectangle(out, (ox1, max(oy1, 0)), (ox2, oy2), (60, 60, 60), -1)
        return out
    if kind == "blur_dark":
        out = cv2.GaussianBlur(img, (9, 9), 0)
        return cv2.convertScaleAbs(out, alpha=0.55, beta=-10)
    return img


def main():
    model = YOLO("models/best.pt")
    names = [os.path.basename(x.strip()) for x in open("data/splits/test.txt") if x.strip()]
    paths = [os.path.join("data/images", n) for n in names if
             os.path.exists(os.path.join("data/images", n))]

    kinds = ["overexpose", "occlude", "blur_dark"]
    cases = []
    for p in paths:
        gt = read_gt(p)
        base = cv2.imread(p)
        for kind in kinds:
            img = perturb(base, kind, gt)
            r = model.predict(img, imgsz=640, conf=CONF, verbose=False)[0]
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
                    cases.append({"image": os.path.basename(p), "perturb": kind,
                                  "type": "miss", "cls": g["cls"],
                                  "iou": round(best_iou, 3), "gt": g["bbox"],
                                  "pred": None, "img": img})
                    continue
                used.add(best_i)
                pr = preds[best_i]
                if pr["cls"] != g["cls"] and best_iou >= IOU_MATCH:
                    cases.append({"image": os.path.basename(p), "perturb": kind,
                                  "type": "class_confusion", "cls": g["cls"],
                                  "pred_cls": pr["cls"], "iou": round(best_iou, 3),
                                  "gt": g["bbox"], "pred": pr["bbox"], "img": img})
                elif best_iou < IOU_GOOD:
                    cases.append({"image": os.path.basename(p), "perturb": kind,
                                  "type": "shift", "cls": g["cls"],
                                  "iou": round(best_iou, 3), "gt": g["bbox"],
                                  "pred": pr["bbox"], "img": img})
            for i, pr in enumerate(preds):
                if i in used:
                    continue
                cases.append({"image": os.path.basename(p), "perturb": kind,
                              "type": "false_pos", "cls": pr["cls"],
                              "conf": round(pr["conf"], 3), "gt": None,
                              "pred": pr["bbox"], "img": img})

    by_type = {}
    by_kind = {}
    for c in cases:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        by_kind[c["perturb"]] = by_kind.get(c["perturb"], 0) + 1
    print(f"[stress] {len(paths)} images x {len(kinds)} perturbations")
    print(f"[stress] failures={len(cases)} by type={by_type} by perturbation={by_kind}")

    # 挑 8 张：三类扰动各覆盖，类型尽量分散
    order = {"miss": 0, "class_confusion": 1, "false_pos": 2, "shift": 3}
    ordered = sorted(cases, key=lambda c: (order.get(c["type"], 9), c["perturb"]))
    picked, seen = [], set()
    for c in ordered:
        key = (c["perturb"], c["image"])
        if key in seen:
            continue
        seen.add(key)
        picked.append(c)
        if len(picked) >= 8:
            break

    tiles = []
    for idx, c in enumerate(picked):
        img = c["img"]
        h, w = img.shape[:2]
        scale = 420.0 / w
        im = cv2.resize(img, (420, int(h * scale)))
        if c.get("gt"):
            b = [int(v * scale) for v in c["gt"]]
            cv2.rectangle(im, (b[0], b[1]), (b[2], b[3]), (0, 255, 0), 2)
            cv2.putText(im, "GT " + CLASSES[c["cls"]], (b[0], max(b[1] - 5, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
        if c.get("pred"):
            b = [int(v * scale) for v in c["pred"]]
            cv2.rectangle(im, (b[0], b[1]), (b[2], b[3]), (0, 0, 255), 2)
            lab = "P " + (CLASSES[c["pred_cls"]] if "pred_cls" in c else CLASSES[c["cls"]])
            if "conf" in c:
                lab += f" {c['conf']:.2f}"
            cv2.putText(im, lab, (b[0], min(b[3] + 14, im.shape[0] - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)
        cap = f"#{idx+1} {c['perturb']} / {c['type']}  IoU={c.get('iou', 0):.2f}"
        if c.get("pred_cls") is not None:
            cap += f"  GT={CLASSES[c['cls']]} P={CLASSES[c['pred_cls']]}"
        cv2.rectangle(im, (0, im.shape[0] - 22), (im.shape[1], im.shape[0]),
                      (20, 20, 20), -1)
        cv2.putText(im, cap, (4, im.shape[0] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (255, 255, 255), 1)
        c["reason"] = REASONS.get(f"{c['image']}#{idx+1}", "")
        tiles.append((c, im))

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
        print(f"[ok] docs/failure_cases.png ({len(tiles)} cases)")

    for c in picked:
        c.pop("img", None)
    with open("docs/failure_cases.json", "w") as f:
        json.dump({"conf": CONF, "iou_good": IOU_GOOD,
                   "by_type": by_type, "by_perturbation": by_kind,
                   "total": len(cases), "picked": picked}, f, indent=1)
    print("[ok] docs/failure_cases.json")


if __name__ == "__main__":
    main()
