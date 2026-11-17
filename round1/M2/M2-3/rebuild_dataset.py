"""根据 data/labels_raw 里的手工标注，重建 M2-3 数据集（含真实标注的增强图）

做的事：
1. 校验 labels_raw 是否覆盖全部原图（缺就报错退出）
2. 按类别分层划分 训练/验证/测试（原始图层面划分，避免同一张图的增强副本泄漏到 val/test）
3. 只对训练集原图做几何+光度增强，**标签跟着一起变换**（水平翻转 cx→1-cx，随机缩放平移同步映射）
4. 每类补齐到 TARGET 张，重写 data/labels 与 data/splits
5. 抽 8 张增强结果连同变换后的框画成 docs/aug_check.png，方便肉眼确认标签没错位

用法:
    cd C:\\Users\\AMDI2025\\Desktop\\M2-3
    python rebuild_dataset.py
"""
import os
import glob
import json
import random
import shutil
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(ROOT, "data", "images")
LBL_DIR = os.path.join(ROOT, "data", "labels")
RAW_DIR = os.path.join(ROOT, "data", "labels_raw")
SPLIT_DIR = os.path.join(ROOT, "data", "splits")
DOC_DIR = os.path.join(ROOT, "docs")

CLASSES = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
CMAP = {n: i for i, n in enumerate(CLASSES)}
TARGET_PER_CLASS = 120
SEED = 42


def read_raw(name):
    p = os.path.join(RAW_DIR, name.rsplit(".", 1)[0] + ".txt")
    if not os.path.exists(p):
        return None
    parts = open(p).read().split()
    if len(parts) != 5:
        raise ValueError(f"标签格式不对: {p} -> {parts}")
    c, cx, cy, w, h = parts
    return int(float(c)), float(cx), float(cy), float(w), float(h)


def write_label(path, lab):
    c, cx, cy, w, h = lab
    with open(path, "w") as f:
        f.write(f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")


def augment(img, lab, rng):
    """随机缩放+平移+翻转+亮度，返回 (aug_img, aug_lab)。标签同步变换。"""
    h, w = img.shape[:2]
    c, cx, cy, bw, bh = lab

    s = rng.uniform(1.0, 1.35)          # 只放大，保证框裁完仍在画面内
    cw, ch = w / s, h / s
    # 裁剪窗口中心围绕目标框中心抖动，模拟目标出现在画面不同位置
    jx = rng.uniform(-0.18, 0.18) * w
    jy = rng.uniform(-0.18, 0.18) * h
    ccx = min(max(cx * w + jx, cw / 2), w - cw / 2)
    ccy = min(max(cy * h + jy, ch / 2), h - ch / 2)
    ox, oy = ccx - cw / 2, ccy - ch / 2

    crop = img[int(oy):int(oy + ch), int(ox):int(ox + cw)]
    if crop.size == 0:
        return img.copy(), lab
    crop = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)

    ncx = (cx * w - ox) / cw
    ncy = (cy * h - oy) / ch
    nbw = bw * w / cw
    nbh = bh * h / ch

    if rng.random() < 0.5:              # 水平翻转
        crop = cv2.flip(crop, 1)
        ncx = 1.0 - ncx

    alpha = rng.uniform(0.8, 1.2)
    beta = rng.uniform(-20, 20)
    crop = cv2.convertScaleAbs(crop, alpha=alpha, beta=beta)

    ncx = float(np.clip(ncx, 0.0, 1.0))
    ncy = float(np.clip(ncy, 0.0, 1.0))
    nbw = float(np.clip(nbw, 0.01, 1.0))
    nbh = float(np.clip(nbh, 0.01, 1.0))
    return crop, (c, ncx, ncy, nbw, nbh)


