import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import SetParametersResult
from std_msgs.msg import Float32

from sensor_interfaces.srv import TriggerAlarm


class AlarmNode(Node):
    """节点C：订阅滤波结果，近距时调用报警服务。

    M1-2 要求每组只有 3 个节点，所以报警服务端也放在本节点里（服务名同样是相对名
    trigger_alarm，加命名空间后每组各有一个，互不干扰）。
    """

    def __init__(self):
        super().__init__('node_c_alarm')
        self.declare_parameter('alarm_threshold', 0.3)
        self.declare_parameter('service_timeout', 1.0)
        self.add_on_set_parameters_callback(self.on_param_set)

        self.threshold = float(self.get_parameter('alarm_threshold').value)
        self.timeout = float(self.get_parameter('service_timeout').value)

        self.pending = False
        self.future = None
        self._timer = None

        self.sub = self.create_subscription(
            Float32, 'processed_distance', self.callback, 10)
        self.srv = self.create_service(
            TriggerAlarm, 'trigger_alarm', self.handle_alarm)
        self.cli = self.create_client(TriggerAlarm, 'trigger_alarm')

        self.get_logger().info(
            f'C_Alarm 已启动：阈值={self.threshold}m, 超时={self.timeout}s, '
            f'订阅={self.sub.topic_name}, 服务={self.srv.srv_name}')

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

    # ------------------------------------------------------------------ 服务端
    def handle_alarm(self, request, response):
        self.get_logger().error(
            f'[ALARM] 距离过近！当前距离: {request.current_distance:.2f}m')
        response.success = True
        response.message = 'Alarm triggered successfully'
        return response

    # ------------------------------------------------------------------ 超时
    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timeout(self):
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
                self.get_logger().info(f'--> [C_Alarm] {resp.message}')
        except Exception as e:                      # noqa: BLE001
            self.get_logger().error(f'服务调用失败: {e}')

    # ------------------------------------------------------------------ 主回调
    def callback(self, msg):
        dist = float(msg.data)
        if dist >= self.threshold:
            return
        if self.pending:
            return
        req = TriggerAlarm.Request()
        req.current_distance = dist
        self.pending = True
        self.future = self.cli.call_async(req)
        self.future.add_done_callback(self._on_response)
        self._timer = self.create_timer(self.timeout, self._on_timeout)


def main(args=None):
    rclpy.init(args=args)
    node = AlarmNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
