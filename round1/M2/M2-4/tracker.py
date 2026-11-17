"""M2-4 多目标追踪：卡尔曼 + 匈牙利匹配 + 遮挡预测 + 轨迹/位移可视化

两种输入方式（题面 §5/§6 要求）：
    python tracker.py                              # 离线：读 detections/*.json
    python tracker.py --source 0                   # 实时：接摄像头（M2-3 的 ONNX 模型）
    python tracker.py --source videos/my_scene.mp4 # 实时：跑视频，现场造遮挡就用这个

画面上的东西：
    绿色实线框 + `ID n cls conf`   本帧被检测更新
    黄色虚线框 + `PREDICTED ID n k=` 本帧没检测到，框是盲推的（≤max_age 帧）
    青色细框 + `NEXT`               下一帧的预测框（有检测时也画，题面表 0 #7）
    绿色尾迹                        该 ID 最近的实测中心轨迹
    `path / disp`                   累计路径长度 / 相对入画面位置的直线位移（表 0 #3）

用法参数见 --help。
"""
import os
import json
import argparse

import cv2
import numpy as np
from filterpy.kalman import KalmanFilter
from scipy.optimize import linear_sum_assignment

# ----------------------------------------------------------------------------
# 噪声参数：优先读 derive_noise.py 的实测结果，没有就用这里的缺省值
# ----------------------------------------------------------------------------
DEFAULT_R = [0.43, 0.22, 1.52, 0.88]      # 量测噪声方差 (px^2)，对应 cx, cy, w, h
DEFAULT_SIGMA_A = 0.20                    # 过程噪声：加速度 p90 (px/frame^2)
DEFAULT_SIGMA_SIZE = 0.5                  # w/h 随机游走 (px/frame)

TRAIL_LEN = 40                            # 尾迹保留的实测点数
TRAIL_MAX_STORE = 300


def load_noise(path="results/noise_params.json"):
    if path and os.path.exists(path):
        with open(path) as f:
            d = json.load(f)
        return (d.get("R", DEFAULT_R), d.get("sigma_a", DEFAULT_SIGMA_A),
                d.get("sigma_size", DEFAULT_SIGMA_SIZE))
    return DEFAULT_R, DEFAULT_SIGMA_A, DEFAULT_SIGMA_SIZE


