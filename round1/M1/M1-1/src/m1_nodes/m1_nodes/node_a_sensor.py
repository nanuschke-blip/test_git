import math
import random

import rclpy
from rclpy.node import Node

from sensor_interfaces.msg import SensorData


class SensorPublisher(Node):
    """节点A：以 10 Hz 发布模拟超声波距离。

    距离用 4 秒一周期的正弦扫掠（0.15~1.05 m），保证周期性地进入 < 0.3 m 的报警区，
    演示时不用干等；另外按 10% 概率注入 status=1 的超量程假数据，用来检验节点B 的过滤。
    """

    def __init__(self):
        super().__init__('node_a_sensor')
        self.pub = self.create_publisher(SensorData, '/sensor_data', 10)
        self.timer = self.create_timer(0.1, self.timer_callback)   # 10 Hz
        self.t = 0.0
        self.period = 4.0                                          # 扫掠周期 (s)

    def timer_callback(self):
        msg = SensorData()
        self.t += 0.1
        base = 0.60 + 0.45 * math.sin(2.0 * math.pi * self.t / self.period)

        if random.random() < 0.10:
            msg.status = 1
            msg.distance = 9.99          # 超量程假数据（节点B 会滤掉）
        else:
            msg.status = 0
            msg.distance = max(0.05, base + random.uniform(-0.02, 0.02))

        msg.unit = "m"
        msg.stamp = self.get_clock().now().to_msg()
        self.pub.publish(msg)
        self.get_logger().info(f'A_Pub: 距离={msg.distance:.2f}m, 状态={msg.status}')


def main(args=None):
    rclpy.init(args=args)
    node = SensorPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
