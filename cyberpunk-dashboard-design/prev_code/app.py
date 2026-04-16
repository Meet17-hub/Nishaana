# app.py (single-file merge of Flask + starter + optional model_prediction)
import math
import os
import sys
import time
import base64
import threading
import logging
import json
import smtplib
from typing import Any, cast
from email.message import EmailMessage
from flask import request, jsonify, Response
from flask_socketio import SocketIO
import socketio as sio_client
from io import BytesIO
import mimetypes
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import sqlite3
import socket

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Load local .env (SMTP credentials, etc.) if available.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # Optional dependency; app will still work with OS environment variables.
    pass
# Try import OpenCV / numpy / requests — these are required for camera + warp
try:
    import cv2 as cv
    import numpy as np
    import requests
except Exception as e:
    # Let PyInstaller include them via hidden-import; but allow dev to see error
    print("Missing CV2/Numpy/requests - make sure they are installed in the environment:", e, flush=True)
    raise
    _have_model_prediction = True
# Optional: attempt to import scoring functions from model_prediction.py (if present)
try:
    from model_prediction import get_scores_from_bytes as _mp_score_bytes, get_scores_from_hardcoded_image as _mp_score_file
    _have_model_prediction = True

    def get_scores_from_bytes(image_bytes: bytes, shooting_mode: str = 'rifle') -> dict[str, Any]:
        return cast(dict[str, Any], _mp_score_bytes(image_bytes, shooting_mode))

    def get_scores_from_hardcoded_image(shooting_mode: str = 'rifle') -> dict[str, Any]:
        return cast(dict[str, Any], _mp_score_file(shooting_mode))
except Exception:
    _have_model_prediction = False

    def get_scores_from_bytes(image_bytes: bytes, shooting_mode: str = 'rifle') -> dict[str, Any]:
        # fallback stub (no detection)
        return {"status": "no_model", "scored_shots": [], "bullets": []}

    def get_scores_from_hardcoded_image(shooting_mode: str = 'rifle') -> dict[str, Any]:
        return {"status": "no_model", "scored_shots": [], "bullets": []}


# Preprocessing (undistort + wrap to 640x640) extracted from wrap_test.py values.
try:
    from frame_preprocess import preprocess_frame
except Exception as e:
    preprocess_frame = None
    print("[app] Warning: frame_preprocess import failed; falling back to legacy warp:", e, flush=True)


# ------------------- Utilities for PyInstaller paths -------------------
# Get the script directory first (for both dev and PyInstaller modes)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def resource_path(relative_path):
    """Return absolute path for resources in dev and PyInstaller onefile mode."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = SCRIPT_DIR  # Use script directory, not current working directory
    return os.path.join(base_path, relative_path)

# Directory where the exe runs (writable) - use this for latest_warped.jpg
RUN_DIR = os.path.abspath(os.getcwd())
LATEST_WARPED_PATH = os.path.join(RUN_DIR, "latest_warped.jpg")
# Path for the raw (live) frame received from the camera (unwarped)
# Ensure raw image is saved in the same directory as this script (where you ran `app.py`)
LATEST_RAW_PATH = os.path.join(SCRIPT_DIR, "latest_raw.jpeg")

# ------------------- Flask app -------------------
templates_dir = resource_path("templates")
static_dir = resource_path("static")
print(f"[app] Templates directory: {templates_dir}", flush=True)
print(f"[app] Static directory: {static_dir}", flush=True)

app = Flask(__name__, template_folder=templates_dir, static_folder=static_dir)
app.secret_key = "your_secret_key"
socketio = SocketIO(app, cors_allowed_origins="*")
print("🚀 APP STARTED: Flask + Socket.IO initialized", flush=True)

@socketio.on("motor_vibration")
def on_vibration(data):
    print("⚡ SHOT / VIBRATION RECEIVED:", data, flush=True)

    # notify UI only
    socketio.emit("shot_ui_signal", {
        "event": "shot",
        "ts": time.time()
    })

    # ⚠️ DO NOT do heavy work here
    # Just signal → UI / frontend reacts

@socketio.on("connect")
def on_browser_connect():
    print("🧭 Browser connected to app Socket.IO", flush=True)

def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )''')
    conn.commit()
    conn.close()

init_db()  # create table if it doesn't exist
shooting_mode = 'rifle'   # default: 'rifle' or 'pistol'
DEMO_MODE = False  # Set to True for demo mode without hardware

# Global state
device_ips = {  # keep your mapping
    '0': "10.0.0.32",
    '1': "192.168.1.1",
    '2': "192.168.1.2",
    '3': "192.168.1.3",
    '4': "192.168.1.4",
    '5': "192.168.1.5",
    '6': "192.168.1.6",
    '7': "192.168.1.7",
    '8': "192.168.1.8",
    '9': "172.20.109.94",
    '10': "10.0.0.40"
}
# ------------------- New Target EXACTLY-ONCE LOCK -------------------
new_target_in_progress = False
new_target_lock = threading.Lock()


selected_ip = None
latest_image = None         # raw jpeg bytes for /api/data
latest_raw_image = None     # raw jpeg bytes (pre-warp) for scoring
last_update_time = None
starter_thread_obj = None
starter_thread_stop = threading.Event()
latest_annotated_image = None  # base64 data URI with detections drawn
latest_display_image = None    # base64 data URI for UI (warped view)
latest_display_jpeg = None     # cached JPEG bytes for UI (/latest_image)

pi_socket = sio_client.Client(reconnection=True)

@pi_socket.on("motor_vibration")
def on_pi_vibration(data):
    print("🎯 SHOT EVENT RECEIVED FROM PI:", data, flush=True)

    def auto_update():
        time.sleep(0.3)  # 🔑 let camera & target settle
        socketio.emit("shot_ui_signal", {
            "ts": time.time()
        })

    threading.Thread(target=auto_update, daemon=True).start()


@pi_socket.on("target_ack")
def on_target_ack(data):
    print("🎯 TARGET READY FROM PI:", data, flush=True)

    # OPTIONAL: auto update score
    socketio.emit("target_ready_ui", data)

# ------------------- Pi Socket.IO client -------------------

# ------------------- Shot ledger (server-side) -------------------
# Stores stable shot history per logged-in user.
SHOT_MATCH_PX = 8  # match threshold on warped image pixel coords
_shot_ledgers: dict[str, dict[str, Any]] = {}
_shot_ledgers_lock = threading.Lock()



def _ledger_user_key() -> str | None:
    # Use the login identity as the stable server-side key.
    user = session.get('user') or session.get('username')
    if isinstance(user, str) and user:
        return user
    return None


def _get_or_create_ledger(user_key: str) -> dict[str, Any]:
    with _shot_ledgers_lock:
        ledger = _shot_ledgers.get(user_key)
        if ledger is None:
            ledger = {"target_seq": 1, "shots": []}
            _shot_ledgers[user_key] = ledger
        return ledger


def _reset_ledger(user_key: str) -> dict[str, Any]:
    with _shot_ledgers_lock:
        ledger = _shot_ledgers.get(user_key)
        if ledger is None:
            ledger = {"target_seq": 1, "shots": []}
        else:
            ledger["target_seq"] = int(ledger.get("target_seq", 0)) + 1
            ledger["shots"] = []
        _shot_ledgers[user_key] = ledger
        return ledger


def _detect_overlapping_shots(detected: list[dict[str, Any]], overlap_threshold_px: float = 15.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Detect overlapping shots.
    Returns: (non_overlapping_shots, overlapping_shots)
    """
    if not detected:
        return [], []
    
    non_overlapping = []
    overlapping = []
    used_indices: set[int] = set()
    
    for i, shot1 in enumerate(detected):
        if i in used_indices:
            continue
        
        try:
            x1 = int(shot1.get("x", 0))
            y1 = int(shot1.get("y", 0))
        except Exception:
            continue
        
        for j in range(i + 1, len(detected)):
            if j in used_indices:
                continue
            
            shot2 = detected[j]
            try:
                x2 = int(shot2.get("x", 0))
                y2 = int(shot2.get("y", 0))
            except Exception:
                continue
            
            distance = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            
            if distance <= overlap_threshold_px:
                overlapping.append(shot2)
                used_indices.add(j)
        
        non_overlapping.append(shot1)
    
    return non_overlapping, overlapping

