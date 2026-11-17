"""M2-4 评测：对比表 + 遮挡时长-误差曲线

数据来源只有 detections/my_scene.json，没有人工标注的 ground truth，所以这里的
"真值"是**检测连续性伪真值**（pseudo-GT）：
    把相邻帧里 IoU >= 0.3 的同类检测串成一条链（允许中间断 15 帧以内），
    一条链 = 一个物体在画面里的存续过程。
这个伪真值只由检测框决定，与两个追踪器完全无关，所以拿来同时评测
tracker.py（卡尔曼）和 compare_iou_only.py（纯 IoU）是公平的。

产出：
    results/compare.csv          对比表（ID 数、ID 换号次数、遮挡恢复率、静止抖动、中心误差）
    results/occlusion_curve.png  遮挡帧数 k -> 预测误差 / 预测框 IoU（给出 max_age=10 的依据）
    results/eval_summary.json    同上数据的机读版

用法:
    python evaluate_tracking.py
"""
import os
import json
import csv
import math

import numpy as np

from tracker import (compute_iou, Track, run_tracker, load_noise)
from compare_iou_only import run_iou_only


# ---------------------------------------------------------------------------
# 伪真值：检测连续性链
# ---------------------------------------------------------------------------
def build_gt(data, gate=0.3, max_gap=15):
    streams = []          # {'cls': int, 'items': [(frame, det_idx, bbox)]}
    active = []           # {'si': int, 'box': bbox, 'cls': int, 'frame': int}
    for fi, fd in enumerate(data["frames"]):
        dets = fd["dets"]
        used = set()
        for d, det in enumerate(dets):
            best, best_iou = None, gate
            for a in active:
                if a["cls"] != det["cls"]:
                    continue
                if fi - a["frame"] > max_gap:
                    continue
                iou = compute_iou(det["bbox"], a["box"])
                if iou > best_iou:
                    best, best_iou = a, iou
            if best is None:
                si = len(streams)
                streams.append({"cls": det["cls"], "items": []})
                active.append({"si": si, "box": det["bbox"], "cls": det["cls"], "frame": fi})
                best = active[-1]
            else:
                best["box"] = det["bbox"]
                best["frame"] = fi
            streams[best["si"]]["items"].append((fi, d, list(det["bbox"])))
            used.add(best["si"])
        # 清理长时间没跟上的链
        active = [a for a in active if fi - a["frame"] <= max_gap]
    return [s for s in streams if len(s["items"]) >= 2]


def gaps_of(stream, min_gap=1, max_gap=15):
    """返回 [(before_item, after_item, k)]，k 为中间缺失的帧数"""
    out = []
    items = stream["items"]
    for i in range(len(items) - 1):
        f0, f1 = items[i][0], items[i + 1][0]
        k = f1 - f0 - 1
        if min_gap <= k <= max_gap:
            out.append((items[i], items[i + 1], k))
    return out


# ---------------------------------------------------------------------------
# 指标
# ---------------------------------------------------------------------------
def id_of(records):
    """frame -> {det_idx: track_id}"""
    m = {}
    for fr in records["frames"]:
        d = {}
        for tid, di in fr["updated"]:
            d[di] = tid
        m[fr["frame"]] = d
    return m


def gt_index(streams):
    """(frame, det_idx) -> 检测链编号；用来判断某条航迹是不是"换了物体" """
    idx = {}
    for si, s in enumerate(streams):
        for f, di, _box in s["items"]:
            idx[(f, di)] = si
    return idx


def stream_medians(streams):
    """每条检测链的中位框；用来区分"真正的另一个物体"和"同一个物体被切成两条链" """
    med = {}
    for si, s in enumerate(streams):
        arr = np.array([it[2] for it in s["items"]], dtype=float)
        med[si] = np.median(arr, axis=0).tolist()
    return med


def count_identity_steals(records, idx, medians=None, same_object_iou=0.1):
    """一条航迹在不同帧匹配到**空间上不同的**物体（检测链）的次数 = 身份被顶替。

    注意：伪真值会把同一个物体的检测断成多条链（纸巾盒被反复遮挡时尤其明显），
    换链不等于换物体。所以只有当新链与旧链的中位框 IoU < same_object_iou 时才计入，
    否则视为"同一物体的碎片链"，不计。
    """
    owner = {}
    steals = 0
    events = []
    for fr in records["frames"]:
        for tid, di in fr["updated"]:
            g = idx.get((fr["frame"], di))
            if g is None:
                continue
            if tid not in owner:
                owner[tid] = g
                continue
            if owner[tid] == g:
                continue
            old, new = owner[tid], g
            same = False
            if medians and old in medians and new in medians:
                same = compute_iou(medians[old], medians[new]) >= same_object_iou
            owner[tid] = new
            if not same:
                steals += 1
                events.append({"frame": fr["frame"], "id": tid, "from": old, "to": new})
    return steals, events


