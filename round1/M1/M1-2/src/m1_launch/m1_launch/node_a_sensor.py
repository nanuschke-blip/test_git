import math
import random

import rclpy
from rclpy.node import Node

from sensor_interfaces.msg import SensorData


class SensorPublisher(Node):
    """节点A：10 Hz 发布模拟超声波距离（相对话题名 sensor_data）。"""

    def __init__(self):
        super().__init__('node_a_sensor')
        # 相对名：加命名空间后自动变成 /<ns>/sensor_data
        self.pub = self.create_publisher(SensorData, 'sensor_data', 10)
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.t = 0.0
        self.period = 4.0
        self.get_logger().info(f'A_Sensor 已启动，话题={self.pub.topic_name}')

    def timer_callback(self):
        msg = SensorData()
        self.t += 0.1
        base = 0.60 + 0.45 * math.sin(2.0 * math.pi * self.t / self.period)
        if random.random() < 0.10:
            msg.status = 1
            msg.distance = 9.99
        else:
            msg.status = 0
            msg.distance = max(0.05, base + random.uniform(-0.02, 0.02))
        msg.unit = "m"
        msg.stamp = self.get_clock().now().to_msg()
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SensorPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
