"""人工遮挡实验：按题面表 4 的做法"剪辑掉检测"，测 5/10/15/20 帧遮挡下的
ID 保持率与预测误差，并给出 max_age = 5/10/20 的权衡。

为什么不用"等自然遮挡"：实测素材里自然断档只有 2 次位移超过 20 px，样本太少、还夹着
检测碎片。这个脚本直接在人造遮挡下测——遮挡期每帧的真实位置是已知的（来自检测连续性
链），所以能逐帧算预测误差，而不是只在"重新出现那一帧"算一个点。

做法：
    1. 用 build_gt 把检测串成链（一条链 = 一个物体在画面里的存续过程）
    2. 对每个遮挡长度 k ∈ {5,10,15,20}，在足够长的链上挑若干"连续帧窗口"，
       把这些帧里目标的检测删掉（视频不动，等于给它挡了一块板）
    3. 每个 k 只跑一次追踪（多个事件同时挖掉，事件在时间上互不重叠）
    4. 统计：遮挡后是否还是同一个 ID；遮挡期每帧预测框与真实位置的中心误差

输出：
    results/occlusion_bench.csv    各 k 的保持率与误差
    results/occlusion_curve.png    遮挡帧数 vs 预测误差 / 保持率（交付物）
    results/max_age_sweep.csv       max_age = 5/10/20 的权衡

用法:
    python occlusion_bench.py
"""
import os
import json
import copy
import csv

import numpy as np

from evaluate_tracking import (build_gt, compute_iou, gt_index,
                               count_identity_steals)

from tracker import run_tracker, load_noise

K_LIST = [5, 10, 15, 20]
MAX_AGE_LIST = [5, 10, 20]
EVENTS_PER_STREAM = 3
MIN_RUN = 25          # 链里连续可用帧数少于这个就不作为事件源
TMP = "detections/_occl_tmp.json"


def tag_streams(data, streams):
    """给每个检测打上所属链的编号（tracker 会忽略多余字段）"""
    for si, s in enumerate(streams):
        for f, di, _box in s["items"]:
            data["frames"][f]["dets"][di]["_gt"] = si


def consecutive_runs(items):
    """把一条链切成若干"帧连续"的片段"""
    runs, cur = [], [items[0]]
    for a, b in zip(items[:-1], items[1:]):
        if b[0] - a[0] == 1:
            cur.append(b)
        else:
            runs.append(cur)
            cur = [b]
    runs.append(cur)
    return [r for r in runs if len(r) >= MIN_RUN]


