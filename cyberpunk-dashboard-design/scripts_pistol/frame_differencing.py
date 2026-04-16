"""
Frame Differencing Module for Bullet Hole Detection
=====================================================

Detects bullet holes by comparing frames to a clean reference image.
Uses texture-based differencing to ignore lighting changes and isolate
permanent texture changes (bullet holes).

Key Features:
- Adaptive background update to handle paper degradation
- Robust noise filtering (blur + morphology)
- Size-based contour filtering to detect only bullet-sized holes
- Confidence scoring for detection quality
- Per-user reference frame management
"""

import cv2 as cv
import numpy as np
import time
from typing import Dict, Any, Tuple, Optional, List


class FrameDifferencer:
    """
    Detects bullet holes using frame differencing with adaptive background update.
    
    Pipeline:
    1. Grayscale conversion
    2. Gaussian blur (smooth sensor noise)
    3. Adaptive threshold (isolate high-frequency changes)
    4. Morphology open (remove tiny artifacts)
    5. Contour detection & size filtering
    6. Adaptive blend update (calibration)
    
    Args:
        min_hole_radius_px: Minimum bullet hole radius in pixels (default: 3)
        max_hole_radius_px: Maximum bullet hole radius in pixels (default: 30)
        update_alpha: Adaptive blend factor [0-1] (default: 0.15)
                     Higher = faster adaptation (less stable)
                     Lower = slower adaptation (more stable)
        blur_kernel: Gaussian blur kernel size (must be odd)
        morph_kernel_size: Morphological operation kernel size
        adaptive_threshold_block: Block size for adaptive threshold (must be odd)
        adaptive_threshold_c: Constant subtracted from mean for adaptive threshold
    """
    
    def __init__(
        self,
        min_hole_radius_px: float = 3.0,
        max_hole_radius_px: float = 30.0,
        update_alpha: float = 0.15,
        blur_kernel: int = 5,
        morph_kernel_size: int = 3,
        adaptive_threshold_block: int = 11,
        adaptive_threshold_c: int = 2,
    ):
        self.min_hole_radius_px = min_hole_radius_px
        self.max_hole_radius_px = max_hole_radius_px
        self.update_alpha = update_alpha
        self.blur_kernel = blur_kernel
        self.morph_kernel_size = morph_kernel_size
        self.adaptive_threshold_block = adaptive_threshold_block
        self.adaptive_threshold_c = adaptive_threshold_c
        
        # Reference frame (initialized on first call)
        self.reference_frame_gray = None
        self.reference_frame_initialized = False
        self.initialization_time = None
        
        # Statistics for monitoring
        self.frame_count = 0
        self.detections_count = 0
        self.last_update_time = None
    
    def initialize_reference(self, frame: np.ndarray) -> None:
        """
        Initialize the reference frame from a clean target image.
        
        Args:
            frame: BGR frame from camera (or already grayscale)
        """
        if frame is None:
            raise ValueError("Cannot initialize reference frame with None")
        
        # Convert to grayscale if needed
        if len(frame.shape) == 3:
            frame_gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
        else:
            frame_gray = frame.copy()
        
        self.reference_frame_gray = frame_gray.astype(np.float32)
        self.reference_frame_initialized = True
        self.initialization_time = time.time()
        print(
            f"[FrameDifferencer] Reference frame initialized: {frame.shape} @ {self.initialization_time:.2f}",
            flush=True
        )
    
    def reset_reference(self) -> None:
        """Clear the reference frame (requires reinitialization)."""
        self.reference_frame_gray = None
        self.reference_frame_initialized = False
        self.initialization_time = None
        print("[FrameDifferencer] Reference frame reset", flush=True)
    
    def detect_holes(
        self,
        frame: np.ndarray,
        auto_init: bool = True,
    ) -> Dict[str, Any]:
        """
        Detect bullet holes in the current frame by comparing to reference.
        
        Args:
            frame: BGR input frame from camera
            auto_init: If True and reference not initialized, use this frame as reference
        
        Returns:
            {
                'detected': List of detections [{'x': px, 'y': px, 'r': radius, 'score': 0-1}, ...]
                'delta_frame': Difference frame for debugging
                'threshold_frame': Binary threshold result
                'confidence': Overall detection confidence (0-1)
                'frame_count': Total frames processed
                'error': Error message if detection failed
            }
        """
        self.frame_count += 1
        
        # Auto-initialize on first frame
        if not self.reference_frame_initialized:
            if auto_init:
                self.initialize_reference(frame)
                # Return empty detections on init frame
                return {
                    'detected': [],
                    'confidence': 0.0,
                    'frame_count': self.frame_count,
                    'status': 'initialized',
                }
            else:
                return {
                    'detected': [],
                    'confidence': 0.0,
                    'frame_count': self.frame_count,
                    'error': 'Reference frame not initialized',
                }
        
        try:
            # Step 1: Convert current frame to grayscale
            if len(frame.shape) == 3:
                frame_gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
            else:
                frame_gray = frame.copy()
            
            frame_gray_fl = frame_gray.astype(np.float32)
            
            # Step 2: Absolute difference from reference
            delta = cv.absdiff(self.reference_frame_gray, frame_gray_fl)
            delta_uint8 = np.clip(delta, 0, 255).astype(np.uint8)
            
            # Step 3: Gaussian blur (smooth sensor noise)
            blurred = cv.GaussianBlur(delta_uint8, (self.blur_kernel, self.blur_kernel), 0)
            
            # Step 4: Adaptive threshold (isolate significant changes)
            binary = cv.adaptiveThreshold(
                blurred,
                maxValue=255,
                adaptiveMethod=cv.ADAPTIVE_THRESH_GAUSSIAN_C,
                thresholdType=cv.THRESH_BINARY,
                blockSize=self.adaptive_threshold_block,
                C=self.adaptive_threshold_c,
            )
            
            # Step 5: Morphology open (remove noise)
            kernel = cv.getStructuringElement(
                cv.MORPH_ELLIPSE,
                (self.morph_kernel_size, self.morph_kernel_size)
            )
            opened = cv.morphologyEx(binary, cv.MORPH_OPEN, kernel)
            
            # Step 6: Find contours and filter by size
            contours, _ = cv.findContours(opened, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
            
            detections = []
            holes_found = 0
            
            for contour in contours:
                # Calculate properties
                area = cv.contourArea(contour)
                if area < 1:
                    continue
                
                # Fit circle to contour
                (cx, cy), radius = cv.minEnclosingCircle(contour)
                
                # Filter by size (bullet hole diameter ~6-60px depending on distance)
                if radius < self.min_hole_radius_px or radius > self.max_hole_radius_px:
                    continue
                
                # Calculate confidence based on circularity
                perimeter = cv.arcLength(contour, True)
                if perimeter == 0:
                    continue
                
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                confidence = min(max(circularity, 0.0), 1.0)
                
                # Only accept reasonably circular contours (0.4+)
                if confidence < 0.4:
                    continue
                
                holes_found += 1
                detections.append({
                    'x': float(cx),
                    'y': float(cy),
                    'r': float(radius),
                    'area': float(area),
                    'circularity': float(circularity),
                    'score': float(confidence),
                    'contour_area': float(area),
                })
            
            # Calculate overall confidence (based on detection quality)
            overall_confidence = min(len(detections) * 0.2, 1.0)  # 0-1 scale
            
            self.detections_count += len(detections)
            self.last_update_time = time.time()
            
            result = {
                'detected': detections,
                'delta_frame': delta_uint8,  # For debugging
                'threshold_frame': opened,   # For debugging
                'confidence': overall_confidence,
                'frame_count': self.frame_count,
                'detections_count': self.detections_count,
                'holes_found': holes_found,
            }
            
            return result
            
        except Exception as e:
            print(f"[FrameDifferencer] Error in detect_holes: {e}", flush=True)
            return {
                'detected': [],
                'confidence': 0.0,
                'frame_count': self.frame_count,
                'error': str(e),
            }
    
    def update_reference_adaptive(self, frame: np.ndarray) -> None:
        """
        Adaptively blend current frame into reference to handle paper degradation.
        
        Paper naturally darkens and degrades over time. This function slowly
        incorporates new observations so the reference adapts without losing
        the original clean target reference.
        
        Formula: ref_new = (1-α) * ref_old + α * current
        - α = 0.15 means: keep 85% old + 15% new
        - Higher α = faster adaptation (less stable, drifts more)
        - Lower α = slower adaptation (more stable, misses gradual changes)
        
        Args:
            frame: Current frame to blend into reference
        """
        if not self.reference_frame_initialized or frame is None:
            return
        
        try:
            # Convert to grayscale
            if len(frame.shape) == 3:
                frame_gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
            else:
                frame_gray = frame.copy()
            
            frame_gray_fl = frame_gray.astype(np.float32)
            
            # Adaptive blend: keep mostly old reference, slowly incorporate new
            self.reference_frame_gray = (
                (1.0 - self.update_alpha) * self.reference_frame_gray +
                self.update_alpha * frame_gray_fl
            )
            
        except Exception as e:
            print(f"[FrameDifferencer] Error in update_reference_adaptive: {e}", flush=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the differencer state.
        
        Returns:
            Dictionary with stats for monitoring/logging
        """
        uptime_sec = (time.time() - self.initialization_time) if self.initialization_time else 0
        fps = self.frame_count / uptime_sec if uptime_sec > 0 else 0
        
        return {
            'initialized': self.reference_frame_initialized,
            'frame_count': self.frame_count,
            'detections_total': self.detections_count,
            'avg_detections_per_frame': self.detections_count / self.frame_count if self.frame_count > 0 else 0,
            'fps': fps,
            'uptime_sec': uptime_sec,
            'last_update': self.last_update_time,
        }


class PerUserFrameDifferencer:
    """
    Manages frame differencing state per user.
    
    Keeps separate reference frames for each logged-in user so that
    when switching between shooters, the reference frame doesn't get
    corrupted.
    """
    
    def __init__(self):
        self.users: Dict[str, FrameDifferencer] = {}
        self.lock = __import__('threading').Lock()
    
    def get_or_create(self, user_key: str) -> FrameDifferencer:
        """Get or create a FrameDifferencer for a user."""
        with self.lock:
            if user_key not in self.users:
                self.users[user_key] = FrameDifferencer()
            return self.users[user_key]
    
    def reset_user(self, user_key: str) -> None:
        """Reset a user's frame differencer."""
        with self.lock:
            if user_key in self.users:
                self.users[user_key].reset_reference()
                print(f"[PerUserFrameDifferencer] Reset reference for user: {user_key}", flush=True)
    
    def get_stats(self, user_key: str) -> Optional[Dict[str, Any]]:
        """Get stats for a specific user."""
        with self.lock:
            if user_key in self.users:
                return self.users[user_key].get_stats()
            return None


# Singleton instance for global use
_global_differencer_pool = PerUserFrameDifferencer()


def get_frame_differencer(user_key: str) -> FrameDifferencer:
    """Get or create a frame differencer for a user."""
    return _global_differencer_pool.get_or_create(user_key)


def reset_frame_differencer(user_key: str) -> None:
    """Reset a user's frame differencer."""
    _global_differencer_pool.reset_user(user_key)