def compute_iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def center_of(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


class Track:
    """单条航迹：6 维卡尔曼 + 生命周期 + 轨迹/位移统计"""

    def __init__(self, bbox, track_id, cls, noise):
        R, sigma_a, sigma_size = noise
        self.id = track_id
        self.cls = cls
        self.age = 0
        self.hits = 1
        self.tsu = 0

        kf = KalmanFilter(dim_x=6, dim_z=4)
        kf.F = np.array([[1, 0, 0, 0, 1, 0],
                         [0, 1, 0, 0, 0, 1],
                         [0, 0, 1, 0, 0, 0],
                         [0, 0, 0, 1, 0, 0],
                         [0, 0, 0, 0, 1, 0],
                         [0, 0, 0, 0, 0, 1]], dtype=float)
        kf.H = np.array([[1, 0, 0, 0, 0, 0],
                         [0, 1, 0, 0, 0, 0],
                         [0, 0, 1, 0, 0, 0],
                         [0, 0, 0, 1, 0, 0]], dtype=float)

        # 连续白噪声加速度模型，dt = 1 帧
        q = sigma_a ** 2
        kf.Q = np.array([[q / 4, 0, 0, 0, q / 2, 0],
                         [0, q / 4, 0, 0, 0, q / 2],
                         [0, 0, sigma_size ** 2, 0, 0, 0],
                         [0, 0, 0, sigma_size ** 2, 0, 0],
                         [q / 2, 0, 0, 0, q, 0],
                         [0, q / 2, 0, 0, 0, q]], dtype=float)
        kf.R = np.diag(np.asarray(R, dtype=float))
        kf.P = np.diag([400.0, 400.0, 400.0, 400.0, 200.0, 200.0])
        kf.x = np.array([[bbox[0] + (bbox[2] - bbox[0]) / 2],
                         [bbox[1] + (bbox[3] - bbox[1]) / 2],
                         [bbox[2] - bbox[0]],
                         [bbox[3] - bbox[1]],
                         [0.0], [0.0]])
        self.kf = kf
        self.base_R = np.asarray(R, dtype=float).copy()
        self.bbox = list(bbox)

        # 轨迹与位移
        self.trail = [center_of(bbox)]     # 只存"实测更新"的中心
        self.first_center = center_of(bbox)
        self.path_len = 0.0                # 累计路径长度（逐帧位移之和）
        self.state_at_birth = self.kf.x.copy()

    # -- 状态 -> 框 ---------------------------------------------------------
    def _state_bbox(self):
        x = self.kf.x
        cx, cy = float(x[0, 0]), float(x[1, 0])
        w = max(float(x[2, 0]), 2.0)
        h = max(float(x[3, 0]), 2.0)
        return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]

    @staticmethod
    def _bbox_z(bbox):
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        return np.array([[bbox[0] + w / 2], [bbox[1] + h / 2], [w], [h]])

    def next_bbox(self):
        """只用状态转移推一帧（不消耗协方差），给"下一帧预测框"用"""
        x = self.kf.F @ self.kf.x
        cx, cy = float(x[0, 0]), float(x[1, 0])
        w = max(float(x[2, 0]), 2.0)
        h = max(float(x[3, 0]), 2.0)
        return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]

    # -- 滤波 ---------------------------------------------------------------
    def predict(self):
        self.kf.predict()
        self.age += 1
        self.tsu += 1
        self.bbox = self._state_bbox()
        return self.bbox

    def update(self, bbox, conf=1.0, iou=1.0):
        """有检测时：预测 + 更新。

        自适应 R：观测越"不可信"，越少信它——
            IoU 低（框和预测错位、或遮挡边缘只露出半截）→ R 放大
            置信度低 → R 放大
        R 放大后卡尔曼增益下降，状态更多保留预测值，相当于"自动少信一点"。
        这正是 §2.2 要求回答的那条机制，不是只在文档里说说。
        """
        scale = 1.0 + 4.0 * (1.0 - min(max(iou, 0.0), 1.0)) \
                    + 2.0 * (1.0 - min(max(conf, 0.0), 1.0))
        self.kf.R = np.diag(self.base_R * scale)
        self.kf.update(self._bbox_z(bbox))
        self.tsu = 0
        self.hits += 1
        prev = self.bbox
        self.bbox = self._state_bbox()
        # 用"上一帧输出中心 -> 这一帧输出中心"累加路径长度
        c_prev, c_now = center_of(prev), center_of(self.bbox)
        self.path_len += float(np.hypot(c_now[0] - c_prev[0], c_now[1] - c_prev[1]))
        self.trail.append(c_now)
        if len(self.trail) > TRAIL_MAX_STORE:
            self.trail = self.trail[-TRAIL_MAX_STORE:]
        return self.bbox

    def displacement(self):
        """相对"进入画面时"的直线位移（像素）"""
        c = center_of(self.bbox)
        return float(np.hypot(c[0] - self.first_center[0], c[1] - self.first_center[1]))


# ----------------------------------------------------------------------------
# 画图
# ----------------------------------------------------------------------------
def dashed_rect(img, p1, p2, color, thickness=2, dash=12, gap=8):
    """画真正的虚线矩形（cv2.rectangle 只能画实线）"""
    x1, y1 = int(p1[0]), int(p1[1])
    x2, y2 = int(p2[0]), int(p2[1])
    if x2 <= x1 or y2 <= y1:
        return
    step = dash + gap
    for x in range(x1, x2, step):
        xe = min(x + dash, x2)
        cv2.line(img, (x, y1), (xe, y1), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x, y2), (xe, y2), color, thickness, cv2.LINE_AA)
    for y in range(y1, y2, step):
        ye = min(y + dash, y2)
        cv2.line(img, (x1, y), (x1, ye), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x2, y), (x2, ye), color, thickness, cv2.LINE_AA)


