"""M2-3 模型评估：验证集 + 测试集，逐类 P/R/F1/mAP，并把混淆矩阵拷进 docs/

用法:
    python eval.py
"""
import os
import json
import shutil

from ultralytics import YOLO

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]


def f1(p, r):
    return 0.0 if (p + r) == 0 else 2 * p * r / (p + r)


def run_split(model, split):
    m = model.val(data="my_data.yaml", split=split, verbose=False)
    per_class = {}
    names = m.names if hasattr(m, "names") else {i: c for i, c in enumerate(CLASSES)}
    for i, name in names.items():
        try:
            p = float(m.box.p[i])
            r = float(m.box.r[i])
            per_class[name] = {
                "precision": round(p, 4),
                "recall": round(r, 4),
                "f1": round(f1(p, r), 4),
                "mAP50": round(float(m.box.ap50[i]), 4),
                "mAP50-95": round(float(m.box.ap[i]), 4),
            }
        except Exception:
            continue

    # 把这次 val 生成的混淆矩阵拷进 docs/（题面 5.1 要求报告混淆矩阵）
    src = os.path.join(str(getattr(m, "save_dir", "")), "confusion_matrix.png")
    dst = None
    if os.path.exists(src):
        os.makedirs("docs", exist_ok=True)
        dst = f"docs/confusion_matrix_{split}.png"
        shutil.copy(src, dst)

    return {
        "images": int(getattr(m, "nt", 0)) or None,
        "precision": round(float(m.box.mp), 4),
        "recall": round(float(m.box.mr), 4),
        "f1": round(f1(float(m.box.mp), float(m.box.mr)), 4),
        "mAP50": round(float(m.box.map50), 4),
        "mAP50-95": round(float(m.box.map), 4),
        "confusion_matrix": dst,
        "per_class": per_class,
    }


def main():
    model = YOLO("models/best.pt")
    out = {}
    for split in ("val", "test"):
        print(f"[eval] split={split} ...")
        r = run_split(model, split)
        out[split] = r
        print(f"  P={r['precision']:.4f}  R={r['recall']:.4f}  F1={r['f1']:.4f}  "
              f"mAP@0.5={r['mAP50']:.4f}  mAP@0.5:0.95={r['mAP50-95']:.4f}")
        for name, v in r["per_class"].items():
            print(f"    {name:7s} P={v['precision']:.3f} R={v['recall']:.3f} "
                  f"F1={v['f1']:.3f} mAP50={v['mAP50']:.3f} mAP50-95={v['mAP50-95']:.3f}")
        if r["confusion_matrix"]:
            print(f"    confusion matrix -> {r['confusion_matrix']}")

    os.makedirs("docs", exist_ok=True)
    with open("docs/eval_metrics.json", "w") as f:
        json.dump(out, f, indent=1)
    print("[ok] docs/eval_metrics.json")


if __name__ == "__main__":
    main()