def main():
    rng = random.Random(SEED)

    originals = [os.path.basename(p) for p in glob.glob(os.path.join(IMG_DIR, "*"))
                 if p.lower().endswith((".jpg", ".png", ".jpeg"))
                 and "_aug" not in os.path.basename(p)]

    missing = [f for f in originals if read_raw(f) is None]
    if missing:
        print("[ERROR] unlabeled originals (run label_tool.py first):")
        for m in missing:
            print("   ", m)
        raise SystemExit(1)

    print(f"原图 {len(originals)} 张，标签齐全")

    # 清理旧的增强图与旧标签
    for p in glob.glob(os.path.join(IMG_DIR, "*_aug_*")):
        os.remove(p)
    for p in glob.glob(os.path.join(LBL_DIR, "*.txt")):
        os.remove(p)
    os.makedirs(LBL_DIR, exist_ok=True)
    os.makedirs(SPLIT_DIR, exist_ok=True)
    os.makedirs(DOC_DIR, exist_ok=True)

    train_list, val_list, test_list = [], [], []

    for cls in CLASSES:
        names = sorted([f for f in originals if f.split("_")[0] == cls])
        rng.shuffle(names)
        n = len(names)
        n_test = max(1, int(round(n * 0.1)))
        n_val = max(1, int(round(n * 0.2)))
        while n - n_test - n_val < 2:
            if n_val > 1:
                n_val -= 1
            elif n_test > 1:
                n_test -= 1
            else:
                break
        test = names[:n_test]
        val = names[n_test:n_test + n_val]
        train = names[n_test + n_val:]

        for f in names:                      # 原图标签
            write_label(os.path.join(LBL_DIR, f.rsplit(".", 1)[0] + ".txt"), read_raw(f))
        train_list += [f"data/images/{f}" for f in train]
        val_list += [f"data/images/{f}" for f in val]
        test_list += [f"data/images/{f}" for f in test]

        # 只用训练集原图做增强，避免验证/测试图泄漏
        need = TARGET_PER_CLASS - n
        print(f"  {cls:7s} 原图{n:2d} (train {len(train)}, val {len(val)}, test {len(test)})  增强 {need}")
        k = 0
        for i in range(need):
            src = train[i % len(train)]
            img = cv2.imread(os.path.join(IMG_DIR, src))
            if img is None:
                continue
            aug_img, aug_lab = augment(img, read_raw(src), rng)
            name = f"{cls}_aug_{k:03d}"
            cv2.imwrite(os.path.join(IMG_DIR, name + ".jpg"), aug_img,
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
            write_label(os.path.join(LBL_DIR, name + ".txt"), aug_lab)
            train_list.append(f"data/images/{name}.jpg")
            k += 1

    for fn, lst in (("train.txt", train_list), ("val.txt", val_list), ("test.txt", test_list)):
        with open(os.path.join(SPLIT_DIR, fn), "w") as f:
            f.write("\n".join(lst) + "\n")

    print(f"[OK] dataset rebuilt  train {len(train_list)} / val {len(val_list)} / test {len(test_list)}")

    # ---- 可视化自检：把 8 张增强图的框画出来 ----
    picks = sorted(glob.glob(os.path.join(IMG_DIR, "*_aug_*.jpg")))[::90][:8]
    tiles = []
    for p in picks:
        img = cv2.imread(p)
        h, w = img.shape[:2]
        lab = read_raw(os.path.basename(p))
        if lab is None:   # 增强图的标签写在 data/labels，不是 labels_raw
            lp = os.path.join(LBL_DIR, os.path.basename(p).rsplit(".", 1)[0] + ".txt")
            if os.path.exists(lp):
                c_, cx_, cy_, bw_, bh_ = open(lp).read().split()
                lab = (int(float(c_)), float(cx_), float(cy_), float(bw_), float(bh_))
        if lab is None:
            continue
        c, cx, cy, bw, bh = lab
        x1, y1 = int((cx - bw / 2) * w), int((cy - bh / 2) * h)
        x2, y2 = int((cx + bw / 2) * w), int((cy + bh / 2) * h)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, CLASSES[c], (x1, max(y1 - 6, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
        tiles.append(cv2.resize(img, (320, 180)))
    if tiles:
        cols = 4
        rows = (len(tiles) + cols - 1) // cols
        sheet = np.zeros((rows * 180, cols * 320, 3), np.uint8)
        for i, t in enumerate(tiles):
            r, cc = divmod(i, cols)
            sheet[r * 180:(r + 1) * 180, cc * 320:(cc + 1) * 320] = t
        out = os.path.join(DOC_DIR, "aug_check.png")
        cv2.imwrite(out, sheet)
        print(f"[OK] aug check image: {out}")


if __name__ == "__main__":
    main()
