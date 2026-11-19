#!/usr/bin/env python3
"""M1-3 合成数据生成器：写一个离线 rosbag（/scan + /camera/image_raw + /camera/camera_info）

场景：base_link 原点在桌面上，前方摆着若干竖直长方体（柱子），其中几根随时间缓慢横移。
- 激光：180 线，-90°~+90°，10 Hz，时间戳带抖动；只返回 z = laser_link.z 平面上的交点。
- 相机：640x480 rgb8，27 Hz，时间戳带抖动、且与雷达不同相位；图像就是把同一批长方体
  按相机内参投影后画出来的实心四边形。
因为两者用的是同一套几何与同一份 extrinsics，所以把激光点投影回图像时，点应当正好落在
画出来的柱子上——这就是 M1-3 要验证的东西。

用法：
    python3 make_bag.py                          # 200 帧（≈20 s，约 500 MB，注意磁盘）
    python3 make_bag.py --frames 40 --seed 7     # 短场景，测试用
    python3 make_bag.py --laser-z 0.45 --camera-z 0.75 --fx 420   # 换一组外参/内参
"""
import argparse
import math
import os
import shutil

import cv2
import numpy as np
import yaml

import rclpy
from rclpy.serialization import serialize_message

from builtin_interfaces.msg import Time
from sensor_msgs.msg import CameraInfo, Image, LaserScan
from std_msgs.msg import Header

from rosbag2_py import (ConverterOptions, SequentialWriter, StorageOptions,
                        TopicMetadata)

IMG_W, IMG_H = 640, 480
LASER_RAYS = 180
LASER_ANGLE_MIN = -math.pi / 2
LASER_ANGLE_MAX = math.pi / 2
RANGE_MAX = 10.0
SCAN_HZ = 10.0
CAM_HZ = 27.0


# ---------------------------------------------------------------- 场景
def make_scene(seed):
    """若干竖直长方体：中心 (cx,cy)、半宽 hx,hy、高度 z0~z1、颜色、速度 (vx,vy)。"""
    rng = np.random.RandomState(seed)
    boxes = []
    # 三根静止的柱子
    for cx, cy, hx, hy, color in [
        (2.6, -0.9, 0.14, 0.14, (60, 120, 220)),
        (3.4, 0.0, 0.18, 0.18, (200, 140, 60)),
        (4.2, 1.0, 0.16, 0.16, (80, 200, 120)),
    ]:
        boxes.append(dict(cx=cx, cy=cy, hx=hx, hy=hy, z0=0.0, z1=0.9,
                          color=color, vx=0.0, vy=0.0))
    # 两根缓慢横移的柱子
    for cx, cy, hx, hy, color, vy in [
        (3.0, 0.7, 0.12, 0.12, (220, 90, 90), -0.25),
        (4.6, -0.6, 0.15, 0.15, (150, 90, 220), 0.20),
    ]:
        boxes.append(dict(cx=cx, cy=cy, hx=hx, hy=hy, z0=0.0, z1=1.1,
                          color=color, vx=0.0, vy=vy))
    rng.shuffle(boxes)
    return boxes


def boxes_at(boxes, t):
    out = []
    for b in boxes:
        c = dict(b)
        c["cx"] = b["cx"] + b["vx"] * t
        c["cy"] = b["cy"] + b["vy"] * t
        out.append(c)
    return out


# ---------------------------------------------------------------- 激光
def raycast_scan(boxes, laser_xyz):
    """2D 射线投射：返回每个角度上的距离（无交点用 inf）。"""
    ranges = []
    lz = laser_xyz[2]
    for i in range(LASER_RAYS):
        a = LASER_ANGLE_MIN + (LASER_ANGLE_MAX - LASER_ANGLE_MIN) * i / (LASER_RAYS - 1)
        dx, dy = math.cos(a), math.sin(a)
        best = math.inf
        for b in boxes:
            if b["z0"] > lz or b["z1"] < lz:
                continue
            x0, x1 = b["cx"] - b["hx"], b["cx"] + b["hx"]
            y0, y1 = b["cy"] - b["hy"], b["cy"] + b["hy"]
            tmin, tmax = -math.inf, math.inf
            ok = True
            for p, d, lo, hi in ((laser_xyz[0], dx, x0, x1), (laser_xyz[1], dy, y0, y1)):
                if abs(d) < 1e-9:
                    if p < lo or p > hi:
                        ok = False
                        break
                else:
                    t1, t2 = (lo - p) / d, (hi - p) / d
                    if t1 > t2:
                        t1, t2 = t2, t1
                    tmin, tmax = max(tmin, t1), min(tmax, t2)
                    if tmin > tmax:
                        ok = False
                        break
            if ok and tmin > 1e-3:
                best = min(best, tmin)
        ranges.append(best)
    return ranges


