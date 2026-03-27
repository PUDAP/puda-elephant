import time
import logging
from elephant_driver import Elephant, ElephantROS


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)
arm = Elephant(ip="192.168.1.159", port=5001)
ros = ElephantROS(arm)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    ros.shutdown()