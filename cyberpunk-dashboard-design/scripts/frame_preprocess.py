import os
from functools import lru_cache
from typing import Final

import cv2 as cv
import numpy as np

# ------------------------------------------------------------
# Preprocess settings captured from wrap_test.py UI
# ------------------------------------------------------------
# Wrap points order must be: top-left, bottom-left, bottom-right, top-right
# and map to output square points: (0,0), (0,S), (S,S), (S,0)
WRAP_POINTS_SRC: Final[np.ndarray] = np.array(
    [
        [656.92, 677.01],
        [851.10, 1595.82],
        [1760.24, 1557.13],
        [1866.63, 599.64],
    ],
    dtype=np.float32,
)

OUTPUT_SIZE: Final[int] = 640

# Undistort tuning from wrap_test.py UI
UNDISTORT_ALPHA: Final[float] = 0.16
UNDISTORT_BALANCE: Final[float] = 0.0

CALIBRATION_NPZ_PATH: Final[str] = os.path.join(os.path.dirname(__file__), "calibration_params.npz")


def _load_calibration_npz(npz_path: str):
    """Load camera intrinsics + distortion from .npz.

    Supports common key names:
      - K / camera_matrix / mtx
      - D / dist / distCoeffs
      - DIM / dim / image_size

    Returns (K, D, is_fisheye, dim_wh) or (None, None, False, None).
    """
    if not npz_path or not os.path.exists(npz_path):
        return None, None, False, None

    data = np.load(npz_path, allow_pickle=True)
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
        return None, None, False, None

    K = np.array(K, dtype=np.float64).reshape(3, 3)
    D = np.array(D, dtype=np.float64).reshape(-1)

    is_fisheye = D.size == 4
    if is_fisheye:
        D = D.reshape(4, 1)
    else:
        D = D.reshape(-1, 1)

    dim_wh = None
    if DIM is not None:
        try:
            arr = np.array(DIM).reshape(-1)
            if arr.size >= 2:
                dim_wh = (int(arr[0]), int(arr[1]))
        except Exception:
            dim_wh = None

    if dim_wh is None:
        # Infer approximate dim from principal point.
        try:
            infer_w = int(round(float(K[0, 2]) * 2.0))
            infer_h = int(round(float(K[1, 2]) * 2.0))
            if infer_w > 0 and infer_h > 0:
                dim_wh = (infer_w, infer_h)
        except Exception:
            dim_wh = None

    return K, D, is_fisheye, dim_wh


_CALIB_K, _CALIB_D, _CALIB_IS_FISHEYE, _CALIB_DIM = _load_calibration_npz(CALIBRATION_NPZ_PATH)


def _best_dim_for_frame(dim_wh: tuple[int, int] | None, frame_wh: tuple[int, int]) -> tuple[int, int]:
    if dim_wh is None:
        return frame_wh
    dw, dh = dim_wh
    fw, fh = frame_wh
    score = abs(fw - dw) + abs(fh - dh)
    score_swapped = abs(fw - dh) + abs(fh - dw)
    if score_swapped < score:
        return (dh, dw)
    return (dw, dh)


@lru_cache(maxsize=32)
def _undistort_maps_for_frame(
    w: int,
    h: int,
    is_fisheye: bool,
    tune_value: float,
) -> tuple[np.ndarray, np.ndarray] | None:
    if _CALIB_K is None or _CALIB_D is None:
        return None

    K = _CALIB_K.copy()
    D = _CALIB_D.copy()

    frame_cx = (w - 1) / 2.0
    frame_cy = (h - 1) / 2.0

    dim = _best_dim_for_frame(_CALIB_DIM, (w, h))

    # If calibration DIM differs from current frame, scale intrinsics.
    if dim != (w, h):
        sx = w / float(dim[0])
        sy = h / float(dim[1])
        K[0, 0] *= sx
        K[0, 2] *= sx
        K[1, 1] *= sy
        K[1, 2] *= sy
        dim = (w, h)

    # Force principal point to current frame center.
    K[0, 2] = frame_cx
    K[1, 2] = frame_cy

    if is_fisheye:
        balance = float(tune_value)
        new_K = cv.fisheye.estimateNewCameraMatrixForUndistortRectify(K, D, dim, np.eye(3), balance=balance)
        try:
            new_K = np.array(new_K, dtype=np.float64)
            new_K[0, 2] = frame_cx
            new_K[1, 2] = frame_cy
        except Exception:
            pass
        map1, map2 = cv.fisheye.initUndistortRectifyMap(K, D, np.eye(3), new_K, dim, cv.CV_16SC2)
    else:
        alpha = float(tune_value)
        new_K, _roi = cv.getOptimalNewCameraMatrix(K, D, dim, alpha, dim)
        try:
            new_K = np.array(new_K, dtype=np.float64)
            new_K[0, 2] = frame_cx
            new_K[1, 2] = frame_cy
        except Exception:
            pass
        map1, map2 = cv.initUndistortRectifyMap(K, D, None, new_K, dim, cv.CV_16SC2)

    return map1, map2


def undistort_frame(frame_bgr: np.ndarray, *, alpha: float = UNDISTORT_ALPHA, balance: float = UNDISTORT_BALANCE) -> np.ndarray:
    """Apply calibration-based undistortion.

    Uses fisheye path if calibration has 4 distortion coeffs; otherwise uses standard pinhole.
    """
    if _CALIB_K is None or _CALIB_D is None:
        return frame_bgr

    h, w = frame_bgr.shape[:2]
    if h <= 0 or w <= 0:
        return frame_bgr

    is_fisheye = bool(_CALIB_IS_FISHEYE)
    tune_value = float(balance) if is_fisheye else float(alpha)

    maps = _undistort_maps_for_frame(w, h, is_fisheye, tune_value)
    if maps is None:
        return frame_bgr

    map1, map2 = maps
    return cv.remap(frame_bgr, map1, map2, interpolation=cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT)


def warp_to_square(frame_bgr: np.ndarray, *, src_points: np.ndarray = WRAP_POINTS_SRC, size: int = OUTPUT_SIZE) -> np.ndarray:
    dst = np.array([[0, 0], [0, size], [size, size], [size, 0]], dtype=np.float32)
    M = cv.getPerspectiveTransform(np.array(src_points, dtype=np.float32), dst)
    return cv.warpPerspective(frame_bgr, M, (size, size))


def preprocess_frame(
    frame_bgr: np.ndarray,
    *,
    apply_undistort: bool = True,
    alpha: float = UNDISTORT_ALPHA,
    balance: float = UNDISTORT_BALANCE,
    src_points: np.ndarray = WRAP_POINTS_SRC,
    size: int = OUTPUT_SIZE,
) -> np.ndarray:
    """Apply undistort (optional) + perspective warp to a 640x640 corrected target view."""
    frame_src = undistort_frame(frame_bgr, alpha=alpha, balance=balance) if apply_undistort else frame_bgr
    return warp_to_square(frame_src, src_points=src_points, size=size)