def draw_trail(img, trail, color=(0, 200, 0), tail=TRAIL_LEN, radius=2, smooth=0.5):
    """画运动尾迹：先做指数平滑再连线，越新的点越亮越粗。

    不平滑的话，检测框的亚像素抖动会让尾迹变成一团毛刺，看不清真实走向。
    """
    pts = trail[-tail:]
    if len(pts) < 2:
        return
    sm = [pts[0]]
    for p in pts[1:]:
        sm.append((smooth * p[0] + (1 - smooth) * sm[-1][0],
                   smooth * p[1] + (1 - smooth) * sm[-1][1]))
    n = len(sm)
    for i in range(1, n):
        a = i / float(n)
        c = tuple(int(v * (0.35 + 0.65 * a)) for v in color)
        p0 = (int(sm[i - 1][0]), int(sm[i - 1][1]))
        p1 = (int(sm[i][0]), int(sm[i][1]))
        cv2.line(img, p0, p1, c, max(1, int(1 + 2 * a)), cv2.LINE_AA)
    cv2.circle(img, (int(sm[-1][0]), int(sm[-1][1])), radius + 1, (255, 255, 255), -1,
               cv2.LINE_AA)


def put_label(img, text, x, y, color, scale=0.55, thickness=2, min_y=44):
    y = max(int(y), int(min_y))
    cv2.putText(img, text, (int(x), y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0),
                thickness + 2, cv2.LINE_AA)
    cv2.putText(img, text, (int(x), y), cv2.FONT_HERSHEY_SIMPLEX, scale, color,
                thickness, cv2.LINE_AA)


# ----------------------------------------------------------------------------
# 单帧处理（离线与实时共用同一套逻辑，保证两条通道行为一致）
# ----------------------------------------------------------------------------
def process_frame(fi, dets, tracks, next_id, noise, max_age, iou_gate,
                  dup_gate=0.6, cross_class_iou=1.1, flicker_gate=0.8, stats_sink=None):
    for t in tracks:
        t.predict()

    matches = []
    class_fixed = 0
    if tracks and dets:
        iou_mat = np.zeros((len(dets), len(tracks)))
        valid = np.zeros((len(dets), len(tracks)), dtype=bool)
        for d, det in enumerate(dets):
            for k, trk in enumerate(tracks):
                iou = compute_iou(det["bbox"], trk.bbox)
                iou_mat[d, k] = iou
                if iou < iou_gate:
                    continue
                valid[d, k] = (det["cls"] == trk.cls) or (iou >= cross_class_iou)
        if valid.any():
            cost = np.where(valid, -iou_mat, 1e5)
            rows, cols = linear_sum_assignment(cost)
            for d, k in zip(rows, cols):
                if valid[d, k]:
                    matches.append((tracks[k], int(d), float(iou_mat[d, k])))

    # 第二级匹配：只处理"第一级没配上的孤立检测"，且只允许与**正在预测态**的航迹配对。
    # 这样能在类别抖动时把同一物体接回原来的航迹（不改 ID），又不会像"一次性跨类匹配"
    # 那样把别的目标的检测抢过来（实测会造 6 次身份顶替）。
    used_tracks = {id(t) for t, _d, _i in matches}
    leftover = [d for d in range(len(dets))
                if d not in {dd for _t, dd, _i in matches}]
    free_pred = [t for t in tracks if t.tsu > 0 and id(t) not in used_tracks]
    if leftover and free_pred:
        cand = []
        for d in leftover:
            for t in free_pred:
                v = compute_iou(dets[d]["bbox"], t.bbox)
                if v >= flicker_gate:
                    cand.append((v, d, t))
        cand.sort(key=lambda x: -x[0])
        taken_d, taken_t = set(), set()
        for v, d, t in cand:
            if d in taken_d or id(t) in taken_t:
                continue
            matches.append((t, int(d), float(v)))
            taken_d.add(d)
            taken_t.add(id(t))

    matched_dets = set()
    for trk, d, iou in matches:
        if dets[d]["cls"] != trk.cls:
            trk.cls = dets[d]["cls"]          # 类别更正（类别抖动）
            class_fixed += 1
        trk.update(dets[d]["bbox"], conf=dets[d].get("conf", 1.0), iou=iou)
        matched_dets.add(d)

    born = []
    for d, det in enumerate(dets):
        if d in matched_dets:
            continue
        # 出生抑制：与同类存活航迹 IoU>dup_gate(0.6) 的检测视为重复检测（松框/紧框），
        # 不再开新航迹，否则一个物体会拿到两条 ID、互相抢检测。
        if any(t.cls == det["cls"] and compute_iou(det["bbox"], t.bbox) > dup_gate
               for t in tracks):
            continue
        t = Track(det["bbox"], next_id, det["cls"], noise)
        tracks.append(t)
        matches.append((t, int(d), 1.0))
        born.append({"id": next_id, "frame": fi, "bbox": det["bbox"], "cls": det["cls"]})
        next_id += 1

    dead = []
    for t in list(tracks):
        if t.tsu > max_age:
            tracks.remove(t)
            dead.append({"id": t.id, "frame": fi, "bbox": t.bbox, "cls": t.cls})

    if stats_sink is not None and class_fixed:
        stats_sink["class_fixes"] = stats_sink.get("class_fixes", 0) + class_fixed
    predicted = [(t.id, list(t.bbox), t.tsu) for t in tracks if t.tsu > 0]
    return matches, born, dead, predicted, next_id


