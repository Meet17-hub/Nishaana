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

# ============== SUPER IMAGE ENHANCEMENT ==============
# Enable/disable 2x image upscaling using super_image library
# Improves detection accuracy for small targets/holes
# Set to False to disable (faster processing)
USE_SUPER_IMAGE_ENHANCEMENT = False
SUPER_IMAGE_SCALE = 2  # Upscale factor (2x, 3x, 4x)

try:
    from super_image import EdsrModel, ImageLoader
    from PIL import Image
    _super_image_model = None
    _have_super_image = True
except ImportError:
    _have_super_image = False
    _super_image_model = None
    print("[model_prediction] super_image not installed. Run: pip install super-image", flush=True)

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

# Suppress near-duplicate/noisy detections that are only a few pixels apart.
# Rifle holes often get multiple overlapping boxes, so the merge distance needs
# to be large enough to collapse those repeats into one scored shot.
NEIGHBOR_NOISE_DISTANCE_PX = 12.0

# Visual debugging overlays on annotated frames.
SHOW_DEBUG_OVERLAYS = False

# ============== CONTOUR-BASED 10-POINT SCORING ==============
# Enable/disable contour-based refinement for shots scoring >= 9.0
# This runs BOTH YOLO and contour detection, compares results for higher precision.
# Set to False to disable this feature and use only YOLO detection.
USE_CONTOUR_10_SCORING = True

# Threshold percentile for contour detection (lower = more sensitive to dark pixels)
CONTOUR_THRESHOLD_PERCENTILE = 15

# Minimum score for contour refinement to activate (10.0 = only ring 10 shots get extra refinement)
CONTOUR_ACTIVATION_MIN_SCORE = 10.0

# Minimum circularity (0-1) to trust contour result over YOLO
# Set to 0.0 to disable circularity check (wrap_test.py doesn't use it)
CONTOUR_MIN_CIRCULARITY = 0.10

# Maximum distance (px) between YOLO and contour centers before logging warning
CONTOUR_MAX_DISAGREEMENT_PX = 5.0

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


def _load_super_image_model():
    """Load super_image EDSR model for 2x upscaling."""
    global _super_image_model
    if not _have_super_image:
        return None
    if _super_image_model is None:
        try:
            # EDSR is a good balance of quality and speed
            _super_image_model = EdsrModel.from_pretrained('eugenesiow/edsr-base', scale=SUPER_IMAGE_SCALE)
            if torch.cuda.is_available():
                _super_image_model = _super_image_model.cuda()
            print(f"[model_prediction] Loaded super_image EDSR model (scale={SUPER_IMAGE_SCALE}x)", flush=True)
        except Exception as e:
            print(f"[model_prediction] Failed to load super_image model: {e}", flush=True)
            return None
    return _super_image_model


def _enhance_image_2x(frame: np.ndarray) -> np.ndarray:
    """Enhance image using super_image library for 2x upscaling.
    
    Args:
        frame: Input BGR image (numpy array)
    
    Returns:
        Enhanced BGR image (2x resolution) or original if enhancement fails
    """
    if not USE_SUPER_IMAGE_ENHANCEMENT or not _have_super_image:
        return frame
    
    model = _load_super_image_model()
    if model is None:
        return frame
    
    try:
        # Convert BGR to RGB PIL Image
        rgb_frame = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_frame)
        
        # Prepare input for model
        inputs = ImageLoader.load_image(pil_image)
        if torch.cuda.is_available():
            inputs = inputs.cuda()
        
        # Run enhancement
        with torch.no_grad():
            preds = model(inputs)
        
        # Convert back to numpy BGR
        output = preds.squeeze(0).permute(1, 2, 0).cpu().numpy()
        output = (output * 255.0).clip(0, 255).astype(np.uint8)
        enhanced = cv.cvtColor(output, cv.COLOR_RGB2BGR)
        
        if DEBUG_DETECTIONS:
            print(f"[super_image] Enhanced {frame.shape[:2]} -> {enhanced.shape[:2]}", flush=True)
        
        return enhanced
    except Exception as e:
        if DEBUG_DETECTIONS:
            print(f"[super_image] Enhancement failed: {e}", flush=True)
        return frame


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

# Ring 10 OUTER boundary (10-ring / X-ring boundary, NOT the inner dot)
# Rifle: 5mm diameter = 2.5mm radius, ratio = 2.5/22.75 = 0.1099
# Pistol: 11.5mm diameter = 5.75mm radius, ratio = 5.75/77.75 = 0.0739
RIFLE_RING_10_OUTER_RATIO = 2.5 / RIFLE_OUTER_MM  # = 0.1099
PISTOL_RING_10_OUTER_RATIO = 5.75 / PISTOL_OUTER_MM  # = 0.0739

