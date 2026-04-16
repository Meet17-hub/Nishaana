#!/bin/python3

from flask import Flask, Response, jsonify, request
from picamera2 import Picamera2
import cv2
import numpy as np
import os
import time
import threading
import subprocess
import socket
import platform
import RPi.GPIO as GPIO
from flask_socketio import SocketIO
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------- CAPTURE STORAGE ----------------
CAPTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
LATEST_CAPTURE_PATH = os.path.join(CAPTURES_DIR, "latest_capture.jpg")

POWER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "power_control.sh")

# ---------------- GPIO SETUP ----------------
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

GPIO.setup(12, GPIO.OUT)
led = GPIO.PWM(12, 5000)
led.start(100)
brightness = 100

SENSOR_PISTOL = 9
SENSOR_RIFLE = 25
STOP_PIN = 5
EXTRA_PIN = 6
VIBRATION_PIN = 14

MODE_PISTOL = 1
MODE_RIFLE = 0
IR_ACTIVE_STATE = 1
MANDATORY_RUN_SEC = 2.0
IR_WAIT_TIMEOUT_SEC = 10.0
IR_POLL_INTERVAL_SEC = 0.05
IR_MONITOR_LOG_EVERY_LOOPS = 20

# Keep this as None when the external circuit already provides a stable IR signal.
# Change to GPIO.PUD_DOWN or GPIO.PUD_UP after validating idle/trigger states on hardware.
IR_SENSOR_PULL = None

if IR_SENSOR_PULL is None:
    GPIO.setup(SENSOR_PISTOL, GPIO.IN)
    GPIO.setup(SENSOR_RIFLE, GPIO.IN)
else:
    GPIO.setup(SENSOR_PISTOL, GPIO.IN, pull_up_down=IR_SENSOR_PULL)
    GPIO.setup(SENSOR_RIFLE, GPIO.IN, pull_up_down=IR_SENSOR_PULL)

