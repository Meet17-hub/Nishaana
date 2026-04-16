"""
Press   :   Function
  P     :   prints wrapped points
  O     :   Shows Original Image
  W     :   Shows Wrapped Image
  V     :   Shows TrackBar For Wrapping points
  R     :   Shows Rings on Image
  B     :   Shows Binary Threshold Image
  S     :   Shows Sharpened Image
  Q     :   Quits Entire Program

NOTE : If a window is already on, pressing its corresponding Button will Close it
NOTE : Sharpened Image ('S') will only show up if Binary Image is active.
"""

# TODO: Add Multi Threading
print("hello")
import sys
import time
import os

import cv2
import numpy as np

# Tk sliders are used for decimal-precision tuning of wrap/ring values
import tkinter as tk

# output_pts will be set after loading the image to match its dimensions
output_pts = None

show_Rings = False
show_Wrapped = False
show_wrapPoints = False
show_Params = False
sharpening = False
show_OG = True
show_Fisheye = False

Thresh = 127
k_size = 3
lim = 0

focal = 0
cx = 0
cy = 0
k1 = 0
k2 = 0

wrap_points = {
       #Pistol
        #'x1': 731, 'y1': 480,   # top-left   
        #'x2': 800, 'y2': 1547,   # BOTTOM-LEFT
        #'x3': 1781, 'y3': 1547,  # BOTTOM-RIGHT
        #'x4': 1867, 'y4': 469    # TOP-RIGHT 
       
       #Rifle
        'x1': 1024, 'y1': 565, 
        'x2': 1067, 'y2': 1077, 
        'x3': 1568, 'y3': 1056, 
        'x4': 1568, 'y4': 544
        #'x1': 1024, 'y1': 565, 'x2': 1067, 'y2': 1077, 'x3': 1568, 'y3': 1056, 'x4': 1568, 'y4': 544}'x4': 1525, 'y4': 1013

        #'x1': 1077, 'y1': 971,   # top-left   
        ##'x2': 1109, 'y2': 1483,   # BOTTOM-LEFT
        #'x3': 1483, 'y3': 1419,  # BOTTOM-RIGHT
        #'x4': 1525, 'y4': 939    # TOP-RIGHT 
         
    }
        # [15, 124],
       # [622, 112],
       # [570, 629],
       # [71, 638]
 #       Click 4 corners in the order: top-left, bottom-left, top-right, bottom-right
#Clicked point: 18, 100
#Clicked point: 77, 648
#Clicked point: 619, 88
#Clicked point: 565, 644

# rings = {
#     "ring_1": {"cx": 251, "cy": 272, "radius": 7, "ratio": 1.03, "rotation": 0},
#     "ring_2": {"cx": 251, "cy": 270, "radius": 16, "ratio": 1.05, "rotation": 0},
#     "ring_3": {"cx": 253, "cy": 269, "radius": 44, "ratio": 0.95, "rotation": 0},
#     "ring_4": {"cx": 251, "cy": 269, "radius": 71, "ratio": 0.99, "rotation": 0},
#     "ring_5": {"cx": 251, "cy": 268, "radius": 94, "ratio": 0.97, "rotation": 0},
#     "ring_6": {"cx": 250, "cy": 267, "radius": 119, "ratio": 0.98, "rotation": 0},
#     "ring_7": {"cx": 250, "cy": 264, "radius": 149, "ratio": 0.96, "rotation": 0},
#     "ring_8": {"cx": 251, "cy": 260, "radius": 170, "ratio": 0.98, "rotation": 0},
#     "ring_9": {"cx": 248, "cy": 257, "radius": 193, "ratio": 0.98, "rotation": 0},
#     "ring_10": {"cx": 248, "cy": 253, "radius": 217, "ratio": 0.99, "rotation": 0},
#     "ring_11": {"cx": 248, "cy": 249, "radius": 240, "ratio": 1.0, "rotation": 0}  # editable
# }

rings = {
    'center_x': 250, 'center_y': 250,
    'ring_11':8,
    'ring_10':18, 'ring_9':46, 'ring_8':74,
    'ring_7':100, 'ring_6': 122, 'ring_5': 147, 'ring_4': 174,
    'ring_3': 199, 'ring_2': 219, 'ring_1': 244
}

RIFLE_BLACK_RATIO = 0.67033
RIFLE_RING8_RATIO = 0.23077
MAX_TARGET_AREA_RATIO = 0.35
MAX_SHOT_SEARCH_RADIUS = 160

# Decimal slider configuration (only used for WrapPoints/Ring_Points)
DECIMAL_PLACES = 2
DECIMAL_RESOLUTION = 10 ** (-DECIMAL_PLACES)  # e.g. 0.01

_tk_root: tk.Tk | None = None
_wrap_gui = None
_rings_gui = None
_cached_auto_points = None
_cached_auto_shape = None
_last_distance_summary = None