# Rifle hole center refinement - uses thresholding to find precise center within black contour
# Set to False to disable this feature
RIFLE_HOLE_CENTER_REFINEMENT = True
RIFLE_HOLE_THRESHOLD = 80  # Threshold value for detecting dark hole pixels (0-255)


def box_center_and_radius(box):
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    r = max(x2 - x1, y2 - y1) / 2.0
    return cx, cy, r


def _refine_hole_center_rifle(frame, hx, hy, hr, black_center, black_radius):
    """Refine hole center for rifle mode using thresholding within black contour.
    
    Only processes holes that are within the black contour region.
    Uses threshold to find dark pixels and fits circle/ellipse to get precise center.
    
    Args:
        frame: The image frame (BGR)
        hx, hy, hr: Hole center x, y and radius from YOLO detection
        black_center: (cx, cy) of black contour center
        black_radius: Estimated radius of black contour
    
    Returns:
        (refined_hx, refined_hy) or original (hx, hy) if refinement fails
    """
    if not RIFLE_HOLE_CENTER_REFINEMENT:
        return hx, hy
    
    if black_center is None or black_radius is None or black_radius <= 0:
        return hx, hy
    
    # Check if hole is within black contour region
    bcx, bcy = black_center
    dist_from_black_center = sqrt((hx - bcx)**2 + (hy - bcy)**2)
    if dist_from_black_center > black_radius * 1.2:  # Allow 20% margin
        return hx, hy  # Hole is outside black region, skip refinement
    
    h, w = frame.shape[:2]
    
    # Extract ROI around the detected hole (with padding)
    pad = int(hr * 1.5)
    ix1 = max(0, int(hx - pad))
    iy1 = max(0, int(hy - pad))
    ix2 = min(w, int(hx + pad))
    iy2 = min(h, int(hy + pad))
    
    if ix2 <= ix1 or iy2 <= iy1:
        return hx, hy
    
    roi = frame[iy1:iy2, ix1:ix2]
    if roi.size == 0:
        return hx, hy
    
    # Convert to grayscale
    if len(roi.shape) == 3:
        gray = cv.cvtColor(roi, cv.COLOR_BGR2GRAY)
    else:
        gray = roi
    
    # Apply threshold to find dark (hole) pixels
    _, mask = cv.threshold(gray, RIFLE_HOLE_THRESHOLD, 255, cv.THRESH_BINARY_INV)
    
    # Clean up mask
    kernel = np.ones((3, 3), np.uint8)
    mask = cv.morphologyEx(mask, cv.MORPH_OPEN, kernel, iterations=1)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel, iterations=1)
    
    # Find contours
    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    if not contours:
        return hx, hy
    
    # Find the contour closest to the original hole center (relative to ROI)
    roi_hx = hx - ix1
    roi_hy = hy - iy1
    
    best_contour = None
    best_dist = float('inf')
    
    for cnt in contours:
        area = cv.contourArea(cnt)
        if area < 20:  # Skip tiny noise
            continue
        
        # Get contour center
        m = cv.moments(cnt)
        if m.get("m00", 0.0) == 0.0:
            continue
        cnt_cx = m["m10"] / m["m00"]
        cnt_cy = m["m01"] / m["m00"]
        
        dist = sqrt((cnt_cx - roi_hx)**2 + (cnt_cy - roi_hy)**2)
        if dist < best_dist:
            best_dist = dist
            best_contour = cnt
    
    if best_contour is None:
        return hx, hy

    # Try to fit ellipse for more precise center
    if len(best_contour) >= 5:
        try:
            (ex, ey), (maj, min_), angle = cv.fitEllipse(best_contour)
            refined_hx = ex + ix1
            refined_hy = ey + iy1
            return float(refined_hx), float(refined_hy)
        except Exception:
            pass

    # Fallback to moments-based center
    m = cv.moments(best_contour)
    if m.get("m00", 0.0) != 0.0:
        refined_hx = (m["m10"] / m["m00"]) + ix1
        refined_hy = (m["m01"] / m["m00"]) + iy1
        return float(refined_hx), float(refined_hy)
    
    return hx, hy