def metric_id_switches(records, max_lookback=90):
    """同一个物体在消失后重新出现却被分配了新 ID 的次数。

    判定方式（不依赖人工标注）：某条新航迹的出生框，与"最近 max_lookback 帧内
    被删除的、同类别的旧航迹的最后一帧框" IoU > 0.1，就算一次换号。
    """
    deaths = records["deaths"]
    count = 0
    events = []
    for b in records["births"]:
        cand = [d for d in deaths
                if d["cls"] == b["cls"] and 0 < b["frame"] - d["frame"] <= max_lookback]
        if not cand:
            continue
        d = max(cand, key=lambda x: x["frame"])
        iou = compute_iou(b["bbox"], d["bbox"])
        if iou > 0.1:
            count += 1
            events.append({"frame": b["frame"], "new_id": b["id"],
                           "old_id": d["id"], "iou": round(iou, 3)})
    return count, events


def metric_occlusion_recovery(records, streams, k_max=15):
    """遮挡期间 ID 保持率：伪真值里有 k 帧断档、前后两个检测被同一个 ID 接住的比例"""
    ids = id_of(records)
    tot = ok = 0
    tot10 = ok10 = 0
    per_k = {}
    for s in streams:
        for before, after, k in gaps_of(s, 1, k_max):
            f0, d0, _ = before
            f1, d1, _ = after
            a = ids.get(f0, {}).get(d0)
            b = ids.get(f1, {}).get(d1)
            hit = (a is not None and a == b)
            tot += 1
            ok += int(hit)
            per_k.setdefault(k, [0, 0])
            per_k[k][0] += 1
            per_k[k][1] += int(hit)
            if k <= 10:
                tot10 += 1
                ok10 += int(hit)
    return {
        "gaps": tot, "kept": ok,
        "rate": (ok / tot) if tot else float("nan"),
        "gaps_le10": tot10, "kept_le10": ok10,
        "rate_le10": (ok10 / tot10) if tot10 else float("nan"),
        "per_k": {str(k): {"gaps": v[0], "kept": v[1]} for k, v in sorted(per_k.items())},
    }


