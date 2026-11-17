"""把训练日志 results.csv 画成 loss / mAP 曲线（题面要求"给出曲线作为过拟合证据"）

早停导致 ultralytics 没有生成 results.png，这里直接从 CSV 画。

用法:
    python plot_loss.py [csv 路径]
"""
import os
import csv
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEFAULT_CSV = "runs/detect/runs/detect/train_fixed/results.csv"
OUT = "docs/loss_curve.png"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    if not os.path.exists(path):
        raise SystemExit(f"找不到训练日志: {path}")
    rows = list(csv.DictReader(open(path)))
    ep = [int(float(r["epoch"])) for r in rows]
    print(f"[loss] {len(rows)} epochs from {path}")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.4), dpi=150)

    for key, label in (("train/box_loss", "train box"), ("train/cls_loss", "train cls"),
                       ("train/dfl_loss", "train dfl")):
        ax1.plot(ep, [float(r[key]) for r in rows], "o-", ms=3.5, lw=1.6, label=label)
    for key, label in (("val/box_loss", "val box"), ("val/cls_loss", "val cls"),
                       ("val/dfl_loss", "val dfl")):
        if key in rows[0]:
            ax1.plot(ep, [float(r[key]) for r in rows], "s--", ms=3, lw=1.2, label=label)
    ax1.set_xlabel("epoch")
    ax1.set_ylabel("loss")
    ax1.set_title("(a) training / validation loss", fontsize=10)
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=7, ncol=2)

    ax2.plot(ep, [float(r["metrics/mAP50(B)"]) for r in rows], "o-", ms=4, lw=1.8,
             label="mAP@0.5")
    ax2.plot(ep, [float(r["metrics/mAP50-95(B)"]) for r in rows], "s-", ms=4, lw=1.8,
             label="mAP@0.5:0.95")
    best = max(rows, key=lambda r: float(r["metrics/mAP50-95(B)"]))
    bx, by = int(float(best["epoch"])), float(best["metrics/mAP50-95(B)"])
    ax2.annotate(f"best {by:.4f} @ep{bx}", xy=(bx, by), xytext=(6, -14),
                 textcoords="offset points", fontsize=8, color="#d62728")
    ax2.scatter([bx], [by], marker="*", s=140, color="#d62728", zorder=5)
    ax2.set_xlabel("epoch")
    ax2.set_ylabel("mAP")
    ax2.set_ylim(0, 1.05)
    ax2.set_title("(b) validation mAP (mAP@0.5 saturates, watch 0.5:0.95)", fontsize=10)
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)

    fig.suptitle(f"Training curves ({len(rows)} epochs, early-stopped)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    os.makedirs("docs", exist_ok=True)
    fig.savefig(OUT)
    plt.close(fig)
    print(f"[ok] {OUT}")


if __name__ == "__main__":
    main()
