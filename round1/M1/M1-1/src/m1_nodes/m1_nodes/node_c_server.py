import rclpy
from rclpy.node import Node
from sensor_interfaces.srv import TriggerAlarm

class AlarmServer(Node):
    def __init__(self):
        super().__init__('alarm_server')
        self.srv = self.create_service(TriggerAlarm, '/trigger_alarm', self.handle_service)
        self.get_logger().info('Alarm_Server 已启动，等待报警请求...')
        
    def handle_service(self, request, response):
        self.get_logger().error(f'[ALARM] 距离过近！当前距离: {request.current_distance:.2f}m')
        response.success = True
        response.message = "Alarm triggered successfully"
        return response

def main(args=None):
    rclpy.init(args=args)
    node = AlarmServer()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()