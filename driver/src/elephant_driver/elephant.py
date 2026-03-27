""" 
PUDA Driver for the Elephant robot.
"""
import logging
from pymycobot import ElephantRobot
        
        
logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
  force=True,
)
class Elephant:
    """Wrapper around `pymycobot`'s Elephant robot client."""

    def __init__(self, *, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.arm = ElephantRobot(ip, port)
        self._startup()
        
    def _startup(self):
        """Start the robot and gripper."""
        try:
            logging.info("Starting the robot and gripper")
            self.arm.start_client()
            self.arm.init_ele_gripper()
        except Exception as e:
            logging.error("Failed to start the robot and gripper: %s", e)
            raise e
        
    # arm methods
    def get_angles(self):
        """Get the current joint angles of the robot in degrees."""
        angles = self.arm.get_angles()
        logging.log(logging.INFO, "Current joint angles: %s", angles)
        return angles

    def get_coords(self):
        """Get the current coordinates of the robot."""
        coords = self.arm.get_coords()
        logging.log(logging.INFO, "Current coordinates: %s", coords)
        return coords

    def move_relative(self, x: float, y: float, z: float, rx: float, ry: float, rz: float, speed: int):
        """Move the robot relative to the current position."""
        coords = (x, y, z, rx, ry, rz)
        self.arm.write_coords(coords, speed)
    
    # gripper methods
    def gripper_open(self):
        """Open the gripper."""
        self.arm.set_ele_gripper_open()
    
    def gripper_close(self):
        """Close the gripper."""
        self.arm.set_ele_gripper_close()