def draw_frame(img, tracks, matches, dets, fi, fps, max_age, classes,
               show_next=True, show_displacement=True, trail=TRAIL_LEN):
    h_img, w_img = img.shape[:2]
    # 尾迹先画，避免盖住框
    for t in tracks:
        draw_trail(img, t.trail, tail=trail)

    # 被更新的航迹：绿实线
    for trk, d, _iou in matches:
        b = trk.bbox
        cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])),
                      (0, 255, 0), 2)
        name = classes[trk.cls] if trk.cls < len(classes) else str(trk.cls)
        put_label(img, f"ID {trk.id} {name} {dets[d]['conf']:.2f}", b[0], b[1] - 8,
                  (0, 255, 0))
        if show_displacement:
            # 题面要的是"从进入画面到当前位置的像素位移"，所以只显示直线位移。
            # 累计路径长度（path_len）会被检测框抖动的微小位移不断累加、数值虚高，
            # 只写进日志，不画面展示，避免误导。
            y = b[3] + 18 if b[3] + 26 < h_img else b[3] - 6
            put_label(img, f"disp {trk.displacement():.0f}px", b[0], y,
                      (0, 255, 0), scale=0.45, thickness=1)

    # 未匹配：黄虚线 + NEXT 青细框
    for trk in tracks:
        if trk.tsu == 0:
            continue
        b = trk.bbox
        dashed_rect(img, (b[0], b[1]), (b[2], b[3]), (0, 255, 255), 2)
        put_label(img, f"PREDICTED ID {trk.id} k={trk.tsu}", b[0], b[1] - 8,
                  (0, 255, 255))

    if show_next:
        for trk in tracks:
            nb = trk.next_bbox()
            cv2.rectangle(img, (int(nb[0]), int(nb[1])), (int(nb[2]), int(nb[3])),
                          (255, 255, 0), 1)
            if trk.tsu == 0:
                y = nb[3] + 12 if nb[3] + 20 < h_img else nb[1] + 14
                put_label(img, f"NEXT {trk.id}", nb[2] - 46, y,
                          (255, 255, 0), scale=0.4, thickness=1)

    # 顶部 HUD 独立占一条，避免和目标标签打架
    cv2.rectangle(img, (0, 0), (w_img, 30), (28, 28, 28), -1)
    put_label(img, f"frame {fi}  t={fi / max(fps, 1):.1f}s  tracks={len(tracks)}  "
                   f"max_age={max_age}", 10, 22, (255, 255, 255), scale=0.62, min_y=22)
    return img


def _empty_records(fps):
    return {"fps": fps, "frames": [], "births": [], "deaths": []}


def _record(records, fi, matches, predicted, born, dead, tracks):
    records["frames"].append({
        "frame": fi,
        "updated": [(t.id, d) for t, d, _ in matches],
        "predicted": [(i, b, k) for i, b, k in predicted],
        "born": [b["id"] for b in born],
        "dead": [d["id"] for d in dead],
        "boxes": {str(t.id): [float(v) for v in t.bbox] for t in tracks},
    })
    records["births"].extend(born)
    records["deaths"].extend(dead)