def metric_jitter(records, streams, win=15, min_len=30, settle=5):
    """框中心的高频抖动：输出中心相对 15 帧滑动平均的 RMS 偏差。

    只统计"连续被更新"的帧（前后 settle 帧内都没有断档），否则会把遮挡结束后
    重新收敛的暂态也算进抖动，对卡尔曼不公平。

    另外单独统计真正静止的目标（伪真值里几乎不动）作为参考：判据是"中心相对中位
    位置的偏离 < 15 px"，不能用中位速度——缓慢平移的物体中位速度也很小。
    """
    ids = id_of(records)
    per_track = []
    static_vals = []
    static_steps = []          # 静止目标的相邻帧位移（题面表 5 的口径）

    # 每条航迹被更新的帧集合
    upd = {}
    for fr in records["frames"]:
        for tid, _ in fr["updated"]:
            upd.setdefault(tid, set()).add(fr["frame"])

    for tid, frames_set in upd.items():
        seq = [(f, records["frames"][f]["boxes"][str(tid)]) for f in sorted(frames_set)
               if str(tid) in records["frames"][f]["boxes"]]
        if len(seq) < min_len:
            continue
        keep = []
        for i, (f, b) in enumerate(seq):
            lo, hi = max(0, i - settle), min(len(seq) - 1, i + settle)
            if all(seq[j + 1][0] - seq[j][0] == 1 for j in range(lo, hi)):
                keep.append((f, b))
        if len(keep) < min_len:
            continue
        cs = np.array([[(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] for _, b in keep])
        k = win // 2
        res = []
        for t in range(k, len(cs) - k):
            res.append(cs[t] - cs[t - k:t + k + 1].mean(axis=0))
        if res:
            res = np.array(res)
            per_track.append(float(np.sqrt(np.mean(np.sum(res ** 2, axis=1)))))

    # 真静止目标：在检测链里找"连续无断档的一段"，用这一段判断是否几乎不动
    for s in streams:
        runs, cur = [], [s["items"][0]]
        for a, b in zip(s["items"][:-1], s["items"][1:]):
            if b[0] - a[0] == 1:
                cur.append(b)
            else:
                runs.append(cur)
                cur = [b]
        runs.append(cur)
        for run in runs:
            if len(run) < max(60, min_len):
                continue
            cs = np.array([[(it[2][0] + it[2][2]) / 2, (it[2][1] + it[2][3]) / 2]
                           for it in run])
            med = np.median(cs, axis=0)
            if float(np.max(np.linalg.norm(cs - med, axis=1))) > 15.0:
                continue                  # 这一段整体位移超过 15 px，不算静止
            out_c = []
            for it in run:
                f, di, _ = it
                tid = ids.get(f, {}).get(di)
                if tid is None:
                    continue
                box = records["frames"][f]["boxes"].get(str(tid))
                if box is None:
                    continue
                out_c.append([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
            if len(out_c) < len(run) * 0.6:
                continue
            out_c = np.array(out_c)
            med2 = np.median(out_c, axis=0)
            static_vals.append(
                float(np.sqrt(np.mean(np.sum((out_c - med2) ** 2, axis=1)))))
            # 题面表 5 的口径：静止目标"相邻帧位移的方差"
            steps = np.linalg.norm(np.diff(out_c, axis=0), axis=1)
            static_steps.append(steps)

    step_mean = float(np.mean([s.mean() for s in static_steps])) if static_steps else float("nan")
    step_var = float(np.mean([s.var() for s in static_steps])) if static_steps else float("nan")

    return (float(np.mean(per_track)) if per_track else float("nan"),
            len(per_track),
            (float(np.mean(static_vals)) if static_vals else float("nan")),
            len(static_vals),
            step_mean, step_var)


def metric_duplicate_tracks(records, iou_thresh=0.8):
    """同一帧里两条航迹框几乎重合（IoU>0.8）的帧-对数。

    这是"一个物体两条 ID"的直接指标：类别抖动或重复检测会让追踪层开两条航迹，
    画面上两个框叠在一起，但 ID 是两套——不测这个指标就发现不了。
    """
    pairs = 0
    frames_with_dup = set()
    for fr in records["frames"]:
        ids = list(fr["boxes"])
        hit = False
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if compute_iou(fr["boxes"][ids[i]], fr["boxes"][ids[j]]) > iou_thresh:
                    pairs += 1
                    hit = True
        if hit:
            frames_with_dup.add(fr["frame"])
    return pairs, len(frames_with_dup)


def metric_center_error(records, data):
    """追踪器输出框中心 与 该帧所属检测框中心 的欧氏距离（仅统计被更新的帧）"""
    errs = []
    for fr in records["frames"]:
        dets = data["frames"][fr["frame"]]["dets"]
        for tid, di in fr["updated"]:
            if di >= len(dets):
                continue
            box = fr["boxes"].get(str(tid))
            if box is None:
                continue
            d = dets[di]["bbox"]
            c1 = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            c2 = ((d[0] + d[2]) / 2, (d[1] + d[3]) / 2)
            errs.append(math.hypot(c1[0] - c2[0], c1[1] - c2[1]))
    if not errs:
        return float("nan"), 0
    return float(np.mean(errs)), len(errs)


# ---------------------------------------------------------------------------
# 遮挡时长 - 误差曲线
# ---------------------------------------------------------------------------
def _smooth_window(items, max_resid=3.0, min_len=5):
    """判断断档前的这段检测是不是"可预测"的：帧必须连续，且中心轨迹近似匀速直线。

    检测碎片（手抖、遮挡边缘的断续检测）会让速度估计完全失真，任何预测器都预测不了，
    这类事件不能进曲线，否则统计量会被噪声主导。判据是线性拟合残差的 RMS。
    """
    if len(items) < min_len:
        return False
    frames = [it[0] for it in items]
    if any(b - a != 1 for a, b in zip(frames[:-1], frames[1:])):
        return False
    cs = np.array([[(it[2][0] + it[2][2]) / 2, (it[2][1] + it[2][3]) / 2]
                   for it in items])
    t = np.arange(len(cs), dtype=float)
    rms = []
    for j in range(2):
        k, b = np.polyfit(t, cs[:, j], 1)
        rms.append(float(np.sqrt(np.mean((cs[:, j] - (k * t + b)) ** 2))))
    return max(rms) <= max_resid


def occlusion_curve(streams, noise, k_max=15, warm=8, min_stream=40):
    """对每个断档事件：用断档前的检测把卡尔曼喂到收敛，再盲推 k 帧，
    与断档后第一个检测比较中心误差 / IoU；同时给出"框原地不动"的基线。

    只统计"可预测事件"：所属检测链足够长（>= min_stream 条检测）、断档前 warm 帧
    连续且近似匀速直线。被过滤掉的事件数会打印出来，不藏在分母里。

    还按"断档期间目标实际移动了多远"拆成两组：移动组才是卡尔曼真正占优的场景，
    原地不动时两种方法应该没有差别——这一点必须如实给出，不能只报移动组。
    """
    R, sigma_a, sigma_size = noise
    rows = {k: {"kf_err": [], "hold_err": [], "kf_iou": [], "hold_iou": []}
            for k in range(1, k_max + 1)}
    split = {"moving": {"kf": [], "hold": [], "n": 0},
             "still": {"kf": [], "hold": [], "n": 0}}
    MOVING_PX = 20.0
    used = skipped = 0

    for s in streams:
        if len(s["items"]) < min_stream:
            skipped += len(gaps_of(s, 1, k_max))
            continue
        for before, after, k in gaps_of(s, 1, k_max):
            idx = s["items"].index(before)
            win = s["items"][max(0, idx - warm + 1): idx + 1]
            if not _smooth_window(win):
                skipped += 1
                continue
            used += 1
            trk = Track(win[0][2], 1, s["cls"], noise)
            prev_f = win[0][0]
            for it in win[1:]:
                # 关键：窗口内部也可能跳帧，必须按“经过了多少帧”逐帧 predict，
                # 否则速度会被高估（帧差当 1 帧用），预测框会直接飞出画面
                for _ in range(it[0] - prev_f):
                    trk.predict()
                trk.update(it[2])
                prev_f = it[0]
            # 断档的 k 帧里没有任何更新，只有预测
            for _ in range(k):
                trk.predict()
            pred = trk.bbox
            truth = after[2]

            c1 = ((pred[0] + pred[2]) / 2, (pred[1] + pred[3]) / 2)
            c2 = ((truth[0] + truth[2]) / 2, (truth[1] + truth[3]) / 2)
            e_kf = math.hypot(c1[0] - c2[0], c1[1] - c2[1])
            rows[k]["kf_err"].append(e_kf)
            rows[k]["kf_iou"].append(compute_iou(pred, truth))

            hold = before[2]
            h1 = ((hold[0] + hold[2]) / 2, (hold[1] + hold[3]) / 2)
            e_hold = math.hypot(h1[0] - c2[0], h1[1] - c2[1])
            rows[k]["hold_err"].append(e_hold)
            rows[k]["hold_iou"].append(compute_iou(hold, truth))

            moved = math.hypot(h1[0] - c2[0], h1[1] - c2[1])
            g = split["moving"] if moved >= MOVING_PX else split["still"]
            g["kf"].append(e_kf)
            g["hold"].append(e_hold)
            g["n"] += 1

    out = {}
    for k, v in rows.items():
        if not v["kf_err"]:
            continue
        out[k] = {"kf_err": float(np.mean(v["kf_err"])),
                  "hold_err": float(np.mean(v["hold_err"])),
                  "kf_iou": float(np.mean(v["kf_iou"])),
                  "hold_iou": float(np.mean(v["hold_iou"])),
                  "n": len(v["kf_err"])}
    out["_split"] = {
        name: {"n": g["n"],
               "kf_err": float(np.mean(g["kf"])) if g["kf"] else float("nan"),
               "hold_err": float(np.mean(g["hold"])) if g["hold"] else float("nan")}
        for name, g in split.items()}
    out["_moving_threshold_px"] = MOVING_PX
    out["_used_events"] = used
    out["_skipped_events"] = skipped
    return out


def plot_curve(rows, out_path, gate=0.3, max_age=10):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ks = sorted(k for k in rows if isinstance(k, int))
    if not ks:
        print("[warn] 没有可用的断档事件，跳过曲线")
        return None
    kf_err = [rows[k]["kf_err"] for k in ks]
    hold_err = [rows[k]["hold_err"] for k in ks]
    kf_iou = [rows[k]["kf_iou"] for k in ks]
    hold_iou = [rows[k]["hold_iou"] for k in ks]
    ns = [rows[k]["n"] for k in ks]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.8), dpi=150)

    ax1.plot(ks, kf_err, "o-", color="#1f77b4", lw=2, ms=5,
             label="Kalman predict (our tracker)")
    ax1.plot(ks, hold_err, "s--", color="#7f7f7f", lw=1.6, ms=5,
             label="last box hold (no motion model)")
    ax1.set_xlabel("occlusion length k (frames)")
    ax1.set_ylabel("center error vs re-appearing box (px)")
    ax1.set_title("(a) prediction error grows while the target moves unseen", fontsize=10)
    ax1.grid(alpha=0.3)
    ax1.set_xticks(ks)
    ax1.legend(fontsize=8, loc="upper left")

    ax2.plot(ks, kf_iou, "o-", color="#1f77b4", lw=2, ms=5, label="Kalman predict")
    ax2.plot(ks, hold_iou, "s--", color="#7f7f7f", lw=1.6, ms=5, label="last box hold")
    ax2.axhline(gate, color="#d62728", ls=":", lw=1.3)
    ax2.text(ks[0], gate + 0.03, f"IoU gate = {gate} (below this: new ID)",
             color="#d62728", fontsize=8)
    ax2.set_xlabel("occlusion length k (frames)")
    ax2.set_ylabel("IoU with re-appearing box")
    ax2.set_title("(b) when IoU drops under the gate, the ID cannot be recovered", fontsize=10)
    ax2.set_ylim(0, 1.05)
    ax2.set_xticks(ks)
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8, loc="lower left")

    for ax in (ax1, ax2):
        ax.axvline(max_age, color="k", ls="--", lw=1.2)
        ax.annotate(f"max_age = {max_age}", xy=(max_age, 0.5),
                    xycoords=("data", "axes fraction"),
                    xytext=(4, 0), textcoords="offset points",
                    fontsize=9, rotation=90, va="center")

    fig.suptitle(f"Prediction error vs occlusion length  "
                 f"({sum(ns)} gap events from detection continuity, "
                 f"{min(ns)}-{max(ns)} per k)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return {"k": ks, "kf_err": kf_err, "hold_err": hold_err,
            "kf_iou": kf_iou, "hold_iou": hold_iou, "n": ns}


