import rclpy
from rclpy.node import Node
from sensor_interfaces.msg import SensorData
from std_msgs.msg import Float32
from rcl_interfaces.msg import SetParametersResult

class FilterNode(Node):
    def __init__(self):
        super().__init__('node_b_filter')
        # 声明参数
        self.declare_parameter('alpha', 0.3)
        self.alpha = self.get_parameter('alpha').value
        
        self.sub = self.create_subscription(SensorData, '/sensor_data', self.callback, 10)
        self.pub = self.create_publisher(Float32, '/processed_distance', 10)
        
        self.last_y = 0.0
        self.is_first = True
        
        # 动态参数回调
        self.add_on_set_parameters_callback(self.param_callback)
        self.get_logger().info('B_Filter 已启动，等待数据...')

    def param_callback(self, params):
        for p in params:
            if p.name == 'alpha':
                self.alpha = p.value
                self.get_logger().info(f'--> [参数更新] alpha 已改为: {self.alpha}')
        return SetParametersResult(successful=True)

    def callback(self, msg):
        if msg.status != 0:
            self.get_logger().warn(f'[WARN] 收到无效数据 (status={msg.status})，已滤除')
            return
            
        x_k = msg.distance
        if self.is_first:
            self.last_y = x_k
            self.is_first = False
            
        # 一阶低通滤波
        y_k = self.alpha * x_k + (1.0 - self.alpha) * self.last_y
        self.last_y = y_k
        
        out_msg = Float32()
        out_msg.data = y_k
        self.pub.publish(out_msg)
        self.get_logger().info(f'B_Filter: 原始={x_k:.2f}, 滤波后={y_k:.2f} (alpha={self.alpha})')

def main(args=None):
    rclpy.init(args=args)
    node = FilterNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()