GPIO.setup(STOP_PIN, GPIO.OUT)
GPIO.setup(EXTRA_PIN, GPIO.OUT)
GPIO.setup(VIBRATION_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

GPIO.output(STOP_PIN, 0)
GPIO.output(EXTRA_PIN, 0)

# ---------------- GLOBALS ----------------
pis = MODE_PISTOL
latest_frame = None
frame_lock = threading.Lock()

motor_running = threading.Event()
SHOT_COOLDOWN_SEC = 1.2
last_score_time = 0

PAIRING_KEY = "TM001_SECRET_9A7F"

VIBRATION_SETTLE_SEC = 0.6
last_vibration_time = 0
vibration_active = False

LAPTOP_IP = None

# ---------------- CAMERA ----------------
picam2 = Picamera2()
config = picam2.create_video_configuration(main={"size": (2592, 1944)})
picam2.configure(config)
picam2.start()

# ---------------- FLASK ----------------
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ---------------- IR LOGIC ----------------

def get_mode_name(mode_value):
    return "PISTOL" if mode_value == MODE_PISTOL else "RIFLE"


def read_ir_states():
    return {
        "pistol": GPIO.input(SENSOR_PISTOL),
        "rifle": GPIO.input(SENSOR_RIFLE),
    }


def get_stop_sensor_key(mode_value):
    return "pistol" if mode_value == MODE_PISTOL else "rifle"


def is_expected_sensor_triggered(mode_value, ir_states):
    return ir_states[get_stop_sensor_key(mode_value)] == IR_ACTIVE_STATE


def IR_read():
    cycle_mode = pis
    mode_name = get_mode_name(cycle_mode)
    stop_sensor_key = get_stop_sensor_key(cycle_mode)

    motor_running.set()
    print(
        f"[IR_read] Motor starting | frozen_mode={mode_name} | mode_value={cycle_mode} | "
        f"mandatory_run_sec={MANDATORY_RUN_SEC} | stop_sensor={stop_sensor_key.upper()}",
        flush=True,
    )

    GPIO.output(STOP_PIN, 1)
    time.sleep(MANDATORY_RUN_SEC)

    print(
        f"[IR_read] Mandatory run finished | frozen_mode={mode_name} | "
        f"expected_sensor={stop_sensor_key.upper()} | active_state={IR_ACTIVE_STATE}",
        flush=True,
    )

    start_wait = time.time()
    loop_count = 0

    while (time.time() - start_wait) < IR_WAIT_TIMEOUT_SEC:
        loop_count += 1
        ir_states = read_ir_states()

        if loop_count % IR_MONITOR_LOG_EVERY_LOOPS == 0:
            print(
                f"[IR_read] Poll | frozen_mode={mode_name} | expected_sensor={stop_sensor_key.upper()} | "
                f"pistol_state={ir_states['pistol']} | rifle_state={ir_states['rifle']} | "
                f"elapsed_sec={time.time() - start_wait:.2f}",
                flush=True,
            )

        if is_expected_sensor_triggered(cycle_mode, ir_states):
            print(
                f"[IR_read] Stop detected | reason={stop_sensor_key.upper()}_IR_ACTIVE | "
                f"frozen_mode={mode_name} | pistol_state={ir_states['pistol']} | "
                f"rifle_state={ir_states['rifle']}",
                flush=True,
            )
            GPIO.output(STOP_PIN, 0)
            break

        time.sleep(IR_POLL_INTERVAL_SEC)
    else:
        print(
            f"[IR_read] Stop detected | reason=TIMEOUT | frozen_mode={mode_name} | "
            f"timeout_sec={IR_WAIT_TIMEOUT_SEC}",
            flush=True,
        )
        GPIO.output(STOP_PIN, 0)

    motor_running.clear()
    print(f"[IR_read] Motor sequence complete | frozen_mode={mode_name}", flush=True)


def monitor_IR_sensor():
    while True:
        time.sleep(1.5)
        ir_states = read_ir_states()
        print(
            f"[monitor_IR_sensor] Debug snapshot | current_mode={get_mode_name(pis)} | "
            f"motor_running={motor_running.is_set()} | pistol_state={ir_states['pistol']} | "
            f"rifle_state={ir_states['rifle']}",
            flush=True,
        )


def socketio_heartbeat():
    while True:
        time.sleep(5)
        socketio.emit("test_event", {"msg": "PI alive", "ts": time.time()})


@socketio.on("connect")
def on_connect():
    global LAPTOP_IP

    client_ip = request.remote_addr
    token = request.args.get("key")

    print("Connect from:", client_ip, flush=True)

    if LAPTOP_IP is None:
        LAPTOP_IP = client_ip
        print("Laptop IP locked:", LAPTOP_IP, flush=True)

    if token == PAIRING_KEY or token is None:
        return True

    return False


def vibration_edge(channel):
    global last_vibration_time, vibration_active
    if motor_running.is_set():
        return
    last_vibration_time = time.time()
    vibration_active = True


GPIO.add_event_detect(VIBRATION_PIN, GPIO.FALLING, callback=vibration_edge, bouncetime=20)


def monitor_vibration():
    global last_vibration_time, vibration_active, last_score_time

    while True:
        time.sleep(0.01)

        if motor_running.is_set():
            continue

        if vibration_active and time.time() - last_vibration_time > VIBRATION_SETTLE_SEC:
            now = time.time()

            if now - last_score_time < SHOT_COOLDOWN_SEC:
                vibration_active = False
                continue

            last_score_time = now
            vibration_active = False

            capture()

            socketio.emit("motor_vibration", {"event": "shot_settled", "timestamp": now})

            try:
                if LAPTOP_IP:
                    flask_url = f"http://{LAPTOP_IP}:5000/api/shot_detected"
                    requests.post(flask_url, json={"event": "shot", "ts": now}, timeout=2)
            except Exception:
                pass


# ---------------- NETWORK SCAN ----------------

def get_local_subnet():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        local_ip = sock.getsockname()[0]
        return ".".join(local_ip.split(".")[:3]), local_ip
    finally:
        sock.close()


def check_device_reachable(ip):
    system_name = platform.system().lower()
    if system_name == "windows":
        command = ["ping", "-n", "1", "-w", "1000", ip]
    else:
        command = ["ping", "-c", "1", "-W", "1", ip]

    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def resolve_hostname(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def sort_ip_key(ip):
    return [int(part) for part in ip.split(".")]


def scan_local_devices():
    subnet, local_ip = get_local_subnet()
    ip_candidates = [f"{subnet}.{host}" for host in range(1, 256)]
    active_ips = []

    print(f"[scan_local_devices] Starting subnet scan | subnet={subnet}.0/24 | local_ip={local_ip}", flush=True)

    with ThreadPoolExecutor(max_workers=128) as executor:
        future_to_ip = {executor.submit(check_device_reachable, ip): ip for ip in ip_candidates}
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                if future.result():
                    active_ips.append(ip)
            except Exception:
                pass

    active_ips.sort(key=sort_ip_key)
    devices = []

    with ThreadPoolExecutor(max_workers=64) as executor:
        future_to_ip = {executor.submit(resolve_hostname, ip): ip for ip in active_ips}
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                hostname = future.result()
            except Exception:
                hostname = None

            devices.append({
                "ip": ip,
                "hostname": hostname,
                "is_local_device": ip == local_ip,
            })

    devices.sort(key=lambda device: sort_ip_key(device["ip"]))
    print(f"[scan_local_devices] Scan complete | active_devices={len(devices)}", flush=True)

    return {
        "status": "ok",
        "subnet": f"{subnet}.0/24",
        "local_ip": local_ip,
        "count": len(devices),
        "devices": devices,
    }


# ---------------- ROUTES ----------------

@app.route('/capture', methods=['GET', 'POST'])
def capture():
    global latest_frame

    frame = picam2.capture_array()

    h, w = frame.shape[:2]
    rot = cv2.getRotationMatrix2D((w // 2, h // 2), 450, 1)
    rotated = cv2.warpAffine(frame, rot, (w, h))

    ok, jpeg = cv2.imencode('.jpg', rotated)
    if not ok:
        return "encode failed", 500

    os.makedirs(CAPTURES_DIR, exist_ok=True)
    jpg = jpeg.tobytes()

    with open(LATEST_CAPTURE_PATH, "wb") as f:
        f.write(jpg)

    name = time.strftime("capture_%Y%m%d_%H%M%S.jpg")
    with open(os.path.join(CAPTURES_DIR, name), "wb") as f:
        f.write(jpg)

    with frame_lock:
        latest_frame = jpg

    return "true", 200


@app.route('/frame')
def frame():
    with frame_lock:
        if latest_frame is None:
            return "no frame", 404
        return Response(latest_frame, mimetype='image/jpeg')


@app.route('/scan_devices')
def scan_devices():
    try:
        return jsonify(scan_local_devices())
    except Exception as exc:
        print(f"[scan_devices] error: {exc}", flush=True)
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route('/pistol')
def pistol():
    global pis
    pis = MODE_PISTOL
    print(f"[/pistol endpoint] Mode switched to PISTOL (pis={pis})", flush=True)
    return "true"


@app.route('/rifle')
def rifle():
    global pis
    pis = MODE_RIFLE
    print(f"[/rifle endpoint] Mode switched to RIFLE (pis={pis})", flush=True)
    return "true"


@app.route('/nexttarget')
def nexttarget():
    if motor_running.is_set():
        return jsonify({"status": "busy"}), 409
    threading.Thread(target=IR_read, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/brightness")
def set_brightness():
    global brightness
    value = request.args.get("value", type=int)
    value = max(0, min(value, 100))
    brightness = value
    led.ChangeDutyCycle(value)
    return jsonify({"brightness": value})


@app.route('/shutdown', methods=['POST'])
def shutdown():
    threading.Thread(target=lambda: subprocess.Popen(["bash", POWER_SCRIPT, "shutdown"]), daemon=True).start()
    return jsonify({"status": "shutting_down"})


@app.route('/reboot', methods=['POST'])
def reboot():
    threading.Thread(target=lambda: subprocess.Popen(["bash", POWER_SCRIPT, "reboot"]), daemon=True).start()
    return jsonify({"status": "rebooting"})


@app.route('/ack')
def ack():
    return jsonify({"motor_running": motor_running.is_set()})


# ---------------- MAIN ----------------

if __name__ == '__main__':
    try:
        threading.Thread(target=monitor_IR_sensor, daemon=True).start()
        threading.Thread(target=monitor_vibration, daemon=True).start()
        threading.Thread(target=socketio_heartbeat, daemon=True).start()

        socketio.run(app, host="0.0.0.0", port=8000)

    finally:
        GPIO.cleanup()
