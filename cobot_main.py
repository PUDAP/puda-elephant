import os
import time
import socket
import paramiko
import cv2
import requests
import base64
import json
import re

from PIL import Image


# =========================
# CONFIG
# =========================

PI_IP = "100.112.113.43"
USERNAME = "pi"
PASSWORD = "elephant"
BRIDGE_PORT = 6000

REMOTE_IMAGE_PATH = "/home/pi/frame.jpg"
LOCAL_IMAGE_PATH = "frame.jpg"
OPTIMIZED_IMAGE_PATH = "optimized.jpg"
DEBUG_IMAGE_PATH = "debug_vlm_pick.jpg"

MODEL = "qwen/qwen-2.5-vl-7b-instruct"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

MOVE_SPEED = 800
WAIT_DONE_TIMEOUT = 120.0
DEFAULT_BRIDGE_TIMEOUT = 15.0

# =========================
# CALIBRATION
# =========================

CAL_Z = 200.0
TABLE_Z = 130.0
MM_PER_PIXEL_AT_CAL_Z = 0.266
CAMERA_TO_TCP_X = -71.0


# =========================
# LOW-LEVEL BRIDGE
# =========================

def bridge_send(cmd, timeout=DEFAULT_BRIDGE_TIMEOUT):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((PI_IP, BRIDGE_PORT))
        s.sendall((cmd.strip() + "\n").encode())

        data = b""
        start = time.time()

        while True:
            if time.time() - start > timeout:
                raise TimeoutError(f"Bridge response timeout for command: {cmd}")

            try:
                chunk = s.recv(4096)
                if not chunk:
                    break

                data += chunk
                text = data.decode(errors="ignore").strip()

                if cmd.strip() == "GET_Z":
                    try:
                        float(text)
                        break
                    except ValueError:
                        pass

                if "get_coords" in cmd and "]" in text:
                    break

                if "[ok]" in text.lower():
                    break

                if ":0" in text:
                    break

                if ":error" in text.lower():
                    break

                if "error" in text.lower():
                    break

            except socket.timeout:
                continue

        return data.decode(errors="ignore").strip()

    finally:
        s.close()


# =========================
# BASIC ROBOT HELPERS
# =========================

def parse_coords(resp):
    if ":" in resp:
        resp = resp.split(":", 1)[1]
    resp = resp.strip().replace("[", "").replace("]", "")
    parts = [x.strip() for x in resp.split(",") if x.strip()]
    return [float(x) for x in parts]


def get_coords():
    resp = bridge_send("get_coords()", timeout=10.0)
    return parse_coords(resp)


def get_current_z():
    resp = bridge_send("GET_Z", timeout=10.0)
    try:
        return float(resp)
    except ValueError:
        raise RuntimeError(f"Invalid GET_Z response: {resp}")


def wait_command_done(timeout=WAIT_DONE_TIMEOUT):
    resp = bridge_send("wait_command_done()", timeout=timeout)
    print("Wait done response:", resp)
    return resp


def move_relative(dx=0.0, dy=0.0, dz=0.0, drx=0.0, dry=0.0, drz=0.0, speed=MOVE_SPEED, wait=True):
    cmd = f"MOVE {dx:.3f} {dy:.3f} {dz:.3f} {drx:.3f} {dry:.3f} {drz:.3f} {int(speed)}"
    resp = bridge_send(cmd, timeout=20.0)
    print("Move response:", resp)
    if wait:
        wait_command_done()
    return resp


def move_relative_z(dz, speed=MOVE_SPEED, wait=True):
    return move_relative(0.0, 0.0, dz, 0.0, 0.0, 0.0, speed=speed, wait=wait)


def move_relative_xy(dx, dy, speed=MOVE_SPEED, wait=True):
    return move_relative(dx, dy, 0.0, 0.0, 0.0, 0.0, speed=speed, wait=wait)


def gripper_init():
    resp = bridge_send("init_ele_gripper()", timeout=10.0)
    print("Gripper init response:", resp)
    return resp


def gripper_open():
    resp = bridge_send("set_ele_gripper_open()", timeout=10.0)
    print("Open response:", resp)
    return resp


def gripper_close():
    resp = bridge_send("set_ele_gripper_close()", timeout=10.0)
    print("Close response:", resp)
    return resp


def power_on():
    resp = bridge_send("power_on()", timeout=10.0)
    print("Power on response:", resp)
    return resp


def power_off():
    resp = bridge_send("power_off()", timeout=10.0)
    print("Power off response:", resp)
    return resp


