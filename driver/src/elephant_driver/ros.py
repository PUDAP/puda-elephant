import math
import threading
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from elephant_driver import Elephant


class ElephantROS:
    """Publishes joint states from an Elephant arm over ROS 2.

    Spinning starts automatically on construction; call :meth:`shutdown`
    when done.  The node runs in a daemon thread so it won't block exit.
    """

    def __init__(self, arm: Elephant, *, publish_rate: float = 0.1):
        self.arm = arm

        if not rclpy.ok():
            rclpy.init()

        self._node = Node("elephant_joint_state_publisher")
        self._pub = self._node.create_publisher(JointState, "joint_states", 10)
        self._timer = self._node.create_timer(publish_rate, self._publish)

        self._spin_thread = threading.Thread(target=self._spin, daemon=True)
        self._spin_thread.start()

    def _publish(self):
        angles = self.arm.get_angles()
        if not angles:
            return
        msg = JointState()
        msg.header.stamp = self._node.get_clock().now().to_msg()
        msg.name = [f"joint{i + 1}" for i in range(len(angles))]
        msg.position = [math.radians(a) for a in angles]
        self._pub.publish(msg)

    def _spin(self):
        rclpy.spin(self._node)

    def shutdown(self):
        self._node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        self._spin_thread.join(timeout=2.0)