def _overlaps_any_detected(x, y, r, detected, thresh_px):
    for d in detected:
        dx = x - int(d.get("x", 0))
        dy = y - int(d.get("y", 0))
        if dx*dx + dy*dy <= thresh_px * thresh_px:
            return True
    return False

def _merge_detected_shots(user_key: str, detected: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge detected shots with overlap-aware hole growth logic."""

    non_overlapping, overlapping_shots = _detect_overlapping_shots(
        detected, overlap_threshold_px=3.0
    )

    ledger = _get_or_create_ledger(user_key)
    shots: list[dict[str, Any]] = ledger.get("shots", [])

    MIN_NEW_HOLE_RADIUS_PX = 3.0  # applies ONLY to non-overlapping shots

    for shot in detected:
        try:
            x = int(shot.get("x"))
            y = int(shot.get("y"))
            score = float(shot.get("score"))
            r = float(shot.get("r", 6.0))
        except Exception:
            continue

        best_idx = None
        best_d2 = None

        # 🔍 STEP 1: OVERLAP CHECK (ALWAYS FIRST)
        for idx, existing in enumerate(shots):
            ex = int(existing.get("x"))
            ey = int(existing.get("y"))
            dx = x - ex
            dy = y - ey
            d2 = dx * dx + dy * dy

            dynamic_match_px = max(
                SHOT_MATCH_PX,
                float(existing.get("max_r", existing.get("r", 0.0))) * 1.3
            )

            if d2 <= dynamic_match_px * dynamic_match_px and (
                best_d2 is None or d2 < best_d2
            ):
                best_d2 = d2
                best_idx = idx

        # 🟡 CASE 1: OVERLAPPING SHOT → ALWAYS ACCEPT
        if best_idx is not None:
           existing = shots[best_idx]

    # 🔒 CHANGE: ensure pellet list exists
           pellets = existing.setdefault("pellets", [])

    # 🔒 CHANGE: record EVERY overlapping shot
           pellets.append({
        "ts": time.time(),
        "r": r,
        "x": x,
        "y": y,
    })

    # 🔒 CHANGE: hits = real pellet count
           existing["hits"] = len(pellets)

    # 🔒 Smooth radius to avoid jitter
           existing["r"] = 0.7 * existing.get("r", r) + 0.3 * r

    # 🔒 Track true hole growth only
           old_r = float(existing.get("max_r", existing.get("r", 0.0)))
           if r > old_r * 1.05:
             existing["max_r"] = r

             existing["ts"] = time.time()
           continue  # 🔒 NEVER create a new hole here


        # 🔴 CASE 2: NON-OVERLAPPING + TOO SMALL → IGNORE
        if r < MIN_NEW_HOLE_RADIUS_PX:
             if not _overlaps_any_detected(x, y, r, detected, SHOT_MATCH_PX):
              continue

        # 🟢 CASE 3: NON-OVERLAPPING + VALID SIZE → NEW HOLE
        cx = shot.get("center_x")
        cy = shot.get("center_y")

        if cx is None or cy is None:
          continue  # safety guard

        dx = x - cx
        dy = cy - y  # invert Y for screen coordinates

        r = float(shot.get("r", 6.0))

        angle_deg = math.degrees(math.atan2(dy, dx))

        shots.append({
    "id": len(shots) + 1,
    "x": x,
    "y": y,
    "dx": dx,
    "dy": dy,
    "angle": angle_deg,   # 🔥 THIS is the arrow direction
    "r": r,
    "max_r": r,
    "hits": 1,
    "pellets": [{
        "ts": time.time(),
        "r": r,
    }],
    "score": float(round(score, 1)),
    "ts": time.time(),
})

    ledger["shots"] = shots
    ledger["overlapping_shots"] = overlapping_shots
    return ledger


# ------------------- starter logic (merged) -------------------
API_BASE = "http://127.0.0.1:5000"  # unused here, kept for compatibility
POST_INTERVAL_SEC = 200.0
CONNECT_RETRY_SEC = 2.0

def hardcoded_perspective(frame):
    # New path: apply the same undistort + wrap used in wrap_test.py (640x640).
    if preprocess_frame is not None:
        try:
             #frame_preprocess.py has a default WRAP_POINTS_SRC (tuned for pistol).
            # For rifle mode, explicitly override with the calibrated rifle wrap points.
            if shooting_mode == 'rifle':
                rifle_src = np.array(
                    [
                        [1044.54, 938.15],
                        [1063.88, 1392.72],
                        [1568.0, 1402.39],
                        [1568.0, 918.81],
                    ],
                    dtype=np.float32,
                )
                return preprocess_frame(frame, src_points=rifle_src)
            return preprocess_frame(frame)
        except Exception as e:
            print(f"[app] preprocess_frame failed, falling back to legacy warp: {e}", flush=True)

    # Fallback legacy warp if preprocessing helper isn't available.
    if shooting_mode == 'pistol':
        points_src = np.array([
            [747, 544],      # top left
            [811.0, 1547.0],  # bottom left
            [1792.0, 1547.0], # bottom right
            [1877.0, 523.0], # top right
        ], dtype=np.float32)
    else:
        points_src = np.array([
            [1024, 565],
            [1067.0, 1077.0],
            [1568.0, 1056.0],
            [1568.0, 544.0],
        ], dtype=np.float32)

    width, height = 640, 640
    points_dst = np.array([[0, 0], [0, height], [width, height], [width, 0]], dtype=np.float32)
    matrix = cv.getPerspectiveTransform(points_src, points_dst)
    return cv.warpPerspective(frame, matrix, (width, height))

def open_stream_for_ip(ip: str):
    url = f"http://{ip}:8000/video_feed"
    cap = cv.VideoCapture(url)
    if not cap or not cap.isOpened():
        return None
    return cap

def create_placeholder_image():
    """Create a placeholder image when device is unavailable."""
    img = np.ones((640, 640, 3), dtype=np.uint8) * 40  # dark gray background
    cv.putText(img, "CAMERA OFFLINE", (100, 200), cv.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
    cv.putText(img, f"IP: {selected_ip}", (120, 350), cv.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 255), 2)
    cv.putText(img, "Waiting for device...", (80, 450), cv.FONT_HERSHEY_SIMPLEX, 1.2, (100, 100, 255), 2)
    return img

def trigger_capture(ip: str, session: requests.Session):
    """Ask the Pi to capture once so the next frame is ready."""
    try:
        session.get(f"http://{ip}:8000/capture", timeout=1.0)
    except Exception:
        # Silently fail - device may not be available
        pass

def fetch_frame_direct(ip: str, session: requests.Session):
    """Pull one JPEG from the Pi's /frame endpoint (single-shot, non-streaming)."""
    url = f"http://{ip}:8000/frame"
    try:
        resp = session.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        # Silently fail - device may not be available
        pass
    return None



def starter_thread():
    """
    Background starter thread:
    - waits for selected_ip to be set (via login)
    - opens stream, applies hardcoded perspective, saves latest_warped.jpg
    - updates global latest_image bytes for /api/data to serve
    - shows placeholder when device is unavailable
    """
    global selected_ip, latest_image, last_update_time

    print("[starter] thread started", flush=True)
    session = requests.Session()

    while not starter_thread_stop.is_set():
        # Wait until selected_ip is set
        if not selected_ip:
            time.sleep(0.5)
            continue

        ip = selected_ip  # e.g. "192.168.0.X"
        print(f"[starter] trying to open stream at {ip}", flush=True)

        cap = None
        # attempt to open stream (retry a few times, then show placeholder)
        attempts = 0
        max_attempts = 10
        while cap is None and not starter_thread_stop.is_set() and attempts < max_attempts:
            cap = open_stream_for_ip(ip)
            if cap is None:
                attempts += 1
                if attempts % 3 == 0:
                    print(f"[starter] waiting for video stream at {ip} (attempt {attempts}/{max_attempts})", flush=True)
                time.sleep(CONNECT_RETRY_SEC)

        if starter_thread_stop.is_set():
            break

        # If we couldn't connect to device, show placeholder image instead of hanging
        if cap is None:
            print(f"[starter] device unavailable, showing placeholder", flush=True)
            last_sent = 0.0
            while not starter_thread_stop.is_set() and selected_ip == ip:
                try:
                    # Create and show placeholder image
                    placeholder = create_placeholder_image()
                    
                    now = time.time()
                    if now - last_sent >= 2.0:  # Update placeholder every 2 seconds
                        try:
                            ok, buf = cv.imencode(".jpg", placeholder)
                            if ok:
                                latest_image = buf.tobytes()
                                last_update_time = time.time()
                                try:
                                    cv.imwrite(LATEST_WARPED_PATH, placeholder)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        last_sent = now
                    
                    # Every 30 seconds, try to reconnect to device
                    if int(now - last_sent) % 30 == 0:
                        print(f"[starter] retrying connection to {ip}", flush=True)
                        cap = open_stream_for_ip(ip)
                        if cap is not None:
                            print(f"[starter] reconnected to {ip}", flush=True)
                            break
                    
                    time.sleep(1)
                except Exception as e:
                    print(f"[starter] placeholder error: {e}", flush=True)
                    time.sleep(1)
            continue

        print("[starter] stream opened", flush=True)

        last_sent = 0.0
        try:
            while not starter_thread_stop.is_set():
                if cap is None:
                    break
                ret, frame = cap.read()
                if not ret or frame is None:
                    # Fallback: fetch a single frame via HTTP /frame to avoid losing the cycle
                    single = fetch_frame_direct(ip, session)
                    if single:
                        npbuf = np.frombuffer(single, np.uint8)
                        frame = cv.imdecode(npbuf, cv.IMREAD_COLOR)
                    if frame is None:
                        print("[starter] frame read failed, reconnecting...", flush=True)
                        try:
                            if cap is not None:
                                cap.release()
                        except Exception:
                            pass
                        cap = None
                        # break to outer while so it reopens stream for same ip
                        break

                now = time.time()
                if now - last_sent >= POST_INTERVAL_SEC:
                    warped = hardcoded_perspective(frame)
                    # save for debug and for any external reading
                    try:
                        cv.imwrite(LATEST_WARPED_PATH, warped)
                    except Exception as e:
                        print(f"[starter] failed to write warped image: {e}", flush=True)

                    # Also save the raw (unwarped) frame that was just received from the camera
                    try:
                        cv.imwrite(LATEST_RAW_PATH, frame)
                    except Exception as e:
                        print(f"[starter] failed to write raw image: {e}", flush=True)

                    # set latest_image bytes so /api/data serves the warped frame
                    try:
                        ok, buf = cv.imencode(".jpg", warped)
                        if ok:
                            latest_image = buf.tobytes()
                            last_update_time = time.time()
                        else:
                            print("[starter] cv.imencode failed", flush=True)
                    except Exception as e:
                        print(f"[starter] failed to encode warped image: {e}", flush=True)

                    last_sent = now
                # small sleep to prevent tight loop
                time.sleep(0.01)

        except Exception as e:
            print(f"[starter] error in capture loop: {e}", flush=True)
        finally:
            try:
                if cap:
                    cap.release()
            except Exception:
                pass

    print("[starter] thread exiting", flush=True)

# ------------------- Flask routes -------------------
USERS_FILE = os.path.join(SCRIPT_DIR, "users.json")
def load_users():
    print(f"[app] Loading users from: {USERS_FILE}", flush=True)
    if not os.path.exists(USERS_FILE):
        print(f"[app] Users file not found at {USERS_FILE}", flush=True)
        return {}
    with open(USERS_FILE, "r") as f:
        users = json.load(f)
        print(f"[app] Loaded {len(users)} users", flush=True)
        return users

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password') or ""

        users = load_users()
        if username in users:
            flash("Username already exists.", "error")
            return render_template('login.html')

        users[username] = {
            "email": email,
            "password": generate_password_hash(password)
        }
        save_users(users)
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    global selected_ip
    try:
        if request.method == 'POST':
            name = request.form.get('username')
            password = request.form.get('password')
            device_id = request.form.get('device_id')

            print(f"[app] Login attempt: username={name}, device_id={device_id}", flush=True)

            if not name or not password or not device_id:
                flash("All fields are required.", "error")
                return render_template('login.html')

            users = load_users()
            user = users.get(name)
            
            if user is None:
                print(f"[app] User '{name}' not found. Available users: {list(users.keys())}", flush=True)
                flash("Invalid name or password.", "error")
                return render_template('login.html')
            
            password_match = check_password_hash(user["password"], password)
            print(f"[app] Password check for '{name}': {password_match}", flush=True)
            
            if not password_match:
                flash("Invalid name or password.", "error")
                return render_template('login.html')

            # Save selected device IP
            selected_ip = f"192.168.1.{device_id}"
            
            connect_pi_socket(selected_ip)

            # Set consistent session keys used elsewhere:
            session['user'] = name            # <-- used by require_login()
            session['username'] = name       # keep this for templates
            session['email'] = user.get('email')
            session['logged_in'] = True

            print(f"[app] Logged in as {name}, selected_ip = {selected_ip}", flush=True)
            
            # Start the background thread to capture frames from device
            ensure_starter_thread_running()
            
            return redirect(url_for('index'))

        return render_template('login.html')

    except Exception as e:
        print("Login error:", e, flush=True)
        return "Error during login", 500
    
    
def connect_pi_socket(ip):
    try:
        pi_socket.connect(
            f"http://{ip}:8000",
            transports=["websocket"],
            headers={}, 
            auth=None,
            query={"key": "TM001_SECRET_9A7F"}
        )
        print(f"🔌 Connected to PI Socket.IO at {ip}", flush=True)
    except Exception as e:
        print("❌ PI Socket.IO connection failed:", e, flush=True)


@app.route('/')
def index():
    try:
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return render_template('index_cam.html', ip_address=selected_ip)
    except Exception as e:
        print("Index error:", e, flush=True)
        return "An error occurred loading the index page.", 500

@app.route('/api/selected_ip', methods=['GET'])
def api_selected_ip():
    global selected_ip
    if selected_ip:
        return jsonify({'selected_ip': selected_ip}), 200
    return jsonify({'error': 'No IP selected'}), 404

@app.route('/api/data', methods=['GET'])
def api_data():
    global latest_image, last_update_time, latest_annotated_image, latest_display_image, latest_display_jpeg
    try:
        image_url = None
        if last_update_time and (latest_display_jpeg or latest_image or os.path.exists(LATEST_WARPED_PATH)):
            image_url = f"/latest_image?ts={int(last_update_time * 1000)}"

        payload = {
            'image': latest_display_image if latest_display_image else ('data:image/jpeg;base64,' + base64.b64encode(latest_image).decode('utf-8') if latest_image else None),
            'image_url': image_url,
            'last_update': last_update_time
        }
        return jsonify(payload)
    except Exception as e:
        print("api_data error:", e, flush=True)
        return "An error occurred while retrieving data.", 500
    
def get_my_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"



@app.route('/latest_image', methods=['GET'])
def latest_image_jpeg():
    """Serve the cached latest warped image as JPEG."""
    try:
        if latest_display_jpeg:
            return Response(latest_display_jpeg, mimetype='image/jpeg')
        if latest_image:
            return Response(latest_image, mimetype='image/jpeg')
        if os.path.exists(LATEST_WARPED_PATH):
            with open(LATEST_WARPED_PATH, 'rb') as fh:
                data = fh.read()
            return Response(data, mimetype='image/jpeg')
        return "No image", 404
    except Exception as e:
        print("latest_image error:", e, flush=True)
        return "Error", 500

@app.route('/api/live_score', methods=['GET'])
def api_live_score():
    global latest_image, latest_raw_image, shooting_mode, latest_annotated_image, latest_display_image, latest_display_jpeg, last_update_time, selected_ip
    try:
        frame_bytes = None
        bytes_for_scoring = None
        scored_on_warped = False

        # On-demand: only trigger capture when this endpoint is hit.
        if selected_ip:
            session = requests.Session()
            trigger_capture(selected_ip, session)
            fresh = fetch_frame_direct(selected_ip, session)
            if fresh:
                npbuf = np.frombuffer(fresh, np.uint8)
                frame = cv.imdecode(npbuf, cv.IMREAD_COLOR)
                if frame is not None:
                    try:
                        cv.imwrite(LATEST_RAW_PATH, frame)
                    except Exception as e:
                        print(f"[api_live_score] failed to write raw image: {e}", flush=True)

                    # Encode raw for scoring (no warp)
                    ok_raw, raw_buf = cv.imencode(".jpg", frame)
                    if ok_raw:
                        latest_raw_image = raw_buf.tobytes()
                        bytes_for_scoring = latest_raw_image

                    # For UI, always show warped frame (hardcoded perspective); fallback to raw on failure
                    warped = frame
                    try:
                        warped = hardcoded_perspective(frame)
                    except Exception as e:
                        print(f"[api_live_score] warp failed, using raw: {e}", flush=True)

                    try:
                        cv.imwrite(LATEST_WARPED_PATH, warped)
                    except Exception as e:
                        print(f"[api_live_score] failed to write warped image: {e}", flush=True)

                    ok, buf = cv.imencode(".jpg", warped)
                    if ok:
                        latest_image = buf.tobytes()  # warped for display
                        frame_bytes = latest_image
                        last_update_time = time.time()

                        # Use the same warped frame for scoring when available.
                        # This compensates for camera tilt/photogrammetry.
                        if shooting_mode == 'rifle':
                          bytes_for_scoring = latest_raw_image
                          scored_on_warped = False
                        else:
                          bytes_for_scoring = latest_image
                          scored_on_warped = True

        # Fallback to existing cached image; do NOT fetch anything else.
        if frame_bytes is None:
            frame_bytes = latest_image
        if bytes_for_scoring is None:
            bytes_for_scoring = latest_raw_image or frame_bytes

        if not bytes_for_scoring:
            return jsonify({"status": "no_image", "message": "No frame available", "scored_shots": [], "bullets": []})

        score_data = get_scores_from_bytes(bytes_for_scoring, shooting_mode)
        center = score_data.get("center")
        if center:
           for s in score_data.get("scored_shots", []):
             s["center_x"] = center["x"]
             s["center_y"] = center["y"]
        latest_annotated_image = score_data.get("annotated_image")

        # Server-side stable shot storage (dedupe by coordinates; freeze first score)
        try:
            user_key = _ledger_user_key()
            if user_key and isinstance(score_data, dict):
                detected = score_data.get('scored_shots')
                if isinstance(detected, list):
                    # Expose raw detections from the model before any server-side merge
                    score_data['pre_merge_detections'] = detected
                    ledger = _merge_detected_shots(user_key, detected)
                    shots = ledger.get('shots', [])
                    score_data['stored_shots'] = shots
                    score_data['stored_total_score'] = float(round(sum(float(s.get('score', 0.0)) for s in shots), 1))
                    score_data['target_seq'] = ledger.get('target_seq', 1)
                    # Include overlapping shots
                    overlapping = ledger.get('overlapping_shots', [])
                    if overlapping:
                        score_data['overlapping_shots'] = overlapping
                        score_data['overlap_count'] = len(overlapping)
        except Exception as e:
            print("[api_live_score] ledger merge error:", e, flush=True)

        # Build a wrapped display image from annotated frame if available
        latest_display_image = None
        latest_display_jpeg = None
        # Build display image with detections: warp annotated frame if available; else use warped base frame.
        latest_display_jpeg = None
        latest_display_image = None
        try:
            if latest_annotated_image and latest_annotated_image.startswith("data:image"):
                b64_part = latest_annotated_image.split(",", 1)[-1]
                ann_bytes = base64.b64decode(b64_part)
                npimg = np.frombuffer(ann_bytes, np.uint8)
                ann_frame = cv.imdecode(npimg, cv.IMREAD_COLOR)
                if ann_frame is not None:
                    # If scoring ran on warped input, annotated is already warped; don't warp again.
                    if scored_on_warped:
                        ann_warped = ann_frame
                    else:
                        try:
                            ann_warped = hardcoded_perspective(ann_frame)
                        except Exception as e:
                            print(f"[api_live_score] annotated warp failed, using annotated raw: {e}", flush=True)
                            ann_warped = ann_frame
                    ok, buf = cv.imencode(".jpg", ann_warped)
                    if ok:
                        latest_display_jpeg = buf.tobytes()
                        latest_display_image = 'data:image/jpeg;base64,' + base64.b64encode(latest_display_jpeg).decode('utf-8')
        except Exception as e:
            print("[api_live_score] display build error:", e, flush=True)

        # Fallback to warped base frame if annotated display not built
        if latest_display_jpeg is None and latest_image:
            latest_display_jpeg = latest_image
            latest_display_image = 'data:image/jpeg;base64,' + base64.b64encode(latest_display_jpeg).decode('utf-8')

        # Return a stable URL the UI can keep showing until next Update Score
        if last_update_time:
            score_data['image_url'] = f"/latest_image?ts={int(last_update_time * 1000)}"

        return jsonify(score_data)
    except Exception as e:
        print("api_live_score error:", e, flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/reset', methods=['GET'])
def api_reset():
    global latest_image, latest_raw_image, latest_display_image, latest_display_jpeg, latest_annotated_image, last_update_time
    latest_image = None
    latest_raw_image = None
    latest_display_image = None
    latest_display_jpeg = None
    latest_annotated_image = None
    last_update_time = None
    # Also clear server-side stored shots for the current user so displayed
    # score resets when the UI calls /api/reset.
    try:
        user_key = _ledger_user_key()
        if user_key:
            _reset_ledger(user_key)
            print(f"[api_reset] cleared ledger for user: {user_key}", flush=True)
    except Exception as e:
        print(f"[api_reset] failed to clear ledger: {e}", flush=True)

    # do NOT stop starter thread — it will keep trying to run
    return "Reset Complete"


@app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    """Shutdown the application process (PyWebview/Flask bundle)."""
    if not (session.get('logged_in') or session.get('user')):
        return jsonify({'error': 'unauthorized'}), 401

    shutdown_func = request.environ.get('werkzeug.server.shutdown')

    def shutdown_later():
        # Give the HTTP response a moment to flush to the client
        time.sleep(0.3)
        try:
            starter_thread_stop.set()
        except Exception:
            pass

        if callable(shutdown_func):
            try:
                shutdown_func()
                return
            except Exception:
                pass

        os._exit(0)

    threading.Thread(target=shutdown_later, daemon=True).start()
    return jsonify({'status': 'shutting_down'}), 200


@app.route('/api/reboot', methods=['POST'])
def api_reboot():
    """Reboot the selected Raspberry Pi device."""
    if not (session.get('logged_in') or session.get('user')):
        return jsonify({'error': 'unauthorized'}), 401
    if not selected_ip:
        return jsonify({'error': 'no_device_selected'}), 400

    try:
        resp = requests.post(f'http://{selected_ip}:8000/reboot', timeout=2)
        if resp.status_code >= 400:
            return jsonify({'error': 'device_reboot_failed', 'status_code': resp.status_code}), 502
        return jsonify({'status': 'rebooting', 'device_ip': selected_ip}), 200
    except Exception as e:
        print("reboot error:", e, flush=True)
        return jsonify({'error': 'device_unreachable'}), 502

# other control endpoints pass-through to device IP endpoints
@app.route('/api/rifle')
def api_rifle():
    global shooting_mode
    try:
        shooting_mode = 'rifle'
        print(f"[app] Shooting mode set to: {shooting_mode}", flush=True)
        if selected_ip:
            try:
                return requests.get(f'http://{selected_ip}:8000/rifle', timeout=2).text
            except Exception:
                pass
        return jsonify({"status": "ok", "mode": "rifle"})
    except Exception:
        return jsonify({"status": "ok", "mode": "rifle"})

@app.route('/api/pistol')
def api_pistol():
    global shooting_mode
    shooting_mode = 'pistol'

    if selected_ip:
        pc_ip = get_my_ip()

        try:
            # 🔑 SEND PC IP TO PI
            requests.post(
                f"http://{selected_ip}:8000/set_pc_ip",
                json={"pc_ip": pc_ip},
                timeout=2
            )
            print(f"[PC] Sent PC IP {pc_ip} to PI", flush=True)

            # 🔫 THEN SET MODE
            requests.get(f"http://{selected_ip}:8000/pistol", timeout=2)

        except Exception as e:
            print("[PC] Failed to send PC IP to PI:", e, flush=True)

    return jsonify({"status": "ok", "mode": "pistol"})


@app.route('/api/nexttarget')
def api_nexttarget():
    global new_target_in_progress

    if not selected_ip:
        return jsonify({
            "status": "error",
            "message": "No device selected"
        }), 400

    with new_target_lock:
        if new_target_in_progress:
            return jsonify({
                "status": "busy",
                "message": "New target already in progress"
            }), 409
        new_target_in_progress = True

    try:
        # 🔫 Trigger target (NON-BLOCKING)
        requests.get(
            f"http://{selected_ip}:8000/nexttarget",
            timeout=1.0
        )

        # 🔄 Reset ledger immediately
        user_key = _ledger_user_key()
        if user_key:
            _reset_ledger(user_key)

        return jsonify({
            "status": "ok",
            "message": "Target movement started"
        })

    except Exception as e:
        print("[api_nexttarget] error:", e, flush=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

    finally:
        with new_target_lock:
            new_target_in_progress = False


@app.route('/api/focus_increase')
def api_focus_increase():
    try:
        if selected_ip:
            try:
                return requests.get(f'http://{selected_ip}:8000/focusin', timeout=2).text
            except Exception:
                pass
        return jsonify({"status": "ok", "focus": "increase"})
    except Exception:
        return jsonify({"status": "ok", "focus": "increase"})

@app.route('/api/focus_decrease')
def api_focus_decrease():
    try:
        if selected_ip:
            try:
                return requests.get(f'http://{selected_ip}:8000/focusout', timeout=2).text
            except Exception:
                pass
        return jsonify({"status": "ok", "focus": "decrease"})
    except Exception:
        return jsonify({"status": "ok", "focus": "decrease"})

@app.route('/api/zoom_increase')
def api_zoom_increase():
    try:
        if selected_ip:
            try:
                return requests.get(f'http://{selected_ip}:8000/zoomin', timeout=2).text
            except Exception:
                pass
        return jsonify({"status": "ok", "zoom": "increase"})
    except Exception:
        return jsonify({"status": "ok", "zoom": "increase"})

@app.route('/api/zoom_decrease')
def api_zoom_decrease():
    try:
        if selected_ip:
            try:
                return requests.get(f'http://{selected_ip}:8000/zoomout', timeout=2).text
            except Exception:
                pass
        return jsonify({"status": "ok", "zoom": "decrease"})
    except Exception:
        return jsonify({"status": "ok", "zoom": "decrease"})

@app.route('/api/send_email', methods=['POST'])
def send_email():
    global latest_image, latest_raw_image, latest_display_image, latest_display_jpeg, latest_annotated_image, last_update_time
    try:
        # current user
        current_user_email = session.get('email')
        current_user_name = session.get('username', 'Shooter')
        if not current_user_email:
            return jsonify({'error': 'No logged-in user email found'}), 401
        if not selected_ip:
            return jsonify({'error': 'No device selected'}), 400

        # SMTP config (Gmail): use env vars, do not hardcode secrets
        SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
        SMTP_USER = os.environ.get('SMTP_USER')
        SMTP_PASS = os.environ.get('SMTP_PASS')
        if not SMTP_USER or not SMTP_PASS:
            return jsonify({'error': 'SMTP not configured. Set SMTP_USER and SMTP_PASS (Gmail App Password).'}), 500

        # 1) Capture a fresh frame from Pi
        session_http = requests.Session()
        trigger_capture(selected_ip, session_http)
        fresh = fetch_frame_direct(selected_ip, session_http)
        if not fresh:
            return jsonify({'error': 'Unable to capture image from device'}), 502

        npbuf = np.frombuffer(fresh, np.uint8)
        frame = cv.imdecode(npbuf, cv.IMREAD_COLOR)
        if frame is None:
            return jsonify({'error': 'Device returned invalid image'}), 502

        # Save raw (best-effort)
        try:
            cv.imwrite(LATEST_RAW_PATH, frame)
        except Exception:
            pass

        ok_raw, raw_buf = cv.imencode('.jpg', frame)
        if ok_raw:
            latest_raw_image = raw_buf.tobytes()

        # 2) Warp for UI/scoring (same path as Update Score)
        warped = frame
        try:
            warped = hardcoded_perspective(frame)
        except Exception as e:
            print(f"[send_email] warp failed, using raw: {e}", flush=True)

        try:
            cv.imwrite(LATEST_WARPED_PATH, warped)
        except Exception:
            pass

        ok_w, buf_w = cv.imencode('.jpg', warped)
        if not ok_w:
            return jsonify({'error': 'Failed to encode image'}), 500

        latest_image = buf_w.tobytes()
        last_update_time = time.time()

        # 3) Score (prediction) on warped frame bytes
        score_data = get_scores_from_bytes(latest_image, shooting_mode)
        latest_annotated_image = score_data.get('annotated_image')

        # Merge into server-side stable ledger so email matches UI numbering
        stored_shots = []
        stored_total = 0.0
        user_key = _ledger_user_key()
        if user_key and isinstance(score_data, dict):
            detected = score_data.get('scored_shots')
            if isinstance(detected, list):
                ledger = _merge_detected_shots(user_key, detected)
                stored_shots = ledger.get('shots', [])
                stored_total = float(round(sum(float(s.get('score', 0.0)) for s in stored_shots), 1))

        # Build predicted/annotated attachment bytes (prefer annotated; fallback to warped)
        attachment_bytes = latest_image
        attachment_filename = f"predicted_{int(last_update_time)}.jpg"
        latest_display_jpeg = None
        latest_display_image = None
        try:
            if latest_annotated_image and isinstance(latest_annotated_image, str) and latest_annotated_image.startswith('data:image'):
                b64_part = latest_annotated_image.split(',', 1)[-1]
                ann_bytes = base64.b64decode(b64_part)
                ann_np = np.frombuffer(ann_bytes, np.uint8)
                ann_frame = cv.imdecode(ann_np, cv.IMREAD_COLOR)
                if ann_frame is not None:
                    # We scored on warped input, so annotated is already warped in our usage.
                    ok_a, buf_a = cv.imencode('.jpg', ann_frame)
                    if ok_a:
                        latest_display_jpeg = buf_a.tobytes()
                        attachment_bytes = latest_display_jpeg
                        attachment_filename = f"predicted_{int(last_update_time)}.jpg"
        except Exception as e:
            print("[send_email] annotated attachment build error:", e, flush=True)

        # Build shot list text
        shots_count = len(stored_shots) if stored_shots else len(score_data.get('scored_shots', []) or [])
        score_total = stored_total if stored_shots else float(score_data.get('total_score', 0) or 0)
        shots_lines = []
        if stored_shots:
            for s in stored_shots:
                try:
                    sid = int(s.get('id'))
                    sc = float(s.get('score'))
                    shots_lines.append(f"Shot {sid}: {sc:.1f}")
                except Exception:
                    continue

        # Build email
        msg = EmailMessage()
        msg['Subject'] = "Your Shooting Performance Summary"
        msg['From'] = SMTP_USER
        msg['To'] = current_user_email

        date_str = datetime.now().strftime('%B %d, %Y %H:%M')
        mode_label = 'Rifle' if shooting_mode == 'rifle' else 'Pistol'

        text_body = (
            f"Hi {current_user_name},\n\n"
            f"Here is your latest target result ({date_str}).\n\n"
            f"Mode: {mode_label}\n"
            f"Total Score: {score_total:.1f}\n"
            f"Shots Taken: {shots_count}\n"
        )
        if shots_lines:
            text_body += "\nShot Breakdown:\n" + "\n".join(shots_lines) + "\n"
        text_body += "\nThe predicted target image is attached.\n"

        msg.set_content(text_body)

        # Attach predicted frame
        msg.add_attachment(attachment_bytes, maintype='image', subtype='jpeg', filename=attachment_filename)

        # Send mail
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        return jsonify({'success': True, 'sent_to': current_user_email, 'shots': shots_count, 'total': score_total})

    except Exception as e:
        print("Email send error:", e, flush=True)
        return jsonify({'error': 'Email send failed'}), 500

@app.route('/logout')
def logout():
    session.pop('user', None)
    # Best-effort cleanup of server-side ledger.
    try:
        user_key = session.get('username')
        if isinstance(user_key, str) and user_key:
            with _shot_ledgers_lock:
                _shot_ledgers.pop(user_key, None)
    except Exception:
        pass
    return redirect(url_for('login'))


@app.route('/api/shots', methods=['GET'])
def api_shots():
    user_key = _ledger_user_key()
    if not user_key:
        return jsonify({'error': 'unauthorized'}), 401

    ledger = _get_or_create_ledger(user_key)
    shots = ledger.get('shots', [])
    total = float(round(sum(float(s.get('score', 0.0)) for s in shots), 1))
    return jsonify({
        'target_seq': ledger.get('target_seq', 1),
        'stored_shots': shots,
        'stored_total_score': total,
    })

@app.before_request
def require_login():
    # allow public endpoints
    allowed_prefixes = ['/login', '/register', '/static', '/favicon.ico']
    # allow all API endpoints (you can restrict specific ones if needed)
    if request.path.startswith('/api/') or any(request.path.startswith(p) for p in allowed_prefixes):
        return None

    if 'user' not in session:
        return redirect(url_for('login'))


@app.route("/api/set_brightness")
def set_brightness():
    try:
        value = request.args.get("value", type=int)
        if value is None:
            return jsonify({"error": "No brightness value provided"}), 400

        if not selected_ip:
            return jsonify({"error": "No device selected"}), 400

        # Send request to the Raspberry Pi endpoint
        target_url = f"http://{selected_ip}:8000/api/brightness?value={value}"
        requests.get(target_url, timeout=2)

        print(f"[INFO] Brightness set to {value} on {selected_ip}", flush=True)
        return jsonify({"status": "success", "brightness": value}), 200
    except Exception as e:
        print(f"[ERROR] Brightness control failed: {e}", flush=True)
        return jsonify({"error": str(e)}), 500



# ------------------- start Flask (background) and PyWebview -------------------
def suppress_flask_logs():
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.logger.setLevel(logging.ERROR)

def start_flask_thread():
    suppress_flask_logs()
    socketio.run(app, debug=False, port=5000, host="0.0.0.0")

# Only start the starter thread once
def ensure_starter_thread_running():
    global starter_thread_obj
    # Start the background thread to capture frames from device
    if starter_thread_obj is None or not starter_thread_obj.is_alive():
        starter_thread_obj = threading.Thread(target=starter_thread, daemon=True)
        starter_thread_obj.start()
        print("[app] starter thread started", flush=True)

# Standard pattern: start Flask in a background thread and create webview window in main thread
if __name__ == "__main__":
    # Start Flask in a background thread
    flask_thread = threading.Thread(target=start_flask_thread, daemon=True)
    flask_thread.start()

    # Launch PyWebview (import locally to avoid packaging issues if unused)
    try:
        import webview
        webview.create_window('Lakshya', 'http://127.0.0.1:5000/login', width=1000, height=800)
        webview.start()
    except Exception as e:
        print("PyWebview error:", e, flush=True)
        print("If running headless, open a browser to http://127.0.0.1:5000/login", flush=True)