def state_on():
    resp = bridge_send("state_on()", timeout=10.0)
    print("State on response:", resp)
    return resp


def state_off():
    resp = bridge_send("state_off()", timeout=10.0)
    print("State off response:", resp)
    return resp


def state_check():
    resp = bridge_send("state_check()", timeout=10.0)
    print("State check response:", resp)
    return resp


def initialize(init_gripper=True):
    results = {
        "power_on": power_on(),
        "state_check": state_check(),
    }

    if init_gripper:
        results["init_ele_gripper"] = gripper_init()

    return results


# =========================
# IMAGE CAPTURE
# =========================

def capture_image_from_pi(
    remote_image_path=REMOTE_IMAGE_PATH,
    local_image_path=LOCAL_IMAGE_PATH,
    optimized_image_path=OPTIMIZED_IMAGE_PATH,
    rotate_180=True,
):
    print("Connecting to Pi...")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PI_IP, username=USERNAME, password=PASSWORD)

    try:
        print("Capturing image...")
        stdin, stdout, stderr = ssh.exec_command("python3 capture_frame.py")
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            err = stderr.read().decode()
            raise RuntimeError(f"capture_frame.py failed: {err}")

        if os.path.exists(local_image_path):
            os.remove(local_image_path)

        ftp = ssh.open_sftp()
        try:
            ftp.get(remote_image_path, local_image_path)
        finally:
            ftp.close()

    finally:
        ssh.close()

    print("Timestamp:", time.ctime(os.path.getmtime(local_image_path)))

    image = Image.open(local_image_path)
    if rotate_180:
        image = image.rotate(180, expand=True)
    image.save(optimized_image_path)

    print("Saved optimized image:", optimized_image_path)
    return optimized_image_path


# =========================
# IMAGE / VLM HELPERS
# =========================

def encode_image_b64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def select_bbox(candidates, selector="center"):
    """
    candidates: list of dicts like:
        [{"bbox":[x1,y1,x2,y2]}, ...]

    selector options:
        - "top_right"
        - "top_left"
        - "bottom_right"
        - "bottom_left"
        - "leftmost"
        - "rightmost"
        - "topmost"
        - "bottommost"
        - "center"

    Returns chosen candidate with cx, cy added.
    """
    if not candidates:
        raise RuntimeError("No candidate objects found")

    enriched = []
    for obj in candidates:
        if "bbox" not in obj or len(obj["bbox"]) != 4:
            continue
        x1, y1, x2, y2 = obj["bbox"]
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        enriched.append({
            "bbox": [x1, y1, x2, y2],
            "cx": cx,
            "cy": cy,
            "area": max(0, x2 - x1) * max(0, y2 - y1),
        })

    if not enriched:
        raise RuntimeError("No valid candidate bounding boxes found")

    if selector == "top_right":
        enriched.sort(key=lambda o: (o["cy"], -o["cx"]))
    elif selector == "top_left":
        enriched.sort(key=lambda o: (o["cy"], o["cx"]))
    elif selector == "bottom_right":
        enriched.sort(key=lambda o: (-o["cy"], -o["cx"]))
    elif selector == "bottom_left":
        enriched.sort(key=lambda o: (-o["cy"], o["cx"]))
    elif selector == "leftmost":
        enriched.sort(key=lambda o: (o["cx"], o["cy"]))
    elif selector == "rightmost":
        enriched.sort(key=lambda o: (-o["cx"], o["cy"]))
    elif selector == "topmost":
        enriched.sort(key=lambda o: (o["cy"], o["cx"]))
    elif selector == "bottommost":
        enriched.sort(key=lambda o: (-o["cy"], o["cx"]))
    elif selector == "center":
        return enriched[0]
    else:
        raise RuntimeError(f"Unknown selector: {selector}")

    return enriched[0]


def select_bbox_with_image_center(candidates, image_center_x, image_center_y, selector="center"):
    if selector != "center":
        return select_bbox(candidates, selector=selector)

    enriched = []
    for obj in candidates:
        if "bbox" not in obj or len(obj["bbox"]) != 4:
            continue
        x1, y1, x2, y2 = obj["bbox"]
        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        dist2 = (cx - image_center_x) ** 2 + (cy - image_center_y) ** 2
        enriched.append({
            "bbox": [x1, y1, x2, y2],
            "cx": cx,
            "cy": cy,
            "dist2": dist2,
        })

    if not enriched:
        raise RuntimeError("No valid candidate bounding boxes found")

    enriched.sort(key=lambda o: o["dist2"])
    return enriched[0]