def _rifle_decimal_score_all_rings(
    d_norm_edge: float,
    outer_radius_px: float,
    center_dist_px: float,
    pellet_radius_px: float,
    mode: str = "rifle",
) -> float:
    """Calculate decimal score for all rings using continuous linear interpolation.
    Matches ISSF logic precisely by interpolating between standard ring boundaries.
    """
    ring_ratios = PISTOL_RING_RATIOS if mode == "pistol" else RIFLE_RING_RATIOS

    d = float(d_norm_edge)
    if d < 0.0:
        d = 0.0
    if d >= 1.0:
        return 0.0

    r10 = float(ring_ratios[10])

    # Inside true 10-ring → 10.0 to 10.9
    if d <= r10:
        t = d / r10
        score = 10.9 - (0.9 * t)
        return round(score, 1)

    # Outside 10-ring → ring interpolation
    edges = [
        (9, float(ring_ratios[9])),
        (8, float(ring_ratios[8])),
        (7, float(ring_ratios[7])),
        (6, float(ring_ratios[6])),
        (5, float(ring_ratios[5])),
        (4, float(ring_ratios[4])),
        (3, float(ring_ratios[3])),
        (2, float(ring_ratios[2])),
        (1, float(ring_ratios[1])),
        (0, 1.0),
    ]

    prev_score = 10
    prev_radius = r10

    for score_out, r_out in edges:
        if prev_radius < d <= r_out:
            t = (d - prev_radius) / (r_out - prev_radius)
            score = prev_score - t * (prev_score - score_out)
            return round(max(0.0, score), 1)

        prev_score = score_out
        prev_radius = r_out

    return 0.0

def _contour_decimal_ten_score(center_distance_px: float, ring10_radius_px: float, pellet_radius_px: float) -> float | None:
    """Calculate decimal 10-score using discrete bands.
    
    Returns score in range 10.0 to 10.9 based on how close shot is to center.
    Uses 10 discrete bands:
        - Inner edge just touching ring 10 outer edge => 10.0
        - Perfect center => 10.9
    
    Args:
        center_distance_px: Distance from shot center to target center (pixels)
        ring10_radius_px: Radius of ring 10 OUTER boundary (pixels) - where ring 10 ends / ring 9 begins
        pellet_radius_px: Radius of the pellet hole (pixels)
    
    Returns:
        Score (10.0, 10.1, 10.2, ..., 10.9) or None if outside ring 10
    """
    if ring10_radius_px <= 0.0 or center_distance_px < 0.0 or pellet_radius_px < 0.0:
        return None
    
    # Maximum center distance where pellet inner edge still touches ring 10
    max_center_for_ten = ring10_radius_px + pellet_radius_px
    if center_distance_px > max_center_for_ten:
        return None
    
    # Progress: 0.0 = inner edge just touching ring 10 boundary, 1.0 = perfect center
    progress = 1.0 - (center_distance_px / max_center_for_ten)
    progress = max(0.0, min(1.0, progress))
    
    # 10 discrete bands: 10.0, 10.1, 10.2, ..., 10.9
    band_index = min(int(progress * 10.0), 9)
    return round(10.0 + (band_index * 0.1), 1)


