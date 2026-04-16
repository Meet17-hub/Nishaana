import base64
import os
from math import sqrt
from pathlib import Path
import torch
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

import cv2 as cv
import numpy as np

# Model loading - weights are in scripts_ml/ folder (parent of scripts/)
WEIGHTS_PATH = Path(__file__).parent.parent / "scripts_ml" / "1080p_model.pt"
_model = None

# Filtering thresholds to suppress spurious bullet detections
HOLE_CONF_THRESHOLD = 0.0
HOLE_RADIUS_MIN_FACTOR = 0.1 # relative to expected hole radius ratio
HOLE_RADIUS_MAX_FACTOR = 4.0
HOLE_MIN_DIAM_MM = 2.0  # ignore holes smaller than this physical diameter
# Known pellet diameter is fixed; allow small tolerance for detection noise.
HOLE_DIAMETER_ERROR_MARGIN_MM = 0.40

# If your model's hole class name doesn't include these substrings, the code can
# incorrectly reject all holes. Set this to None to accept any non-black class.
# Example (strict): HOLE_CLASS_TOKENS = ("hole", "impact")
HOLE_CLASS_TOKENS: tuple[str, ...] | None = None

# Set env var DEBUG_DETECTIONS=1 to print detected class names/confidences.
DEBUG_DETECTIONS = os.environ.get("DEBUG_DETECTIONS") == "1"
USE_ILLUMINATION_NORMALIZATION = False

_printed_yolo_names = False

# Scale factors for black radii derived from bbox (axis-specific). >1 enlarges; <1 shrinks.
BLACK_RADIUS_SCALE_X = 1.00
BLACK_RADIUS_SCALE_Y = 1.00

# Additional scale for derived outer radii (post black-ratio expansion)
# Use different X/Y scales to make yellow ellipse wider horizontally
OUTER_RADIUS_SCALE_X = 0.98  # horizontal stretch
OUTER_RADIUS_SCALE_Y = 0.98  # vertical shrink

# Shift outer ring center relative to black center (pixels; approximate 1cm offset)
# This is used to visually align the outer ring overlay when the camera/warp introduces
# a small systematic offset, while scoring remains anchored to the black center.
OUTER_CENTER_SHIFT_X = 10  # ~1cm at typical resolution
OUTER_CENTER_SHIFT_Y = 0

# Camera rotation correction (legacy path).
# If frames are preprocessed (undistort + wrap to 640x640), we skip rotation.
CAMERA_ROTATE = None


def load_model():
    global _model
    if _model is None:
        if YOLO is None:
            raise RuntimeError("ultralytics not available; install to run scoring")
        if not WEIGHTS_PATH.exists():
            raise FileNotFoundError(f"Weights not found at {WEIGHTS_PATH}")
        _model = YOLO(str(WEIGHTS_PATH))
    return _model


# Air pistol geometry
PISTOL_RING_RATIOS = {
    10: 0.0739,
    9: 0.1768,
    8: 0.2796,
    7: 0.3827,
    6: 0.4855,
    5: 0.5884,
    4: 0.6913,
    3: 0.7942,
    2: 0.8970,
    1: 1.0100,
}

PISTOL_BLACK_RATIO = PISTOL_RING_RATIOS[7]
PISTOL_OUTER_MM = 77.75
PISTOL_HOLE_DIAM_MM = 4.32
PISTOL_HOLE_RADIUS_RATIO = (PISTOL_HOLE_DIAM_MM / 2.0) / PISTOL_OUTER_MM
PISTOL_CENTER_SHIFT_Y_MM = 0  # no shift; rely on detected black center
PISTOL_CENTER_SHIFT_X_MM = 0   # no shift; rely on detected black center
PISTOL_CENTER_SHIFT_Y_RATIO = PISTOL_CENTER_SHIFT_Y_MM / PISTOL_OUTER_MM
PISTOL_CENTER_SHIFT_X_RATIO = PISTOL_CENTER_SHIFT_X_MM / PISTOL_OUTER_MM