def _load_start_frame() -> np.ndarray | None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    candidate_paths = [
        os.path.join(script_dir, "test.jpeg"),
        os.path.join(project_dir, "test.jpeg"),
        os.path.join(script_dir, "test.jpeg"),
        os.path.join(project_dir, "test.jpeg"),
    ]

    for candidate_path in candidate_paths:
        if not os.path.exists(candidate_path):
            continue
        frame = cv2.imread(candidate_path)
        if frame is not None:
            print(f"Loaded image: {candidate_path}")
            return frame

    return None


def _ensure_tk_root() -> tk.Tk:
    global _tk_root
    if _tk_root is None:
        _tk_root = tk.Tk()
        _tk_root.withdraw()  # keep root hidden; we only use Toplevel windows
    return _tk_root


def _format_float(val: float) -> str:
    return f"{val:.{DECIMAL_PLACES}f}"


class _DecimalSlidersWindow:
    def __init__(
        self,
        title: str,
        values_dict: dict,
        sliders: list[tuple[str, float, float]],
    ):
        _ensure_tk_root()
        self._values = values_dict
        self._win = tk.Toplevel(_tk_root)
        self._win.title(title)
        self._win.protocol("WM_DELETE_WINDOW", self.destroy)
        self._vars: dict[str, tk.DoubleVar] = {}
        self._labels: dict[str, tk.Label] = {}

        container = tk.Frame(self._win, padx=10, pady=10)
        container.pack(fill=tk.BOTH, expand=True)

        for row, (key, min_val, max_val) in enumerate(sliders):
            initial = float(self._values.get(key, 0.0))
            var = tk.DoubleVar(value=initial)
            self._vars[key] = var

            label = tk.Label(container, text=f"{key}: {_format_float(initial)}", anchor="w")
            label.grid(row=row, column=0, sticky="w", pady=3)
            self._labels[key] = label

            scale = tk.Scale(
                container,
                from_=min_val,
                to=max_val,
                orient=tk.HORIZONTAL,
                showvalue=False,
                resolution=DECIMAL_RESOLUTION,
                variable=var,
                length=300,
            )
            scale.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=3)
            container.grid_columnconfigure(1, weight=1)

            def _on_change(_unused=None, *, k=key):
                v = float(self._vars[k].get())
                self._values[k] = v
                self._labels[k].config(text=f"{k}: {_format_float(v)}")

            # Update dict/label when the slider changes
            var.trace_add("write", lambda *_args, k=key: _on_change(k=k))

            # Keyboard/mouse-wheel “scrolling” on the focused slider
            def _nudge(delta: float, *, k=key):
                cur = float(self._vars[k].get())
                nxt = max(min(cur + delta, max_val), min_val)
                # snap to resolution to avoid float drift
                step = DECIMAL_RESOLUTION
                if step > 0:
                    nxt = round(nxt / step) * step
                self._vars[k].set(nxt)

            scale.bind("<Up>", lambda _e, k=key: (_nudge(DECIMAL_RESOLUTION, k=k), "break"))
            scale.bind("<Down>", lambda _e, k=key: (_nudge(-DECIMAL_RESOLUTION, k=k), "break"))
            scale.bind("<Right>", lambda _e, k=key: (_nudge(DECIMAL_RESOLUTION, k=k), "break"))
            scale.bind("<Left>", lambda _e, k=key: (_nudge(-DECIMAL_RESOLUTION, k=k), "break"))
            scale.bind("<Prior>", lambda _e, k=key: (_nudge(10 * DECIMAL_RESOLUTION, k=k), "break"))  # PageUp
            scale.bind("<Next>", lambda _e, k=key: (_nudge(-10 * DECIMAL_RESOLUTION, k=k), "break"))  # PageDown

            # Mouse wheel (Windows)
            def _on_wheel(e, *, k=key):
                # e.delta is typically +/-120 per notch
                direction = 1 if e.delta > 0 else -1
                _nudge(direction * DECIMAL_RESOLUTION, k=k)
                return "break"

            scale.bind("<MouseWheel>", _on_wheel)

        # Helpful hint line
        hint = tk.Label(
            container,
            text="Use mouse wheel or arrow keys for decimal steps (PgUp/PgDn = x10).",
            fg="#555",
            anchor="w",
        )
        hint.grid(row=len(sliders), column=0, columnspan=2, sticky="w", pady=(10, 0))

    def update(self):
        if self._win is None:
            return
        try:
            self._win.update_idletasks()
            self._win.update()
        except tk.TclError:
            # window closed
            self._win = None

    def destroy(self):
        if self._win is None:
            return
        try:
            self._win.destroy()
        except tk.TclError:
            pass
        self._win = None

    @property
    def is_open(self) -> bool:
        return self._win is not None

def update_ring(ring_name, key, val):
    rings[ring_name][key] = val

