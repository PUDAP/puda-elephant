# start publishing to /joint_states
`~/colcon_ws/install/mycobot_630/share/mycobot_630/launch$ python3 robot_state.py`


# listen to /joint_states
`ros2 topic echo /joint_states`

```
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from pymycobot.elephantrobot import ElephantRobot
import math

class JointStatePublisher(Node):
    def __init__(self):
        super().__init__('elephant_joint_state_publisher')
        self.declare_parameter('ip', '192.168.1.159')
        self.declare_parameter('port', 5001)
        ip = self.get_parameter('ip').get_parameter_value().string_value
        port = self.get_parameter('port').get_parameter_value().integer_value

        self.mc = ElephantRobot(ip, port)
        self.mc.start_client()

        self.pub = self.create_publisher(JointState, 'joint_states', 10)
        self.timer = self.create_timer(0.1, self.publish_joint_states)

    def publish_joint_states(self):
        angles = self.mc.get_angles()
        if angles:
            msg = JointState()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.name = [f'joint{i+1}' for i in range(len(angles))]
            msg.position = [math.radians(a) for a in angles]
            self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = JointStatePublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```