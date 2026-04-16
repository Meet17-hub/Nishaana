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
from typing import Any, cast, Dict
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
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# CORS support for Next.js frontend
try:
    from flask_cors import CORS
    _have_cors = True
except ImportError:
    _have_cors = False
    print("[app] flask-cors not installed. Run: pip install flask-cors", flush=True)

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

    def get_scores_from_bytes(image_bytes: bytes, shooting_mode: str = 'pistol') -> dict[str, Any]:
        return cast(dict[str, Any], _mp_score_bytes(image_bytes, shooting_mode))

    def get_scores_from_hardcoded_image(shooting_mode: str = 'pistol') -> dict[str, Any]:
        return cast(dict[str, Any], _mp_score_file(shooting_mode))
except Exception:
    _have_model_prediction = False

    def get_scores_from_bytes(image_bytes: bytes, shooting_mode: str = 'pistol') -> dict[str, Any]:
        # fallback stub (no detection)
        return {"status": "no_model", "scored_shots": [], "bullets": []}

    def get_scores_from_hardcoded_image(shooting_mode: str = 'pistol') -> dict[str, Any]:
        return {"status": "no_model", "scored_shots": [], "bullets": []}


# Preprocessing (undistort + wrap to 640x640) extracted from wrap_test.py values.
try:
    from frame_preprocess import preprocess_frame
except Exception as e:
    preprocess_frame = None
    print("[app] Warning: frame_preprocess import failed; falling back to legacy warp:", e, flush=True)

try:
    from frame_differencing import get_frame_differencer, reset_frame_differencer
    _have_frame_differencing = True
    print("[app] Frame differencing module imported successfully", flush=True)
except Exception as e:
    _have_frame_differencing = False

    def get_frame_differencer(user_key: str):
        raise RuntimeError("Frame differencing is unavailable")

    def reset_frame_differencer(user_key: str):
        return None

    print("[app] Warning: frame_differencing import failed:", e, flush=True)


# ------------------- Utilities for PyInstaller paths -------------------
# Get the script directory first (for both dev and PyInstaller modes)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Load device IPs from shared JSON config
DEVICE_IPS_JSON_PATH = os.path.join(SCRIPT_DIR, "..", "config", "device-ips.json")

def load_device_ips_from_json() -> dict[str, str]:
    """Load device IPs from shared JSON config file."""
    try:
        if os.path.exists(DEVICE_IPS_JSON_PATH):
            with open(DEVICE_IPS_JSON_PATH, 'r') as f:
                config = json.load(f)
                return config.get("devices", {})
        else:
            print(f"[app] Warning: device-ips.json not found at {DEVICE_IPS_JSON_PATH}", flush=True)
    except Exception as e:
        print(f"[app] Warning: Failed to load device-ips.json: {e}", flush=True)
    # Fallback to default
    return {}

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

