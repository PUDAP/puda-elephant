import os
import sys
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
# CONNECTION
# =========================

PI_IP = "100.112.113.43"
USERNAME = "pi"
PASSWORD = "elephant"

BRIDGE_PORT = 6000

REMOTE_IMAGE_PATH = "/home/pi/frame.jpg"
LOCAL_IMAGE_PATH = "C:\\Users\\kylek\\vlm_env\\frame.jpg"
DEBUG_IMAGE_PATH = "C:\\Users\\kylek\\vlm_env\\debug_vlm_pick.jpg"
OPTIMIZED_IMAGE_PATH = "C:\\Users\\kylek\\vlm_env\\optimized.jpg"
MODEL = "qwen/qwen-2.5-vl-7b-instruct"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# =========================
# CALIBRATION
# =========================

# Camera Z during calibration
CAL_Z = 200.0

# Surface/table Z where calibration squares were placed
TABLE_Z = 130.0

# Measured mm/pixel when camera was at CAL_Z and looking at the TABLE_Z plane
MM_PER_PIXEL_AT_CAL_Z = 0.266

# Fixed camera center to TCP offset in robot X
CAMERA_TO_TCP_X = -71.0

# =========================
# USER INPUT
# =========================

object_name = input("Enter object to move to: ")
Z_TOUCH = float(input("Enter Z when gripper touches object: "))

# =========================
# CAPTURE IMAGE FROM PI
# =========================

print("Connecting to Pi...")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(PI_IP, username=USERNAME, password=PASSWORD)

print("Capturing image...")

stdin, stdout, stderr = ssh.exec_command("python3 capture_frame.py")
exit_status = stdout.channel.recv_exit_status()

if exit_status != 0:
    print(stderr.read().decode())
    ssh.close()
    sys.exit(1)

if os.path.exists(LOCAL_IMAGE_PATH):
    os.remove(LOCAL_IMAGE_PATH)

ftp = ssh.open_sftp()
ftp.get(REMOTE_IMAGE_PATH, LOCAL_IMAGE_PATH)
ftp.close()
ssh.close()

print("Timestamp:", time.ctime(os.path.getmtime(LOCAL_IMAGE_PATH)))

# =========================
# ROTATE IMAGE
# =========================

image = Image.open(LOCAL_IMAGE_PATH)
image = image.rotate(180, expand=True)
image.save(OPTIMIZED_IMAGE_PATH)

print("Image rotated.")

# =========================
# LOAD IMAGE
# =========================

img = cv2.imread(OPTIMIZED_IMAGE_PATH)

if img is None:
    raise RuntimeError(f"Failed to load image: {OPTIMIZED_IMAGE_PATH}")

h, w = img.shape[:2]

IMAGE_CENTER_X = w // 2
IMAGE_CENTER_Y = h // 2

print("Image size:", w, "x", h)
print("Camera center:", IMAGE_CENTER_X, IMAGE_CENTER_Y)

# =========================
# ENCODE IMAGE
# =========================

with open(OPTIMIZED_IMAGE_PATH, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

# =========================
# MODEL PROMPT
# =========================

prompt = f"""
You are a precision computer vision system for robotic manipulation.

Locate the specified object.

Target object:
{object_name}

Return ONLY JSON in this format:

{{
  "bbox":[x1,y1,x2,y2]
}}

All coordinates must be integers.
"""

payload = {
    "model": MODEL,
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

print("Running Qwen2.5-VL detection...")

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

print("Model Response:", response)

# =========================
# PARSE BBOX
# =========================

json_match = re.search(r"\{.*\}", response, re.DOTALL)

if not json_match:
    raise RuntimeError(f"No JSON detected. Raw output: {response}")

result = json.loads(json_match.group(0))

if "bbox" not in result or len(result["bbox"]) != 4:
    raise RuntimeError(f"Invalid bbox response: {result}")

x1, y1, x2, y2 = result["bbox"]

cx = int((x1 + x2) / 2)
cy = int((y1 + y2) / 2)

print("Bounding box:", x1, y1, x2, y2)
print("BBox center:", cx, cy)

# =========================
# DEBUG IMAGE
# =========================

debug_img = img.copy()

cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
cv2.circle(debug_img, (cx, cy), 6, (0, 0, 255), -1)

cv2.drawMarker(
    debug_img,
    (IMAGE_CENTER_X, IMAGE_CENTER_Y),
    (255, 0, 0),
    markerType=cv2.MARKER_CROSS,
    markerSize=20,
    thickness=2
)

cv2.imwrite(DEBUG_IMAGE_PATH, debug_img)

print("Debug image saved:", DEBUG_IMAGE_PATH)

# =========================
# GET CURRENT CAMERA Z
# =========================

sock = socket.socket()
sock.connect((PI_IP, BRIDGE_PORT))
sock.send(b"GET_Z\n")

Z_CAM = float(sock.recv(1024).decode().strip())

sock.close()

print("Current Z:", Z_CAM)

# =========================
# PIXEL → ROBOT WITH HEIGHT CORRECTION
# =========================

dx_px = cx - IMAGE_CENTER_X
dy_px = cy - IMAGE_CENTER_Y

print("Pixel offset:", dx_px, dy_px)

# Calibration geometry:
# - MM_PER_PIXEL_AT_CAL_Z was measured with camera at CAL_Z
# - calibration target was on TABLE_Z plane
# - object top is at Z_TOUCH
#
# So:
# camera-to-plane distance during calibration = CAL_Z - TABLE_Z
# camera-to-object distance now              = Z_CAM - Z_TOUCH
#
# Scale mm/pixel by the ratio of those distances.

camera_to_plane_cal = CAL_Z - TABLE_Z
camera_to_object_now = Z_CAM - Z_TOUCH

if camera_to_plane_cal <= 0:
    raise RuntimeError(
        f"Invalid calibration: CAL_Z ({CAL_Z}) must be greater than TABLE_Z ({TABLE_Z})"
    )

if camera_to_object_now <= 0:
    raise RuntimeError(
        f"Invalid geometry: Z_CAM ({Z_CAM}) must be greater than Z_TOUCH ({Z_TOUCH})"
    )

scale_ratio = camera_to_object_now / camera_to_plane_cal
mm_per_pixel = MM_PER_PIXEL_AT_CAL_Z * scale_ratio

print("Camera-to-plane distance at calibration:", camera_to_plane_cal)
print("Camera-to-object distance now:", camera_to_object_now)
print("Scale ratio:", scale_ratio)
print("Adjusted mm_per_pixel:", mm_per_pixel)

# Map camera image axes to robot XY
delta_x_mm = -(dy_px) * mm_per_pixel
delta_y_mm = (dx_px) * mm_per_pixel

# Apply fixed camera-to-TCP offset
delta_x_mm += CAMERA_TO_TCP_X

print("Move X:", delta_x_mm)
print("Move Y:", delta_y_mm)

# =========================
# SEND MOVE COMMAND
# =========================

move_cmd = f"MOVE {delta_x_mm:.3f} {delta_y_mm:.3f} 0 0 0 0 800"

print("Sending:", move_cmd)

sock = socket.socket()
sock.connect((PI_IP, BRIDGE_PORT))
sock.send((move_cmd + "\n").encode())

resp = sock.recv(1024).decode().strip()

print("Bridge reply:", resp)

sock.close()

print("Move command sent.")