# ---------------------------------------------------------------- 相机
def rpy_to_matrix(r, p, y):
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


# 机体坐标系（x 前, y 左, z 上）-> 光学坐标系（x 右, y 下, z 前）
R_BODY_TO_OPT = np.array([[0.0, -1.0, 0.0],
                          [0.0, 0.0, -1.0],
                          [1.0, 0.0, 0.0]])


def project(points_body, cam_xyz, cam_R, intr):
    """把 base_link 下的点投到像素；返回 (u, v, depth, mask)"""
    p = np.asarray(points_body, dtype=float)
    pc = (p - np.asarray(cam_xyz, dtype=float)) @ cam_R.T      # 到相机机体坐标
    po = pc @ R_BODY_TO_OPT.T                                  # 到手光学坐标
    z = po[:, 2]
    mask = z > 1e-3
    u = np.full(len(p), -1.0)
    v = np.full(len(p), -1.0)
    fx, fy = intr["fx"], intr["fy"]
    cx, cy = intr["cx"], intr["cy"]
    u[mask] = fx * po[mask, 0] / z[mask] + cx
    v[mask] = fy * po[mask, 1] / z[mask] + cy
    return u, v, z, mask


def render_image(boxes, cam_xyz, cam_R, intr, rng):
    img = np.zeros((IMG_H, IMG_W, 3), np.uint8)
    # 背景：上暗下亮的灰蓝渐变 + 噪声
    grad = np.linspace(90, 170, IMG_H).astype(np.uint8)[:, None]
    img[:, :, 0] = grad
    img[:, :, 1] = (grad * 0.95).astype(np.uint8)
    img[:, :, 2] = (grad * 1.05).clip(0, 255).astype(np.uint8)
    img = np.clip(img.astype(np.int16) + rng.randint(-6, 7, img.shape), 0, 255).astype(np.uint8)

    order = sorted(boxes, key=lambda b: -(b["cx"] ** 2 + b["cy"] ** 2))
    for b in order:
        x0, x1 = b["cx"] - b["hx"], b["cx"] + b["hx"]
        y0, y1 = b["cy"] - b["hy"], b["cy"] + b["hy"]
        z0, z1 = b["z0"], b["z1"]
        face = np.array([[x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1]])
        u, v, z, mask = project(face, cam_xyz, cam_R, intr)
        if not mask.all():
            continue
        pts = np.stack([u, v], axis=1).astype(np.int32)
        if cv2.contourArea(pts) < 4:
            continue
        shade = 0.75 + 0.25 * rng.rand()
        color = tuple(int(c * shade) for c in b["color"])
        cv2.fillConvexPoly(img, pts, color, lineType=cv2.LINE_AA)
        cv2.polylines(img, [pts], True, tuple(min(255, int(c * 1.15)) for c in color),
                      2, cv2.LINE_AA)
    return img