def detect_objects_bbox(
    object_name,
    image_path=OPTIMIZED_IMAGE_PATH,
    model=MODEL,
    save_debug=True,
    debug_image_path=DEBUG_IMAGE_PATH,
    selector="center",
):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"Failed to load image: {image_path}")

    h, w = img.shape[:2]
    image_center_x = w // 2
    image_center_y = h // 2

    print("Image size:", w, "x", h)
    print("Camera center:", image_center_x, image_center_y)

    img_b64 = encode_image_b64(image_path)

    prompt = f"""
You are a precision computer vision system for robotic manipulation.

Find ALL visible instances of this target object:
{object_name}

Return ONLY valid JSON in this exact format:

{{
  "objects": [
    {{"bbox":[x1,y1,x2,y2]}},
    {{"bbox":[x1,y1,x2,y2]}}
  ]
}}

Rules:
- Include every plausible visible instance of the target object.
- Coordinates must be integers.
- Do not include text outside JSON.
- If only one object is found, still return it inside the objects list.
- If none are found, return:
  {{"objects":[]}}
""".strip()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}"
                        }
                    }
                ]
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    print("Running VLM multi-object detection...")

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )

    data = r.json()

    if "choices" not in data:
        print(json.dumps(data, indent=2))
        raise RuntimeError("OpenRouter request failed")

    response = data["choices"][0]["message"]["content"]
    print("Model response:", response)

    json_match = re.search(r"\{.*\}", response, re.DOTALL)
    if not json_match:
        raise RuntimeError(f"No JSON detected. Raw output: {response}")

    result = json.loads(json_match.group(0))

    if "objects" not in result or not isinstance(result["objects"], list):
        raise RuntimeError(f"Invalid response format: {result}")

    candidates = result["objects"]
    if len(candidates) == 0:
        raise RuntimeError(f"No objects found for target: {object_name}")

    chosen = select_bbox_with_image_center(
        candidates,
        image_center_x=image_center_x,
        image_center_y=image_center_y,
        selector=selector,
    )

    x1, y1, x2, y2 = chosen["bbox"]
    cx = chosen["cx"]
    cy = chosen["cy"]

    print(f"Found {len(candidates)} candidate(s)")
    print("Chosen selector:", selector)
    print("Chosen bbox:", x1, y1, x2, y2)
    print("Chosen center:", cx, cy)

    if save_debug:
        debug_img = img.copy()

        for obj in candidates:
            if "bbox" not in obj or len(obj["bbox"]) != 4:
                continue
            ax1, ay1, ax2, ay2 = obj["bbox"]
            acx = int((ax1 + ax2) / 2)
            acy = int((ay1 + ay2) / 2)
            cv2.rectangle(debug_img, (ax1, ay1), (ax2, ay2), (0, 255, 255), 2)
            cv2.circle(debug_img, (acx, acy), 4, (0, 255, 255), -1)

        cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 3)
        cv2.circle(debug_img, (cx, cy), 6, (0, 0, 255), -1)

        cv2.drawMarker(
            debug_img,
            (image_center_x, image_center_y),
            (255, 0, 0),
            markerType=cv2.MARKER_CROSS,
            markerSize=20,
            thickness=2
        )

        cv2.imwrite(debug_image_path, debug_img)
        print("Debug image saved:", debug_image_path)

    return {
        "objects": candidates,
        "selected": {
            "bbox": [x1, y1, x2, y2],
            "center_px": [cx, cy],
        },
        "image_size": [w, h],
        "image_center_px": [image_center_x, image_center_y],
        "debug_image_path": debug_image_path if save_debug else None,
    }


# =========================
# PIXEL TO ROBOT OFFSET
# =========================