def _contour_refine_shot_center(frame, yolo_x: float, yolo_y: float, search_radius: float) -> tuple | None:
    """Refine shot center using contour-based detection (from wrap_test.py approach).
    
    Uses thresholding + contour moments for sub-pixel precision shot center detection.
    Runs as parallel detection to YOLO for shots near center (score >= 9.0).
    
    Args:
        frame: The warped image frame (BGR)
        yolo_x, yolo_y: YOLO-detected shot center
        search_radius: Radius around YOLO center to search for shot
    
    Returns:
        (x, y, r, circularity) if detection succeeds, None otherwise
        - x, y: Refined shot center coordinates
        - r: Estimated radius from contour area
        - circularity: 0.0-1.0, how circular the detection is (1.0 = perfect circle)
    """
    if frame is None or frame.size == 0:
        return None
    
    h, w = frame.shape[:2]
    
    # Convert to grayscale
    if len(frame.shape) == 3:
        gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
    else:
        gray = frame
    
    # Define search ROI around YOLO detection
    sr = max(24, int(search_radius))
    x1 = max(0, int(yolo_x) - sr)
    x2 = min(w, int(yolo_x) + sr + 1)
    y1 = max(0, int(yolo_y) - sr)
    y2 = min(h, int(yolo_y) + sr + 1)
    
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    
    # Adaptive threshold based on ROI intensity (from wrap_test.py)
    roi_blur = cv.GaussianBlur(roi, (5, 5), 0)
    threshold_value = max(0.0, float(np.percentile(roi_blur, CONTOUR_THRESHOLD_PERCENTILE)) - 8.0)
    _, dark_mask = cv.threshold(roi_blur, threshold_value, 255, cv.THRESH_BINARY_INV)
    
    # Create radial mask to focus on area near YOLO detection
    roi_h, roi_w = roi.shape[:2]
    yy, xx = np.ogrid[:roi_h, :roi_w]
    cx_roi = float(yolo_x - x1)
    cy_roi = float(yolo_y - y1)
    radial_mask = ((xx - cx_roi) ** 2 + (yy - cy_roi) ** 2) <= float(sr * sr)
    dark_mask = np.where(radial_mask, dark_mask, 0).astype(np.uint8)
    
    # Clean up mask
    kernel = np.ones((3, 3), np.uint8)
    dark_mask = cv.morphologyEx(dark_mask, cv.MORPH_OPEN, kernel, iterations=1)
    dark_mask = cv.morphologyEx(dark_mask, cv.MORPH_CLOSE, kernel, iterations=2)
    
    # Find contours
    contours, _ = cv.findContours(dark_mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    
    # Find best contour: largest area that's close to YOLO center
    best_contour = None
    best_score = None
    
    for contour in contours:
        area = float(cv.contourArea(contour))
        if area < 8.0:  # Skip tiny noise
            continue
        
        m = cv.moments(contour)
        if m.get("m00", 0.0) == 0.0:
            continue
        
        shot_x = float(m["m10"] / m["m00"])
        shot_y = float(m["m01"] / m["m00"])
        distance_to_yolo = float(sqrt((shot_x - cx_roi)**2 + (shot_y - cy_roi)**2))
        
        if distance_to_yolo > sr:
            continue
        
        # Score: prefer larger area, penalize distance from YOLO center
        score = area - (0.35 * distance_to_yolo)
        if best_score is None or score > best_score:
            best_score = score
            best_contour = contour
    
    if best_contour is None:
        return None
    
    # Calculate circularity
    area = float(cv.contourArea(best_contour))
    perimeter = float(cv.arcLength(best_contour, True))
    circularity = 0.0
    if perimeter > 0:
        circularity = 4.0 * 3.14159 * area / (perimeter * perimeter)
        circularity = min(1.0, max(0.0, circularity))
    
    # Get precise center using moments
    m = cv.moments(best_contour)
    if m.get("m00", 0.0) == 0.0:
        return None
    
    shot_x = float(m["m10"] / m["m00"]) + x1
    shot_y = float(m["m01"] / m["m00"]) + y1
    shot_r = float(sqrt(max(area, 1.0) / 3.14159))
    
    # Try to fit ellipse for even more precise center (if enough points)
    if len(best_contour) >= 5:
        try:
            (ex, ey), (maj, min_), angle = cv.fitEllipse(best_contour)
            shot_x = float(ex) + x1
            shot_y = float(ey) + y1
        except Exception:
            pass
    
    return (shot_x, shot_y, shot_r, circularity)


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


def _suppress_neighbor_hole_noise(hole_list, min_distance_px=NEIGHBOR_NOISE_DISTANCE_PX):
    """Keep one detection per tiny neighborhood and suppress near-duplicate noise.

    Args:
        hole_list: iterable of (hx, hy, hr)
        min_distance_px: detections closer than this are treated as same local blob

    Returns:
        Filtered list of (hx, hy, hr), preferring larger radius per neighborhood.
    """
    if not hole_list:
        return []

    # Larger holes are preferred as primary representatives of a local cluster.
    ordered = sorted(hole_list, key=lambda h: float(h[2]), reverse=True)
    kept = []

    for hx, hy, hr in ordered:
        is_neighbor = False
        for kx, ky, _kr in kept:
            dx = float(hx) - float(kx)
            dy = float(hy) - float(ky)
            # Use a simple fixed distance — the dynamic formula was merging
            # legitimate second shots that happened to be close together.
            if (dx * dx + dy * dy) <= (float(min_distance_px) ** 2):
                is_neighbor = True
                break

        if not is_neighbor:
            kept.append((hx, hy, hr))

    return kept


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
            print(f"[Shape Validation] Hole at ({hx:.1f}, {hy:.1f}) PASSED: circularity={circularity:.2f}", flush=True)
        
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

    # Use the convex hull of the largest dark contour for all geometry computations.
    # Bullet holes at or near the edge of the black scoring disk create inward
    # indentations in the detected contour. These dents pull the ellipse-fitted
    # center toward the opposite side of the disk, mis-scoring EVERY shot on the
    # frame (one hole scores too high, the other too low). The convex hull removes
    # the indentations and recovers the true circular boundary of the disk.
    hull = cv.convexHull(largest)
    hull_area = float(cv.contourArea(hull))
    # Fall back to raw contour only if hull is degenerate (shouldn't happen in practice).
    fit_contour = hull if hull_area >= 50 else largest
    fit_area = hull_area if hull_area >= 50 else area

    ellipse = _fit_ellipse_from_contour(fit_contour)
    if ellipse is not None:
        ex, ey, ea, eb, ang = ellipse
        ellipse = (ex + ix1, ey + iy1, ea, eb, ang)
        cx = float(ellipse[0])
        cy = float(ellipse[1])
        r_est = float((ea + eb) * 0.5)
        return cx, cy, r_est, ellipse

    m = cv.moments(fit_contour)
    if m.get("m00", 0.0) != 0.0:
        cx = float(m["m10"] / m["m00"]) + ix1
        cy = float(m["m01"] / m["m00"]) + iy1
        r_est = float(np.sqrt(max(fit_area, 1.0) / np.pi))
        return cx, cy, r_est, None

    (cx0, cy0), r_est0 = cv.minEnclosingCircle(fit_contour)
    cx = float(cx0) + ix1
    cy = float(cy0) + iy1
    r_est = float(r_est0)
    return cx, cy, r_est, None


def pistol_decimal_score(d_norm):
    """Calculate pistol score based on inner edge position.
    
    Discrete scoring: Score = innermost ring touched by inner edge.
    
    Args:
        d_norm: Normalized inner edge distance from center
    
    Returns:
        Discrete score (10, 9, 8, ..., 1, 0)
    """
    # Inner edge inside inner 10 (< PISTOL_RING_RATIOS[10]) → Score 10
    if d_norm < PISTOL_RING_RATIOS[10]:
        return 10.0
    
    # Inner edge inside ring 10 zone → Score 10
    if d_norm < PISTOL_RING_RATIOS[9]:
        return 10.0
    
    # Inner edge inside ring 9 zone → Score 9
    if d_norm < PISTOL_RING_RATIOS[8]:
        return 9.0
    
    # Inner edge inside ring 8 zone → Score 8
    if d_norm < PISTOL_RING_RATIOS[7]:
        return 8.0
    
    # Inner edge inside ring 7 zone → Score 7
    if d_norm < PISTOL_RING_RATIOS[6]:
        return 7.0
    
    # Inner edge inside ring 6 zone → Score 6
    if d_norm < PISTOL_RING_RATIOS[5]:
        return 6.0
    
    # Inner edge inside ring 5 zone → Score 5
    if d_norm < PISTOL_RING_RATIOS[4]:
        return 5.0
    
    # Inner edge inside ring 4 zone → Score 4
    if d_norm < PISTOL_RING_RATIOS[3]:
        return 4.0
    
    # Inner edge inside ring 3 zone → Score 3
    if d_norm < PISTOL_RING_RATIOS[2]:
        return 3.0
    
    # Inner edge inside ring 2 zone → Score 2
    if d_norm < PISTOL_RING_RATIOS[1]:
        return 2.0
    
    # Inner edge inside ring 1 zone → Score 1
    if d_norm < 1.0:
        return 1.0
    
    # Outside target
    return 0.0


def rifle_decimal_score(d_norm_edge, d_norm_center=None):
    """Calculate rifle score based on inner edge position.
    
    Discrete scoring: Score = innermost ring touched by inner edge.
    Ring boundaries (RIFLE_RING_RATIOS) define where each ring STARTS from center.
    So RIFLE_RING_RATIOS[9] = 0.12088 is where ring 9 starts (and ring 10 ends).
    
    Args:
        d_norm_edge: Normalized edge distance (center distance minus pellet radius)
        d_norm_center: Normalized center-to-center distance (unused, kept for compatibility)
    
    Returns:
        Discrete score (10, 9, 8, ..., 1, 0)
    """
    # Ring boundaries: RIFLE_RING_RATIOS[N] is where ring N STARTS (inner boundary)
    # So if inner edge < RIFLE_RING_RATIOS[N], it's INSIDE ring N+1
    
    # Inner edge inside inner 10 dot (< 0.01099) → Score 10 (decimal handled separately)
    if d_norm_edge < RIFLE_RING_RATIOS[10]:
        return 10.0
    
    # Inner edge inside ring 10 zone (< 0.12088) → Score 10
    if d_norm_edge < RIFLE_RING_RATIOS[9]:
        return 10.0
    
    # Inner edge inside ring 9 zone (< 0.23077) → Score 9
    if d_norm_edge < RIFLE_RING_RATIOS[8]:
        return 9.0
    
    # Inner edge inside ring 8 zone (< 0.34066) → Score 8
    if d_norm_edge < RIFLE_RING_RATIOS[7]:
        return 8.0
    
    # Inner edge inside ring 7 zone (< 0.45055) → Score 7
    if d_norm_edge < RIFLE_RING_RATIOS[6]:
        return 7.0
    
    # Inner edge inside ring 6 zone (< 0.56044) → Score 6
    if d_norm_edge < RIFLE_RING_RATIOS[5]:
        return 6.0
    
    # Inner edge inside ring 5 zone (< 0.67033) → Score 5
    if d_norm_edge < RIFLE_RING_RATIOS[4]:
        return 5.0
    
    # Inner edge inside ring 4 zone (< 0.78022) → Score 4
    if d_norm_edge < RIFLE_RING_RATIOS[3]:
        return 4.0
    
    # Inner edge inside ring 3 zone (< 0.89011) → Score 3
    if d_norm_edge < RIFLE_RING_RATIOS[2]:
        return 3.0
    
    # Inner edge inside ring 2 zone (< 1.0) → Score 2
    if d_norm_edge < RIFLE_RING_RATIOS[1]:
        return 2.0
    
    # Inner edge inside ring 1 zone (< 1.0 normalized) → Score 1
    if d_norm_edge < 1.0:
        return 1.0
    
    # Outside target
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

    # Apply super_image 2x enhancement if enabled
    # Track scale factor to convert coordinates back to original resolution
    enhancement_scale = 1.0
    if USE_SUPER_IMAGE_ENHANCEMENT and _have_super_image:
        original_shape = infer_frame.shape[:2]
        infer_frame = _enhance_image_2x(infer_frame)
        enhanced_shape = infer_frame.shape[:2]
        # Calculate actual scale achieved
        if enhanced_shape[0] > original_shape[0]:
            enhancement_scale = float(enhanced_shape[0]) / float(original_shape[0])

    # Use standardized 0.12 confidence threshold identical to scripts_pistol.
    # Lower thresholds caused massive hallucination of shots.
    model_conf = 0.12
    res = model(infer_frame, conf=model_conf)[0]
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
            
            # Scale coordinates back to original resolution if enhanced
            if enhancement_scale > 1.0:
                x1, y1, x2, y2 = x1 / enhancement_scale, y1 / enhancement_scale, x2 / enhancement_scale, y2 / enhancement_scale

            conf = None
            try:
                conf = float(res.boxes.conf[i])
            except Exception:
                conf = None

            if cls_name == "black_contour":
                area = float(max(0.0, x2 - x1) * max(0.0, y2 - y1))
                if area >= black_area:
                    black_area = area
                    black_box = np.array([x1, y1, x2, y2])  # Use scaled coordinates
            else:


                # Optional class-name filtering. If HOLE_CLASS_TOKENS is None, accept
                # any non-black class as a hole candidate.
                if HOLE_CLASS_TOKENS is not None:
                    is_hole_like = any(token in cls_name for token in HOLE_CLASS_TOKENS)
                    if not is_hole_like:
                        continue

                if conf is not None and conf < HOLE_CONF_THRESHOLD:
                    continue

                cx, cy, r = box_center_and_radius(np.array([x1, y1, x2, y2]))  # Use scaled coordinates
                hole_detections.append((cx, cy, r))

                if DEBUG_DETECTIONS:
                    print(f"hole cand: cls={cls_name} conf={conf} r={r:.2f}", flush=True)

    # Use original resolution frame for contour operations (not enhanced)
    infer_frame_original = frame_proc
    if USE_ILLUMINATION_NORMALIZATION:
        try:
            infer_frame_original = _illumination_normalize_bgr(frame_proc)
        except Exception:
            infer_frame_original = frame_proc

    if black_box is not None:
        bc = _black_contour_geometry_px(infer_frame_original, black_box)
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
    if SHOW_DEBUG_OVERLAYS:
        # Draw center dot (bright green)
        cv.circle(annotated, (int(score_center[0]), int(score_center[1])), 3, (0, 255, 0), -1)
        # Draw black ring circle (blue)
        if R_black_x is not None and R_black_y is not None:
            r_black = (R_black_x + R_black_y) / 2.0
            cv.circle(annotated, (int(score_center[0]), int(score_center[1])), int(max(1.0, r_black)), (255, 0, 0), 2)
        # Draw outer ring circle (cyan)
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

    # Validate hole shapes (filter out noise/scratches based on circularity)
    validated_holes = []
    frame_gray = cv.cvtColor(infer_frame_original, cv.COLOR_BGR2GRAY) if len(infer_frame_original.shape) == 3 else infer_frame_original
    
    for hx, hy, hr in hole_detections:
        # Quick size check first: only use relative HOLE_RADIUS_MIN_FACTOR floor
        # to avoid incorrect physical-mm cutoffs on small-frame images.
        if hr < hole_radius_min_px or hr > hole_radius_max_px:
            continue

        # Shape validation: circularity + aspect ratio
        # Standardized to highly-reliable pistol levels to prevent false positives.
        if _validate_hole_shape(frame_gray, hx, hy, hr, min_circularity=0.55, min_aspect_ratio=0.6):
            validated_holes.append((hx, hy, hr))


    # Final de-noise pass: remove near-neighbor duplicate detections (4-5px noise).
    validated_holes = _suppress_neighbor_hole_noise(validated_holes, NEIGHBOR_NOISE_DISTANCE_PX)

    if validated_holes:
        # Force the scoring pellet gauge to be exactly the nominal physical size.
        # YOLO bounding boxes often overestimate the radius due to irregular paper
        # tears. Overestimated radii artifically reduce the edge distance, inflating
        # the final score (e.g. a 7.9 gets pushed into 8.9).
        effective_hole_radius_px = expected_hole_radius_px
    else:
        effective_hole_radius_px = expected_hole_radius_px
    effective_hole_radius_ratio = effective_hole_radius_px / outer_radius_px

    # Apply center refinement for rifle shots (no additional dedup — a
    # simple fixed-distance pass was already done above, and a second pass
    # with radius-scaled distances here was merging valid second shots).
    if mode == "rifle" and validated_holes:
        refined_validated_holes = []
        for hx, hy, hr in validated_holes:
            black_center_for_refine = (center_x, center_y)
            black_radius_for_refine = (R_black_x + R_black_y) / 2.0 if R_black_x and R_black_y else None
            if RIFLE_HOLE_CENTER_REFINEMENT:
                hx, hy = _refine_hole_center_rifle(
                    infer_frame_original,
                    hx,
                    hy,
                    hr,
                    black_center_for_refine,
                    black_radius_for_refine,
                )
            refined_validated_holes.append((hx, hy, hr))
        validated_holes = refined_validated_holes

    for hx, hy, hr in validated_holes:
        # Store original YOLO position for comparison
        yolo_hx, yolo_hy = hx, hy
        detection_method = "yolo"
        contour_x, contour_y, contour_r, contour_circularity = None, None, None, None

        dx = hx - score_center[0]
        dy = hy - score_center[1]

        d_norm = _circular_normalized_radius(dx, dy, outer_radius_px)
        
        # Score both modes from pellet-edge position so line-cutters receive the
        # higher value instead of being biased low by center-only distance.
        if mode == "rifle":
            d_norm_edge = max(d_norm - effective_hole_radius_ratio, 0.0)
            score = _rifle_decimal_score_all_rings(
                d_norm_edge,
                outer_radius_px,
                sqrt(dx * dx + dy * dy),
                effective_hole_radius_px,
                mode="rifle",
            )
            # DEBUG: Log normalized distance and score for diagnostics
            print(
                f"[Rifle Scoring] Shot at ({hx:.1f}, {hy:.1f}): "
                f"d_norm={d_norm:.4f}, d_norm_edge={d_norm_edge:.4f}, score={score:.1f}",
                flush=True,
            )
        else:
            d_norm_edge = max(d_norm - effective_hole_radius_ratio, 0.0)
            score = score_fn(d_norm_edge)

        # ============== CONTOUR-BASED 10-POINT REFINEMENT ==============
        # Run contour detection for shots scoring > 9.9 (inner-10 shots only)
        # Uses discrete band scoring: 10.4, 10.5, 10.6, 10.7, 10.8, 10.9
        if USE_CONTOUR_10_SCORING and score >= CONTOUR_ACTIVATION_MIN_SCORE:
            print(f"[Contour 10] Initial score={score:.1f}, activating contour detection...", flush=True)
            # Search radius based on detected hole size
            search_r = max(hr * 2.0, expected_hole_radius_px * 2.5)
            contour_result = _contour_refine_shot_center(infer_frame_original, hx, hy, search_r)
            
            if contour_result is not None:
                contour_x, contour_y, contour_r, contour_circularity = contour_result
                print(f"[Contour 10] Contour found: circularity={contour_circularity:.2f} (min={CONTOUR_MIN_CIRCULARITY})", flush=True)
                
                # Check if contour detection is reliable (circularity threshold)
                if contour_circularity >= CONTOUR_MIN_CIRCULARITY:
                    # Calculate distance between YOLO and contour centers
                    disagreement = sqrt((contour_x - yolo_hx)**2 + (contour_y - yolo_hy)**2)
                    
                    if DEBUG_DETECTIONS:
                        print(f"[Contour 10-scoring] YOLO: ({yolo_hx:.1f}, {yolo_hy:.1f}) "
                              f"Contour: ({contour_x:.1f}, {contour_y:.1f}) "
                              f"Disagreement: {disagreement:.2f}px Circularity: {contour_circularity:.2f}", flush=True)
                    
                    # Log warning if significant disagreement
                    if disagreement > CONTOUR_MAX_DISAGREEMENT_PX:
                        if DEBUG_DETECTIONS:
                            print(f"[Contour 10-scoring] WARNING: Large disagreement ({disagreement:.2f}px) - using contour for inner 10", flush=True)
                    
                    # Use contour center for inner-10 scoring (more precise)
                    hx, hy = contour_x, contour_y
                    detection_method = "contour" if disagreement > 1.0 else "combined"
                    
                    # Calculate center distance in pixels for discrete band scoring
                    dx_px = hx - score_center[0]
                    dy_px = hy - score_center[1]
                    center_distance_px = sqrt(dx_px * dx_px + dy_px * dy_px)
                    
                    # Calculate ring 10 OUTER boundary radius in pixels.
                    # Use ring_ratios[9] for rifle — same boundary as the decimal band scorer
                    # (ring_ratios[9] = 0.12088 for rifle, PISTOL_RING_RATIOS[9] for pistol).
                    ring10_outer_ratio = (
                        float(RIFLE_RING_RATIOS[9]) if mode == "rifle"
                        else float(PISTOL_RING_RATIOS[9])
                    )
                    ring10_radius_px = ring10_outer_ratio * outer_radius_px
                    pellet_radius_px = expected_hole_radius_px
                    
                    # Use discrete band scoring (10.0 to 10.9)
                    contour_score = _contour_decimal_ten_score(center_distance_px, ring10_radius_px, pellet_radius_px)
                    max_dist = ring10_radius_px + pellet_radius_px
                    print(f"[Contour 10] Scoring: dist={center_distance_px:.2f}px, ring10={ring10_radius_px:.2f}px, "
                          f"pellet={pellet_radius_px:.2f}px, max={max_dist:.2f}px, score={contour_score}", flush=True)
                    
                    if contour_score is not None:
                        score = contour_score
                        if DEBUG_DETECTIONS:
                            print(f"[Contour 10-scoring] Distance: {center_distance_px:.2f}px, "
                                  f"Ring10 outer: {ring10_radius_px:.2f}px, Score: {score:.1f}", flush=True)
                    else:
                        print(f"[Contour 10] contour_score=None, falling back to standard scoring", flush=True)
                        # Fallback: recalculate with standard method if outside ring 10
                        dx = hx - score_center[0]
                        dy = hy - score_center[1]
                        d_norm = _circular_normalized_radius(dx, dy, outer_radius_px)
                        
                        if mode == "rifle":
                            d_norm_edge = max(d_norm - effective_hole_radius_ratio, 0.0)
                            score = _rifle_decimal_score_all_rings(
                                d_norm_edge,
                                outer_radius_px,
                                sqrt(dx * dx + dy * dy),
                                effective_hole_radius_px,
                                mode="rifle",
                            )
                        else:
                            d_norm_edge = max(d_norm - effective_hole_radius_ratio, 0.0)
                            score = score_fn(d_norm_edge)
                    
                    if DEBUG_DETECTIONS:
                        print(f"[Contour 10-scoring] Final score: {score:.1f} (method: {detection_method})", flush=True)
                else:
                    print(f"[Contour 10] Circularity {contour_circularity:.2f} < {CONTOUR_MIN_CIRCULARITY}, using YOLO score", flush=True)
            else:
                print(f"[Contour 10] contour_result is None, using YOLO score", flush=True)

        total_score += score
        dx = hx - center_x
        dy = center_y - hy   # invert Y for screen coords
        angle = float(np.degrees(np.arctan2(dy, dx)))

        shot_data = {
            "x": int(hx),
            "y": int(hy),
            "r": float(hr),
            "score": float(score),
            "detection_method": detection_method,

            # 🔥 For arrows
            "center_x": center_x,
            "center_y": center_y,
            "dx": float(dx),
            "dy": float(dy),
            "angle": angle
        }
        
        # Add contour data if available
        if contour_x is not None:
            shot_data["contour_x"] = float(contour_x)
            shot_data["contour_y"] = float(contour_y)
            shot_data["contour_r"] = float(contour_r) if contour_r else None
            shot_data["contour_circularity"] = float(contour_circularity) if contour_circularity else None
            shot_data["yolo_x"] = float(yolo_hx)
            shot_data["yolo_y"] = float(yolo_hy)
        
        scored_shots.append(shot_data)

    # ============== VISUALIZATION: CENTER-TO-CENTER DISTANCE ==============
    # Draw lines and distance values for rifle (can be hidden/toggled later)
    VISUALIZE_CENTER_DISTANCE = SHOW_DEBUG_OVERLAYS  # Toggle this to show/hide distance visualization
    
    if VISUALIZE_CENTER_DISTANCE and mode == "rifle":
        for shot in scored_shots:
            shot_x = shot["x"]
            shot_y = shot["y"]
            
            # Draw line from target center to shot center
            cv.line(annotated, (int(center_x), int(center_y)), (int(shot_x), int(shot_y)), (200, 100, 255), 2)
            
            # Calculate distance in pixels
            dist_px = sqrt((shot_x - center_x)**2 + (shot_y - center_y)**2)
            
            # Calculate normalized distance
            dist_norm = dist_px / (R_outer_x + R_outer_y) * 2.0 if (R_outer_x and R_outer_y) else dist_px / outer_radius_px
            
            # Display distance text at midpoint
            mid_x = int((center_x + shot_x) / 2.0)
            mid_y = int((center_y + shot_y) / 2.0)
            dist_text = f"d={dist_px:.1f}px (n={dist_norm:.3f})"
            cv.putText(annotated, dist_text, (mid_x - 60, mid_y - 10), cv.FONT_HERSHEY_SIMPLEX, 0.5, (200, 100, 255), 1)

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
