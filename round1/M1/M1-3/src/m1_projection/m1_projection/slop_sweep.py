#!/usr/bin/env python3
"""slop 扫描实验：离线读 bag，统计不同 slop 下"能配上的帧数"与"配对时间差"

说明：这里用"按时间顺序贪心找最近未用相机帧"来近似 ApproximateTimeSynchronizer 的配对，
用于比较不同 slop 的趋势；真实节点用的是 message_filters 的 ApproximateTimeSynchronizer，
两者在同一份数据上的配对数很接近（README 里有对照）。

图用 OpenCV 画（不依赖 matplotlib，避免 numpy 版本冲突）。

用法：
    python3 slop_sweep.py --bag sample_bag --out slop_sweep.csv --plot slop_sweep.png
"""
import argparse
import csv

import cv2
import numpy as np

from rclpy.serialization import deserialize_message
from rosbag2_py import ConverterOptions, SequentialReader, StorageOptions
from sensor_msgs.msg import Image, LaserScan


def read_stamps(bag):
    reader = SequentialReader()
    reader.open(StorageOptions(uri=bag, storage_id='sqlite3'), ConverterOptions('', ''))
    scans, cams = [], []
    while reader.has_next():
        topic, data, _t = reader.read_next()
        if topic == '/scan':
            m = deserialize_message(data, LaserScan)
            scans.append(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
        elif topic == '/camera/image_raw':
            m = deserialize_message(data, Image)
            cams.append(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
    return np.array(sorted(scans)), np.array(sorted(cams))


def match(scans, cams, slop):
    """贪心：按时间顺序给每个 scan 找 |dt|<=slop 的最近未用相机帧"""
    used = set()
    dts = []
    for ts in scans:
        best, best_dt = None, None
        for k, tc in enumerate(cams):
            if k in used:
                continue
            d = tc - ts
            if d > slop:
                break
            if abs(d) <= slop and (best_dt is None or abs(d) < abs(best_dt)):
                best, best_dt = k, d
        if best is not None:
            used.add(best)
            dts.append(abs(best_dt))
    return dts


def plot_cv(rows, path):
    W, H = 900, 460
    m = 70
    img = np.full((H, W, 3), 255, np.uint8)
    xs = [r['slop_ms'] for r in rows]
    rates = [r['match_rate'] * 100 for r in rows]
    dts = [r['median_dt_ms'] for r in rows]

    def X(v):
        return int(m + (v - min(xs)) / max(max(xs) - min(xs), 1) * (W - 2 * m))

    def Y(v, vmax):
        return int(H - m - v / max(vmax, 1e-6) * (H - 2 * m))

    # 网格
    for g in range(0, 101, 20):
        y = Y(g, 100)
        cv2.line(img, (m, y), (W - m, y), (230, 230, 230), 1)
        cv2.putText(img, f'{g}', (m - 40, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (90, 90, 90), 1)
    for v in xs:
        x = X(v)
        cv2.line(img, (x, m), (x, H - m), (240, 240, 240), 1)
        cv2.putText(img, str(v), (x - 10, H - m + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (90, 90, 90), 1)

    pts_r = [(X(v), Y(r, 100)) for v, r in zip(xs, rates)]
    pts_d = [(X(v), Y(d, max(dts) * 1.3 if max(dts) > 0 else 1)) for v, d in zip(xs, dts)]
    for pts, color in ((pts_r, (200, 90, 30)), (pts_d, (30, 60, 200))):
        for i in range(len(pts) - 1):
            cv2.line(img, pts[i], pts[i + 1], color, 2, cv2.LINE_AA)
        for p in pts:
            cv2.circle(img, p, 4, color, -1, cv2.LINE_AA)

    cv2.putText(img, 'slop (ms)', (W // 2 - 40, H - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (60, 60, 60), 1)
    cv2.putText(img, 'matched frames (%)', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (200, 90, 30), 1)
    cv2.putText(img, 'median |dt| (ms, scaled)', (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (30, 60, 200), 1)
    cv2.putText(img, f'ApproximateTime slop sweep  (scan={rows[0]["total"]} frames)',
                (W // 2 - 220, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 30, 30), 1)
    cv2.imwrite(path, img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bag', default='sample_bag')
    ap.add_argument('--out', default='slop_sweep.csv')
    ap.add_argument('--plot', default='slop_sweep.png')
    ap.add_argument('--slops', default='0.005,0.008,0.010,0.012,0.015,0.018,0.020,0.030,0.060,0.100')
    args = ap.parse_args()

    scans, cams = read_stamps(args.bag)
    print(f'[sweep] {len(scans)} 帧雷达, {len(cams)} 帧相机')

    rows = []
    for s in [float(x) for x in args.slops.split(',')]:
        dts = match(scans, cams, s)
        rows.append(dict(slop_ms=int(s * 1000), matched=len(dts), total=len(scans),
                         match_rate=round(len(dts) / max(len(scans), 1), 3),
                         median_dt_ms=round(float(np.median(dts)) * 1000, 2) if dts else 0.0,
                         max_dt_ms=round(float(np.max(dts)) * 1000, 2) if dts else 0.0))
        print(f'  slop={int(s*1000):>3d} ms -> 配对 {len(dts):>3d}/{len(scans)} '
              f'({rows[-1]["match_rate"]*100:.0f}%), 中位差 {rows[-1]["median_dt_ms"]} ms, '
              f'最大差 {rows[-1]["max_dt_ms"]} ms')

    with open(args.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'[sweep] -> {args.out}')
    plot_cv(rows, args.plot)
    print(f'[sweep] -> {args.plot}')


if __name__ == '__main__':
    main()
