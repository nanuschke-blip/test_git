import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import SetParametersResult
from std_msgs.msg import Float32

from sensor_interfaces.msg import SensorData


class FilterNode(Node):
    """节点B：一阶低通滤波，alpha 来自 YAML 参数，可运行时动态修改。"""

    def __init__(self):
        super().__init__('node_b_filter')
        self.declare_parameter('alpha', 0.3)
        self.alpha = float(self.get_parameter('alpha').value)

        self.sub = self.create_subscription(
            SensorData, 'sensor_data', self.callback, 10)
        self.pub = self.create_publisher(Float32, 'processed_distance', 10)

        self.last_y = 0.0
        self.is_first = True

        self.add_on_set_parameters_callback(self.on_param_set)
        self.get_logger().info(
            f'B_Filter 已启动：alpha={self.alpha}, 订阅={self.sub.topic_name}, '
            f'发布={self.pub.topic_name}')

    def on_param_set(self, params):
        for p in params:
            if p.name == 'alpha':
                self.alpha = float(p.value)
                self.get_logger().info(f'--> [参数更新] alpha={self.alpha}')
        return SetParametersResult(successful=True)

    def callback(self, msg):
        if msg.status != 0:
            self.get_logger().warn(f'[WARN] 无效数据 status={msg.status}，已滤除')
            return
        x_k = float(msg.distance)
        if self.is_first:
            self.last_y = x_k
            self.is_first = False
        y_k = self.alpha * x_k + (1.0 - self.alpha) * self.last_y
        self.last_y = y_k

        out = Float32()
        out.data = y_k
        self.pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = FilterNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
