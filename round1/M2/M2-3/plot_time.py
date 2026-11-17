"""把 benchmark.py 的实测结果画成耗时分布图（不再硬编码数字）

用法:
    python plot_time.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SRC = "docs/benchmark_result.json"
OUT = "docs/time_distribution.png"


def main():
    with open(SRC) as f:
        r = json.load(f)
    labels = ["Preprocess", "Inference", "Postprocess"]
    vals = [r["preprocess_ms"], r["inference_ms"], r["postprocess_ms"]]
    colors = ["#ff9999", "#66b3ff", "#99ff99"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6), dpi=150)
    ax1.pie(vals, labels=labels, autopct="%1.1f%%", colors=colors,
            startangle=90, textprops={"fontsize": 9})
    ax1.set_title(f"CPU time breakdown (total {r['total_ms']:.1f} ms, "
                  f"{r['fps']:.1f} FPS)", fontsize=10)

    bars = ax2.bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        ax2.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f} ms",
                 ha="center", va="bottom", fontsize=9)
    ax2.set_ylabel("ms / frame")
    ax2.set_title(f"ONNX Runtime, {r['providers'][0]}, imgsz={r['imgsz']}", fontsize=10)
    ax2.grid(axis="y", alpha=0.3)
    ax2.set_ylim(0, max(vals) * 1.25)

    fig.tight_layout()
    os.makedirs("docs", exist_ok=True)
    fig.savefig(OUT)
    plt.close(fig)
    print(f"[ok] {OUT}")


if __name__ == "__main__":
    main()
