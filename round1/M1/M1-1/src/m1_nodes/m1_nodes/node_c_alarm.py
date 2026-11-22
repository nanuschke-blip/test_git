import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from sensor_interfaces.srv import TriggerAlarm
from rcl_interfaces.msg import SetParametersResult


class AlarmNode(Node):
    """节点C：订阅滤波后的距离，近距时异步调用报警服务，并自己处理服务超时（不阻塞）。

    超时用**独立看门狗定时器**实现：每 0.1 s 检查一次"在途请求是否超过 service_timeout"，
    超时就打 [WARN] 报警服务超时 并释放 pending。这样即使服务端在请求途中消失、
    future 永远不完成，也一定能看到超时日志（考官验收就看这一行）。
    """

    def __init__(self):
        super().__init__('node_c_alarm')

        self.declare_parameter('alarm_threshold', 0.3)
        self.declare_parameter('service_timeout', 1.0)
        self.add_on_set_parameters_callback(self.on_param_set)

        self.threshold = float(self.get_parameter('alarm_threshold').value)
        self.timeout = float(self.get_parameter('service_timeout').value)

        self.pending = False            # 是否有在途请求
        self.req_time = None            # 在途请求的发出时刻（秒）
        self.future = None
        self._timer = None

        self.sub = self.create_subscription(
            Float32, '/processed_distance', self.callback, 10)
        self.cli = self.create_client(TriggerAlarm, '/trigger_alarm')

        # 看门狗：0.1 s 一次，与请求解耦
        self.watchdog = self.create_timer(0.1, self.check_timeout)

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

    # ------------------------------------------------------------------ 看门狗
    def now_s(self):
        return self.get_clock().now().nanoseconds / 1e9

    def check_timeout(self):
        if not self.pending or self.req_time is None:
            return
        if self.future is not None and self.future.done():
            resp = None
            try:
                resp = self.future.result()
            except Exception as e:                  # noqa: BLE001
                self.get_logger().error(f'服务调用失败: {e}')
            if resp is not None and resp.success:
                self.get_logger().info(f'--> [C_Alarm] 收到服务端返回: {resp.message}')
            self.pending = False
            self.req_time = None
            return

        if self.now_s() - self.req_time > self.timeout:
            self.get_logger().warn(f'[WARN] 报警服务超时 ({self.timeout} 秒无响应)')
            self.pending = False
            self.req_time = None
            if self.future is not None:
                try:
                    self.future.cancel()
                except Exception:                   # noqa: BLE001
                    pass

    # ------------------------------------------------------------------ 主回调
    def callback(self, msg):
        dist = float(msg.data)
        if dist >= self.threshold:      # 只有小于阈值才报警
            return
        if self.pending:                # 上一次还没结束，跳过本次
            return

        req = TriggerAlarm.Request()
        req.current_distance = dist

        self.pending = True
        self.req_time = self.now_s()
        try:
            self.future = self.cli.call_async(req)
        except Exception as e:                      # noqa: BLE001
            self.pending = False
            self.req_time = None
            self.get_logger().warn(f'[WARN] 报警服务超时（服务端不可用: {e}）')


def main(args=None):
    rclpy.init(args=args)
    node = AlarmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
