import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from sensor_interfaces.srv import TriggerAlarm
from rcl_interfaces.msg import SetParametersResult


class AlarmNode(Node):
    """节点C：订阅滤波后的距离，近距时异步调用报警服务，并自己处理服务超时。"""

    def __init__(self):
        super().__init__('node_c_alarm')

        # 参数：阈值与超时（题面要求默认 0.3 / 1.0，并且能被 ros2 param set 动态修改）
        self.declare_parameter('alarm_threshold', 0.3)
        self.declare_parameter('service_timeout', 1.0)
        self.add_on_set_parameters_callback(self.on_param_set)

        self.threshold = float(self.get_parameter('alarm_threshold').value)
        self.timeout = float(self.get_parameter('service_timeout').value)

        # 一次只允许一个在途请求，避免 10 Hz 下请求堆积
        self.pending = False
        self.future = None
        self._timer = None

        self.sub = self.create_subscription(
            Float32, '/processed_distance', self.callback, 10)
        self.cli = self.create_client(TriggerAlarm, '/trigger_alarm')

        self.get_logger().info(
            f'C_Alarm 已启动。阈值={self.threshold}m, 服务超时={self.timeout}s')

    # ------------------------------------------------------------------ 参数
    def on_param_set(self, params):
        for p in params:
            if p.name == 'alarm_threshold':
                self.threshold = float(p.value)
                self.get_logger().info(f'[参数更新] alarm_threshold={self.threshold}')
            elif p.name == 'service_timeout':
                self.timeout = float(p.value)
                self.get_logger().info(f'[参数更新] service_timeout={self.timeout}')
        return SetParametersResult(successful=True)

    # ------------------------------------------------------------------ 超时
    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timeout(self):
        """定时器到点：请求还没完成就判定超时（不阻塞回调，不和 executor 打架）。"""
        self._cancel_timer()
        if self.future is not None and self.future.done():
            self.pending = False
            return
        self.get_logger().warn(f'[WARN] 报警服务超时 ({self.timeout} 秒无响应)')
        self.pending = False

    def _on_response(self, fut):
        self._cancel_timer()
        self.pending = False
        if fut.cancelled():
            return
        try:
            resp = fut.result()
            if resp.success:
                self.get_logger().info(
                    f'--> [C_Alarm] 收到服务端返回: {resp.message}')
        except Exception as e:                      # noqa: BLE001
            self.get_logger().error(f'服务调用失败: {e}')

    # ------------------------------------------------------------------ 主回调
    def callback(self, msg):
        dist = msg.data
        if dist >= self.threshold:      # 只有小于阈值才报警
            return
        if self.pending:                # 上一次还没结束，跳过本次
            return

        req = TriggerAlarm.Request()
        req.current_distance = dist

        self.pending = True
        self.future = self.cli.call_async(req)          # 存到成员变量
        self.future.add_done_callback(self._on_response)
        # 定时器必须在两个回调方法都定义好之后再创建
        self._timer = self.create_timer(self.timeout, self._on_timeout)


def main(args=None):
    rclpy.init(args=args)
    node = AlarmNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