# ---------------------------------------------------------------------------
def main():
    os.makedirs("results", exist_ok=True)
    with open("detections/my_scene.json") as f:
        data = json.load(f)
    noise = load_noise()
    print(f"[noise] R={noise[0]} sigma_a={noise[1]} sigma_size={noise[2]}")

    streams = build_gt(data)
    print(f"[gt] {len(streams)} detection streams, "
          f"{sum(len(s['items']) for s in streams)} detections covered")

    print("[run] Kalman tracker ...")
    rec_kf = run_tracker("detections/my_scene.json", draw=False,
                         log_path="results/track_log.json", verbose=False)
    print("[run] IoU-only baseline ...")
    rec_iou = run_iou_only("detections/my_scene.json", draw=False,
                           log_path="results/iou_log.json", verbose=False)

    results = {}
    gidx = gt_index(streams)
    gmed = stream_medians(streams)

    for name, rec in (("kalman", rec_kf), ("iou_only", rec_iou)):
        sw, ev = metric_id_switches(rec)
        occ = metric_occlusion_recovery(rec, streams)
        jit, jit_n, jit_static, jit_static_n, step_mean, step_var = metric_jitter(rec, streams)
        err, nerr = metric_center_error(rec, data)
        steals, steal_ev = count_identity_steals(rec, gidx, gmed)
        dup_pairs, dup_frames = metric_duplicate_tracks(rec)
        results[name] = {
            "ids_created": rec["stats"]["ids_created"],
            "id_switch_events": sw,
            "id_switch_detail": ev,
            "identity_steals": steals,
            "duplicate_pairs": dup_pairs,
            "duplicate_frames": dup_frames,
            "identity_steal_detail": steal_ev,
            "occlusion": occ,
            "jitter_rms_px": jit,
            "jitter_tracks": jit_n,
            "static_jitter_px": jit_static,
            "static_tracks": jit_static_n,
            "static_step_mean_px": step_mean,
            "static_step_var_px2": step_var,
            "center_error_px": err,
            "center_error_n": nerr,
        }
        print(f"[{name}] ids={rec['stats']['ids_created']} id_switch={sw} "
              f"steals={steals} dupPairs={dup_pairs} occ_keep={occ['kept']}/{occ['gaps']} "
              f"jitter={jit:.2f}px (static {jit_static:.2f}px, "
              f"step {step_mean:.2f}±{math.sqrt(max(step_var,0)):.2f}px) err={err:.2f}px")

    with open("results/compare.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["algorithm", "metric", "value", "unit", "note"])

        def wrow(algo, metric, value, unit, note):
            if isinstance(value, float) and math.isnan(value):
                return            # 没有对应样本的指标不写，免得表里一堆 nan
            w.writerow([algo, metric, value, unit, note])

        for name in ("kalman", "iou_only"):
            r = results[name]
            wrow(name, "ids_created", r["ids_created"], "count",
                 "total track IDs allocated over the clip (lower is better)")
            wrow(name, "id_switch_events", r["id_switch_events"], "count",
                 "new ID born on the last box of a recently dead same-class track")
            wrow(name, "identity_steal_events", r["identity_steals"], "count",
                 "one track matched detections of two different objects "
                 "(ID continuity faked by locking onto another target)")
            wrow(name, "duplicate_track_pairs", r["duplicate_pairs"], "count",
                 f"frame-pairs where two live tracks overlap IoU>0.8 "
                 f"({r['duplicate_frames']} frames)")
            wrow(name, "occlusion_kept", r["occlusion"]["kept"], "count",
                 f"gaps where the same ID re-acquired the object (of {r['occlusion']['gaps']})")
            wrow(name, "occlusion_keep_rate", round(r["occlusion"]["rate"], 4), "ratio",
                 "kept / gaps, gap length 1-15 frames")
            wrow(name, "occlusion_keep_rate_le10", round(r["occlusion"]["rate_le10"], 4),
                 "ratio", "subset with gap length <= 10 (i.e. within max_age)")
            wrow(name, "jitter_rms_px", round(r["jitter_rms_px"], 3), "px",
                 f"high-frequency box centre jitter vs 15-frame moving average "
                 f"({r['jitter_tracks']} tracks)")
            wrow(name, "static_jitter_px", round(r["static_jitter_px"], 3), "px",
                 f"centre RMS on near-static targets ({r['static_tracks']} tracks)")
            wrow(name, "static_step_mean_px", round(r["static_step_mean_px"], 3), "px",
                 "mean frame-to-frame centre displacement on static targets")
            wrow(name, "static_step_var_px2", round(r["static_step_var_px2"], 3), "px^2",
                 "variance of frame-to-frame centre displacement on static targets")
            wrow(name, "center_error_px", round(r["center_error_px"], 3), "px",
                 "mean |output center - detection center| on updated frames")


    curve = occlusion_curve(streams, noise)
    plotted = plot_curve(curve, "results/occlusion_natural.png",
                         gate=rec_kf["stats"]["iou_gate"], max_age=rec_kf["stats"]["max_age"])

    split = curve.get("_split", {})
    print(f"[curve] used {curve.get('_used_events', 0)} predictable gap events, "
          f"skipped {curve.get('_skipped_events', 0)} (fragmented / not smooth)")
    for name in ("moving", "still"):
        if name in split:
            g = split[name]
            thr = curve.get("_moving_threshold_px", 20)
            tag = f"moved >= {thr:.0f}px" if name == "moving" else f"moved < {thr:.0f}px"
            print(f"[gap/{name}] n={g['n']} ({tag})  kalman err={g['kf_err']:.2f}px  "
                  f"hold err={g['hold_err']:.2f}px")

    summary = {"noise": {"R": noise[0], "sigma_a": noise[1], "sigma_size": noise[2]},
               "gt_streams": len(streams), "results": results,
               "occlusion_curve": plotted,
               "occlusion_split": split}
    with open("results/eval_summary.json", "w") as f:
        json.dump(summary, f, indent=1)
    print("[ok] results/compare.csv, results/occlusion_natural.png, results/eval_summary.json")


if __name__ == "__main__":
    main()
