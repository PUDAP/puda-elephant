# cobot_main.py

`cobot_main.py` is a Python control script for a MyCobot Pro 630 / Elephant Robotics setup that combines robot bridge communication, gripper control, image capture from a Raspberry Pi, VLM-based object detection using OpenRouter, pixel-to-robot motion conversion, and high-level pick/drop workflows. It is designed so all actions are called through Python functions with parameters rather than terminal prompts.

## Important architecture note

This system depends on a separate bridge process running on the Raspberry Pi. `pro630_bridge.py` **must be running on the Pi**. `cobot_main.py` runs on the PC. `cobot_main.py` sends motion and gripper commands to the Pi bridge over TCP, and the Pi bridge forwards commands to the Pro 630 robot socket API. Without `pro630_bridge.py` running on the Pi, `cobot_main.py` will not be able to get the robot Z position, send move commands, wait for command completion, or control the gripper.

## System overview

On the PC side, `cobot_main.py` handles capturing an image from the Pi, sending the image to a vision-language model, selecting a target object, converting image offsets into robot XY motion, and issuing movement and gripper commands through the bridge.

On the Raspberry Pi side, the Pi must run both the camera capture script (`capture_frame.py`) and `pro630_bridge.py`. The Pi bridge listens for TCP commands on port `6000`, translates `MOVE ...` and other commands into robot socket API commands, and maintains persistent communication with the robot.

On the robot side, the Pro 630 receives commands through the bridge using the Elephant Robotics socket API.

## Required files

Typical setup:

### On the PC
- `cobot_main.py`

### On the Raspberry Pi
- `pro630_bridge.py`
- `capture_frame.py`

## Dependencies

Install the required Python packages on the PC:

```bash
pip install paramiko opencv-python requests pillow


If using a virtual environment, activate it first.

Configuration

At the top of cobot_main.py, update these values as needed:

PI_IP = "100.112.113.43"
USERNAME = "pi"
PASSWORD = "elephant"
BRIDGE_PORT = 6000

These must match your Raspberry Pi connection and bridge server settings.

Also configure your OpenRouter API key in your environment.

Windows CMD
set OPENROUTER_API_KEY=your_key_here
PowerShell
$env:OPENROUTER_API_KEY="your_key_here"

cobot_main.py reads it with:

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
Calibration parameters

The script uses these calibration constants:

CAL_Z = 200.0
TABLE_Z = 130.0
MM_PER_PIXEL_AT_CAL_Z = 0.266
CAMERA_TO_TCP_X = -71.0

Meaning:

CAL_Z: camera Z during calibration

TABLE_Z: Z height of the calibration plane

MM_PER_PIXEL_AT_CAL_Z: measured image scale at calibration height

CAMERA_TO_TCP_X: fixed camera-to-tool-center-point X offset

These values are critical for converting pixel offsets into robot movement. If the camera mount, tool, or workspace changes, recalibrate these values.

Required Pi bridge
pro630_bridge.py must be running on the Raspberry Pi

Start it on the Pi before running cobot_main.py on the PC:

python3 pro630_bridge.py

The bridge should print something like:

Bridge running on port 6000
Connected to robot at 127.0.0.1:5001

If this process is not running, cobot_main.py will fail when trying to send robot commands.

Required camera script on Pi

cobot_main.py expects this command to work over SSH:

python3 capture_frame.py

This script must capture a camera image on the Pi and save it to:

/home/pi/frame.jpg

cobot_main.py then downloads that file to the PC.

How it works

cobot_main.py SSHes into the Pi and runs python3 capture_frame.py.

It downloads /home/pi/frame.jpg to the PC.

The image is rotated 180 degrees and saved locally.

The script sends the image to OpenRouter using a VLM model such as qwen/qwen-2.5-vl-7b-instruct.

The model returns bounding boxes for target objects.

If multiple objects are found, the script can select one based on a selector such as center, top_right, top_left, bottom_right, bottom_left, leftmost, rightmost, topmost, or bottommost.

The script converts the selected object center from image coordinates into robot XY movement using current Z and calibration parameters.

The PC sends commands to pro630_bridge.py, which sends them to the robot.

High-level functions handle opening the gripper, descending to target Z, closing or opening the gripper, and returning upward.

Main functions
initialize(init_gripper=True)

Basic setup helper.

What it does:

sends power_on()

checks robot state

optionally initializes the gripper

Example:

initialize()
capture_image_from_pi(...)

Captures and downloads a fresh image from the Pi.

Returns the path to the local optimized image.

Example:

image_path = capture_image_from_pi()
detect_objects_bbox(object_name, selector="center", ...)

Uses the VLM to detect all visible instances of a target object and choose one.

Parameters:

object_name: description of the object category to find

selector: how to choose among multiple objects

Example:

result = detect_objects_bbox("blue vial", selector="top_right")
vlm_move(object_name, z_touch, selector="center", speed=800, ...)

Detects an object and moves robot XY so the tool aligns with it.

Parameters:

object_name: target class, such as "blue vial"

z_touch: Z height where the gripper touches the object

selector: object selection mode

speed: move speed

Example:

vlm_move(object_name="blue vial", z_touch=160, selector="top_right")
grab(action, z_target, speed=800, settle_time=0.5)

Performs a vertical pick or drop motion.

Parameters:

action: "pick" or "drop"

z_target: Z height to descend to

speed: move speed

settle_time: pause between steps

Examples:

grab(action="pick", z_target=160)
grab(action="drop", z_target=160)
pick_object(object_name, z_touch, selector="center", ...)

Combined workflow:

detect object

move above it

open gripper

descend

close gripper

rise back up

Example:

pick_object(object_name="blue vial", z_touch=160, selector="top_right")
drop_object(z_target, ...)

Combined drop workflow:

descend

open gripper

rise

Example:

drop_object(z_target=160)
Lower-level motion helpers
move_relative(...)

Send a relative move in XYZ + rotation.

Example:

move_relative(dx=10, dy=0, dz=0, speed=800)
move_relative_xy(dx, dy, ...)

Relative XY move only.

move_relative_xy(-20, 15, speed=800)
move_relative_z(dz, ...)

Relative Z move only.

move_relative_z(-30, speed=800)
wait_command_done()

Waits until the previous motion command completes.

gripper_open()

Open the electric gripper.

gripper_close()

Close the electric gripper.

gripper_init()

Initialize the electric gripper.

Example usage
Initialize the system
from cobot_main import initialize

initialize()
Move to the top-right blue vial
from cobot_main import vlm_move

vlm_move(object_name="blue vial", z_touch=160, selector="top_right")
Pick the top-right blue vial
from cobot_main import pick_object

pick_object(object_name="blue vial", z_touch=160, selector="top_right")
Drop an object
from cobot_main import drop_object

drop_object(z_target=160)
Manual relative move
from cobot_main import move_relative_xy

move_relative_xy(-30, 10, speed=800)
Debug images

The script saves a rotated image and a debug image with detected boxes and the selected target. These are useful for checking what the model detected, which object was selected, and whether calibration and target choice make sense.

If paths are relative, files may save to the current working directory. Absolute paths are recommended if you want them saved beside the script.

Common failure modes
1. Bridge not running

If pro630_bridge.py is not running on the Pi:

GET_Z fails

move commands fail

gripper commands fail

Fix: start pro630_bridge.py on the Pi first.

2. capture_frame.py missing or failing

If the Pi cannot create /home/pi/frame.jpg, image download will fail.

Fix: verify on the Pi:

python3 capture_frame.py
ls /home/pi/frame.jpg
3. OpenRouter key missing

If OPENROUTER_API_KEY is not set, detection fails.

Fix: set the environment variable before running.

4. Robot accepts commands but does not move

This is usually a robot state, servo, or E-stop issue, not a problem in cobot_main.py. The bridge and script may be functioning correctly while the robot itself is not enabled.

5. Wrong calibration

If the robot moves to the wrong place, MM_PER_PIXEL_AT_CAL_Z, CAL_Z, TABLE_Z, or CAMERA_TO_TCP_X may need recalibration.

Recommended startup order

Power the robot and ensure it is in a valid operational state.

On the Pi, start pro630_bridge.py.

Verify capture_frame.py works on the Pi.

On the PC, set OPENROUTER_API_KEY.

Run your Python code using cobot_main.py.

Example full workflow
On Pi
python3 pro630_bridge.py
On PC
from cobot_main import initialize, pick_object

initialize()
pick_object(object_name="blue vial", z_touch=160, selector="top_right")
Summary

cobot_main.py provides a function-based interface for vision-guided movement, object selection among multiple candidates, gripper control, and pick/drop workflows.

Critical requirement

pro630_bridge.py must be running on the Raspberry Pi before using cobot_main.py.