def pixel_to_robot_offset(cx, cy, image_center_x, image_center_y, z_cam, z_touch):
    dx_px = cx - image_center_x
    dy_px = cy - image_center_y

    print("Pixel offset:", dx_px, dy_px)

    camera_to_plane_cal = CAL_Z - TABLE_Z
    camera_to_object_now = z_cam - z_touch

    if camera_to_plane_cal <= 0:
        raise RuntimeError(
            f"Invalid calibration: CAL_Z ({CAL_Z}) must be greater than TABLE_Z ({TABLE_Z})"
        )

    if camera_to_object_now <= 0:
        raise RuntimeError(
            f"Invalid geometry: Z_CAM ({z_cam}) must be greater than Z_TOUCH ({z_touch})"
        )

    scale_ratio = camera_to_object_now / camera_to_plane_cal
    mm_per_pixel = MM_PER_PIXEL_AT_CAL_Z * scale_ratio

    print("Camera-to-plane distance at calibration:", camera_to_plane_cal)
    print("Camera-to-object distance now:", camera_to_object_now)
    print("Scale ratio:", scale_ratio)
    print("Adjusted mm_per_pixel:", mm_per_pixel)

    delta_x_mm = -(dy_px) * mm_per_pixel
    delta_y_mm = (dx_px) * mm_per_pixel

    delta_x_mm += CAMERA_TO_TCP_X

    print("Move X:", delta_x_mm)
    print("Move Y:", delta_y_mm)

    return delta_x_mm, delta_y_mm, mm_per_pixel


# =========================
# HIGH-LEVEL ACTIONS
# =========================

def vlm_move(
    object_name,
    z_touch,
    selector="center",
    speed=MOVE_SPEED,
    capture=True,
    wait=True,
    image_path=None,
):
    if image_path is None:
        if not capture:
            raise RuntimeError("image_path must be provided if capture=False")
        image_path = capture_image_from_pi()
    elif capture:
        image_path = capture_image_from_pi()

    detection = detect_objects_bbox(
        object_name=object_name,
        image_path=image_path,
        selector=selector,
    )

    cx, cy = detection["selected"]["center_px"]
    image_center_x, image_center_y = detection["image_center_px"]

    z_cam = get_current_z()
    print("Current Z:", z_cam)

    delta_x_mm, delta_y_mm, mm_per_pixel = pixel_to_robot_offset(
        cx=cx,
        cy=cy,
        image_center_x=image_center_x,
        image_center_y=image_center_y,
        z_cam=z_cam,
        z_touch=z_touch,
    )

    move_relative_xy(delta_x_mm, delta_y_mm, speed=speed, wait=wait)

    return {
        "object_name": object_name,
        "selector": selector,
        "z_touch": z_touch,
        "z_cam": z_cam,
        "delta_x_mm": delta_x_mm,
        "delta_y_mm": delta_y_mm,
        "mm_per_pixel": mm_per_pixel,
        "detection": detection,
    }


def grab(action, z_target, speed=MOVE_SPEED, settle_time=0.5):
    action = action.strip().lower()
    if action not in ("pick", "drop"):
        raise RuntimeError("action must be 'pick' or 'drop'")

    z_start = get_current_z()
    print("Current Z:", z_start)

    dz_down = z_target - z_start
    print("Moving by dZ:", dz_down)

    if action == "pick":
        gripper_open()
        time.sleep(settle_time)

        move_relative_z(dz_down, speed=speed, wait=True)
        time.sleep(settle_time)

        gripper_close()
        time.sleep(settle_time)

        move_relative_z(-dz_down, speed=speed, wait=True)
        time.sleep(settle_time)

    elif action == "drop":
        move_relative_z(dz_down, speed=speed, wait=True)
        time.sleep(settle_time)

        gripper_open()
        time.sleep(settle_time)

        move_relative_z(-dz_down, speed=speed, wait=True)
        time.sleep(settle_time)

    print(f"{action.capitalize()} sequence complete.")

    return {
        "action": action,
        "z_start": z_start,
        "z_target": z_target,
        "dz_down": dz_down,
    }


def pick_object(object_name, z_touch, selector="center", speed=MOVE_SPEED, settle_time=0.5):
    move_info = vlm_move(
        object_name=object_name,
        z_touch=z_touch,
        selector=selector,
        speed=speed,
        wait=True,
    )
    grab_info = grab(action="pick", z_target=z_touch, speed=speed, settle_time=settle_time)
    return {
        "move": move_info,
        "grab": grab_info,
    }


def drop_object(z_target, speed=MOVE_SPEED, settle_time=0.5):
    return grab(action="drop", z_target=z_target, speed=speed, settle_time=settle_time)


# =========================
# EXAMPLE USAGE
# =========================

if __name__ == "__main__":
    initialize(init_gripper=True)

    # Examples:
    # vlm_move(object_name="blue vial", z_touch=160, selector="top_right")
    # pick_object(object_name="blue vial", z_touch=160, selector="top_right")
    # grab(action="pick", z_target=160)
    # drop_object(z_target=160)

    print("Module loaded. Call functions directly.")