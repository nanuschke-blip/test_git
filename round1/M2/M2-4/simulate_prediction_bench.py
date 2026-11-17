"""受控仿真：单独验证"运动预测"到底比"原地保持"好多少

真实素材里的遮挡大多发生在准静止目标上（见 report.md 第 7 节的实测），无法体现匀速运动
带来的收益。这个脚本用**已知真值**的仿真轨迹补上这一块：

    场景：目标以恒定速度 v 直线运动，检测框带标准差 σ 的高斯噪声，
          在第 20 帧后人为遮挡 k 帧，然后恢复检测。
    对比：卡尔曼预测 vs 最后一帧框原地保持。
    指标：恢复那一帧预测框中心与真值中心的距离。

注意：这是仿真，不是实测，报告里单独标注，不和真实素材的数字混在一起。

用法:
    python simulate_prediction_bench.py
"""
import os
import json

import numpy as np

from tracker import Track, load_noise

FRAMES = 20          # 遮挡前的观测帧数
K_LIST = [1, 3, 5, 8, 10, 15]
V_LIST = [0.0, 2.0, 5.0, 10.0, 20.0]
SIGMA = 1.0          # 检测框中心噪声标准差 (px)
TRIALS = 200


def run_once(v, k, sigma, noise, rng):
    x0, y0 = 300.0, 300.0
    w, h = 120.0, 90.0

    def box(i):
        x = x0 + v * i + rng.normal(0, sigma)
        y = y0 + rng.normal(0, sigma)
        return [x, y, x + w, y + h]

    trk = Track(box(0), 1, 0, noise)
    for i in range(1, FRAMES):
        trk.predict()
        trk.update(box(i))

    last = trk.bbox
    for _ in range(k):
        trk.predict()
    pred = trk.bbox

    # 真值要取"框中心"，别忘了加半个宽高
    truth_x = x0 + v * (FRAMES - 1 + k) + w / 2
    truth_y = y0 + h / 2
    c_kf = ((pred[0] + pred[2]) / 2, (pred[1] + pred[3]) / 2)
    c_hold = ((last[0] + last[2]) / 2, (last[1] + last[3]) / 2)
    e_kf = float(np.hypot(c_kf[0] - truth_x, c_kf[1] - truth_y))
    e_hold = float(np.hypot(c_hold[0] - truth_x, c_hold[1] - truth_y))
    return e_kf, e_hold


def main():
    noise = load_noise()
    rng = np.random.default_rng(0)
    table = {}
    print(f"[sim] frames_before_gap={FRAMES} sigma={SIGMA}px trials={TRIALS} noise={noise}")
    print(" v(px/f)  k   kalman_err  hold_err   ratio")
    for v in V_LIST:
        for k in K_LIST:
            ek, eh = [], []
            for _ in range(TRIALS):
                a, b = run_once(v, k, SIGMA, noise, rng)
                ek.append(a)
                eh.append(b)
            table[f"v{v}_k{k}"] = {"v": v, "k": k,
                                   "kf_err": float(np.mean(ek)),
                                   "hold_err": float(np.mean(eh))}
            ratio = (np.mean(ek) / np.mean(eh)) if np.mean(eh) > 1e-6 else float("nan")
            print(f"{v:7.1f} {k:3d}  {np.mean(ek):10.2f}  {np.mean(eh):8.2f}  {ratio:6.3f}")

    os.makedirs("results", exist_ok=True)
    with open("results/prediction_sim.json", "w") as f:
        json.dump({"sigma": SIGMA, "frames_before_gap": FRAMES, "trials": TRIALS,
                   "noise": {"R": noise[0], "sigma_a": noise[1],
                             "sigma_size": noise[2]},
                   "table": table}, f, indent=1)

    # 画图：不同速度下误差随遮挡帧数的变化
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=150)
    colors = plt.cm.viridis(np.linspace(0, 0.85, len(V_LIST)))
    for v, c in zip(V_LIST, colors):
        kf = [table[f"v{v}_k{k}"]["kf_err"] for k in K_LIST]
        hd = [table[f"v{v}_k{k}"]["hold_err"] for k in K_LIST]
        ax1.plot(K_LIST, kf, "o-", color=c, lw=1.8, ms=4, label=f"kalman v={v:g}")
        ax1.plot(K_LIST, hd, "x--", color=c, lw=1.2, ms=5)
    ax1.set_xlabel("occlusion length k (frames)")
    ax1.set_ylabel("centre error vs ground truth (px)")
    ax1.set_title("(a) kalman (solid) vs hold (dashed)", fontsize=10)
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=7)

    for v, c in zip(V_LIST, colors):
        ratio = [table[f"v{v}_k{k}"]["kf_err"] / max(table[f"v{v}_k{k}"]["hold_err"], 1e-6)
                 for k in K_LIST]
        ax2.plot(K_LIST, ratio, "o-", color=c, lw=1.8, ms=4, label=f"v={v:g} px/f")
    ax2.axhline(1.0, color="k", ls=":", lw=1)
    ax2.set_xlabel("occlusion length k (frames)")
    ax2.set_ylabel("kalman error / hold error")
    ax2.set_title("(b) below 1.0 = kalman wins", fontsize=10)
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=7)

    fig.suptitle(f"Controlled simulation: constant velocity + Gaussian detection noise "
                 f"(sigma={SIGMA}px, {TRIALS} trials)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig("results/prediction_sim.png")
    plt.close(fig)
    print("[ok] results/prediction_sim.json, results/prediction_sim.png")


if __name__ == "__main__":
    main()