def startRings_old():
    cv2.namedWindow("Ring_Points", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Ring_Points", 800, 600)
    ring = "ring_9"
    # Center X
    cv2.createTrackbar(f"{ring}_cx", "Ring_Points", rings[ring]["cx"], 640,
                       lambda val, r=ring: update_ring(r, "cx", val))
    # Center Y
    cv2.createTrackbar(f"{ring}_cy", "Ring_Points", rings[ring]["cy"], 570,
                       lambda val, r=ring: update_ring(r, "cy", val))
    # Radius
    cv2.createTrackbar(f"{ring}_radius", "Ring_Points", rings[ring]["radius"], 400,
                       lambda val, r=ring: update_ring(r, "radius", val))
    # Oval ratio (scaled by 100 for slider)
    cv2.createTrackbar(f"{ring}_ratio", "Ring_Points", int(rings[ring]["ratio"]*100), 200,
                       lambda val, r=ring: update_ring(r, "ratio", val/100))
    # Rotation (in degrees, 0-360)
    cv2.createTrackbar(f"{ring}_rotation", "Ring_Points", rings[ring]["rotation"], 360,
                       lambda val, r=ring: update_ring(r, "rotation", val))
# Video capture removed — use file selection in __main__ instead

def startRings():
    # Deprecated: kept for compatibility, Ring sliders are now Tk-based for decimal precision.
    pass

params = {'alpha': 1.5, 'beta': -0.5, 'gamma': 0}

key_actions = {
    ord('W'): 'show_Wrapped',
    ord('O'): 'show_OG',
    ord('V'): 'show_wrapPoints',
    ord('R'): 'show_Rings',
    ord('B'): 'show_Params',
    ord('S'): 'sharpening',
    ord('F'): 'show_Fisheye',
}


# ------------------- Fisheye / undistort -------------------
CALIBRATION_NPZ_PATH = os.path.join(os.path.dirname(__file__), "calibration_params.npz")

# Undistort tuning controls (exposed via Tk sliders).
# - For fisheye calibration (D has 4 coeffs): uses "balance".
# - For pinhole calibration (D has 5+ coeffs): uses "alpha".
undistort_tune = {
    "balance": 0.0,  # 0=crop, 1=keep all pixels (more black borders)
    "alpha": 1.0,    # 0=crop, 1=keep all pixels
}

_calib_loaded = False
_calib_is_fisheye = False
_calib_K = None
_calib_D = None
_calib_DIM = None  # (w, h)
_undistort_maps: dict[tuple[int, int, bool, float], tuple[np.ndarray, np.ndarray]] = {}
_last_undistort_tune: tuple[float, float] | None = None
_undistort_gui = None


def _as_dim_wh(dim_like, fallback_wh: tuple[int, int]) -> tuple[int, int]:
    try:
        if dim_like is None:
            return fallback_wh
        arr = np.array(dim_like).reshape(-1)
        if arr.size >= 2:
            w = int(arr[0])
            h = int(arr[1])
            if w > 0 and h > 0:
                return (w, h)
    except Exception:
        pass
    return fallback_wh


def _best_dim_for_frame(dim_wh: tuple[int, int], frame_wh: tuple[int, int]) -> tuple[int, int]:
    """Pick (w,h) vs swapped (h,w) whichever is closer to the frame."""
    dw, dh = dim_wh
    fw, fh = frame_wh
    score = abs(fw - dw) + abs(fh - dh)
    score_swapped = abs(fw - dh) + abs(fh - dw)
    if score_swapped < score:
        return (dh, dw)
    return (dw, dh)


def _load_calibration_npz(npz_path: str) -> None:
    """Best-effort calibration loader.

    Supports common key names:
      - K / camera_matrix / mtx
      - D / dist / distCoeffs / dist_coeffs
      - DIM / dim / image_size
    """
    global _calib_loaded, _calib_is_fisheye, _calib_K, _calib_D, _calib_DIM

    _calib_loaded = False
    _calib_is_fisheye = False
    _calib_K = None
    _calib_D = None
    _calib_DIM = None

    if not npz_path or not os.path.exists(npz_path):
        return

    try:
        data = np.load(npz_path, allow_pickle=True)
    except Exception:
        return

    keys = set(getattr(data, "files", []))

    def _pick(*candidates: str):
        for c in candidates:
            if c in keys:
                return data[c]
        return None

    K = _pick("K", "camera_matrix", "cameraMatrix", "mtx")
    D = _pick("D", "dist", "distCoeffs", "dist_coeffs", "distCoefficients")
    DIM = _pick("DIM", "dim", "image_size", "imageSize")

    if K is None or D is None:
        return

    try:
        K = np.array(K, dtype=np.float64).reshape(3, 3)
        D = np.array(D, dtype=np.float64).reshape(-1)
    except Exception:
        return

    # Heuristic: fisheye calibration commonly uses 4 coefficients
    _calib_is_fisheye = (D.size == 4)
    if _calib_is_fisheye:
        D = D.reshape(4, 1)
    else:
        # Standard pinhole distortion expects (N,1)
        D = D.reshape(-1, 1)

    _calib_K = K
    _calib_D = D
    # If DIM isn't provided, infer it from principal point (approx width/height ~= 2*cx, 2*cy).
    if DIM is None:
        try:
            infer_w = int(round(float(K[0, 2]) * 2.0))
            infer_h = int(round(float(K[1, 2]) * 2.0))
            if infer_w > 0 and infer_h > 0:
                DIM = np.array([infer_w, infer_h], dtype=np.int32)
        except Exception:
            DIM = None

    _calib_DIM = DIM
    _calib_loaded = True

    try:
        dim_dbg = None
        if _calib_DIM is not None:
            dim_dbg = np.array(_calib_DIM).reshape(-1)[:2].tolist()
        kind = "fisheye" if _calib_is_fisheye else "pinhole"
        print(f"Loaded {kind} calibration: DIM={dim_dbg}")
    except Exception:
        pass


def _undistort_frame(frame_bgr: np.ndarray) -> np.ndarray:
    """Undistort using loaded calibration. Returns original if not available."""
    if not _calib_loaded or _calib_K is None or _calib_D is None:
        return frame_bgr

    balance = float(undistort_tune.get("balance", 0.0))
    alpha = float(undistort_tune.get("alpha", 1.0))

    h, w = frame_bgr.shape[:2]
    dim = _best_dim_for_frame(_as_dim_wh(_calib_DIM, (w, h)), (w, h))

    # Include tuning params in cache so changing sliders takes effect.
    cache_key = (w, h, bool(_calib_is_fisheye), float(balance) if _calib_is_fisheye else float(alpha))
    maps = _undistort_maps.get(cache_key)

    try:
        if maps is None:
            K = _calib_K.copy()
            D = _calib_D.copy()

            # Always center the correction on the current frame.
            # This makes undistortion symmetric around the image center for any resolution.
            frame_cx = (w - 1) / 2.0
            frame_cy = (h - 1) / 2.0

            # If calibration DIM differs from current frame, scale intrinsics.
            if dim != (w, h):
                sx = w / float(dim[0])
                sy = h / float(dim[1])
                K[0, 0] *= sx
                K[0, 2] *= sx
                K[1, 1] *= sy
                K[1, 2] *= sy
                dim = (w, h)

            # Force principal point to the exact center of the frame.
            K[0, 2] = frame_cx
            K[1, 2] = frame_cy

            if _calib_is_fisheye:
                new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(
                    K, D, dim, np.eye(3), balance=balance
                )
                try:
                    new_K = np.array(new_K, dtype=np.float64)
                    new_K[0, 2] = frame_cx
                    new_K[1, 2] = frame_cy
                except Exception:
                    pass
                map1, map2 = cv2.fisheye.initUndistortRectifyMap(
                    K, D, np.eye(3), new_K, dim, cv2.CV_16SC2
                )
            else:
                new_K, _roi = cv2.getOptimalNewCameraMatrix(K, D, dim, alpha, dim)
                try:
                    new_K = np.array(new_K, dtype=np.float64)
                    new_K[0, 2] = frame_cx
                    new_K[1, 2] = frame_cy
                except Exception:
                    pass
                map1, map2 = cv2.initUndistortRectifyMap(
                    K, D, None, new_K, dim, cv2.CV_16SC2
                )

            maps = (map1, map2)
            _undistort_maps[cache_key] = maps

        map1, map2 = maps
        return cv2.remap(frame_bgr, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    except Exception:
        return frame_bgr


def _ensure_undistort_gui():
    global _undistort_gui
    if _undistort_gui is not None and getattr(_undistort_gui, "is_open", False):
        return

    sliders = [
        ("balance", 0.0, 1.0),
        ("alpha", 0.0, 1.0),
    ]
    _undistort_gui = _DecimalSlidersWindow("Undistort Tuning", undistort_tune, sliders)



def manage_window(window_name, should_show, show_func=None, close_func=None, draw_func=None):

    if should_show:
        if draw_func:
            draw_func()
        if show_func and cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
            show_func()
    else:
        if close_func:
            close_func(window_name)
        else:
            cv2.destroyWindow(window_name)


def show_image_window(name, image):
    # Show `image` in window `name` at the image's native size (no distortion)
    cv2.namedWindow(name, cv2.WINDOW_NORMAL)
    cv2.imshow(name, image)
    # Resize window to the image's native size (width, height)
    try:
        height, width = image.shape[:2]
        # cv2.resizeWindow(name, int(width), int(height))
        cv2.resizeWindow(name, 800, 600)
    except Exception:
        try:
            cv2.resizeWindow(name, 800, 600)
        except Exception:
            pass

def show_image_window_wrapped(name, image):
    # Show `image` in window `name` at the image's native size (no distortion)
    cv2.namedWindow(name, cv2.WINDOW_NORMAL)
    cv2.imshow(name, image)
    # Resize window to the image's native size (width, height)
    try:
        height, width = image.shape[:2]
        # cv2.resizeWindow(name, int(width), int(height))
        cv2.resizeWindow(name, 640, 640)
    except Exception:
        try:
            cv2.resizeWindow(name, 800, 600)
        except Exception:
            pass

def closeWindow(name: str):
    if cv2.getWindowProperty(name, cv2.WND_PROP_VISIBLE) >= 1:
        cv2.destroyWindow(name)


def startWrapPoints():
    # Deprecated: kept for compatibility, Wrap sliders are now Tk-based for decimal precision.
    pass


def startParams():
    cv2.namedWindow("Params")
    cv2.resizeWindow("Params", (400, 300))
    for key1, initial_val in params.items():
        cv2.createTrackbar(key1, 'Params', int(initial_val*2+20), 40,
                           lambda val, key=key1: update_point(((val / 2) - 10), key, params))

    cv2.createTrackbar("Thresh", "Params", Thresh, 255, lambda x: globals().update(Thresh=x))
    cv2.createTrackbar("k_size", "Params", k_size, 255, lambda x: globals().update(k_size=(x + (0 if x % 2 else 1))))


def imageProcessor(frame1, sharp: bool):

    frame1 = frame1.copy()
    gray = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)

    # Apply a Gaussian blur to reduce noise and improve detection
    gray_blurred = cv2.GaussianBlur(gray, (k_size, k_size), 2)

    output_image = gray_blurred
    if sharp:
        output_image = sharpened_image = cv2.addWeighted(gray, params['alpha'], gray_blurred, params['beta'], params['gamma'])
        cv2.imshow("Sharpened Image", sharpened_image)
    else:
        closeWindow("Sharpened Image")

    _, binary_image = cv2.threshold(output_image, Thresh, 255, cv2.THRESH_BINARY)

    cv2.imshow("Binary Image", binary_image)


#def startRings():
    
def drawRings_old(canvas):

    for ring in rings.values():
        cx, cy, radius, ratio = ring["cx"], ring["cy"], ring["radius"], ring["ratio"]
        rotation = ring.get("rotation", 0)
        axes = (radius, int(radius * ratio))
        cv2.ellipse(canvas, (cx, cy), axes, rotation, 0, 360, (255, 0, 255), 2)
    cv2.imshow("Rings", canvas)


def drawRings(canvas):
    center_x, center_y = int(round(rings['center_x'])), int(round(rings['center_y']))
    cv2.circle(canvas, (center_x, center_y), 1, (0, 0, 255), 2)

    for i in range(1, 12):
        radius = int(round(rings["ring_" + str(i)]))
        cv2.circle(canvas, (center_x, center_y), radius, (255, 0, 255), 2)

    cv2.imshow("Rings", canvas)


def detect_rifle_square_from_image(frame: np.ndarray) -> np.ndarray | None:
    if frame is None or frame.size == 0:
        return None

    h, w = frame.shape[:2]
    max_dim = max(h, w)
    scale = 1.0
    if max_dim > 1200:
        scale = 1200.0 / float(max_dim)
        work = cv2.resize(frame, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
    else:
        work = frame

    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(largest))
    if area < 50.0:
        return None

    moments = cv2.moments(largest)
    if moments.get("m00", 0.0) == 0.0:
        return None

    center_x = float(moments["m10"] / moments["m00"])
    center_y = float(moments["m01"] / moments["m00"])
    black_radius = float(np.sqrt(area / np.pi))
    if scale != 1.0:
        inv_scale = 1.0 / scale
        center_x *= inv_scale
        center_y *= inv_scale
        black_radius *= inv_scale
    ring8_radius = black_radius * (RIFLE_RING8_RATIO / RIFLE_BLACK_RATIO)
    half_side = max(ring8_radius, 1.0)

    left = max(0.0, center_x - half_side)
    right = min(float(w - 1), center_x + half_side)
    top = max(0.0, center_y - half_side)
    bottom = min(float(h - 1), center_y + half_side)

    rings['center_x'] = center_x
    rings['center_y'] = center_y
    rings['ring_8'] = ring8_radius

    return np.array(
        [
            [left, top],
            [left, bottom],
            [right, bottom],
            [right, top],
        ],
        dtype=np.float32,
    )


def detect_target_center_from_warped(frame: np.ndarray) -> tuple[float, float, float] | None:
    if frame is None or frame.size == 0:
        return None

    height, width = frame.shape[:2]
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    radius = float(min(width, height)) * 0.45
    return center_x, center_y, radius


def detect_black_center_from_warped(frame: np.ndarray) -> tuple[float, float, float] | None:
    if frame is None or frame.size == 0:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0

    roi_half_w = max(40, int(round(width * 0.28)))
    roi_half_h = max(40, int(round(height * 0.28)))
    x1 = max(0, int(round(center_x)) - roi_half_w)
    x2 = min(width, int(round(center_x)) + roi_half_w)
    y1 = max(0, int(round(center_y)) - roi_half_h)
    y2 = min(height, int(round(center_y)) + roi_half_h)
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    roi_blur = cv2.GaussianBlur(roi, (5, 5), 0)
    threshold_value = min(90, int(np.percentile(roi_blur, 20)))
    _, mask = cv2.threshold(roi_blur, threshold_value, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best_contour = None
    best_score = None
    roi_area = float(roi.shape[0] * roi.shape[1])
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 400.0 or area > roi_area * 0.8:
            continue

        moments = cv2.moments(contour)
        if moments.get("m00", 0.0) == 0.0:
            continue

        blob_x = float(moments["m10"] / moments["m00"])
        blob_y = float(moments["m01"] / moments["m00"])
        distance = float(np.hypot(blob_x - (roi.shape[1] - 1) / 2.0, blob_y - (roi.shape[0] - 1) / 2.0))
        score = area - (distance * 8.0)
        if best_score is None or score > best_score:
            best_score = score
            best_contour = contour

    if best_contour is None:
        return None

    moments = cv2.moments(best_contour)
    if moments.get("m00", 0.0) == 0.0:
        return None

    black_x = float(moments["m10"] / moments["m00"]) + x1
    black_y = float(moments["m01"] / moments["m00"]) + y1
    black_area = float(cv2.contourArea(best_contour))
    black_r = float(np.sqrt(max(black_area, 1.0) / np.pi))
    return black_x, black_y, black_r


def get_decimal_ten_score(center_distance_px: float, ring10_radius_px: float, pellet_radius_px: float) -> float | None:
    if ring10_radius_px <= 0.0 or center_distance_px < 0.0 or pellet_radius_px < 0.0:
        return None

    max_center_for_ten = ring10_radius_px + pellet_radius_px
    if center_distance_px > max_center_for_ten:
        return None

    # Decimal 10 scoring:
    # - inner edge just touching ring 10 boundary => 10.0
    # - moving inward toward center ramps up to 10.9
    progress = 1.0 - (center_distance_px / max_center_for_ten)
    progress = max(0.0, min(1.0, progress))
    band_index = min(int(progress * 10.0), 9)
    return round(10.0 + (band_index * 0.1), 1)


def detect_shot_center_from_warped(
    frame: np.ndarray,
    target: tuple[float, float, float] | None,
) -> tuple[float, float, float] | None:
    if frame is None or frame.size == 0 or target is None:
        return None

    target_x, target_y, target_r = target
    if not np.isfinite(target_x) or not np.isfinite(target_y) or not np.isfinite(target_r):
        return None
    if target_r <= 0.0:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    max_radius_for_frame = max(24, min(MAX_SHOT_SEARCH_RADIUS, min(gray.shape[:2]) // 3))
    search_radius = max(24, min(int(round(target_r * 1.35)), max_radius_for_frame))
    x1 = max(0, int(round(target_x)) - search_radius)
    x2 = min(gray.shape[1], int(round(target_x)) + search_radius + 1)
    y1 = max(0, int(round(target_y)) - search_radius)
    y2 = min(gray.shape[0], int(round(target_y)) + search_radius + 1)
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    roi_blur = cv2.GaussianBlur(roi, (5, 5), 0)
    roi_for_threshold = roi_blur
    if roi_blur.size > 40000:
        roi_for_threshold = cv2.resize(roi_blur, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    threshold_value = max(0.0, float(np.percentile(roi_for_threshold, 15)) - 8.0)
    _, dark_mask = cv2.threshold(roi_blur, threshold_value, 255, cv2.THRESH_BINARY_INV)

    roi_h, roi_w = roi.shape[:2]
    yy, xx = np.ogrid[:roi_h, :roi_w]
    cx_roi = float(target_x - x1)
    cy_roi = float(target_y - y1)
    radial_mask = ((xx - cx_roi) ** 2 + (yy - cy_roi) ** 2) <= float(search_radius * search_radius)
    dark_mask = np.where(radial_mask, dark_mask, 0).astype(np.uint8)

    kernel = np.ones((3, 3), np.uint8)
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best_contour = None
    best_score = None
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 8.0:
            continue
        moments = cv2.moments(contour)
        if moments.get("m00", 0.0) == 0.0:
            continue
        shot_x = float(moments["m10"] / moments["m00"])
        shot_y = float(moments["m01"] / moments["m00"])
        distance_to_target = float(np.hypot(shot_x - cx_roi, shot_y - cy_roi))
        if distance_to_target > search_radius:
            continue
        score = area - (0.35 * distance_to_target)
        if best_score is None or score > best_score:
            best_score = score
            best_contour = contour

    if best_contour is None:
        return None

    moments = cv2.moments(best_contour)
    if moments.get("m00", 0.0) == 0.0:
        return None

    shot_x = float(moments["m10"] / moments["m00"]) + x1
    shot_y = float(moments["m01"] / moments["m00"]) + y1
    shot_area = float(cv2.contourArea(best_contour))
    shot_r = float(np.sqrt(max(shot_area, 1.0) / np.pi))
    return shot_x, shot_y, shot_r


def annotate_shot_metrics(frame: np.ndarray) -> np.ndarray:
    global _last_distance_summary

    annotated = frame.copy()
    target = detect_target_center_from_warped(frame)
    black = detect_black_center_from_warped(frame)

    if target is not None:
        target_x, target_y, target_r = target
        cv2.circle(annotated, (int(round(target_x)), int(round(target_y))), 5, (255, 0, 0), -1)
        cv2.drawMarker(
            annotated,
            (int(round(target_x)), int(round(target_y))),
            (255, 255, 0),
            markerType=cv2.MARKER_CROSS,
            markerSize=18,
            thickness=2,
        )
        rings['center_x'] = target_x
        rings['center_y'] = target_y

    if black is not None:
        black_x, black_y, black_r = black
        cv2.circle(annotated, (int(round(black_x)), int(round(black_y))), max(4, int(round(black_r))), (0, 255, 0), 2)
        cv2.circle(annotated, (int(round(black_x)), int(round(black_y))), 4, (0, 255, 0), -1)
        cv2.drawMarker(
            annotated,
            (int(round(black_x)), int(round(black_y))),
            (0, 255, 255),
            markerType=cv2.MARKER_TILTED_CROSS,
            markerSize=18,
            thickness=2,
        )

    if target is not None and black is not None:
        target_x, target_y, _ = target
        black_x, black_y, black_r = black
        distance_px = float(np.hypot(black_x - target_x, black_y - target_y))
        edge_distance_px = max(0.0, distance_px - black_r)
        ring10_radius_px = float(rings.get("ring_10", 0.0))
        decimal_score = get_decimal_ten_score(distance_px, ring10_radius_px, black_r)
        summary = (
            f"Target center: ({target_x:.2f}, {target_y:.2f}) | "
            f"Black center: ({black_x:.2f}, {black_y:.2f}) | "
            f"Distance: {distance_px:.2f}px | "
            f"Edge distance: {edge_distance_px:.2f}px"
        )
        if decimal_score is not None:
            summary += f" | Score: {decimal_score:.1f}"
        if summary != _last_distance_summary:
            print(summary)
            _last_distance_summary = summary

        cv2.line(
            annotated,
            (int(round(target_x)), int(round(target_y))),
            (int(round(black_x)), int(round(black_y))),
            (0, 255, 255),
            2,
        )
        cv2.putText(
            annotated,
            f"Dist: {distance_px:.2f}px",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.rectangle(annotated, (12, 38), (370, 160), (0, 0, 0), -1)
        cv2.putText(
            annotated,
            f"Target: ({target_x:.1f}, {target_y:.1f})",
            (20, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 0, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"Black: ({black_x:.1f}, {black_y:.1f})",
            (20, 88),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            annotated,
            f"Edge dist: {edge_distance_px:.2f}px",
            (20, 116),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        score_text = f"10-ring score: {decimal_score:.1f}" if decimal_score is not None else "Outside hardcoded 10-ring"
        score_color = (0, 255, 255) if decimal_score is not None else (0, 165, 255)
        cv2.putText(
            annotated,
            score_text,
            (20, 144),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            score_color,
            2,
            cv2.LINE_AA,
        )
    else:
        _last_distance_summary = None
        cv2.rectangle(annotated, (12, 12), (330, 44), (0, 0, 0), -1)
        cv2.putText(
            annotated,
            "Target/black center not detected",
            (20, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    return annotated

def update_point(val, key, cus_dict):
    cus_dict[key] = val


def _ensure_wrap_gui():
    global _wrap_gui
    if _wrap_gui is not None and getattr(_wrap_gui, "is_open", False):
        return
    sliders = [
        ("x1", 0.0, float(lim)),
        ("y1", 0.0, float(lim)),
        ("x2", 0.0, float(lim)),
        ("y2", 0.0, float(lim)),
        ("x3", 0.0, float(lim)),
        ("y3", 0.0, float(lim)),
        ("x4", 0.0, float(lim)),
        ("y4", 0.0, float(lim)),
    ]
    _wrap_gui = _DecimalSlidersWindow("WrapPoints", wrap_points, sliders)


def _ensure_rings_gui():
    global _rings_gui
    if _rings_gui is not None and getattr(_rings_gui, "is_open", False):
        return
    sliders: list[tuple[str, float, float]] = [
        ("center_x", 0.0, 640.0),
        ("center_y", 0.0, 640.0),
    ]
    # show ring_11 down to ring_1 like the existing UI
    for i in range(11, 0, -1):
        sliders.append((f"ring_{i}", 0.0, 400.0))
    _rings_gui = _DecimalSlidersWindow("Ring_Points", rings, sliders)


def startFishPoints():

    cv2.namedWindow("FishPoints")
    cv2.resizeWindow("FishPoints", (600, 200))

    # Fish points removed in this simplified version


def printAll():
    print(f"wrap Points: {wrap_points}")
    print(rings)
    print(params)
    print(f"Threshold: {Thresh}")
    print(f"Kernal Size: {k_size}")
    print(f"Fisheye enabled: {show_Fisheye}")

print("hello1")
if __name__ == "__main__":
    # _load_calibration_npz(CALIBRATION_NPZ_PATH)
    # # Capture a single image from the IP video feed and run the interactive UI on that image
    # stream_url = "http://192.168.1.34:8000/frame"
    # cap = cv2.VideoCapture(stream_url)
    # if not cap or not cap.isOpened():
    #     print(f"Failed to open stream: {stream_url}")
    #     sys.exit(1)

    # Grab the first good frame (short retry loop)
    frame = _load_start_frame()
    # for _ in range(50):
    #     ret, f = cap.read()
    #     if ret and f is not None:
    #         frame = f
    #         break
    #     time.sleep(0.1)

    # cap.release()
    if frame is None:
        print("No input image found. Checked test1.jpeg/test.jpeg near wrap_test.py.")
        sys.exit(1)

    frame_raw = frame.copy()
    height, width = frame.shape[:2]
    print(height, width)
    lim = max(height, width)
    # output_pts = np.float32([[0, 0], [0, height], [width, height], [width, 0]])
    output_pts = np.float32([[0, 0], [0, 640], [640, 640], [640, 0]])
    
    # Interactive loop operates on the single captured image
    try:
        while True:
            # Optional undistort (fisheye/pinhole) (applied before wrap + ring drawing)
            cur_tune = (float(undistort_tune.get("balance", 0.0)), float(undistort_tune.get("alpha", 1.0)))
            if _last_undistort_tune is None or cur_tune != _last_undistort_tune:
                _undistort_maps.clear()
                _last_undistort_tune = cur_tune

            if show_Fisheye:
                _ensure_undistort_gui()
                if _undistort_gui is not None:
                    _undistort_gui.update()
                frame_src = _undistort_frame(frame_raw)
            else:
                if _undistort_gui is not None:
                    _undistort_gui.destroy()
                frame_src = frame_raw

            current_shape = frame_src.shape[:2]
            if _cached_auto_points is None or _cached_auto_shape != current_shape or show_Fisheye:
                points_f = detect_rifle_square_from_image(frame_src)
                if points_f is not None and not show_Fisheye:
                    _cached_auto_points = points_f.copy()
                    _cached_auto_shape = current_shape
            else:
                points_f = _cached_auto_points.copy()
            if points_f is None:
                points_f = np.array(
                    [
                        [float(wrap_points['x1']), float(wrap_points['y1'])],
                        [float(wrap_points['x2']), float(wrap_points['y2'])],
                        [float(wrap_points['x3']), float(wrap_points['y3'])],
                        [float(wrap_points['x4']), float(wrap_points['y4'])],
                    ],
                    dtype=np.float32,
                )

            points_i = np.round(points_f).astype(np.int32)
            disp = frame_src.copy()
            cv2.polylines(disp, [points_i], True, (0, 255, 0), 3)

            input_pts = points_f
            try:
                M = cv2.getPerspectiveTransform(input_pts, output_pts)
                frameW = cv2.warpPerspective(frame_src, M, (640, 640))
            except Exception as e:
                print(f"warp error: {e}", flush=True)
                frameW = frame_src.copy()

            frameW_annotated = annotate_shot_metrics(frameW)

            manage_window("Original Image", show_OG, None, closeWindow, lambda: show_image_window("Original Image", disp))
            manage_window("Wrapped Image", show_Wrapped, None, closeWindow, lambda: show_image_window_wrapped("Wrapped Image", frameW_annotated))
            manage_window("Params", show_Params, startParams, closeWindow, lambda: imageProcessor(frameW_annotated, sharpening))

            # Decimal-precision slider windows (Tk) for wrapping & rings
            if show_wrapPoints:
                _ensure_wrap_gui()
                if _wrap_gui is not None:
                    _wrap_gui.update()
            else:
                if _wrap_gui is not None:
                    _wrap_gui.destroy()

            if show_Rings:
                _ensure_rings_gui()
                if _rings_gui is not None:
                    _rings_gui.update()
                drawRings(frameW)
            else:
                if _rings_gui is not None:
                    _rings_gui.destroy()
                closeWindow("Rings")

            k = cv2.waitKey(1) & 0xFF
            if k == ord('P'):
                print(points_i)
            elif k == ord('Q'):
                printAll()
                cv2.destroyAllWindows()
                break
            else:
                # Accept both upper/lowercase hotkeys for convenience
                action_key = k
                if 97 <= k <= 122:  # a-z
                    action_key = ord(chr(k).upper())

                if action_key in key_actions:
                    name = key_actions[action_key]
                    globals()[name] = not globals()[name]
                    if name == 'show_Fisheye':
                        if globals()[name] and not _calib_loaded:
                            print("Fisheye toggle ON, but calibration_params.npz not loaded.")
                        else:
                            print(f"Fisheye enabled: {globals()[name]}")

            if not show_Params:
                closeWindow("Binary Image")
                closeWindow("Sharpened Image")
    except KeyboardInterrupt:
        print("\nInterrupted. Closing windows.")
        cv2.destroyAllWindows()

    sys.exit()