def pick_events(streams, k):
    """在每个足够长的片段里均匀挑若干窗口（窗口内 k 帧都要有检测）"""
    events = []
    for si, s in enumerate(streams):
        for run in consecutive_runs(s["items"]):
            span = len(run) - k - 1
            if span <= 3:
                continue
            n = min(EVENTS_PER_STREAM, max(1, span // 25))
            starts = np.linspace(1, span - 1, n).astype(int)
            for st in starts:
                before = run[st - 1]
                occ = run[st: st + k]
                after = run[st + k]
                if after[0] - before[0] != k + 1:
                    continue
                events.append({"stream": si, "before": before, "occ": occ,
                               "after": after})
    return events


def build_occluded(data, events):
    """返回挖掉事件帧后的副本（事件所在帧删掉对应 stream 的检测）"""
    d = copy.deepcopy(data)
    # _gt 标记要先打在副本上，再按 stream 删
    for ev in events:
        for f, _di, _box in ev["occ"]:
            dets = d["frames"][f]["dets"]
            d["frames"][f]["dets"] = [x for x in dets if x.get("_gt") != ev["stream"]]
    return d


def id_at(rec, frame, gt_stream):
    """该帧里属于 gt_stream 的检测被分到哪个航迹 ID（按 _gt 标记匹配）"""
    fr = rec["frames"][frame]
    dets = rec["_dets"][frame]
    for tid, di in fr["updated"]:
        if di < len(dets) and dets[di].get("_gt") == gt_stream:
            return tid
    return None


def eval_events(rec, events, data_mod):
    out = []
    for ev in events:
        id_before = id_at(rec, ev["before"][0], ev["stream"])
        id_after = id_at(rec, ev["after"][0], ev["stream"])
        kept = (id_before is not None and id_before == id_after)

        # 遮挡期逐帧误差：用遮挡前那个 ID 的预测框 vs 真实框
        errs, ious = [], []
        if id_before is not None:
            for f, _di, gt_box in ev["occ"]:
                box = rec["frames"][f]["boxes"].get(str(id_before))
                if box is None:
                    continue
                c1 = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                c2 = ((gt_box[0] + gt_box[2]) / 2, (gt_box[1] + gt_box[3]) / 2)
                errs.append(float(np.hypot(c1[0] - c2[0], c1[1] - c2[1])))
                ious.append(compute_iou(box, gt_box))
        out.append({"kept": kept, "id_before": id_before, "id_after": id_after,
                    "errs": errs, "ious": ious,
                    "err_first": errs[0] if errs else float("nan"),
                    "err_last": errs[-1] if errs else float("nan")})
    return out


def run_for_k(data, streams, k, max_age=10):
    events = pick_events(streams, k)
    if not events:
        return None, None
    data_mod = build_occluded(data, events)
    with open(TMP, "w") as f:
        json.dump(data_mod, f)
    rec = run_tracker(TMP, draw=False, max_age=max_age, verbose=False)
    rec["_dets"] = [fr["dets"] for fr in data_mod["frames"]]
    return events, eval_events(rec, events, data_mod)



def main():
    noise = load_noise()
    with open("detections/my_scene.json") as f:
        data = json.load(f)
    streams = build_gt(data)
    tag_streams(data, streams)
    print(f"[gt] {len(streams)} streams, noise={noise}")

    # 带 _gt 标记的完整副本，给 max_age 权衡用（测身份顶替）
    tagged = "detections/_tagged_tmp.json"
    with open(tagged, "w") as f:
        json.dump(data, f)
    idx_gt = gt_index(streams)

    rows = []
    per_frame = {}          # k -> 每帧平均误差（用于曲线）
    for k in K_LIST:
        events, results = run_for_k(data, streams, k)
        if not events:
            print(f"[k={k}] 没有可用事件，跳过")
            continue
        kept = sum(1 for r in results if r["kept"])
        rate = kept / len(results)
        errs_first = [r["err_first"] for r in results if not np.isnan(r["err_first"])]
        errs_last = [r["err_last"] for r in results if not np.isnan(r["err_last"])]
        iou_first = [r["ious"][0] for r in results if r["ious"]]

        # 逐帧平均误差曲线：第 i 帧（0-based）在所有事件上的均值
        cols = []
        for i in range(k):
            vals = [r["errs"][i] for r in results if len(r["errs"]) > i]
            cols.append(float(np.mean(vals)) if vals else float("nan"))
        per_frame[k] = cols

        rows.append({
            "k": k, "events": len(results), "kept": kept,
            "keep_rate": round(rate, 4),
            "err_first_px": round(float(np.mean(errs_first)), 2) if errs_first else "",
            "err_last_px": round(float(np.mean(errs_last)), 2) if errs_last else "",
            "iou_first": round(float(np.mean(iou_first)), 3) if iou_first else "",
        })
        print(f"[k={k:2d}] events={len(results):2d} kept={kept:2d} "
              f"rate={rate:.2f} err_first={rows[-1]['err_first_px']}px "
              f"err_last={rows[-1]['err_last_px']}px iou_first={rows[-1]['iou_first']}")

    os.makedirs("results", exist_ok=True)
    with open("results/occlusion_bench.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("[ok] results/occlusion_bench.csv")

    # ---- max_age 权衡 ----
    from evaluate_tracking import metric_id_switches
    sweep = []
    for ma in MAX_AGE_LIST:
        # (a) 人造 10 帧遮挡下的保持率
        events, results = run_for_k(data, streams, 10, max_age=ma)
        rate10 = (sum(1 for r in results if r["kept"]) / len(results)) if results else float("nan")
        # (b) 原始素材上的碎片率、换号次数、身份顶替次数（僵尸航迹的代价）
        rec = run_tracker(tagged, draw=False, max_age=ma,
                          verbose=False, noise=noise)
        sw, _ = metric_id_switches(rec)
        steals, _ = count_identity_steals(rec, idx_gt)
        sweep.append({"max_age": ma, "keep_rate_10f": round(rate10, 4),
                      "ids_created": rec["stats"]["ids_created"],
                      "id_switch_events": sw,
                      "identity_steal_events": steals})
        print(f"[max_age={ma:2d}] 10 帧遮挡保持率={rate10:.2f}  "
              f"全片 ID 数={rec['stats']['ids_created']}  换号={sw}  "
              f"身份顶替={steals}")

    with open("results/max_age_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sweep[0].keys()))
        w.writeheader()
        w.writerows(sweep)
    print("[ok] results/max_age_sweep.csv")

    if os.path.exists(TMP):
        os.remove(TMP)

    # ---- 画图 ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=150)

    ks = [r["k"] for r in rows]
    rates = [r["keep_rate"] * 100 for r in rows]
    bars = ax1.bar([str(k) for k in ks], rates, color="#4c72b0")
    for b, r in zip(bars, rates):
        ax1.text(b.get_x() + b.get_width() / 2, r + 1, f"{r:.0f}%", ha="center",
                 fontsize=9)
    ax1.set_ylim(0, 110)
    ax1.set_xlabel("occlusion length k (frames)")
    ax1.set_ylabel("ID keep rate (%)")
    ax1.set_title("(a) ID keep rate after artificial occlusion", fontsize=10)
    ax1.grid(axis="y", alpha=0.3)

    for k in sorted(per_frame):
        vals = per_frame[k]
        ax2.plot(range(1, len(vals) + 1), vals, "o-", ms=4, lw=1.8, label=f"k={k}")
    ax2.axvline(10, color="k", ls="--", lw=1.2)
    ax2.annotate("max_age = 10", xy=(10, 0.5), xycoords=("data", "axes fraction"),
                 xytext=(4, 0), textcoords="offset points", fontsize=9, rotation=90,
                 va="center")
    ax2.set_xlabel("frames since detection lost")
    ax2.set_ylabel("prediction centre error (px)")
    ax2.set_title("(b) per-frame prediction error while occluded", fontsize=10)
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)

    fig.suptitle("Artificial occlusion benchmark (detections removed, "
                 "ground-truth positions known)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig("results/occlusion_curve.png")
    plt.close(fig)
    print("[ok] results/occlusion_curve.png")


if __name__ == "__main__":
    main()
