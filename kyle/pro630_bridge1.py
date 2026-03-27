import socket
import threading
import time

ROBOT_IP = "127.0.0.1"
ROBOT_PORT = 5001
BRIDGE_PORT = 6000


class RobotClient:
    def __init__(self, ip, port, timeout=10.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.lock = threading.Lock()
        self.connect()

    def connect(self):
        self.close()

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect((self.ip, self.port))
        self.sock = s
        print(f"Connected to robot at {self.ip}:{self.port}")

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def reconnect(self):
        print("Reconnecting to robot socket...")
        self.connect()

    def send(self, cmd, timeout=None):
        if timeout is None:
            timeout = self.timeout

        with self.lock:

            if self.sock is None:
                self.connect()

            if not cmd.endswith("\n"):
                cmd += "\n"

            try:
                self.sock.settimeout(timeout)
                self.sock.sendall(cmd.encode())
                return self._recv_response(cmd, timeout)

            except Exception:
                # reconnect and retry once
                self.reconnect()
                self.sock.settimeout(timeout)
                self.sock.sendall(cmd.encode())
                return self._recv_response(cmd, timeout)

    def _recv_response(self, cmd, timeout):
        data = b""
        start = time.time()

        while True:

            if time.time() - start > timeout:
                print("Robot response timeout")
                break

            try:
                chunk = self.sock.recv(4096)

                if not chunk:
                    break

                data += chunk
                text = data.decode(errors="ignore").strip()

                # get_coords returns bracketed list
                if "get_coords" in cmd and "]" in text:
                    break

                # success responses
                if ":0" in text or "[ok]" in text.lower():
                    break

                # error responses
                if ":error" in text.lower():
                    break

            except socket.timeout:
                continue

        return data.decode(errors="ignore").strip()


robot = RobotClient(ROBOT_IP, ROBOT_PORT, timeout=15.0)


def parse_coords(resp):
    if ":" in resp:
        resp = resp.split(":", 1)[1]

    resp = resp.replace("[", "").replace("]", "")
    return [float(x) for x in resp.split(",")]


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", BRIDGE_PORT))
server.listen(5)

print(f"Bridge running on port {BRIDGE_PORT}")


while True:

    conn, addr = server.accept()
    conn.settimeout(20.0)

    try:

        data = conn.recv(4096).decode().strip()

        print("Received:", data)

        # ------------------------
        # GET CURRENT Z
        # ------------------------
        if data == "GET_Z":

            resp = robot.send("get_coords()", timeout=10.0)
            coords = parse_coords(resp)

            conn.sendall(str(coords[2]).encode())
            continue

        # ------------------------
        # RELATIVE MOVE
        # ------------------------
        if data.startswith("MOVE"):

            parts = data.split()

            if len(parts) != 8:
                conn.sendall(b"BAD_FORMAT")
                continue

            dx, dy, dz, drx, dry, drz, speed = map(float, parts[1:])

            coords_resp = robot.send("get_coords()", timeout=10.0)
            coords = parse_coords(coords_resp)

            target = [
                coords[0] + dx,
                coords[1] + dy,
                coords[2] + dz,
                coords[3] + drx,
                coords[4] + dry,
                coords[5] + drz,
            ]

            cmd = (
                f"set_coords({target[0]:.3f},{target[1]:.3f},{target[2]:.3f},"
                f"{target[3]:.3f},{target[4]:.3f},{target[5]:.3f},{int(speed)})"
            )

            print("Sending:", cmd)

            resp = robot.send(cmd, timeout=20.0)

            print("Robot response:", resp)

            conn.sendall((resp if resp else "OK").encode())
            continue

        # ------------------------
        # DIRECT PASSTHROUGH
        # ------------------------
        print("Passthrough:", data)

        timeout = 120.0 if "wait_command_done" in data else 15.0

        resp = robot.send(data, timeout=timeout)

        print("Robot response:", resp)

        conn.sendall((resp if resp else "OK").encode())

    except Exception as e:

        print("Bridge error:", e)

        try:
            conn.sendall(f"ERROR:{e}".encode())
        except Exception:
            pass

    finally:
        conn.close()