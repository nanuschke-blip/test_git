"""验证 PT 与 ONNX 两个模型在**同一批图**上的一致性（题面 §6.3）

做法：取 test 集（6 张）全部强制 640x640 输入，消除 letterbox 还原时的浮点差异，
逐张比较置信度最高的框的 xyxy 与 conf，报每张的值和全批最大值。

用法:
    python check_final_consistency.py
"""
import os
import json

import cv2
import numpy as np
from ultralytics import YOLO

PT = "models/best.pt"
ONNX = "models/best.onnx"
OUT = "docs/consistency_result.json"


def load_images():
    """优先用 test 集，退化到 data/images 里任意 6 张"""
    imgs = []
    test_list = "data/splits/test.txt"
    if os.path.exists(test_list):
        names = [os.path.basename(x.strip()) for x in open(test_list) if x.strip()]
        imgs = [os.path.join("data/images", n) for n in names]
        imgs = [p for p in imgs if os.path.exists(p)]
    if not imgs:
        import glob
        imgs = sorted(glob.glob("data/images/*.jpg"))[:6]
    return imgs


def main():
    model_pt = YOLO(PT)
    model_onnx = YOLO(ONNX)
    imgs = load_images()
    print(f"[consistency] {len(imgs)} images (test split), input forced to 640x640")

    rows = []
    worst_box = worst_conf = 0.0
    for p in imgs:
        img = cv2.imread(p)
        img = cv2.resize(img, (640, 640))
        r_pt = model_pt.predict(img, imgsz=640, verbose=False)[0]
        r_onnx = model_onnx.predict(img, imgsz=640, verbose=False)[0]
        if len(r_pt.boxes) == 0 or len(r_onnx.boxes) == 0:
            print(f"  {os.path.basename(p):16s} 跳过（有一侧没检到目标）")
            continue
        box_pt = r_pt.boxes.xyxy[0].cpu().numpy()
        conf_pt = float(r_pt.boxes.conf[0])
        box_onnx = r_onnx.boxes.xyxy[0].cpu().numpy()
        conf_onnx = float(r_onnx.boxes.conf[0])
        d_box = float(np.max(np.abs(box_pt - box_onnx)))
        d_conf = abs(conf_pt - conf_onnx)
        worst_box = max(worst_box, d_box)
        worst_conf = max(worst_conf, d_conf)
        rows.append({"image": os.path.basename(p), "box_pt": box_pt.tolist(),
                     "box_onnx": box_onnx.tolist(), "conf_pt": conf_pt,
                     "conf_onnx": conf_onnx, "delta_box_px": d_box,
                     "delta_conf": d_conf})
        print(f"  {os.path.basename(p):16s} max|d_box|={d_box:.8f} px   "
              f"max|d_conf|={d_conf:.8f}")

    if not rows:
        raise SystemExit("没有可比对的图片")
    print(f"\n[consistency] 全批最大偏差: max|d_box|={worst_box:.8f} px, "
          f"max|d_conf|={worst_conf:.8f}")

    os.makedirs("docs", exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"images": rows, "n": len(rows),
                   "max_delta_box_px": worst_box, "max_delta_conf": worst_conf}, f,
                  indent=1)
    print(f"[ok] {OUT}")


if __name__ == "__main__":
    main()