# Air rifle geometry
RIFLE_RING_RATIOS = {
    10: 0.01099,
    9: 0.12088,
    8: 0.23077,
    7: 0.34066,
    6: 0.45055,
    5: 0.56044,
    4: 0.67033,
    3: 0.78022,
    2: 0.89011,
    1: 1.0000,
}

RIFLE_BLACK_RATIO = RIFLE_RING_RATIOS[4]
RIFLE_OUTER_MM = 22.75
RIFLE_HOLE_DIAM_MM = 3.41  # 1.5 ring widths (1.5 × 2.275mm)
RIFLE_HOLE_RADIUS_RATIO = (RIFLE_HOLE_DIAM_MM / 2.0) / RIFLE_OUTER_MM


def box_center_and_radius(box):
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    r = max(x2 - x1, y2 - y1) / 2.0
    return cx, cy, r


def _fit_ellipse_from_contour(contour):
    """Fit an ellipse to a contour.

    Returns (cx, cy, a, b, angle_deg) where a/b are semi-axis lengths.
    Returns None if an ellipse can't be fit.
    """
    if contour is None:
        return None
    # OpenCV requires at least 5 points to fit an ellipse.
    if len(contour) < 5:
        return None
    try:
        (cx, cy), (maj, min_), angle = cv.fitEllipse(contour)
        a = float(maj) / 2.0
        b = float(min_) / 2.0
        if a <= 0.0 or b <= 0.0:
            return None
        return float(cx), float(cy), a, b, float(angle)
    except Exception:
        return None


def _circular_normalized_radius(dx, dy, r):
    if r is None or r <= 0.0:
        return float("inf")
    return sqrt(dx * dx + dy * dy) / float(r)


def _clamp(value, lo, hi):
    return max(lo, min(value, hi))


def _illumination_normalize_bgr(frame_bgr):
    """Normalize illumination using LAB+CLAHE and homomorphic-style correction."""
    if frame_bgr is None or frame_bgr.size == 0:
        return frame_bgr

    h, w = frame_bgr.shape[:2]
    if h < 8 or w < 8:
        return frame_bgr

    # 1) LAB + CLAHE on luminance
    lab = cv.cvtColor(frame_bgr, cv.COLOR_BGR2LAB)
    l, a, b = cv.split(lab)
    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_eq = clahe.apply(l)

    # 2) Homomorphic-style correction: divide by low-frequency illumination field
    l_float = l_eq.astype(np.float32) + 1.0
    blur_k = max(31, int(round(min(h, w) * 0.08)))
    if blur_k % 2 == 0:
        blur_k += 1
    illum = cv.GaussianBlur(l_float, (blur_k, blur_k), 0)
    illum = np.maximum(illum, 1.0)

    l_homo = l_float / illum
    l_norm = cv.normalize(l_homo, None, 0, 255, cv.NORM_MINMAX).astype(np.uint8)

    out_lab = cv.merge((l_norm, a, b))
    return cv.cvtColor(out_lab, cv.COLOR_LAB2BGR)