# Enable CORS for Next.js frontend (localhost:3000)
if _have_cors:
    CORS(app, 
         supports_credentials=True, 
         origins=["http://localhost:3000", "http://127.0.0.1:3000"],
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    print("✅ CORS enabled for Next.js frontend", flush=True)

socketio = SocketIO(app, cors_allowed_origins="*")
print("🚀 APP STARTED: Flask + Socket.IO initialized (API-only mode for Next.js)", flush=True)

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

# Database path: use root database (shared between rifle and pistol)
DB_PATH = os.path.join(SCRIPT_DIR, "..", "users.db")
LEGACY_USERS_FILE = os.path.join(SCRIPT_DIR, "..", "users.json")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

SUBSCRIPTION_WINDOWS = {
    "trial": timedelta(days=1),
    "monthly": timedelta(days=1),
    "half_yearly": timedelta(days=180),
    "yearly": timedelta(days=365),
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _normalize_username(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""

def _normalize_email(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""

def _serialize_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None

    return {
        "id": row["id"],
        "username": row["name"],
        "email": row["email"],
        "subscription_start": row["subscription_start"],
        "subscription_end": row["subscription_end"],
        "subscription_id": row["subscription_id"],
        "plan_type": row["plan_type"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }

def _ensure_user_schema(conn: sqlite3.Connection):
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    migrations = {
        "subscription_start": "TEXT",
        "subscription_end": "TEXT",
        "subscription_id": "TEXT",
        "plan_type": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }

    for column_name, column_type in migrations.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")

    conn.execute(
        """
        UPDATE users
        SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
            updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)
        """
    )

    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_name_nocase ON users(name COLLATE NOCASE)")
    except sqlite3.IntegrityError as exc:
        print(f"[app] Could not create username index: {exc}", flush=True)

    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_nocase ON users(email COLLATE NOCASE)")
    except sqlite3.IntegrityError as exc:
        print(f"[app] Could not create email index: {exc}", flush=True)

    conn.commit()

def init_db():
    with get_db_connection() as conn:
        conn.execute(
            '''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    subscription_start TEXT,
                    subscription_end TEXT,
                    subscription_id TEXT,
                    plan_type TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )'''
        )
        _ensure_user_schema(conn)
    print(f"[app] Database initialized at: {DB_PATH}", flush=True)

def migrate_legacy_users_to_db():
    if not os.path.exists(LEGACY_USERS_FILE):
        return

    try:
        with open(LEGACY_USERS_FILE, "r", encoding="utf-8") as f:
            legacy_users = json.load(f)
    except Exception as exc:
        print(f"[app] Failed to read legacy users file: {exc}", flush=True)
        return

    if not isinstance(legacy_users, dict):
        return

    migrated_count = 0
    with get_db_connection() as conn:
        for raw_username, payload in legacy_users.items():
            if not isinstance(payload, dict):
                continue

            username = _normalize_username(raw_username)
            email = _normalize_email(payload.get("email"))
            password_hash = payload.get("password")
            if not username or not email or not isinstance(password_hash, str) or not password_hash:
                continue

            existing = conn.execute(
                "SELECT 1 FROM users WHERE lower(name) = lower(?) OR lower(email) = lower(?)",
                (username, email),
            ).fetchone()
            if existing:
                continue

            conn.execute(
                """
                INSERT INTO users (name, email, password, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (username, email, password_hash),
            )
            migrated_count += 1

        conn.commit()

    if migrated_count:
        print(f"[app] Migrated {migrated_count} legacy users into SQLite", flush=True)

def _get_user_by_username(username: str) -> sqlite3.Row | None:
    normalized = _normalize_username(username)
    if not normalized:
        return None

    with get_db_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE lower(name) = lower(?)",
            (normalized,),
        ).fetchone()

def _get_current_user_row() -> sqlite3.Row | None:
    username = session.get("user") or session.get("username")
    if not isinstance(username, str) or not username:
        return None
    return _get_user_by_username(username)

def _set_logged_in_user(user_row: sqlite3.Row):
    canonical_username = user_row["name"]
    session["user"] = canonical_username
    session["username"] = canonical_username
    session["email"] = user_row["email"]
    session["logged_in"] = True

def _clear_logged_in_user():
    session.pop("user", None)
    session.pop("username", None)
    session.pop("email", None)
    session.pop("logged_in", None)

def _cleanup_user_runtime_state(username: str):
    if not isinstance(username, str) or not username:
        return

    try:
        _shot_ledgers.pop(username, None)
    except Exception:
        pass

    if _have_frame_differencing:
        try:
            reset_frame_differencer(username)
        except Exception:
            pass

    _fd_frame_skip_counter.pop(username, None)

def _move_user_runtime_state(old_username: str, new_username: str):
    if old_username == new_username:
        return

    if old_username in _shot_ledgers:
        _shot_ledgers[new_username] = _shot_ledgers.pop(old_username)

    if old_username in _fd_frame_skip_counter:
        _fd_frame_skip_counter[new_username] = _fd_frame_skip_counter.pop(old_username)

    if _have_frame_differencing:
        try:
            reset_frame_differencer(old_username)
            _ = get_frame_differencer(new_username)
        except Exception:
            pass

init_db()  # create table if it doesn't exist
migrate_legacy_users_to_db()
shooting_mode = 'pistol'   # default: 'rifle' or 'pistol'
DEMO_MODE = False  # Set to True for demo mode without hardware

# Frame Differencing global controls
USE_FRAME_DIFFERENCING = True  # Enable/disable frame differencing detection
HYBRID_MODE = True  # Use both frame differencing AND ML model for validation
FD_INIT_FRAMES_SKIP = 1  # Skip N frames before initializing reference (let camera settle)
_fd_frame_skip_counter = {}  # Per-user frame skip counter

# Global state
# Load device IPs from JSON config (with fallback to hardcoded values)
_loaded_device_ips = load_device_ips_from_json()
device_ips = _loaded_device_ips if _loaded_device_ips else {
    '0': "10.0.0.32",
    '1': "192.168.1.1",
    '2': "192.168.1.2",
    '3': "192.168.1.3",
    '4': "192.168.1.4",
    '5': "192.168.1.5",
    '6': "192.168.1.6",
    '7': "192.168.1.7",
    '8': "192.168.1.30",
    '9': "172.20.109.94",
    '10': "10.0.0.40"
}
print(f"[app] Loaded {len(device_ips)} device IPs from config", flush=True)
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

# Pi socket with stable connection settings
pi_socket = sio_client.Client(
    reconnection=True, 
    reconnection_attempts=0,  # infinite
    reconnection_delay=1,
    reconnection_delay_max=5,
    logger=False, 
    engineio_logger=False,
    request_timeout=60
)

@pi_socket.on("motor_vibration")
def on_pi_vibration(data):
    print("=" * 50, flush=True)
    print("🎯 SHOT EVENT RECEIVED FROM PI:", data, flush=True)
    print("=" * 50, flush=True)

    def auto_update():
        time.sleep(0.3)  # 🔑 let camera & target settle
        print("📡 Emitting shot_ui_signal to browser...", flush=True)
        socketio.emit("shot_ui_signal", {
            "event": "shot",
            "ts": time.time()
        })
        print("✅ shot_ui_signal emitted!", flush=True)

    threading.Thread(target=auto_update, daemon=True).start()

# Also listen for test_event heartbeat from Pi
@pi_socket.on("test_event")
def on_pi_test_event(data):
    print(f"💓 PI heartbeat received: {data}", flush=True)


@pi_socket.on("target_ack")
def on_target_ack(data):
    print("🎯 TARGET READY FROM PI:", data, flush=True)

    # OPTIONAL: auto update score
    socketio.emit("target_ready_ui", data)

# ------------------- Pi Socket.IO client -------------------

# ------------------- Shot ledger (server-side) -------------------
# Stores stable shot history per logged-in user.
SHOT_MATCH_PX = 8  # match threshold on warped image pixel coords
CENTER_EMA_ALPHA = 0.3
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
            ledger = {
                "target_seq": 1,
                "current_series": 1,
                "shots_per_series": 10,   # 🔥 change if needed
                "smoothed_center_x": None,
                "smoothed_center_y": None,
                "series": {
                    1: []
                }
            }
            _shot_ledgers[user_key] = ledger
        return ledger


def _reset_ledger(user_key: str) -> dict[str, Any]:
    with _shot_ledgers_lock:
        ledger = {
            "target_seq": 1,
            "current_series": 1,
            "shots_per_series": 10,
            "smoothed_center_x": None,
            "smoothed_center_y": None,
            "series": {
                1: []
            }
        }
        _shot_ledgers[user_key] = ledger
        return ledger


def _smooth_target_center(ledger: dict[str, Any], center: Any) -> dict[str, float] | None:
    """EMA smooth center to reduce frame-to-frame target center jitter."""
    if not isinstance(center, dict):
        return None

    try:
        new_cx = float(center.get("x"))
        new_cy = float(center.get("y"))
    except Exception:
        return None

    old_cx = ledger.get("smoothed_center_x")
    old_cy = ledger.get("smoothed_center_y")

    if old_cx is None or old_cy is None:
        smoothed_cx = new_cx
        smoothed_cy = new_cy
    else:
        smoothed_cx = (1.0 - CENTER_EMA_ALPHA) * float(old_cx) + CENTER_EMA_ALPHA * new_cx
        smoothed_cy = (1.0 - CENTER_EMA_ALPHA) * float(old_cy) + CENTER_EMA_ALPHA * new_cy

    ledger["smoothed_center_x"] = smoothed_cx
    ledger["smoothed_center_y"] = smoothed_cy
    return {"x": smoothed_cx, "y": smoothed_cy}


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

#def_merge_detected_shots(user_key: str, detected: list[dict[str, Any]]) -> dict[str, Any]:
def _merge_detected_shots(user_key: str,detected: list[dict[str, Any]],force_new_shot: bool = False) -> dict[str, Any]:
    """Merge detected shots with overlap-aware hole growth logic."""

    non_overlapping, overlapping_shots = _detect_overlapping_shots(
        detected, overlap_threshold_px=3.0
    )

    ledger = _get_or_create_ledger(user_key)
    current_series = ledger.get("current_series", 1)
    series_dict = ledger.setdefault("series", {1: []})
    shots = series_dict.setdefault(current_series, [])

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

             existing["updated_ts"] = time.time()

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
    "created_ts": time.time(),   # ✅ NEW
    "updated_ts": time.time(), 
})

    # 🔥 Auto advance series
    shots_per_series = ledger.get("shots_per_series", 10)

    if len(shots) >= shots_per_series:
      ledger["current_series"] += 1
      next_series = ledger["current_series"]
      series_dict.setdefault(next_series, [])

      ledger["overlapping_shots"] = overlapping_shots

    return ledger


def _detect_shots_hybrid(
    user_key: str,
    frame_bgr: np.ndarray,
    frame_bytes: bytes,
    shooting_mode: str = 'rifle',
) -> Dict[str, Any]:
    """
    Hybrid shot detection: Combine frame differencing with optional ML model validation.
    
    Process:
    1. Frame differencing (texture-based): Fast, robust to lighting
    2. Optional ML model: Validates detections, adds scoring confidence
    
    Args:
        user_key: User identifier for frame differencing state
        frame_bgr: BGR frame from camera
        frame_bytes: JPEG bytes for ML model (optional)
        shooting_mode: 'rifle' or 'pistol'
    
    Returns:
        Dictionary with combined detection results:
        {
            'scored_shots': [...],  # Primary detections
            'ml_shots': [...],       # ML model detections (if HYBRID_MODE)
            'fd_shots': [...],       # Frame differencing detections
            'method': 'fd|hybrid|ml',  # Which method was primary
            'confidence': 0-1,
            'status': 'ok|...',
        }
    """
    
    if not _have_frame_differencing:
        # Fallback to ML model only
        print("[_detect_shots_hybrid] Frame differencing not available, using ML model only", flush=True)
        ml_result = get_scores_from_bytes(frame_bytes, shooting_mode)
        ml_result['method'] = 'ml'
        ml_result['fd_shots'] = []
        return ml_result
    
    try:
        # Get or create frame differencer for this user
        fd = get_frame_differencer(user_key)
        
        # Skip frames for initialization (wait for camera to settle)
        if user_key not in _fd_frame_skip_counter:
            _fd_frame_skip_counter[user_key] = 0
        
        skip_count = _fd_frame_skip_counter[user_key]
        if skip_count < FD_INIT_FRAMES_SKIP:
            _fd_frame_skip_counter[user_key] += 1
            print(f"[_detect_shots_hybrid] Skipping frame {skip_count + 1}/{FD_INIT_FRAMES_SKIP} for user {user_key}", flush=True)
            
            # On first frame, just initialize reference
            fd.detect_holes(frame_bgr, auto_init=True)
            # Still run ML once so the first visible shot after reset/target change
            # is not dropped while frame differencing warms up its reference frame.
            ml_result = get_scores_from_bytes(frame_bytes, shooting_mode)
            ml_result['method'] = 'ml_init'
            ml_result['fd_shots'] = []
            ml_result['status'] = 'initializing'
            ml_result['confidence'] = ml_result.get('confidence', 0.0)
            return ml_result
        
        # Perform frame differencing detection
        fd_result = fd.detect_holes(frame_bgr, auto_init=False)
        fd_detections = fd_result.get('detected', [])
        
        if not USE_FRAME_DIFFERENCING:
            # Use ML model only (frame differencing disabled)
            ml_result = get_scores_from_bytes(frame_bytes, shooting_mode)
            ml_result['method'] = 'ml'
            ml_result['fd_shots'] = []
            return ml_result
        
        # Frame differencing is primary
        if not HYBRID_MODE:
            # Use ONLY frame differencing
            print(f"[_detect_shots_hybrid] FD-only mode: {len(fd_detections)} detections", flush=True)
            
            # Adaptive update: slowly incorporate new frame into reference
            try:
                fd.update_reference_adaptive(frame_bgr)
            except Exception as e:
                print(f"[_detect_shots_hybrid] Adaptive update error: {e}", flush=True)
            
            return {
                'scored_shots': fd_detections,
                'method': 'fd',
                'fd_shots': fd_detections,
                'ml_shots': [],
                'status': 'ok' if fd_detections else 'no_detections',
                'confidence': fd_result.get('confidence', 0.0),
                'frame_count': fd_result.get('frame_count', 0),
            }
        
        # HYBRID_MODE: Use frame differencing + ML validation
        print(f"[_detect_shots_hybrid] Hybrid mode: {len(fd_detections)} FD detections", flush=True)
        
        # Get ML predictions
        ml_result = get_scores_from_bytes(frame_bytes, shooting_mode)
        ml_detections = ml_result.get('scored_shots', [])
        print(f"[_detect_shots_hybrid] ML model found {len(ml_detections)} detections", flush=True)
        
        # Merge strategy: prioritize high-confidence FD detections, validate with ML
        merged_detections = []
        matched_ml_indices = set()
        
        for fd_shot in fd_detections:
            fd_x = fd_shot.get('x')
            fd_y = fd_shot.get('y')
            fd_r = fd_shot.get('r', 6.0)
            
            # Find closest ML detection
            best_ml_idx = None
            best_distance = 20.0  # Match threshold (pixels)
            
            for ml_idx, ml_shot in enumerate(ml_detections):
                if ml_idx in matched_ml_indices:
                    continue
                
                ml_x = ml_shot.get('x', 0)
                ml_y = ml_shot.get('y', 0)
                distance = ((ml_x - fd_x) ** 2 + (ml_y - fd_y) ** 2) ** 0.5
                
                if distance < best_distance:
                    best_distance = distance
                    best_ml_idx = ml_idx
            
            # Create merged detection
            if best_ml_idx is not None:
                # Use ML score, FD position (usually more accurate for positioning)
                ml_shot = ml_detections[best_ml_idx]
                merged_detections.append({
                    'x': fd_x,  # FD position (more accurate)
                    'y': fd_y,
                    'r': fd_r,
                    'score': ml_shot.get('score', 0.5),  # ML score
                    'fd_confidence': fd_shot.get('score', 0.5),
                    'ml_confidence': ml_shot.get('score', 0.5),
                    'source': 'hybrid_match',
                })
                matched_ml_indices.add(best_ml_idx)
            else:
                # Unmatched FD detection (texture but no ML match)
                merged_detections.append({
                    'x': fd_x,
                    'y': fd_y,
                    'r': fd_r,
                    'score': min(fd_shot.get('score', 0.5) * 0.8, 0.9),  # Reduce score if unmatched
                    'fd_confidence': fd_shot.get('score', 0.5),
                    'source': 'fd_only',
                })
        
        # Add unmatched ML detections with reduced confidence
        for ml_idx, ml_shot in enumerate(ml_detections):
            if ml_idx not in matched_ml_indices:
                merged_detections.append({
                    'x': ml_shot.get('x', 0),
                    'y': ml_shot.get('y', 0),
                    'r': ml_shot.get('r', 6.0),
                    'score': min(ml_shot.get('score', 0.5) * 0.6, 0.85),  # Lower score if texture doesn't match
                    'ml_confidence': ml_shot.get('score', 0.5),
                    'source': 'ml_only',
                })
        
        print(f"[_detect_shots_hybrid] Merged to {len(merged_detections)} detections", flush=True)
        
        # Adaptive update: slowly incorporate new frame into reference
        try:
            fd.update_reference_adaptive(frame_bgr)
        except Exception as e:
            print(f"[_detect_shots_hybrid] Adaptive update error: {e}", flush=True)
        
        return {
            'scored_shots': merged_detections,
            'method': 'hybrid',
            'fd_shots': fd_detections,
            'ml_shots': ml_detections,
            'status': 'ok' if merged_detections else 'no_detections',
            'confidence': fd_result.get('confidence', 0.0),
            'frame_count': fd_result.get('frame_count', 0),
        }
    
    except Exception as e:
        print(f"[_detect_shots_hybrid] Error: {e}", flush=True)
        # Fallback to ML model on error
        ml_result = get_scores_from_bytes(frame_bytes, shooting_mode)
        ml_result['method'] = 'ml_fallback'
        ml_result['error'] = str(e)
        return ml_result


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
                        #[1044.54, 938.15],
                        #[1063.88, 1392.72],
                        #[1568.0, 1402.39],
                        #[1568.0, 918.81],
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
            [1044.54, 938.15],
            [1063.88, 1392.72],
            [1568.0, 1402.39],
            [1568.0, 918.81],
            #[1024, 565],
            #[1067.0, 1077.0],
            #[1568.0, 1056.0],
            #[1568.0, 544.0],
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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        payload = request.get_json(silent=True) if request.is_json else request.form
        username = _normalize_username(payload.get('username'))
        email = _normalize_email(payload.get('email'))
        password = payload.get('password') or ""

        if not username or not email or not password:
            return jsonify({'success': False, 'error': 'All fields are required'}), 400

        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

        with get_db_connection() as conn:
            username_conflict = conn.execute(
                "SELECT 1 FROM users WHERE lower(name) = lower(?)",
                (username,),
            ).fetchone()
            if username_conflict:
                return jsonify({'success': False, 'error': 'Username already exists'}), 400

            email_conflict = conn.execute(
                "SELECT 1 FROM users WHERE lower(email) = lower(?)",
                (email,),
            ).fetchone()
            if email_conflict:
                return jsonify({'success': False, 'error': 'Email already registered'}), 400

            conn.execute(
                """
                INSERT INTO users (name, email, password, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (username, email, generate_password_hash(password)),
            )
            conn.commit()

        user = _get_user_by_username(username)
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'user': _serialize_user(user),
        }), 201

    return jsonify({'message': 'Use POST to register', 'fields': ['username', 'email', 'password']})



@app.route('/login', methods=['GET', 'POST'])
def login():
    global selected_ip
    try:
        if request.method == 'POST':
            payload = request.get_json(silent=True) if request.is_json else request.form
            name = _normalize_username(payload.get('username'))
            password = payload.get('password')
            device_id = str(payload.get('device_id') or "").strip()
            custom_ip = str(payload.get('custom_ip') or payload.get('ip') or "").strip()

            print(f"[app] Login attempt: username={name}, device_id={device_id}", flush=True)

            if not name or not password or not device_id:
                return jsonify({'success': False, 'error': 'All fields are required'}), 400

            user = _get_user_by_username(name)
            
            if user is None:
                print(f"[app] User '{name}' not found in SQLite", flush=True)
                return jsonify({'success': False, 'error': 'Invalid username or password'}), 401
            
            password_match = check_password_hash(user["password"], password)
            print(f"[app] Password check for '{user['name']}': {password_match}", flush=True)
            
            if not password_match:
                return jsonify({'success': False, 'error': 'Invalid username or password'}), 401

            if custom_ip:
                selected_ip = custom_ip
            elif device_id in device_ips:
                selected_ip = device_ips[device_id]
            else:
                selected_ip = f"192.168.1.{device_id}"
            
            connect_pi_socket(selected_ip)

            _set_logged_in_user(user)

            print(f"[app] Logged in as {user['name']}, selected_ip = {selected_ip}", flush=True)
            
            # Start the background thread to capture frames from device
            ensure_starter_thread_running()
            
            # Initialize frame differencer for this user (for bullet hole detection)
            if _have_frame_differencing:
                _ = get_frame_differencer(user['name'])
                print(f"[app] ✅ Frame differencer initialized for user: {user['name']}", flush=True)
            
            # Return JSON for Next.js frontend
            return jsonify({
                'success': True, 
                'message': 'Login successful',
                'username': user['name'],
                'email': user['email'],
                'selected_ip': selected_ip,
                'user': _serialize_user(user),
            }), 200

        return jsonify({'message': 'Use POST to login', 'fields': ['username', 'password', 'device_id', 'custom_ip']})

    except Exception as e:
        print("Login error:", e, flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/me', methods=['GET'])
def get_current_user():
    user = _get_current_user_row()
    if user is None:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    return jsonify({'success': True, 'user': _serialize_user(user)}), 200

@app.route('/api/me', methods=['PUT'])
def update_current_user():
    current_user = _get_current_user_row()
    if current_user is None:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    payload = request.get_json(silent=True) or {}
    next_username = _normalize_username(payload.get('username') or current_user['name'])
    next_email = _normalize_email(payload.get('email') or current_user['email'])

    if not next_username or not next_email:
        return jsonify({'success': False, 'error': 'Username and email are required'}), 400

    with get_db_connection() as conn:
        username_conflict = conn.execute(
            "SELECT 1 FROM users WHERE lower(name) = lower(?) AND id != ?",
            (next_username, current_user['id']),
        ).fetchone()
        if username_conflict:
            return jsonify({'success': False, 'error': 'Username already exists'}), 400

        email_conflict = conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = lower(?) AND id != ?",
            (next_email, current_user['id']),
        ).fetchone()
        if email_conflict:
            return jsonify({'success': False, 'error': 'Email already registered'}), 400

        conn.execute(
            """
            UPDATE users
            SET name = ?, email = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (next_username, next_email, current_user['id']),
        )
        conn.commit()

    updated_user = _get_user_by_username(next_username)
    if updated_user is None:
        return jsonify({'success': False, 'error': 'Unable to load updated user'}), 500

    _set_logged_in_user(updated_user)
    _move_user_runtime_state(current_user['name'], updated_user['name'])
    return jsonify({'success': True, 'user': _serialize_user(updated_user)}), 200

@app.route('/api/me/password', methods=['POST'])
def change_current_user_password():
    current_user = _get_current_user_row()
    if current_user is None:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    payload = request.get_json(silent=True) or {}
    current_password = payload.get('current_password') or ""
    new_password = payload.get('new_password') or ""

    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'Current password and new password are required'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

    if not check_password_hash(current_user['password'], current_password):
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400

    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET password = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (generate_password_hash(new_password), current_user['id']),
        )
        conn.commit()

    return jsonify({'success': True, 'message': 'Password updated successfully'}), 200

@app.route('/api/me/subscription', methods=['POST'])
def activate_current_user_subscription():
    current_user = _get_current_user_row()
    if current_user is None:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    payload = request.get_json(silent=True) or {}
    plan_code = str(payload.get('plan_code') or "").strip()
    if plan_code not in SUBSCRIPTION_WINDOWS:
        return jsonify({'success': False, 'error': 'Invalid plan code'}), 400

    now = datetime.utcnow()
    expires_at = now + SUBSCRIPTION_WINDOWS[plan_code]
    subscription_id = f"{plan_code}_{current_user['name']}_{int(now.timestamp() * 1000)}"
    start_iso = f"{now.isoformat()}Z"
    end_iso = f"{expires_at.isoformat()}Z"

    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET subscription_start = ?, subscription_end = ?, subscription_id = ?, plan_type = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (start_iso, end_iso, subscription_id, plan_code, current_user['id']),
        )
        conn.commit()

    updated_user = _get_user_by_username(current_user['name'])
    if updated_user is None:
        return jsonify({'success': False, 'error': 'Unable to load updated user'}), 500

    _set_logged_in_user(updated_user)
    return jsonify({'success': True, 'user': _serialize_user(updated_user)}), 200

@app.route('/api/me', methods=['DELETE'])
def delete_current_user():
    current_user = _get_current_user_row()
    if current_user is None:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    username = current_user['name']
    with get_db_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (current_user['id'],))
        conn.commit()

    _clear_logged_in_user()
    _cleanup_user_runtime_state(username)
    return jsonify({'success': True, 'message': 'Account deleted successfully'}), 200


# Pi socket connection events
@pi_socket.on("connect")
def on_pi_socket_connect():
    print("🔌 ✅ PI Socket.IO CONNECTED!", flush=True)

@pi_socket.on("disconnect")
def on_pi_socket_disconnect():
    print("❌ PI Socket.IO DISCONNECTED", flush=True)

@pi_socket.on("connect_error")
def on_pi_socket_error(data):
    print(f"❌ PI Socket.IO connection error: {data}", flush=True)

_pi_target_ip = None  # Track target IP for reconnection
    
def connect_pi_socket(ip):
    global pi_socket, _pi_target_ip
    _pi_target_ip = ip
    
    def do_connect():
        global pi_socket
        try:
            # Skip if already connected to same IP
            if pi_socket.connected:
                print(f"ℹ️ Already connected to PI Socket.IO", flush=True)
                return
            
            print(f"🔌 Connecting to PI Socket.IO at {ip}:8000...", flush=True)
            pi_socket.connect(
                f"http://{ip}:8000",
                transports=["websocket"],
                wait=True,
                wait_timeout=15
            )
            print(f"🔌 ✅ Connected to PI Socket.IO at {ip}: {pi_socket.connected}", flush=True)
        except sio_client.exceptions.ConnectionError as e:
            if "Already connected" in str(e):
                print(f"ℹ️ PI Socket already connected", flush=True)
            else:
                print(f"❌ PI Socket.IO connection failed: {e}", flush=True)
        except Exception as e:
            print(f"❌ PI Socket.IO connection failed: {e}", flush=True)
    
    # Run in background thread to avoid blocking
    threading.Thread(target=do_connect, daemon=True).start()


@app.route('/')
def index():
    """API mode: Return status info. Next.js frontend handles the UI."""
    try:
        logged_in = session.get('logged_in', False)
        return jsonify({
            'status': 'ok',
            'logged_in': logged_in,
            'username': session.get('username') if logged_in else None,
            'selected_ip': selected_ip if logged_in else None,
            'message': 'Lakshya API Backend - Use Next.js frontend at http://localhost:3000'
        })
    except Exception as e:
        print("Index error:", e, flush=True)
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/selected_ip', methods=['GET'])
def api_selected_ip():
    global selected_ip
    if selected_ip:
        return jsonify({'selected_ip': selected_ip}), 200
    return jsonify({'error': 'No IP selected'}), 404

@app.route('/api/select_ip', methods=['GET', 'POST', 'OPTIONS'])
def api_select_ip():
    """Set the selected device IP for API commands. Called from Next.js after login."""
    global selected_ip
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        # Support both GET (query params) and POST (JSON body)
        if request.method == 'GET':
            device_id = request.args.get('device_id')
        else:
            data = request.get_json(silent=True) or {}
            device_id = data.get('device_id') or request.form.get('device_id') or request.args.get('device_id')
        
        if not device_id:
            return jsonify({'success': False, 'error': 'device_id is required'}), 400
        
        # Look up IP from device_ips mapping
        if device_id in device_ips:
            selected_ip = device_ips[device_id]
        else:
            # Fallback to direct IP format
            selected_ip = f"192.168.1.{device_id}"
        
        # Connect to the Raspberry Pi socket
        connect_pi_socket(selected_ip)
        
        # Start the background thread to capture frames from device
        ensure_starter_thread_running()
        
        print(f"[app] ✅ Device selected: device_id={device_id}, selected_ip={selected_ip}", flush=True)
        
        return jsonify({
            'success': True,
            'device_id': device_id,
            'selected_ip': selected_ip,
            'message': f'Device {device_id} selected successfully'
        }), 200
        
    except Exception as e:
        print(f"[app] Error selecting device: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/select_ip_direct', methods=['POST', 'OPTIONS'])
def api_select_ip_direct():
    """Set the selected device IP directly (for custom IPs)."""
    global selected_ip
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        data = request.get_json(silent=True) or {}
        ip = data.get('ip')
        
        if not ip:
            return jsonify({'success': False, 'error': 'ip is required'}), 400
        
        # Validate IP format (basic check)
        parts = ip.split('.')
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            return jsonify({'success': False, 'error': 'Invalid IP address format'}), 400
        
        selected_ip = ip
        
        # Connect to the Raspberry Pi socket
        connect_pi_socket(selected_ip)
        
        # Start the background thread to capture frames from device
        ensure_starter_thread_running()
        
        print(f"[app] ✅ Custom IP selected: selected_ip={selected_ip}", flush=True)
        
        return jsonify({
            'success': True,
            'device_id': 'custom',
            'selected_ip': selected_ip,
            'message': f'Custom IP {selected_ip} selected successfully'
        }), 200
        
    except Exception as e:
        print(f"[app] Error selecting custom IP: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices', methods=['GET'])
def api_devices():
    """Return the list of available devices and their IPs."""
    devices = [
        {'id': k, 'ip': v, 'label': f'Device {k} ({v})'}
        for k, v in device_ips.items()
    ]
    return jsonify({'devices': devices}), 200

@app.route('/api/pi_status', methods=['GET'])
def api_pi_status():
    """Check Pi socket connection status."""
    return jsonify({
        'connected': pi_socket.connected,
        'selected_ip': selected_ip
    }), 200

@app.route('/api/test_shot', methods=['POST'])
def api_test_shot():
    """Manually trigger shot_ui_signal for testing."""
    print("🧪 TEST: Manually emitting shot_ui_signal...", flush=True)
    socketio.emit("shot_ui_signal", {
        "event": "test_shot",
        "ts": time.time()
    })
    return jsonify({'success': True, 'message': 'shot_ui_signal emitted'}), 200

@app.route('/api/shot_detected', methods=['POST', 'OPTIONS'])
def api_shot_detected():
    """Called by Pi when a shot is detected (HTTP fallback for Socket.IO)."""
    if request.method == 'OPTIONS':
        return '', 200
    
    print("=" * 50, flush=True)
    print("🎯 SHOT DETECTED via HTTP from Pi!", flush=True)
    print("=" * 50, flush=True)
    
    socketio.emit("shot_ui_signal", {
        "event": "shot",
        "ts": time.time()
    })
    print("✅ shot_ui_signal emitted to browser!", flush=True)
    
    return jsonify({'success': True, 'message': 'Shot signal sent to UI'}), 200

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



@app.route('/latest_image', methods=['GET', 'OPTIONS'])
def latest_image_jpeg():
    """Serve the cached latest warped image as JPEG."""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = Response('', status=200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        return response
    
    try:
        if latest_display_jpeg:
            response = Response(latest_display_jpeg, mimetype='image/jpeg')
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        if latest_image:
            response = Response(latest_image, mimetype='image/jpeg')
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        if os.path.exists(LATEST_WARPED_PATH):
            with open(LATEST_WARPED_PATH, 'rb') as fh:
                data = fh.read()
            response = Response(data, mimetype='image/jpeg')
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
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

        print(f"[api_live_score] selected_ip = {selected_ip}", flush=True)

        # On-demand: only trigger capture when this endpoint is hit.
        if selected_ip:
            session = requests.Session()
            trigger_capture(selected_ip, session)
            fresh = fetch_frame_direct(selected_ip, session)
            print(f"[api_live_score] fetch_frame_direct returned {len(fresh) if fresh else 'None'} bytes", flush=True)
            if fresh:
                npbuf = np.frombuffer(fresh, np.uint8)
                frame = cv.imdecode(npbuf, cv.IMREAD_COLOR)
                print(f"[api_live_score] decoded frame shape: {frame.shape if frame is not None else 'None'}", flush=True)
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
                          bytes_for_scoring = latest_image
                          scored_on_warped = True
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

        # 🔥 HYBRID DETECTION: Frame Differencing + Optional ML
        user_key = _ledger_user_key()
        
        # For frame differencing, we need BGR frame. Reconstruct it if we have bytes.
        frame_for_fd = None
        if bytes_for_scoring:
            try:
                npbuf = np.frombuffer(bytes_for_scoring, np.uint8)
                frame_for_fd = cv.imdecode(npbuf, cv.IMREAD_COLOR)
            except Exception:
                pass
        
        if frame_for_fd is not None and user_key and _have_frame_differencing:
            # Use hybrid detection (frame differencing + ML)
            score_data = _detect_shots_hybrid(
                user_key,
                frame_for_fd,
                bytes_for_scoring,
                shooting_mode
            )
            print(f"[api_live_score] Hybrid detection used method: {score_data.get('method', 'unknown')}", flush=True)
        else:
            # Fallback to ML model only
            score_data = get_scores_from_bytes(bytes_for_scoring, shooting_mode)
        
        center = score_data.get("center")
        if center and user_key:
            center_ledger = _get_or_create_ledger(user_key)
            smoothed_center = _smooth_target_center(center_ledger, center)
            if smoothed_center is not None:
                center = smoothed_center
                score_data["center"] = smoothed_center
        if center:
           for s in score_data.get("scored_shots", []):
             s["center_x"] = center["x"]
             s["center_y"] = center["y"]
        latest_annotated_image = score_data.get("annotated_image")

        # Server-side stable shot storage (dedupe by coordinates; freeze first score)
        try:
            if user_key and isinstance(score_data, dict):
                detected = score_data.get('scored_shots')
                if isinstance(detected, list):
                    # Expose raw detections from the model before any server-side merge
                    score_data['pre_merge_detections'] = detected
                    ledger = _merge_detected_shots(user_key, detected)
                    series_dict = ledger.get('series', {}) if isinstance(ledger.get('series', {}), dict) else {}
                    flattened_shots = []
                    series_payload = {}
                    series_totals = {}

                    for series_num in sorted(series_dict.keys()):
                        series_key = f"Series {series_num}"
                        raw_series_shots = series_dict.get(series_num, [])
                        normalized_series_shots = []
                        for idx, shot in enumerate(raw_series_shots):
                            if not isinstance(shot, dict):
                                continue
                            shot_copy = dict(shot)
                            shot_copy.setdefault('id', idx + 1)
                            shot_copy['series'] = shot_copy.get('series') or series_key
                            normalized_series_shots.append(shot_copy)
                            flattened_shots.append(shot_copy)

                        series_payload[series_key] = normalized_series_shots
                        series_totals[series_key] = float(round(
                            sum(float(s.get('score', 0.0)) for s in normalized_series_shots), 1
                        ))

                    score_data['stored_shots'] = flattened_shots
                    score_data['stored_total_score'] = float(round(
                        sum(float(s.get('score', 0.0)) for s in flattened_shots), 1
                    ))
                    score_data['series'] = series_payload
                    score_data['series_totals'] = series_totals
                    score_data['current_series'] = ledger.get('current_series', 1)
                    score_data['grand_total'] = score_data['stored_total_score']
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
            
            # Also reset frame differencer reference so next frame initializes fresh
            if _have_frame_differencing:
                reset_frame_differencer(user_key)
                # Clear frame skip counter so next frame initializes immediately
                _fd_frame_skip_counter.pop(user_key, None)
                print(f"[api_reset] frame differencer reset for user: {user_key}", flush=True)
    except Exception as e:
        print(f"[api_reset] failed to clear ledger/frame differencer: {e}", flush=True)

    # do NOT stop starter thread — it will keep trying to run
    return "Reset Complete"


@app.route('/api/clear_shots', methods=['POST'])
def api_clear_shots():
    """Clear only the current user's stored shot/session state without blanking the live feed."""
    try:
        user_key = _ledger_user_key()
        if not user_key:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401

        _reset_ledger(user_key)
        if _have_frame_differencing:
            reset_frame_differencer(user_key)
            _fd_frame_skip_counter.pop(user_key, None)

        print(f"[api_clear_shots] cleared shot state for user: {user_key}", flush=True)
        return jsonify({'success': True, 'message': 'Shot state cleared'}), 200
    except Exception as e:
        print(f"[api_clear_shots] failed: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

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
    shooting_mode = 'rifle'

    # Best-effort passthrough to device; do not fail local mode switch if device is unavailable.
    if selected_ip:
        try:
            requests.get(f'http://{selected_ip}:8000/rifle', timeout=2)
        except Exception as e:
            print(f"[api_rifle] device passthrough failed: {e}", flush=True)

    return jsonify({"status": "ok", "mode": "rifle"})


@app.route('/api/pistol')
def api_pistol():
    global shooting_mode
    shooting_mode = 'pistol'

    # Best-effort passthrough to device; do not fail local mode switch if device is unavailable.
    if selected_ip:
        try:
            pc_ip = get_my_ip()
            try:
                requests.post(
                    f"http://{selected_ip}:8000/set_pc_ip",
                    json={"pc_ip": pc_ip},
                    timeout=2,
                )
            except Exception:
                pass
            requests.get(f"http://{selected_ip}:8000/pistol", timeout=2)
        except Exception as e:
            print(f"[api_pistol] device passthrough failed: {e}", flush=True)

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

        # Get request data
        req_data = request.get_json(silent=True) or {}
        req_email = req_data.get('email')  # Allow overriding recipient email
        image_data_b64 = req_data.get('imageData')  # Base64 image from client
        
        # Use provided email or fall back to session email
        recipient_email = req_email if req_email else current_user_email

        # SMTP config (Gmail): use env vars, do not hardcode secrets
        SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
        SMTP_USER = os.environ.get('SMTP_USER')
        SMTP_PASS = os.environ.get('SMTP_PASS')
        if not SMTP_USER or not SMTP_PASS:
            return jsonify({'error': 'SMTP not configured. Set SMTP_USER and SMTP_PASS (Gmail App Password).'}), 500

        # Determine if we have imageData or need to capture fresh frame
        attachment_bytes = None
        attachment_filename = None
        score_data = None
        stored_shots = []
        stored_total = 0.0
        
        if image_data_b64:
            # Use image provided by client
            try:
                attachment_bytes = base64.b64decode(image_data_b64)
                attachment_filename = f"wrapped_target_{int(time.time())}.jpg"
                # For wrap email with provided image, we don't rescore
                score_data = {}
            except Exception as e:
                print(f"[send_email] Failed to decode provided image: {e}", flush=True)
                return jsonify({'error': 'Invalid image data'}), 400
        else:
            # Original behavior: capture fresh frame from device
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
            user_key = _ledger_user_key()
            if user_key and isinstance(score_data, dict):
                detected = score_data.get('scored_shots')
                if isinstance(detected, list):
                    ledger = _merge_detected_shots(user_key, detected,force_new_shot=True)
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
        msg['To'] = recipient_email

        date_str = datetime.now().strftime('%B %d, %Y %H:%M')
        mode_label = 'Rifle' if shooting_mode == 'rifle' else 'Pistol'

        # Check if this is a wrap email with summary from request
        wrap_summary = req_data.get('summary')
        if wrap_summary:
            # Wrap email format from analytics
            text_body = (
                f"Hi {current_user_name},\n\n"
                f"{wrap_summary}\n\n"
                f"Date: {req_data.get('date', date_str)}\n"
            )
        else:
            # Original single-shot email format
            text_body = (
                f"Hi {current_user_name},\n\n"
                f"Here is your latest target result ({date_str}).\n\n"
                f"Mode: {mode_label}\n"
                f"Total Score: {score_total:.1f}\n"
                f"Shots Taken: {shots_count}\n"
            )
            if shots_lines:
                text_body += "\nShot Breakdown:\n" + "\n".join(shots_lines) + "\n"
        
        text_body += "\nThe target image is attached.\n"

        msg.set_content(text_body)

        # Attach predicted frame
        if attachment_bytes:
            msg.add_attachment(attachment_bytes, maintype='image', subtype='jpeg', filename=attachment_filename)

        # Send mail

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        return jsonify({'success': True, 'sent_to': recipient_email, 'shots': shots_count, 'total': score_total})

    except Exception as e:
        print("Email send error:", e, flush=True)
        return jsonify({'error': 'Email send failed'}), 500

@app.route('/logout')
def logout():
    """API mode: Clear session and return JSON response."""
    username = session.get('username')
    session.pop('user', None)
    session.pop('username', None)
    session.pop('email', None)
    session.pop('logged_in', None)
    # Best-effort cleanup of server-side ledger.
    try:
        if isinstance(username, str) and username:
            with _shot_ledgers_lock:
                _shot_ledgers.pop(username, None)
    except Exception:
        pass
    
    # Clean up frame differencer for this user
    if _have_frame_differencing and isinstance(username, str) and username:
        try:
            reset_frame_differencer(username)
            print(f"[logout] Frame differencer reset for user: {username}", flush=True)
        except Exception as e:
            print(f"[logout] Frame differencer cleanup error: {e}", flush=True)
    
    return jsonify({'success': True, 'message': 'Logged out successfully'})


@app.route('/api/shots', methods=['GET'])
def api_shots():
    user_key = _ledger_user_key()
    if not user_key:
        return jsonify({'error': 'unauthorized'}), 401

    ledger = _get_or_create_ledger(user_key)
    series = ledger.get("series", {})

    series_totals = {}
    grand_total = 0.0

    for s_num, shots in series.items():
        subtotal = float(round(sum(float(s.get('score', 0.0)) for s in shots), 1))
        series_totals[s_num] = subtotal
        grand_total += subtotal

    return jsonify({
        "current_series": ledger.get("current_series"),
        "series": series,
        "series_totals": series_totals,
        "grand_total": float(round(grand_total, 1)),
        "shots_per_series": ledger.get("shots_per_series", 10)
    })

@app.before_request
def require_login():
    # allow public endpoints
    allowed_prefixes = ['/login', '/register', '/static', '/favicon.ico', '/latest_image']
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


# ------------------- Frame Differencing Control APIs -------------------

@app.route('/api/frame_differencing/status', methods=['GET'])
def fd_status():
    """Get frame differencing status and statistics."""
    try:
        user_key = _ledger_user_key()
        if not user_key:
            return jsonify({'error': 'unauthorized'}), 401
        
        if not _have_frame_differencing:
            return jsonify({
                'available': False,
                'message': 'Frame differencing module not available'
            }), 200
        
        fd = get_frame_differencer(user_key)
        stats = fd.get_stats()
        
        return jsonify({
            'available': True,
            'enabled': USE_FRAME_DIFFERENCING,
            'hybrid_mode': HYBRID_MODE,
            'stats': stats,
        }), 200
    except Exception as e:
        print(f"[fd_status] Error: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/frame_differencing/enable', methods=['POST'])
def fd_enable():
    """Enable or disable frame differencing globally."""
    try:
        global USE_FRAME_DIFFERENCING
        data = request.get_json(silent=True) or {}
        enabled = data.get('enabled', True)
        
        USE_FRAME_DIFFERENCING = bool(enabled)
        print(f"[fd_enable] Frame differencing set to: {USE_FRAME_DIFFERENCING}", flush=True)
        
        return jsonify({
            'status': 'ok',
            'enabled': USE_FRAME_DIFFERENCING,
            'message': f"Frame differencing {'enabled' if USE_FRAME_DIFFERENCING else 'disabled'}"
        }), 200
    except Exception as e:
        print(f"[fd_enable] Error: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/frame_differencing/hybrid_mode', methods=['POST'])
def fd_hybrid_mode():
    """Enable or disable hybrid mode (frame differencing + ML validation)."""
    try:
        global HYBRID_MODE
        data = request.get_json(silent=True) or {}
        enabled = data.get('enabled', True)
        
        HYBRID_MODE = bool(enabled)
        print(f"[fd_hybrid_mode] Hybrid mode set to: {HYBRID_MODE}", flush=True)
        
        return jsonify({
            'status': 'ok',
            'hybrid_mode': HYBRID_MODE,
            'message': f"Hybrid mode {'enabled' if HYBRID_MODE else 'disabled'}"
        }), 200
    except Exception as e:
        print(f"[fd_hybrid_mode] Error: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/frame_differencing/reset_reference', methods=['POST'])
def fd_reset_reference():
    """Force reset the reference frame for the current user."""
    try:
        user_key = _ledger_user_key()
        if not user_key:
            return jsonify({'error': 'unauthorized'}), 401
        
        reset_frame_differencer(user_key)
        _fd_frame_skip_counter.pop(user_key, None)
        
        print(f"[fd_reset_reference] Reference frame reset for user: {user_key}", flush=True)
        
        return jsonify({
            'status': 'ok',
            'message': f"Reference frame reset for user {user_key}"
        }), 200
    except Exception as e:
        print(f"[fd_reset_reference] Error: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


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
    # DISABLED: Live streaming not needed - we use on-demand /frame fetching instead
    # This stops the continuous retry spam for /video_feed which doesn't exist on Pi
    pass

# API-only mode: Flask runs directly, Next.js handles the UI
if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("🚀 Lakshya API Backend Starting...", flush=True)
    print("=" * 60, flush=True)
    print("", flush=True)
    print("📡 Flask API running at: http://127.0.0.1:5000", flush=True)
    print("🌐 Open Next.js frontend at: http://localhost:3000", flush=True)
    print("", flush=True)
    print("=" * 60, flush=True)
    
    # Run Flask directly (no webview window - Next.js is the UI)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