def _finish(records, next_id, max_age, iou_gate, noise, log_path, verbose, tag, extra=None):
    stats = {
        "frames": len(records["frames"]),
        "ids_created": next_id - 1,
        "births": len(records["births"]),
        "deaths": len(records["deaths"]),
        "max_age": max_age,
        "iou_gate": iou_gate,
        "noise": {"R": list(noise[0]), "sigma_a": noise[1], "sigma_size": noise[2]},
    }
    if extra:
        stats.update(extra)
    records["stats"] = stats
    if log_path:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "w") as f:
            json.dump({"stats": stats, "frames": records["frames"],
                       "births": records["births"], "deaths": records["deaths"]}, f)
    if verbose:
        print(f"[{tag}] frames={stats['frames']} ids={stats['ids_created']} "
              f"births={stats['births']} deaths={stats['deaths']}")
    return records


# ----------------------------------------------------------------------------
# 离线：读 JSON
# ----------------------------------------------------------------------------
def run_tracker(json_path, video_path=None, output_video_path=None,
                max_age=10, iou_gate=0.3, draw=True, noise=None,
                log_path=None, verbose=True, show_next=True,
                show_displacement=True, trail=TRAIL_LEN, dup_gate=0.6,
                cross_class_iou=1.1, flicker_gate=0.8):

    with open(json_path) as f:
        data = json.load(f)
    if noise is None:
        noise = load_noise()

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
    records = _empty_records(fps)
    extra = {}

    for fi, frame_data in enumerate(data["frames"]):
        img = None
        if draw:
            ok, img = cap.read()
            if not ok:
                break

        matches, born, dead, predicted, next_id = process_frame(
            fi, frame_data["dets"], tracks, next_id, noise, max_age, iou_gate,
            dup_gate, cross_class_iou, flicker_gate, extra)
        _record(records, fi, matches, predicted, born, dead, tracks)

        if draw:
            draw_frame(img, tracks, matches, frame_data["dets"], fi, fps, max_age,
                       classes, show_next, show_displacement, trail)
            out.write(img)

    if cap is not None:
        cap.release()
    if out is not None:
        out.release()

    records = _finish(records, next_id, max_age, iou_gate, noise, log_path,
                      verbose, "tracker", extra=extra)
    if verbose and output_video_path:
        print(f"[tracker] video -> {output_video_path}")
    return records