def _validate_hole_shape(frame_gray, hx, hy, hr, min_circularity=0.55, min_aspect_ratio=0.6):
    """
    Validate if a detected hole is actually circular (not noise/scratches).
    
    Args:
        frame_gray: Grayscale frame
        hx, hy, hr: Hole center x, y and radius
        min_circularity: Minimum circularity (0-1), 1.0 = perfect circle
        min_aspect_ratio: Minimum width/height ratio, ensures not too elongated
    
    Returns:
        True if hole passes circularity and aspect ratio checks
    """
    try:
        # Extract region around hole
        x1 = max(0, int(hx - hr - 5))
        y1 = max(0, int(hy - hr - 5))
        x2 = min(frame_gray.shape[1], int(hx + hr + 5))
        y2 = min(frame_gray.shape[0], int(hy + hr + 5))
        
        roi = frame_gray[y1:y2, x1:x2]
        if roi.size == 0:
            return True  # Can't validate, assume valid
        
        # Create binary mask around the detected hole
        h, w = roi.shape
        cy, cx = int(hy - y1), int(hx - x1)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv.circle(mask, (cx, cy), int(hr + 2), 255, -1)
        
        # Find contours in ROI
        cnts, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return True
        
        # Get largest contour
        cnt = max(cnts, key=cv.contourArea)
        area = cv.contourArea(cnt)
        peri = cv.arcLength(cnt, True)
        
        if peri == 0:
            return True
        
        # Check circularity: 4*pi*area / perimeter^2
        # Circle = 1.0, lower values = less circular
        circularity = 4 * np.pi * area / (peri * peri)
        
        if circularity < min_circularity:
            if DEBUG_DETECTIONS:
                print(f"[Shape Validation] Hole at ({hx:.1f}, {hy:.1f}) rejected: circularity={circularity:.2f} < {min_circularity}", flush=True)
            return False
        
        # Check aspect ratio: must be roughly circular (not stretched)
        if len(cnt) >= 5:
            ellipse = cv.fitEllipse(cnt)
            (_, _), (w_ell, h_ell), _ = ellipse
            ratio = min(w_ell, h_ell) / max(w_ell, h_ell) if max(w_ell, h_ell) > 0 else 0
            
            if ratio < min_aspect_ratio:
                if DEBUG_DETECTIONS:
                    print(f"[Shape Validation] Hole at ({hx:.1f}, {hy:.1f}) rejected: aspect_ratio={ratio:.2f} < {min_aspect_ratio}", flush=True)
                return False
        
        if DEBUG_DETECTIONS:
            print(f"[Shape Validation] Hole at ({hx:.1f}, {hy:.1f}) PASSED: circularity={circularity:.2f}, aspect_ratio={ratio:.2f}", flush=True)
        
        return True
    except Exception as e:
        if DEBUG_DETECTIONS:
            print(f"[Shape Validation] Error validating hole: {e}", flush=True)
        return True  # On error, assume valid







def _black_contour_center_px(frame, black_box):
    """Estimate center and radius of the black region using contour centroid.

    Returns (cx, cy, r_px) in full-frame pixel coordinates, or None if not found.
    r_px is estimated from contour area (area = pi*r^2).
    """
    if black_box is None:
        return None

    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [float(v) for v in black_box]
    pad = int(0.05 * max(x2 - x1, y2 - y1))

    ix1 = max(0, int(round(x1)) - pad)
    iy1 = max(0, int(round(y1)) - pad)
    ix2 = min(w, int(round(x2)) + pad)
    iy2 = min(h, int(round(y2)) + pad)
    if ix2 <= ix1 or iy2 <= iy1:
        return None

    roi = frame[iy1:iy2, ix1:ix2]
    if roi.size == 0:
        return None

    gray = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
    gray = cv.GaussianBlur(gray, (5, 5), 0)

    # Black pixels -> white in mask
    _, mask = cv.threshold(gray, 0, 255, cv.THRESH_BINARY_INV + cv.THRESH_OTSU)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv.morphologyEx(mask, cv.MORPH_OPEN, kernel, iterations=1)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv.contourArea)
    if cv.contourArea(largest) < 50:
        return None

    m = cv.moments(largest)
    if m.get("m00", 0.0) != 0.0:
        cx = float(m["m10"] / m["m00"]) + ix1
        cy = float(m["m01"] / m["m00"]) + iy1
        area = float(cv.contourArea(largest))
        r_est = float(np.sqrt(max(area, 1.0) / np.pi))
        return cx, cy, r_est

    (cx, cy), r_est = cv.minEnclosingCircle(largest)
    return float(cx) + ix1, float(cy) + iy1, float(r_est)


