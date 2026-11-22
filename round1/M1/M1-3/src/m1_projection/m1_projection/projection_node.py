import math
import os

import cv2
import numpy as np
import yaml

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from geometry_msgs.msg import TransformStamped
from message_filters import ApproximateTimeSynchronizer, Subscriber
from sensor_msgs.msg import CameraInfo, Image, LaserScan
from tf2_ros import StaticTransformBroadcaster

# 机体坐标系（x 前, y 左, z 上）-> 光学坐标系（x 右, y 下, z 前）
R_BODY_TO_OPT = np.array([[0.0, -1.0, 0.0],
                          [0.0, 0.0, -1.0],
                          [1.0, 0.0, 0.0]])


def rpy_to_matrix(r, p, y):
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


class ProjectionNode(Node):
    """读 extrinsics.yaml → 发布静态 TF → 同步 /scan 与 /camera/image_raw → 投影 → 出图。"""

    def __init__(self):
        super().__init__('projection_node')

        self.declare_parameter('extrinsics_file', 'extrinsics.yaml')
        self.declare_parameter('output_dir', '.')
        self.declare_parameter('max_images', 3)
        self.declare_parameter('sync_slop', 0.06)
        self.declare_parameter('queue_size', 50)

        self.ext_path = self.get_parameter('extrinsics_file').value
        self.out_dir = self.get_parameter('output_dir').value
        self.max_images = int(self.get_parameter('max_images').value)
        self.slop = float(self.get_parameter('sync_slop').value)
        qsize = int(self.get_parameter('queue_size').value)

        self.ext = self._load_extrinsics(self.ext_path)
        self._publish_static_tf()

        # 内参：优先用 bag 里的 /camera/camera_info，收不到再用 extrinsics.yaml
        self.intr = dict(self.ext['camera_intrinsics'])

        self.bridge_free_pub = self.create_publisher(Image, '/projection/debug_image', 10)
        self.info_sub = self.create_subscription(
            CameraInfo, '/camera/camera_info', self.on_info, 10)

        self.scan_sub = Subscriber(self, LaserScan, '/scan')
        self.img_sub = Subscriber(self, Image, '/camera/image_raw')
        self.sync = ApproximateTimeSynchronizer(
            [self.scan_sub, self.img_sub], queue_size=qsize, slop=self.slop)
        self.sync.registerCallback(self.on_synced)

        self.n_pairs = 0
        self.n_saved = 0
        self.last_save_t = -1e9
        self.first_log_done = False
        os.makedirs(self.out_dir, exist_ok=True)

        self.get_logger().info(
            f'projection_node 已启动: extrinsics={self.ext_path}, slop={self.slop}s, '
            f'queue={qsize}, output_dir={self.out_dir}, max_images={self.max_images}')
        self.get_logger().info(
            f'激光 xyz={self.ext["laser_link"]["xyz"]}, 相机 xyz={self.ext["camera_link"]["xyz"]} '
            f'rpy={self.ext["camera_link"].get("rpy", [0, 0, 0])}, 内参={self.intr}')

    # ---------------------------------------------------------------- 配置
    def _load_extrinsics(self, path):
        if not os.path.isfile(path):
            self.get_logger().error(f'extrinsics 文件不存在: {path}（用 --ros-args -p extrinsics_file:=... 指定）')
            raise SystemExit(1)
        with open(path) as f:
            ext = yaml.safe_load(f)
        for key in ('laser_link', 'camera_link', 'camera_intrinsics'):
            if key not in ext:
                self.get_logger().error(f'extrinsics 缺少字段: {key}')
                raise SystemExit(1)
        return ext

    def _publish_static_tf(self):
        self.tf_pub = StaticTransformBroadcaster(self)
        msgs = []
        # map -> odom -> base_link：本题车身静止，都用单位变换
        for parent, child in (('map', 'odom'), ('odom', 'base_link')):
            msgs.append(self._mk_tf(parent, child, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]))
        laser = self.ext['laser_link']
        cam = self.ext['camera_link']
        msgs.append(self._mk_tf(laser['parent'], 'laser_link', laser['xyz'],
                                laser.get('rpy', [0.0, 0.0, 0.0])))
        msgs.append(self._mk_tf(cam['parent'], 'camera_link', cam['xyz'],
                                cam.get('rpy', [0.0, 0.0, 0.0])))
        self.tf_pub.sendTransform(msgs)
        self.get_logger().info('静态 TF 已发布: map->odom->base_link->{laser_link,camera_link}')

    @staticmethod
    def _mk_tf(parent, child, xyz, rpy):
        t = TransformStamped()
        t.header.frame_id = parent
        t.child_frame_id = child
        t.transform.translation.x = float(xyz[0])
        t.transform.translation.y = float(xyz[1])
        t.transform.translation.z = float(xyz[2])
        q = ProjectionNode._rpy_to_quat(*[float(v) for v in rpy])
        t.transform.rotation.x, t.transform.rotation.y = q[0], q[1]
        t.transform.rotation.z, t.transform.rotation.w = q[2], q[3]
        return t

    @staticmethod
    def _rpy_to_quat(r, p, y):
        cr, sr = math.cos(r / 2), math.sin(r / 2)
        cp, sp = math.cos(p / 2), math.sin(p / 2)
        cy, sy = math.cos(y / 2), math.sin(y / 2)
        return (sr * cp * cy - cr * sp * sy,
                cr * sp * cy + sr * cp * sy,
                cr * cp * sy - sr * sp * cy,
                cr * cp * cy + sr * sp * sy)

    def on_info(self, msg):
        if msg.k[0] > 0 and msg.k[4] > 0:
            self.intr = {'fx': msg.k[0], 'fy': msg.k[4], 'cx': msg.k[2], 'cy': msg.k[5]}

    # ---------------------------------------------------------------- 投影
    def _project(self, scan, img_w, img_h):
        laser = self.ext['laser_link']
        cam = self.ext['camera_link']
        R_laser = rpy_to_matrix(*laser.get('rpy', [0.0, 0.0, 0.0]))
        R_cam = rpy_to_matrix(*cam.get('rpy', [0.0, 0.0, 0.0]))

        ang = scan.angle_min + np.arange(len(scan.ranges)) * scan.angle_increment
        rng = np.asarray(scan.ranges, dtype=float)
        good = np.isfinite(rng) & (rng >= scan.range_min) & (rng <= scan.range_max)
        ang, rng = ang[good], rng[good]

        pts_l = np.stack([rng * np.cos(ang), rng * np.sin(ang),
                          np.zeros_like(ang)], axis=1)
        # 行向量形式：v' = v @ R 等价于 v' = R^T v（把 base 下的点转到传感器系）
        pts_base = pts_l @ R_laser.T + np.asarray(laser['xyz'], dtype=float)
        p_cam = (pts_base - np.asarray(cam['xyz'], dtype=float)) @ R_cam
        p_opt = p_cam @ R_BODY_TO_OPT.T          # 机体 -> 光学，注意是 R.T

        z = p_opt[:, 2]
        fx, fy = self.intr['fx'], self.intr['fy']
        cx, cy = self.intr['cx'], self.intr['cy']
        with np.errstate(divide='ignore', invalid='ignore'):
            u = fx * p_opt[:, 0] / z + cx
            v = fy * p_opt[:, 1] / z + cy
        inside = (z > 0.05) & (u >= 0) & (u < img_w) & (v >= 0) & (v < img_h)
        return u, v, rng, inside

    def on_synced(self, scan, img):
        self.n_pairs += 1
        dt = abs((self.get_clock().now().nanoseconds / 1e9)
                 - (scan.header.stamp.sec + scan.header.stamp.nanosec / 1e9))
        if not self.first_log_done:
            self.first_log_done = True
            self.get_logger().info(
                f'[时间检查] use_sim_time={self.get_parameter("use_sim_time").value}, '
                f'node_clock={self.get_clock().now().nanoseconds / 1e9:.3f}, '
                f'scan_stamp={scan.header.stamp.sec + scan.header.stamp.nanosec / 1e9:.3f}, '
                f'差值={dt:.3f}s')
            if dt > 2.0:
                self.get_logger().warn(
                    '时间基准不一致！回放 bag 请加 use_sim_time:=true（并 ros2 bag play --clock）')

        frame = np.frombuffer(bytes(img.data), dtype=np.uint8).reshape(
            img.height, img.width, 3).copy()

        u, v, rng, inside = self._project(scan, img.width, img.height)
        rr = rng[inside]
        if rr.size:
            rmin, rmax = float(rr.min()), float(rr.max())
        else:
            rmin, rmax = 0.0, 1.0
        span = max(rmax - rmin, 0.5)          # 至少 0.5 m，避免同距离时颜色跳变
        for ui, vi, ri in zip(u[inside], v[inside], rr):
            t = min(max((ri - rmin) / span, 0.0), 1.0)
            color = (int(255 * (1 - t)), 40, int(255 * t))     # 近红远蓝
            cv2.circle(frame, (int(round(ui)), int(round(vi))), 4, color, -1, cv2.LINE_AA)

        out = Image()
        out.header = scan.header
        out.height, out.width = frame.shape[0], frame.shape[1]
        out.encoding = 'rgb8'
        out.is_bigendian = 0
        out.step = frame.shape[1] * 3
        out.data = frame.tobytes()
        self.bridge_free_pub.publish(out)

        now = self.get_clock().now().nanoseconds / 1e9
        if self.n_saved < self.max_images and (now - self.last_save_t) > 0.7:
            self.last_save_t = now
            self.n_saved += 1
            path = os.path.join(self.out_dir, f'projection_{self.n_saved}.png')
            cv2.imwrite(path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            self.get_logger().info(
                f'已保存 {path}（第 {self.n_pairs} 对，点数={int(inside.sum())}，'
                f'stamp={scan.header.stamp.sec}.{scan.header.stamp.nanosec:09d}）')


def main(args=None):
    rclpy.init(args=args)
    node = ProjectionNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            node.get_logger().info(f'共配对 {node.n_pairs} 帧，保存 {node.n_saved} 张图')
        except Exception:                           # noqa: BLE001
            pass
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:                           # noqa: BLE001
            pass


if __name__ == '__main__':
    main()
