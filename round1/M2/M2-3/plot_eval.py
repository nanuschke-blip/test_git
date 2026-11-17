"""把 eval.py 的结果画成逐类 mAP 图（替代旧的手工终端截图，数字直接来自 JSON）

用法:
    python plot_eval.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SRC = "docs/eval_metrics.json"
OUT = "docs/eval_result.png"


def main():
    with open(SRC) as f:
        m = json.load(f)
    val = m.get("val", {})
    test = m.get("test", {})
    classes = list(val.get("per_class", {}).keys())
    if not classes:
        raise SystemExit("eval_metrics.json 里没有 per_class，先跑 eval.py")

    v50 = [val["per_class"][c]["mAP50"] for c in classes]
    v5095 = [val["per_class"][c]["mAP50-95"] for c in classes]
    t5095 = [test.get("per_class", {}).get(c, {}).get("mAP50-95", np.nan) for c in classes]

    x = np.arange(len(classes))
    w = 0.26
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=150)
    b1 = ax.bar(x - w, v50, w, label="val mAP@0.5", color="#4c72b0")
    b2 = ax.bar(x, v5095, w, label="val mAP@0.5:0.95", color="#8fb4e3")
    b3 = ax.bar(x + w, t5095, w, label="test mAP@0.5:0.95", color="#dd8452")
    for bars in (b1, b2, b3):
        for b in bars:
            h = b.get_height()
            if not np.isnan(h):
                ax.text(b.get_x() + b.get_width() / 2, h + 0.01, f"{h:.2f}",
                        ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(classes)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("mAP")
    ax.set_title(f"per-class mAP  (val {val.get('images') or 11} imgs, "
                 f"test {test.get('images') or 6} imgs; "
                 f"val mAP50-95={val.get('mAP50-95', 0):.4f}, "
                 f"test mAP50-95={test.get('mAP50-95', 0):.4f})", fontsize=10)
    ax.legend(fontsize=8, ncol=3, loc="upper center")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    os.makedirs("docs", exist_ok=True)
    fig.savefig(OUT)
    plt.close(fig)
    print(f"[ok] {OUT}")


if __name__ == "__main__":
    main()