def _black_contour_geometry_px(frame, black_box):
    """Estimate black contour center and (optionally) ellipse geometry.

    Returns (cx, cy, r_est, ellipse)
      - (cx, cy): center in full-frame pixel coordinates (ellipse center preferred)
      - r_est: radius estimate from contour area (fallback to enclosing circle)
      - ellipse: (cx, cy, a, b, angle_deg) in full-frame pixel coordinates, or None
    """
    if black_box is None:
        return None

    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [float(v) for v in black_box]
    pad = int(0.05 * max(x2 - x1, y2 - y1))

    ix1 = max(0, int(round(x1)) - pad)
    iy1 = max(0, int(round(y1)) - pad)
    ix2 = min(w, int(round(x2)) + pad)
    iy2 = min(h, int(round(y2)) + pad)
    if ix2 <= ix1 or iy2 <= iy1:
        return None

    roi = frame[iy1:iy2, ix1:ix2]
    if roi.size == 0:
        return None

    gray = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
    gray = cv.GaussianBlur(gray, (5, 5), 0)

    # Black pixels -> white in mask
    _, mask = cv.threshold(gray, 0, 255, cv.THRESH_BINARY_INV + cv.THRESH_OTSU)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv.morphologyEx(mask, cv.MORPH_OPEN, kernel, iterations=1)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv.contourArea)
    area = float(cv.contourArea(largest))
    if area < 50:
        return None

    ellipse = _fit_ellipse_from_contour(largest)
    if ellipse is not None:
        ex, ey, ea, eb, ang = ellipse
        ellipse = (ex + ix1, ey + iy1, ea, eb, ang)
        cx = float(ellipse[0])
        cy = float(ellipse[1])
        r_est = float((ea + eb) * 0.5)
        return cx, cy, r_est, ellipse

    m = cv.moments(largest)
    if m.get("m00", 0.0) != 0.0:
        cx = float(m["m10"] / m["m00"]) + ix1
        cy = float(m["m01"] / m["m00"]) + iy1
        r_est = float(np.sqrt(max(area, 1.0) / np.pi))
        return cx, cy, r_est, None

    (cx0, cy0), r_est0 = cv.minEnclosingCircle(largest)
    cx = float(cx0) + ix1
    cy = float(cy0) + iy1
    r_est = float(r_est0)
    return cx, cy, r_est, None


def pistol_decimal_score(d_norm):
    """
    10m Air Pistol INTEGER scoring (no decimals).

    - Pellet edge scoring (already handled outside this function)
    - Returns whole numbers: 10, 9, 8 ... 0
    """

    edges = [
        (10, PISTOL_RING_RATIOS[10]),
        (9, PISTOL_RING_RATIOS[9]),
        (8, PISTOL_RING_RATIOS[8]),
        (7, PISTOL_RING_RATIOS[7]),
        (6, PISTOL_RING_RATIOS[6]),
        (5, PISTOL_RING_RATIOS[5]),
        (4, PISTOL_RING_RATIOS[4]),
        (3, PISTOL_RING_RATIOS[3]),
        (2, PISTOL_RING_RATIOS[2]),
        (1, PISTOL_RING_RATIOS[1]),
        (0, 1.0),
    ]

    for score_value, radius in edges:
        if d_norm <= radius:
            return int(score_value)

    return 0


def rifle_decimal_score(d_norm):
    """
    ISSF 10m Air Rifle decimal scoring.

    - 10-ring is true decimal zone (10.0 → 10.9)
    - 10.9 only at absolute center
    - 10.0 exactly at 10-ring edge
    - Outside 10-ring → linear interpolation between integer rings
    """

    r10 = RIFLE_RING_RATIOS[10]

    # ----------------------------------
    # Inside true 10-ring → 10.0 to 10.9
    # ----------------------------------
    if d_norm <= r10:
        # 10.9 at center (d_norm = 0)
        # 10.0 at edge of 10-ring (d_norm = r10)
        t = d_norm / r10
        score = 10.9 - (0.9 * t)
        return round(score, 1)

    # ----------------------------------
    # Outside 10-ring → ring interpolation
    # ----------------------------------
    edges = [
        (9, RIFLE_RING_RATIOS[9]),
        (8, RIFLE_RING_RATIOS[8]),
        (7, RIFLE_RING_RATIOS[7]),
        (6, RIFLE_RING_RATIOS[6]),
        (5, RIFLE_RING_RATIOS[5]),
        (4, RIFLE_RING_RATIOS[4]),
        (3, RIFLE_RING_RATIOS[3]),
        (2, RIFLE_RING_RATIOS[2]),
        (1, RIFLE_RING_RATIOS[1]),
        (0, 1.0),
    ]

    prev_score = 10
    prev_radius = r10

    for score_out, r_out in edges:
        if prev_radius < d_norm <= r_out:
            t = (d_norm - prev_radius) / (r_out - prev_radius)
            score = prev_score - t * (prev_score - score_out)
            return round(max(0.0, score), 1)

        prev_score = score_out
        prev_radius = r_out

    return 0.0


