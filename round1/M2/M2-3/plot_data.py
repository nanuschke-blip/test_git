"""统计数据集真实分布并画图（之前是硬编码的 [120]*6，现在全部从磁盘数）

用法:
    python plot_data.py
"""
import os
import json
import glob
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
IMG_DIR = "data/images"
SPLIT_DIR = "data/splits"
OUT_PNG = "docs/data_distribution.png"
OUT_JSON = "docs/data_stats.json"


def read_split(name):
    p = os.path.join(SPLIT_DIR, name)
    if not os.path.exists(p):
        return []
    return [os.path.basename(x.strip()) for x in open(p) if x.strip()]


def main():
    train = set(read_split("train.txt"))
    val = set(read_split("val.txt"))
    test = set(read_split("test.txt"))
    all_imgs = {os.path.basename(p) for p in glob.glob(os.path.join(IMG_DIR, "*.jpg"))}

    stat = {c: {"train_orig": 0, "train_aug": 0, "val": 0, "test": 0} for c in CLASSES}
    for name in all_imgs:
        cls = name.split("_")[0]
        if cls not in stat:
            continue
        if name in test:
            stat[cls]["test"] += 1
        elif name in val:
            stat[cls]["val"] += 1
        elif "_aug_" in name:
            stat[cls]["train_aug"] += 1
        elif name in train:
            stat[cls]["train_orig"] += 1

    tot = {c: sum(v.values()) for c, v in stat.items()}
    print(f"[data] {len(all_imgs)} images total, splits train={len(train)} "
          f"val={len(val)} test={len(test)}")
    for c in CLASSES:
        s = stat[c]
        print(f"  {c:7s} total={tot[c]:3d}  train {s['train_orig']:2d}+{s['train_aug']:3d}aug"
              f"  val {s['val']:2d}  test {s['test']:2d}")

    # 标签框尺寸真实分布（用来证明标注不是同一个固定框）
    boxes = {c: [] for c in CLASSES}
    for p in glob.glob(os.path.join(IMG_DIR, "*.jpg")):
        cls = os.path.basename(p).split("_")[0]
        lp = os.path.join("data/labels", os.path.basename(p).rsplit(".", 1)[0] + ".txt")
        if cls not in boxes or not os.path.exists(lp):
            continue
        parts = open(lp).read().split()
        if len(parts) == 5:
            boxes[cls].append((float(parts[3]), float(parts[4])))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8), dpi=150)
    x = range(len(CLASSES))
    b1 = [stat[c]["train_orig"] for c in CLASSES]
    b2 = [stat[c]["train_aug"] for c in CLASSES]
    b3 = [stat[c]["val"] for c in CLASSES]
    b4 = [stat[c]["test"] for c in CLASSES]
    ax1.bar(x, b1, label="train (original)", color="#4c72b0")
    ax1.bar(x, b2, bottom=b1, label="train (augmented)", color="#8fb4e3")
    ax1.bar(x, b3, bottom=[b1[i] + b2[i] for i in x], label="val", color="#dd8452")
    ax1.bar(x, b4, bottom=[b1[i] + b2[i] + b3[i] for i in x], label="test", color="#937860")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(CLASSES)
    ax1.set_ylabel("images")
    ax1.set_title("dataset distribution (counted from disk)", fontsize=10)
    ax1.legend(fontsize=8)
    ax1.grid(axis="y", alpha=0.3)

    # 每类框宽高的分散程度：证明不是 0.6x0.6 的固定框
    for i, c in enumerate(CLASSES):
        if not boxes[c]:
            continue
        ws = [b[0] for b in boxes[c]]
        hs = [b[1] for b in boxes[c]]
        ax2.scatter(ws, hs, s=8, alpha=0.5, label=c)
    ax2.set_xlabel("box width (normalized)")
    ax2.set_ylabel("box height (normalized)")
    ax2.set_title("label box sizes per class (hand-labeled)", fontsize=10)
    ax2.legend(fontsize=8, markerscale=2)
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    os.makedirs("docs", exist_ok=True)
    fig.savefig(OUT_PNG)
    plt.close(fig)

    with open(OUT_JSON, "w") as f:
        json.dump({"total_images": len(all_imgs),
                   "splits": {"train": len(train), "val": len(val), "test": len(test)},
                   "per_class": stat, "total_per_class": tot}, f, indent=1)
    print(f"[ok] {OUT_PNG}\n[ok] {OUT_JSON}")


if __name__ == "__main__":
    main()