# ---------------------------------------------------------------- 时间戳
def to_time(ns):
    t = Time()
    t.sec = int(ns // 1_000_000_000)
    t.nanosec = int(ns % 1_000_000_000)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=200, help="雷达帧数（每帧约 2.5 MB）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--laser-x", type=float, default=0.15)
    ap.add_argument("--laser-z", type=float, default=0.20)
    ap.add_argument("--camera-x", type=float, default=0.10)
    ap.add_argument("--camera-z", type=float, default=0.30)
    ap.add_argument("--fx", type=float, default=500.0)
    ap.add_argument("--fy", type=float, default=None)
    ap.add_argument("--cx", type=float, default=320.0)
    ap.add_argument("--cy", type=float, default=240.0)
    ap.add_argument("--out", default="sample_bag")
    ap.add_argument("--extrinsics", default="extrinsics.yaml")
    args = ap.parse_args()

    fy = args.fx if args.fy is None else args.fy
    intr = dict(fx=args.fx, fy=fy, cx=args.cx, cy=args.cy)
    laser_xyz = [args.laser_x, 0.0, args.laser_z]
    cam_xyz = [args.camera_x, 0.0, args.camera_z]
    cam_R = rpy_to_matrix(0.0, 0.0, 0.0)

    ext = {
        "laser_link": {"parent": "base_link", "xyz": laser_xyz},
        "camera_link": {"parent": "base_link", "xyz": cam_xyz, "rpy": [0.0, 0.0, 0.0]},
        "camera_intrinsics": intr,
    }
    with open(args.extrinsics, "w") as f:
        yaml.safe_dump(ext, f, sort_keys=False)
    print(f"[make_bag] extrinsics -> {args.extrinsics}")

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    writer = SequentialWriter()
    writer.open(StorageOptions(uri=args.out, storage_id="sqlite3"),
                ConverterOptions("", ""))
    for name, typ in (("/scan", "sensor_msgs/msg/LaserScan"),
                      ("/camera/image_raw", "sensor_msgs/msg/Image"),
                      ("/camera/camera_info", "sensor_msgs/msg/CameraInfo")):
        writer.create_topic(TopicMetadata(name=name, type=typ,
                                          serialization_format="cdr", offered_qos_profiles=""))

    rng = np.random.RandomState(args.seed)
    boxes0 = make_scene(args.seed)
    t0 = 1.0
    dur = args.frames / SCAN_HZ

    # 预先算好每条消息 (stamp_ns, topic, msg)，再按时间排序写入
    msgs = []
    for k in range(args.frames):
        t = t0 + k / SCAN_HZ + rng.uniform(-0.003, 0.003)
        boxes = boxes_at(boxes0, t)
        scan = LaserScan()
        scan.header = Header(stamp=to_time(int(t * 1e9)), frame_id="laser_link")
        scan.angle_min = LASER_ANGLE_MIN
        scan.angle_max = LASER_ANGLE_MAX
        scan.angle_increment = (LASER_ANGLE_MAX - LASER_ANGLE_MIN) / (LASER_RAYS - 1)
        scan.time_increment = 0.0
        scan.scan_time = 1.0 / SCAN_HZ
        scan.range_min = 0.05
        scan.range_max = RANGE_MAX
        scan.ranges = [float(r) for r in raycast_scan(boxes, laser_xyz)]
        msgs.append((int(t * 1e9), "/scan", scan))

    n_cam = int(dur * CAM_HZ)
    for k in range(n_cam):
        t = t0 + k / CAM_HZ + rng.uniform(-0.004, 0.004) + 0.006
        boxes = boxes_at(boxes0, t)
        img = render_image(boxes, cam_xyz, cam_R, intr, rng)
        im = Image()
        im.header = Header(stamp=to_time(int(t * 1e9)), frame_id="camera_link")
        im.height, im.width = IMG_H, IMG_W
        im.encoding = "rgb8"
        im.is_bigendian = 0
        im.step = IMG_W * 3
        im.data = img.tobytes()
        msgs.append((int(t * 1e9), "/camera/image_raw", im))

        ci = CameraInfo()
        ci.header = im.header
        ci.height, ci.width = IMG_H, IMG_W
        ci.distortion_model = "plumb_bob"
        ci.d = [0.0] * 5
        ci.k = [intr["fx"], 0.0, intr["cx"], 0.0, intr["fy"], intr["cy"], 0.0, 0.0, 1.0]
        ci.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        ci.p = [intr["fx"], 0.0, intr["cx"], 0.0, 0.0, intr["fy"], intr["cy"], 0.0,
                0.0, 0.0, 1.0, 0.0]
        msgs.append((int(t * 1e9), "/camera/camera_info", ci))

    msgs.sort(key=lambda x: x[0])
    for stamp_ns, topic, msg in msgs:
        writer.write(topic, serialize_message(msg), stamp_ns)

    n_scan = sum(1 for m in msgs if m[1] == "/scan")
    print(f"[make_bag] {args.out}: {n_scan} 帧雷达, {n_cam} 帧相机, "
          f"{dur:.1f} s, {len(msgs)} 条消息")
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(args.out) for f in fs)
    print(f"[make_bag] bag 体积 ≈ {size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
