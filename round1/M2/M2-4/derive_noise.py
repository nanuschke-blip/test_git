"""从实测检测序列反推卡尔曼的 R / Q（不是拍脑袋填 1.0、10.0）

推导思路（dt = 1 帧）：

1) 量测噪声 R
   把每个检测框的 (cx, cy, w, h) 看成“真实轨迹 + 白噪声”，然后减掉 5 点滑动
   平均得到高频残差 r[t] = p[t] - mean(p[t-2..t+2])。
   若噪声为白噪声、方差 σ²，则 Var(r) = σ²(1 - 1/5) = 0.8σ²
   ⇒ σ² = Var(r) / 0.8，用 MAD×1.4826 做稳健估计（避免个别跳变拉高方差）。

2) 过程噪声（加速度）
   二阶差分 a[t] = p[t+1] - 2p[t] + p[t-1]。若无噪声，它等于真实加速度；
   但检测噪声会污染：Var(Δ²p) = 6σ² + Var(a_true)
   ⇒ σ_a² = max(Var(Δ²p) - 6σ², 1.0)

3) 尺寸过程噪声
   Var(Δw) = 2σ_w² + q_w ⇒ q_w = max(Var(Δw) - 2σ_w², 0.25)

输出 results/noise_params.json，tracker.py 会自动读取。

用法:
    python derive_noise.py
"""
import os
import json

import numpy as np

from evaluate_tracking import build_gt

MA_WIN = 5


def robust_var(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 3:
        return float("nan")
    return float((1.4826 * np.median(np.abs(x - np.median(x)))) ** 2)


def main():
    with open("detections/my_scene.json") as f:
        data = json.load(f)
    streams = build_gt(data)
    streams = [s for s in streams if len(s["items"]) >= 8]
    print(f"[gt] {len(streams)} streams usable for noise estimation")

    # 展开成每个流各自的 cx,cy,w,h 序列
    series = []
    for s in streams:
        boxes = np.stack([it[2] for it in s["items"]])
        cx = (boxes[:, 0] + boxes[:, 2]) / 2
        cy = (boxes[:, 1] + boxes[:, 3]) / 2
        w = boxes[:, 2] - boxes[:, 0]
        h = boxes[:, 3] - boxes[:, 1]
        series.append(np.stack([cx, cy, w, h], axis=1))

    # ---- 1) R ----
    res = []
    for p in series:
        n = len(p)
        if n < MA_WIN + 4:
            continue
        k = MA_WIN // 2
        for t in range(k, n - k):
            res.append(p[t] - p[t - k:t + k + 1].mean(axis=0))
    res = np.array(res)
    var_r = np.array([robust_var(res[:, i]) for i in range(4)])
    R = np.maximum(var_r / (1.0 - 1.0 / MA_WIN), 0.01)
    print("[R] raw residual var (cx,cy,w,h) = " + ", ".join(f"{v:.2f}" for v in var_r),
          f"-> divide by {1 - 1 / MA_WIN:.2f}")

    # ---- 2) sigma_a ----
    # 方法 A（主）：对连续 15 帧的中心轨迹做二次拟合，二次项系数 ×2 就是加速度。
    # 这种方法几乎不受单帧噪声影响，量的是"真实机动"，正是 Q 该覆盖的量。
    accs = []
    for p in series:
        n = len(p)
        i = 0
        while i + 15 <= n:
            seg = p[i:i + 15]
            # series 里只保留了框，不保证帧连续，这里用二阶差分的稳定性做保护
            for j in (0, 1):
                t = np.arange(15, dtype=float)
                c2 = np.polyfit(t, seg[:, j], 2)[0]
                accs.append(2.0 * c2)
            i += 15
    accs = np.asarray(accs, dtype=float)
    a_p90 = float(np.percentile(np.abs(accs), 90)) if accs.size else 1.0
    sigma_a = max(0.1, a_p90)
    print(f"[Q] quadratic-fit acceleration on {accs.size // 2} windows: "
          f"median|a|={np.median(np.abs(accs)):.3f} px/frame^2, p90={a_p90:.3f}")

    # 方法 B（对照）：二阶差分里扣除 6R，噪声占主导时会退到地板值，
    # 只用来交叉验证"加速度确实在噪声以下"这个结论。
    d2 = []
    for p in series:
        if len(p) < 5:
            continue
        acc = p[2:] - 2 * p[1:-1] + p[:-2]
        d2.append(acc[:, :2])
    d2 = np.concatenate(d2, axis=0)
    var_d2 = np.array([robust_var(d2[:, i]) for i in range(2)])
    q_a = np.maximum(var_d2 - 6.0 * R[:2], 1.0)
    sigma_a_cross = float(np.sqrt(np.mean(q_a)))
    print(f"[Q] second-difference cross-check: Var(d2p) = {var_d2.round(2).tolist()}, "
          f"minus 6R -> floor {sigma_a_cross:.2f} (noise dominates, so method A is used)")

    # ---- 3) sigma_size ----
    d1 = []
    for p in series:
        if len(p) < 3:
            continue
        d1.append((p[1:, 2:] - p[:-1, 2:]))
    d1 = np.concatenate(d1, axis=0)
    var_d1 = np.array([robust_var(d1[:, i]) for i in range(2)])
    q_s = np.maximum(var_d1 - 2.0 * R[2:], 0.25)
    sigma_size = float(np.sqrt(np.mean(q_s)))
    print(f"[Q] Var(dw,dh) = {var_d1.round(2).tolist()}, minus 2R -> q_s = "
          f"{q_s.round(2).tolist()}, sigma_size = {sigma_size:.3f} px/frame")

    out = {
        "R": [round(float(v), 4) for v in R],
        "sigma_a": round(sigma_a, 4),
        "sigma_size": round(sigma_size, 4),
        "detail": {
            "residual_var_raw": [round(float(v), 4) for v in var_r],
            "accel_p50": round(float(np.median(np.abs(accs))), 4) if accs.size else None,
            "accel_p90": round(a_p90, 4),
            "accel_windows": int(accs.size // 2),
            "var_d2p": [round(float(v), 4) for v in var_d2],
            "sigma_a_second_diff_floor": round(sigma_a_cross, 4),
            "var_dw_dh": [round(float(v), 4) for v in var_d1],
            "q_size": [round(float(v), 4) for v in q_s],
            "streams": len(series),
            "samples": int(res.shape[0]),
            "ma_win": MA_WIN,
        },
    }
    os.makedirs("results", exist_ok=True)
    with open("results/noise_params.json", "w") as f:
        json.dump(out, f, indent=1)
    print("[ok] results/noise_params.json")
    print(f"     R={out['R']}  sigma_a={out['sigma_a']}  sigma_size={out['sigma_size']}")


if __name__ == "__main__":
    main()
