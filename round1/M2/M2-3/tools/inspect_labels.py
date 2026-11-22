"""M2-3 标注质量抽查：随机抽 N 张图，把 YOLO 标注画上去，拼成一张图。

用法：
    python3 tools/inspect_labels.py --n 8 --out docs/label_check.png
"""
import argparse
import os
import random

import cv2
import numpy as np

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
COLORS = [(0, 0, 255), (0, 165, 255), (0, 255, 255), (0, 255, 0), (255, 0, 0), (255, 0, 255)]


def find_pairs(root):
    pairs = []
    for dp, _, fs in os.walk(root):
        if os.path.basename(dp) != "images":
            continue
        for f in fs:
            if not f.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            img = os.path.join(dp, f)
            lab = os.path.join(dp.replace(os.sep + "images", os.sep + "labels"),
                               os.path.splitext(f)[0] + ".txt")
            if os.path.isfile(lab):
                pairs.append((img, lab))
    return pairs


def draw(img_path, lab_path, tile_w=480):
    img = cv2.imread(img_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    n = 0
    with open(lab_path) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 5:
                continue
            c, cx, cy, bw, bh = int(parts[0]), *map(float, parts[1:5])
            x1, y1 = int((cx - bw / 2) * w), int((cy - bh / 2) * h)
            x2, y2 = int((cx + bw / 2) * w), int((cy + bh / 2) * h)
            color = COLORS[c % len(COLORS)]
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
            cv2.putText(img, CLASSES[c] if c < len(CLASSES) else str(c),
                        (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            n += 1
    scale = tile_w / w
    img = cv2.resize(img, (tile_w, int(h * scale)))
    cv2.putText(img, f"{os.path.basename(img_path)}  boxes={n}",
                (8, img.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--out", default="docs/label_check.png")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    pairs = find_pairs(args.root)
    if not pairs:
        raise SystemExit(f"没找到 images/labels 配对（root={args.root}）")
    random.Random(args.seed).shuffle(pairs)
    tiles = [t for t in (draw(i, l) for i, l in pairs[:args.n]) if t is not None]

    cols = 4 if len(tiles) > 4 else len(tiles)
    rows = (len(tiles) + cols - 1) // cols
    th, tw = tiles[0].shape[:2]
    sheet = np.full((rows * th, cols * tw, 3), 32, np.uint8)
    for k, t in enumerate(tiles):
        r, c = divmod(k, cols)
        sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    cv2.imwrite(args.out, sheet)
    print(f"[inspect] {len(pairs)} 对样本中抽了 {len(tiles)} 张 -> {args.out}")


if __name__ == "__main__":
    main()
