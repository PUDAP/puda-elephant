from elephant_driver import Elephant

arm = Elephant(ip="192.168.1.159", port=5001)
try:
    print(arm.get_coords())
except Exception as e:
    raise e