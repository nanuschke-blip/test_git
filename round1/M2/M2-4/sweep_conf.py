"""置信度阈值选择：同一份检测序列，扫一遍阈值看追踪结果怎么变

为什么要单独做这件事：检测阈值不是"拍个 0.5"，它直接决定追踪的碎片率——
阈值太低，背景上的低分假阳性会变成一条条幽灵航迹（ID 暴涨）；
阈值太高，真目标频繁漏检，遮挡期变长、更容易超时删号（ID 也涨）。
所以用 ID 数量 + 同时存活航迹数作为选择依据。

注意：扫描必须基于**低阈值**的原始检测（detections/my_scene_lowconf.json，
由 `python detector_adapter.py --conf 0.15 --out detections/my_scene_lowconf.json`
生成）。直接拿 conf=0.5 过滤过的文件来扫，每个阈值都是同一份数据，扫了等于没扫。

用法:
    python sweep_conf.py
"""
import json
import copy
import csv
import os
import argparse

from tracker import run_tracker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--confs", default="0.15,0.25,0.3,0.4,0.5,0.6")
    args = ap.parse_args()

    src = args.json
    if src is None:
        src = ("detections/my_scene_lowconf.json"
               if os.path.exists("detections/my_scene_lowconf.json")
               else "detections/my_scene.json")
    print(f"[sweep] source = {src}")

    with open(src) as f:
        base = json.load(f)

    rows = []
    print("conf    dets   ids  deaths  empty_frames  max_simul")
    for th in [float(x) for x in args.confs.split(",")]:
        d = copy.deepcopy(base)
        n = 0
        for fr in d["frames"]:
            keep = [x for x in fr["dets"] if x["conf"] >= th]
            n += len(keep)
            fr["dets"] = keep
        tmp = "detections/_sweep_tmp.json"
        with open(tmp, "w") as f:
            json.dump(d, f)
        rec = run_tracker(tmp, draw=False, verbose=False)
        empty = sum(1 for fr in rec["frames"] if not fr["boxes"])
        mx = max(len(fr["boxes"]) for fr in rec["frames"])
        rows.append({"conf": th, "dets": n, "ids": rec["stats"]["ids_created"],
                     "deaths": rec["stats"]["deaths"], "empty_frames": empty,
                     "max_simul": mx})
        print(f"{th:4.2f} {n:7d} {rec['stats']['ids_created']:5d} "
              f"{rec['stats']['deaths']:7d} {empty:13d} {mx:9d}")
    if os.path.exists(tmp):
        os.remove(tmp)

    os.makedirs("results", exist_ok=True)
    with open("results/conf_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("[ok] results/conf_sweep.csv")


if __name__ == "__main__":
    main()