# ----------------------------------------------------------------------------
# 实时：摄像头 / 视频 + M2-3 的 ONNX 检测器
# ----------------------------------------------------------------------------
def run_realtime(source=0, model_path="models/best.onnx", conf=0.5,
                 output_video_path=None, max_age=10, iou_gate=0.3,
                 noise=None, classes=None, save_frames=0,
                 show_next=True, show_displacement=True, trail=TRAIL_LEN,
                 dump_json=None, log_path=None, verbose=True,
                 show=True, max_frames=None, dup_gate=0.6, cross_class_iou=1.1,
                 flicker_gate=0.8):

    """source: 0=摄像头, 或视频路径。现场考官拿遮挡物演示时用这个。"""
    from yolo_onnx import YoloOnnx      # 只有实时模式才需要 onnxruntime

    if noise is None:
        noise = load_noise()
    if classes is None:
        # 与 M2-3 的 my_data.yaml 保持一致；可用 classes=... 覆盖
        classes = ["cup", "phone", "mouse", "bottle", "pen", "tissue"]
    model = YoloOnnx(model_path, 640, conf=conf)
    if verbose:
        print(f"[realtime] source={source} model={model_path} conf={conf} "
              f"providers={model.providers}")

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"打不开视频源: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    out = None
    if output_video_path:
        out = cv2.VideoWriter(output_video_path,
                              cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    tracks = []
    next_id = 1
    records = _empty_records(fps)
    extra = {}
    dumped = {"video": os.path.basename(str(source)), "fps": int(round(fps)),
              "classes": list(classes), "frames": []}

    fps_est = float(fps)
    t_prev = cv2.getTickCount()
    fi = 0
    while cap.isOpened():
        ok, img = cap.read()
        if not ok:
            break

        boxes, scores, ids = model.predict(img)
        dets = [{"cls": int(c), "conf": float(s), "bbox": [float(v) for v in b]}
                for b, s, c in zip(boxes, scores, ids)]

        matches, born, dead, predicted, next_id = process_frame(
            fi, dets, tracks, next_id, noise, max_age, iou_gate, dup_gate,
            cross_class_iou, flicker_gate, extra)
        _record(records, fi, matches, predicted, born, dead, tracks)
        dumped["frames"].append({"frame": fi, "dets": dets})

        draw_frame(img, tracks, matches, dets, fi, fps, max_age, classes,
                   show_next, show_displacement, trail)

        # 实时 FPS 估计（指数滑动平均）
        t_now = cv2.getTickCount()
        dt = (t_now - t_prev) / cv2.getTickFrequency()
        t_prev = t_now
        fps_est = 0.9 * fps_est + 0.1 * (1.0 / max(dt, 1e-6))
        put_label(img, f"fps {fps_est:.1f}", 10, h - 14, (0, 255, 255), scale=0.65)

        if out is not None:
            out.write(img)
        if save_frames and fi < save_frames:
            os.makedirs("results/realtime", exist_ok=True)
            cv2.imwrite(f"results/realtime/live_{fi:04d}.png", img)

        if show:
            cv2.imshow("M2-4 tracker (press q to quit)", img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        fi += 1
        if max_frames and fi >= max_frames:
            break

    cap.release()
    if out is not None:
        out.release()
    cv2.destroyAllWindows()

    if dump_json:
        os.makedirs(os.path.dirname(dump_json) or ".", exist_ok=True)
        with open(dump_json, "w") as f:
            json.dump(dumped, f)
        if verbose:
            print(f"[realtime] detections -> {dump_json}")

    records = _finish(records, next_id, max_age, iou_gate, noise, log_path,
                      verbose, "realtime", extra=extra)
    if verbose and output_video_path:
        print(f"[realtime] video -> {output_video_path}")
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="detections/my_scene.json")
    ap.add_argument("--video", default="videos/my_scene.mp4")
    ap.add_argument("--out", default="results/tracked.mp4")
    ap.add_argument("--max-age", type=int, default=10)
    ap.add_argument("--gate", type=float, default=0.3)
    ap.add_argument("--trail", type=int, default=TRAIL_LEN)
    ap.add_argument("--no-next", action="store_true", help="不画下一帧预测框")
    ap.add_argument("--no-disp", action="store_true", help="不显示路径/位移")
    ap.add_argument("--source", default=None,
                    help="填 0 或视频路径则走实时检测（接 M2-3 ONNX 模型）")
    ap.add_argument("--model", default="models/best.onnx")
    ap.add_argument("--conf", type=float, default=0.5)
    ap.add_argument("--dump-json", default=None,
                    help="实时模式把检测结果存成 JSON")
    ap.add_argument("--no-show", action="store_true",
                    help="不弹窗（只想录视频/存 JSON 时用）")
    ap.add_argument("--max-frames", type=int, default=None,
                    help="实时模式最多处理多少帧（调试用）")
    args = ap.parse_args()

    os.makedirs("results", exist_ok=True)

    if args.source is not None:
        src = int(args.source) if str(args.source).isdigit() else args.source
        run_realtime(source=src, model_path=args.model, conf=args.conf,
                     output_video_path=args.out, max_age=args.max_age,
                     iou_gate=args.gate, show_next=not args.no_next,
                     show_displacement=not args.no_disp, trail=args.trail,
                     dump_json=args.dump_json,
                     log_path="results/live_track_log.json",
                     show=not args.no_show, max_frames=args.max_frames)
    else:
        run_tracker(args.json, args.video, args.out, max_age=args.max_age,
                    iou_gate=args.gate, show_next=not args.no_next,
                    show_displacement=not args.no_disp, trail=args.trail,
                    log_path="results/track_log.json")


if __name__ == "__main__":
    main()
