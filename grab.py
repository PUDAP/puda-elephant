import socket
import time

PI_IP = "100.112.113.43"
BRIDGE_PORT = 6000

MOVE_SPEED = 800
STEP_WAIT = 2
WAIT_DONE_TIMEOUT = 120


def bridge_send(cmd, timeout=8.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((PI_IP, BRIDGE_PORT))
        s.sendall((cmd.strip() + "\n").encode())
        resp = s.recv(4096).decode(errors="ignore").strip()
        return resp
    finally:
        s.close()


def get_current_z():
    resp = bridge_send("GET_Z")
    try:
        return float(resp)
    except ValueError:
        raise RuntimeError(f"Invalid GET_Z response: {resp}")


def move_relative_z(dz, speed=MOVE_SPEED):
    cmd = f"MOVE 0 0 {dz:.3f} 0 0 0 {int(speed)}"
    resp = bridge_send(cmd, timeout=15.0)
    print("Move response:", resp)
    return resp


def wait_command_done():
    resp = bridge_send("wait_command_done()", timeout=WAIT_DONE_TIMEOUT)
    print("Wait done response:", resp)
    return resp


def move_relative_z_and_wait(dz, speed=MOVE_SPEED):
    move_relative_z(dz, speed)
    wait_command_done()


def gripper_open():
    resp = bridge_send("set_ele_gripper_open()")
    print("Open response:", resp)
    return resp


def gripper_close():
    resp = bridge_send("set_ele_gripper_close()")
    print("Close response:", resp)
    return resp


if __name__ == "__main__":
    action = input("Enter action (pick/drop): ").strip().lower()
    z_target = float(input("Enter target Z: "))

    if action not in ("pick", "drop"):
        raise RuntimeError("Action must be 'pick' or 'drop'")

    z_start = get_current_z()
    print("Current Z:", z_start)

    dz_down = z_target - z_start
    print("Moving by dZ:", dz_down)

    if action == "pick":
        # open, move down, grab, move up
        gripper_open()
        time.sleep(STEP_WAIT)

        move_relative_z_and_wait(dz_down, MOVE_SPEED)
        time.sleep(STEP_WAIT)

        gripper_close()
        time.sleep(STEP_WAIT)

        move_relative_z_and_wait(-dz_down, MOVE_SPEED)
        time.sleep(STEP_WAIT)

    elif action == "drop":
        # move down, open, move up
        move_relative_z_and_wait(dz_down, MOVE_SPEED)
        time.sleep(STEP_WAIT)

        gripper_open()
        time.sleep(STEP_WAIT)

        move_relative_z_and_wait(-dz_down, MOVE_SPEED)
        time.sleep(STEP_WAIT)

    print(f"{action.capitalize()} sequence complete.")