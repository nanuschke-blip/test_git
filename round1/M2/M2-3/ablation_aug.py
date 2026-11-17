"""长尾/增强消融实验：只用 43 张原始训练图 vs 加上增强到 703 张，对比 val mAP

题面 §3 的必做项："如果某类样本明显少（长尾），说明你打算怎么处理，并实测处理前后的 mAP 差"。
本项目的长尾：mouse 只有 7 张、phone 12 张（其余 10~12 张），处理办法是每类增强补齐到 120 张。
这里用同样的 8 轮、同样超参，只改"训练集是否含增强图"，测出增强带来的实际增益。

用法:
    python ablation_aug.py
"""
import os
import json
import glob

from ultralytics import YOLO

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
EPOCHS = 8
YAML_NOAUG = "my_data_noaug.yaml"
OUT = "docs/ablation_aug.json"


def build_split():
    names = [x.strip() for x in open("data/splits/train.txt") if x.strip()]
    orig = [p for p in names if "_aug_" not in p]
    with open("data/splits/train_orig.txt", "w") as f:
        f.write("\n".join(orig) + "\n")
    print(f"[ablation] train_orig = {len(orig)} 张（不含增强），train 全量 = {len(names)} 张")
    with open(YAML_NOAUG, "w") as f:
        f.write("path: .\n")
        f.write("train: data/splits/train_orig.txt\n")
        f.write("val: data/splits/val.txt\n")
        f.write("names:\n")
        for i, c in enumerate(CLASSES):
            f.write(f"  {i}: {c}\n")
    return len(orig), len(names)


def main():
    n_orig, n_full = build_split()

    print(f"[ablation] 训练无增强版本：{n_orig} 张 / {EPOCHS} 轮")
    model = YOLO("yolov8n.pt")
    model.train(data=YAML_NOAUG, epochs=EPOCHS, imgsz=640, batch=8, device="cpu",
                workers=4, seed=42, project="runs/detect", name="ablation_noaug",
                exist_ok=True, mosaic=0.5, close_mosaic=3, degrees=5.0,
                translate=0.1, scale=0.3, fliplr=0.5)

    print("[ablation] 在同一个 val 集上评估")
    import glob as _glob
    cand = _glob.glob("runs/detect/**/ablation_noaug/weights/best.pt", recursive=True)
    if not cand:
        raise SystemExit("找不到消融实验权重")
    best = max(cand, key=os.path.getmtime)
    m = YOLO(best).val(data=YAML_NOAUG, split="val", verbose=False)
    noaug = {"images": n_orig, "mAP50": float(m.box.map50), "mAP50-95": float(m.box.map),
             "precision": float(m.box.mp), "recall": float(m.box.mr)}

    with open("docs/eval_metrics.json") as f:
        cur = json.load(f)["val"]
    aug = {"images": n_full, "mAP50": cur["mAP50"], "mAP50-95": cur["mAP50-95"],
           "precision": cur["precision"], "recall": cur["recall"]}

    res = {"epochs": EPOCHS,
           "no_aug": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in noaug.items()},
           "with_aug": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in aug.items()}}
    res["delta_mAP50-95"] = round(aug["mAP50-95"] - noaug["mAP50-95"], 4)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)

    print(f"[ablation] 无增强 {n_orig} 张: mAP@0.5={noaug['mAP50']:.4f} "
          f"mAP@0.5:0.95={noaug['mAP50-95']:.4f}")
    print(f"[ablation] 有增强 {n_full} 张: mAP@0.5={aug['mAP50']:.4f} "
          f"mAP@0.5:0.95={aug['mAP50-95']:.4f}")
    print(f"[ablation] ΔmAP@0.5:0.95 = {res['delta_mAP50-95']:+.4f}")
    print(f"[ok] {OUT}")


if __name__ == "__main__":
    main()
