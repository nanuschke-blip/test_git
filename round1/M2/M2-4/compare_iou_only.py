"""M2-4 对比基线：纯 IoU 贪心匹配（无运动模型、无卡尔曼平滑）

这是用来和 tracker.py 做对照实验的“朴素版本”，两者唯一的差别就是
本文件没有预测/滤波：
  - 匹配时用“上一次看到的框”原样比 IoU（不预测目标一动框就对不上）
  - 输出框就是检测框（不滤波，所以框会抖）
  - 生命周期管理与 tracker.py 完全一致（max_age=10、IoU 门限 0.3、ID 不复用），
    这样对比表里 ID 数量和抖动差异才能归因到“有无运动模型”，而不是别的参数

用法:
    python compare_iou_only.py   # 生成 results/iou_only.mp4 + results/iou_log.json
"""
import os
import json
import argparse

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment


def compute_iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


class IoUTrack:
    """只记住“上一次看到的框”，没有任何运动模型"""

    def __init__(self, bbox, track_id, cls):
        self.id = track_id
        self.cls = cls
        self.bbox = list(bbox)
        self.tsu = 0
        self.hits = 1

    def predict(self):
        # 朴素外推：位置完全不变（这就是“匀速外推/卡尔曼”缺失的代价）
        self.tsu += 1
        return self.bbox

    def update(self, bbox):
        self.bbox = list(bbox)
        self.tsu = 0
        self.hits += 1


def run_iou_only(json_path, video_path=None, output_video_path=None,
                 max_age=10, iou_gate=0.3, draw=True, log_path=None, verbose=True):
    with open(json_path) as f:
        data = json.load(f)

    fps = int(data.get("fps", 30))
    classes = data.get("classes", [])

    cap = out = None
    if draw:
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if output_video_path:
            out = cv2.VideoWriter(output_video_path,
                                  cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    tracks = []
    next_id = 1
    records = {"fps": fps, "frames": [], "births": [], "deaths": []}

    for fi, frame_data in enumerate(data["frames"]):
        if draw:
            ok, img = cap.read()
            if not ok:
                break
        else:
            img = None

        dets = frame_data["dets"]

        for t in tracks:
            t.predict()

        matches = []
        if tracks and dets:
            iou_mat = np.zeros((len(dets), len(tracks)))
            valid = np.zeros((len(dets), len(tracks)), dtype=bool)
            for d, det in enumerate(dets):
                for k, trk in enumerate(tracks):
                    if det["cls"] != trk.cls:
                        continue
                    iou = compute_iou(det["bbox"], trk.bbox)
                    iou_mat[d, k] = iou
                    valid[d, k] = iou >= iou_gate
            if valid.any():
                cost = np.where(valid, -iou_mat, 1e5)
                rows, cols = linear_sum_assignment(cost)
                for d, k in zip(rows, cols):
                    if valid[d, k]:
                        matches.append((tracks[k], int(d)))

        matched_dets = set()
        for trk, d in matches:
            trk.update(dets[d]["bbox"])
            matched_dets.add(d)

        born = []
        for d, det in enumerate(dets):
            if d in matched_dets:
                continue
            t = IoUTrack(det["bbox"], next_id, det["cls"])
            tracks.append(t)
            matches.append((t, int(d)))
            born.append(next_id)
            records["births"].append({"id": next_id, "frame": fi,
                                      "bbox": det["bbox"], "cls": det["cls"]})
            next_id += 1

        dead = []
        for t in list(tracks):
            if t.tsu > max_age:
                tracks.remove(t)
                dead.append(t.id)
                records["deaths"].append({"id": t.id, "frame": fi,
                                          "bbox": t.bbox, "cls": t.cls})

        predicted = [(t.id, list(t.bbox), t.tsu) for t in tracks if t.tsu > 0]
        records["frames"].append({
            "frame": fi,
            "updated": [(t.id, d) for t, d in matches],
            "predicted": [(i, b, k) for i, b, k in predicted],
            "born": born,
            "dead": dead,
            "boxes": {str(t.id): [float(v) for v in t.bbox] for t in tracks},
        })

        if draw:
            for trk, d in matches:
                b = trk.bbox
                cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])),
                              (0, 255, 0), 2)
                name = classes[trk.cls] if trk.cls < len(classes) else str(trk.cls)
                cv2.putText(img, f"ID {trk.id} {name}",
                            (int(b[0]), max(int(b[1]) - 8, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
            for trk in tracks:
                if trk.tsu == 0:
                    continue
                b = trk.bbox
                cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])),
                              (255, 0, 255), 2)
                cv2.putText(img, f"HOLD ID {trk.id}", (int(b[0]), max(int(b[1]) - 8, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(img, f"IoU-only baseline  frame {fi}  t={fi / fps:.1f}s  "
                             f"tracks={len(tracks)}",
                        (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            out.write(img)

    if cap is not None:
        cap.release()
    if out is not None:
        out.release()

    stats = {"frames": len(records["frames"]), "ids_created": next_id - 1,
             "births": len(records["births"]), "deaths": len(records["deaths"]),
             "max_age": max_age, "iou_gate": iou_gate}
    records["stats"] = stats
    if log_path:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "w") as f:
            json.dump({"stats": stats, "frames": records["frames"],
                       "births": records["births"], "deaths": records["deaths"]}, f)
    if verbose:
        print(f"[iou-only] frames={stats['frames']} ids={stats['ids_created']} "
              f"births={stats['births']} deaths={stats['deaths']}")
        if output_video_path:
            print(f"[iou-only] video -> {output_video_path}")
    return records


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="detections/my_scene.json")
    ap.add_argument("--video", default="videos/my_scene.mp4")
    ap.add_argument("--out", default="results/iou_only.mp4")
    ap.add_argument("--max-age", type=int, default=10)
    ap.add_argument("--gate", type=float, default=0.3)
    args = ap.parse_args()
    os.makedirs("results", exist_ok=True)
    run_iou_only(args.json, args.video, args.out, max_age=args.max_age,
                 iou_gate=args.gate, log_path="results/iou_log.json")