def _annotate_and_score(frame, shooting_mode="rifle"):
    global _printed_yolo_names
    mode = (shooting_mode or "rifle").lower()
    model = load_model()

    # If input is already a 640x640 wrapped view, do not rotate.
    # Otherwise keep legacy rotation behavior.
    if CAMERA_ROTATE is not None and (frame.shape[0] != 640 or frame.shape[1] != 640):
        frame_proc = cv.rotate(frame, CAMERA_ROTATE)
    else:
        frame_proc = frame

    infer_frame = frame_proc
    if USE_ILLUMINATION_NORMALIZATION:
        try:
            infer_frame = _illumination_normalize_bgr(frame_proc)
        except Exception:
            infer_frame = frame_proc

    res = model(infer_frame, conf=0.12)[0]
    names = res.names

    if DEBUG_DETECTIONS and not _printed_yolo_names:
        print("YOLO class names:", names, flush=True)
        _printed_yolo_names = True

    black_box = None
    black_area = 0.0
    black_center_px = None
    black_center_radius = None
    black_ellipse = None
    hole_detections = []  # store (cx, cy, r_px)

    if res.boxes is not None:
        for i in range(len(res.boxes)):
            cls_id = int(res.boxes.cls[i])
            cls_name = names[cls_id].lower()
            x1, y1, x2, y2 = res.boxes.xyxy[i].cpu().numpy()

            conf = None
            try:
                conf = float(res.boxes.conf[i])
            except Exception:
                conf = None

            if cls_name == "black_contour":
                area = float(max(0.0, x2 - x1) * max(0.0, y2 - y1))
                if area >= black_area:
                    black_area = area
                    black_box = res.boxes.xyxy[i].cpu().numpy()
            else:
                # Optional class-name filtering. If HOLE_CLASS_TOKENS is None, accept
                # any non-black class as a hole candidate.
                if HOLE_CLASS_TOKENS is not None:
                    is_hole_like = any(token in cls_name for token in HOLE_CLASS_TOKENS)
                    if not is_hole_like:
                        continue

                if conf is not None and conf < HOLE_CONF_THRESHOLD:
                    continue

                cx, cy, r = box_center_and_radius(res.boxes.xyxy[i].cpu().numpy())
                hole_detections.append((cx, cy, r))

                if DEBUG_DETECTIONS:
                    print(f"hole cand: cls={cls_name} conf={conf} r={r:.2f}", flush=True)

    if black_box is not None:
        bc = _black_contour_geometry_px(infer_frame, black_box)
        if bc is not None:
            black_center_px = (bc[0], bc[1])
            black_center_radius = bc[2]
            black_ellipse = bc[3]

    R_outer_x = None
    R_outer_y = None
    R_black_x = None
    R_black_y = None
    center_px = None

    if black_box is not None:
        if black_ellipse is not None:
            # Semi-axes from fitted ellipse (used only to estimate radius scale).
            _, _, a, b, _ang = black_ellipse
            R_black_x = float(max(1.0, a)) * BLACK_RADIUS_SCALE_X
            R_black_y = float(max(1.0, b)) * BLACK_RADIUS_SCALE_Y
        else:
            bx1, by1, bx2, by2 = black_box
            bw = max(1.0, bx2 - bx1)
            bh = max(1.0, by2 - by1)
            # Elliptical radii from bbox axes with axis-specific scale
            R_black_x = 0.5 * bw * BLACK_RADIUS_SCALE_X
            R_black_y = 0.5 * bh * BLACK_RADIUS_SCALE_Y

        if mode == "pistol":
            R_outer_x = (R_black_x / PISTOL_BLACK_RATIO) * OUTER_RADIUS_SCALE_X
            R_outer_y = (R_black_y / PISTOL_BLACK_RATIO) * OUTER_RADIUS_SCALE_Y
        else:
            R_outer_x = (R_black_x / RIFLE_BLACK_RATIO) * OUTER_RADIUS_SCALE_X
            R_outer_y = (R_black_y / RIFLE_BLACK_RATIO) * OUTER_RADIUS_SCALE_Y

        if black_center_px is not None:
            center_px = black_center_px
        else:
            center_px = box_center_and_radius(black_box)[:2]

    if (R_outer_x is None or R_outer_y is None) or center_px is None:
        return {
            "status": "no_target",
            "message": "Black contour not detected",
            "scored_shots": [],
            "total_score": 0,
            "annotated_image": None,
            "mode": mode,
        }

    if mode == "pistol":
        center_px = (
            center_px[0] + PISTOL_CENTER_SHIFT_X_RATIO * R_outer_x,
            center_px[1] + PISTOL_CENTER_SHIFT_Y_RATIO * R_outer_y,
        )

    # Scoring should be based on the black contour center.
    score_center = (center_px[0], center_px[1])

    # With proper undistort+wrap (perfect circle), keep overlay centered as well.
    outer_center = (center_px[0], center_px[1])

    annotated = frame_proc.copy()
    # Draw center dot (bright green)
    cv.circle(annotated, (int(score_center[0]), int(score_center[1])), 3, (0, 255, 0), -1)
    if R_black_x is not None and R_black_y is not None:
        r_black = (R_black_x + R_black_y) / 2.0
        cv.circle(annotated, (int(score_center[0]), int(score_center[1])), int(max(1.0, r_black)), (255, 0, 0), 2)
    if R_outer_x is not None and R_outer_y is not None:
        r_outer = (R_outer_x + R_outer_y) / 2.0
        cv.circle(annotated, (int(outer_center[0]), int(outer_center[1])), int(max(1.0, r_outer)), (0, 255, 255), 2)

    scored_shots = []
    center_x = float(score_center[0])
    center_y = float(score_center[1])
    total_score = 0.0

    if mode == "pistol":
        hole_radius_ratio = PISTOL_HOLE_RADIUS_RATIO
        hole_diam_mm = PISTOL_HOLE_DIAM_MM
        outer_mm = PISTOL_OUTER_MM
        score_fn = pistol_decimal_score
        min_hole_radius_ratio = (HOLE_MIN_DIAM_MM / 2.0) / PISTOL_OUTER_MM
    else:
        hole_radius_ratio = RIFLE_HOLE_RADIUS_RATIO
        hole_diam_mm = RIFLE_HOLE_DIAM_MM
        outer_mm = RIFLE_OUTER_MM
        score_fn = rifle_decimal_score
        min_hole_radius_ratio = (HOLE_MIN_DIAM_MM / 2.0) / RIFLE_OUTER_MM

    # Use circularized outer radius for sizing/scoring (assumes wrapped view is a circle).
    outer_radius_px = (R_outer_x + R_outer_y) / 2.0
    min_hole_radius_px = min_hole_radius_ratio * outer_radius_px
    expected_hole_radius_px = hole_radius_ratio * outer_radius_px
    hole_radius_min_px = expected_hole_radius_px * HOLE_RADIUS_MIN_FACTOR
    hole_radius_max_px = expected_hole_radius_px * HOLE_RADIUS_MAX_FACTOR
    hole_radius_tol_ratio = (HOLE_DIAMETER_ERROR_MARGIN_MM / 2.0) / outer_mm
    hole_radius_tol_px = hole_radius_tol_ratio * outer_radius_px
    scoring_hole_radius_min_px = max(min_hole_radius_px, expected_hole_radius_px - hole_radius_tol_px)
    scoring_hole_radius_max_px = expected_hole_radius_px + hole_radius_tol_px

    # ✅ NEW: Validate hole shapes (filter out noise/scratches based on circularity)
    validated_holes = []
    frame_gray = cv.cvtColor(infer_frame, cv.COLOR_BGR2GRAY) if len(infer_frame.shape) == 3 else infer_frame
    
    for hx, hy, hr in hole_detections:
        # Quick size check first
        if hr < min_hole_radius_px or hr < hole_radius_min_px or hr > hole_radius_max_px:
            continue
        
        # Shape validation: circularity + aspect ratio
        if _validate_hole_shape(frame_gray, hx, hy, hr, min_circularity=0.55, min_aspect_ratio=0.6):
            validated_holes.append((hx, hy, hr))

    if validated_holes:
        clamped_radii = [
            _clamp(float(hr), scoring_hole_radius_min_px, scoring_hole_radius_max_px)
            for _, _, hr in validated_holes
        ]
        effective_hole_radius_px = float(np.median(clamped_radii))
    else:
        effective_hole_radius_px = expected_hole_radius_px
    effective_hole_radius_ratio = effective_hole_radius_px / outer_radius_px

    for hx, hy, hr in validated_holes:

        dx = hx - score_center[0]
        dy = hy - score_center[1]

        d_norm = _circular_normalized_radius(dx, dy, outer_radius_px)
        d_norm_edge = max(d_norm - effective_hole_radius_ratio, 0.0)
        score = score_fn(d_norm_edge)

        total_score += score
        dx = hx - center_x
        dy = center_y - hy   # invert Y for screen coords
        angle = float(np.degrees(np.arctan2(dy, dx)))

        scored_shots.append({
    "x": int(hx),
    "y": int(hy),
    "r": float(hr),
    "score": float(score),

    # 🔥 NEW (for arrows)
    "center_x": center_x,
    "center_y": center_y,
    "dx": float(dx),
    "dy": float(dy),
    "angle": angle
})

    annotated_b64 = None
    try:
        annotated_out = annotated
        # Rotate back to original camera orientation for UI if we rotated in
        if CAMERA_ROTATE is not None and (frame.shape[0] != 640 or frame.shape[1] != 640):
            annotated_out = cv.rotate(annotated, cv.ROTATE_90_COUNTERCLOCKWISE)
        ok, buf = cv.imencode(".jpg", annotated_out)
        if ok:
            annotated_b64 = "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")
    except Exception:
        annotated_b64 = None

    return {
    "status": "success",
    "mode": mode,
    "total_score": float(round(total_score, 1)),
    "effective_hole_diameter_mm": float(round(2.0 * effective_hole_radius_px * outer_mm / outer_radius_px, 3)),
    "hole_diameter_nominal_mm": float(hole_diam_mm),
    "hole_diameter_error_margin_mm": float(HOLE_DIAMETER_ERROR_MARGIN_MM),
    "center": {
        "x": center_x,
        "y": center_y
    },
    "scored_shots": scored_shots,
    "annotated_image": annotated_b64,
}


def get_scores_from_hardcoded_image(shooting_mode="rifle"):
    image_path = Path(__file__).parent / "latest_warped.jpg"
    frame = cv.imread(str(image_path))
    if frame is None:
        return {"status": "error", "message": "Could not load test image."}
    return _annotate_and_score(frame, shooting_mode)


def get_scores_from_bytes(image_bytes, shooting_mode="rifle"):
    npimg = np.frombuffer(image_bytes, np.uint8)
    frame = cv.imdecode(npimg, cv.IMREAD_COLOR)
    if frame is None:
        return {"status": "error", "message": "Could not decode image."}
    return _to_native(_annotate_and_score(frame, shooting_mode))


def _to_native(obj):
    """Recursively convert numpy/float32 scalars to built-in Python types for JSON."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    if isinstance(obj, (np.generic, np.bool_)):
        return obj.item()
    return obj


if __name__ == "__main__":
    result = get_scores_from_hardcoded_image("rifle")
    print(result)
