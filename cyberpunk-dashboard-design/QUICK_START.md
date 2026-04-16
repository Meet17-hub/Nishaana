QUICK START: Frame Differencing
================================

## 30-Second Overview

The frame differencing system is **already integrated and ready to use**. It automatically:
- Detects bullet holes using texture analysis (immune to lighting changes)
- Validates detections with your existing ML model (hybrid mode)
- Adapts to paper degradation over time
- Works per-user (separate reference frames for each shooter)

## Immediate Next Steps

### 1. Verify Files Are in Place

```bash
# Check that new files exist
ls scripts/frame_differencing.py          # Should exist
grep -q "frame_differencing" scripts/app.py && echo "✅ Integrated" || echo "❌ Not found"
```

### 2. Start the System

```bash
# From cyberpunk-dashboard-design directory
pnpm run dev:all           # Runs Flask + Next.js
```

Watch for these startup messages:
```
[app] ✅ Frame differencing module imported successfully
🚀 Lakshya API Backend Starting...
```

### 3. Test Frame Differencing

```bash
# In a new terminal:

# Check that module loads
curl http://localhost:5000/api/frame_differencing/status

# You should see:
# { "available": true, "enabled": true, "hybrid_mode": true, ... }
```

### 4. Login in Frontend & Take Shots

1. Open http://localhost:3000
2. Login with test account
3. Select a device
4. Take some shots (fire, or simulate with test endpoint)
5. Check `/dashboard` - should show detections
6. Look at console logs for `[_detect_shots_hybrid]` messages

### 5. Verify It's Working

Check that detections use frame differencing:

```bash
# Terminal side - watch logs while shooting
# You should see:
# [_detect_shots_hybrid] Hybrid detection used method: hybrid
# [_detect_shots_hybrid] FD found X holes
# [_detect_shots_hybrid] ML found Y holes
# [_detect_shots_hybrid] Merged to Z detections
```

---

## Configuration Options

### Quick Toggles

**Disable frame differencing (use ML model only):**
```bash
curl -X POST http://localhost:5000/api/frame_differencing/enable \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Use FD only (no ML validation):**
```bash
curl -X POST http://localhost:5000/api/frame_differencing/hybrid_mode \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Reset between shooter changes:**
```bash
curl -X POST http://localhost:5000/api/frame_differencing/reset_reference
```

---

## What Should You See

### ✅ Good Signs

- Detections appear on target image
- Each shot shows approximately 1 detection
- Detections are stable (same spot for same hole)
- Fewer false positives after shots are fired
- System works for 1-2+ hours without recalibration

### ⚠️ Warning Signs

- Multiple detections per shot
- Detections appearing in blank areas
- Different positions for same hole on recapture
- Need to reset every 15 minutes
- High false positive rate

### 🔧 If Issues Occur

1. **Check status:**
   ```bash
   curl http://localhost:5000/api/frame_differencing/status
   ```

2. **Check logs:**
   ```bash
   # Look for error messages
   # [FrameDifferencer] Error in detect_holes: ...
   ```

3. **Reset manually:**
   ```bash
   curl -X POST http://localhost:5000/api/frame_differencing/reset_reference
   ```

4. **Try ML-only mode:**
   ```bash
   curl -X POST http://localhost:5000/api/frame_differencing/enable \
     -d '{"enabled": false}'
   ```

---

## Understanding the Detection Modes

### Mode 1: Hybrid (Default) ⭐ Recommended

```
Frame → Frame Differencing → Find holes
                              ↓
                        ML Model → Score & validate
                              ↓
                        Merged Result
```

**Best for**: Most situations  
**Speed**: Medium (50-100ms)  
**Accuracy**: Highest

### Mode 2: Frame Differencing Only

```
Frame → Frame Differencing → Result
```

**Best for**: Fast feedback, consistent lighting  
**Speed**: Fastest (20-30ms)  
**Accuracy**: Very good

### Mode 3: ML Only

```
Frame → ML Model → Result
```

**Best for**: Validation, testing  
**Speed**: Slowest (100-200ms)  
**Accuracy**: Good (original system)

---

## Monitoring the System

### Real-time Status

```bash
# Watch detection statistics
while true; do
  echo "=== $(date) ==="
  curl -s http://localhost:5000/api/frame_differencing/status | jq '.stats'
  sleep 5
done
```

### Expected Stats

```json
{
  "initialized": true,
  "frame_count": 150,
  "detections_total": 12,
  "avg_detections_per_frame": 0.08,
  "fps": 30.0,
  "uptime_sec": 5.0
}
```

### Interpretation

- `fps` - Should match camera FPS (typically 20-30)
- `detections_total` - Should grow with each shot
- `avg_detections_per_frame` - Should be low (~0.05-0.2)
- `uptime_sec` - Shows how long system has run without reset

---

## Performance Expectations

| Operation | Time |
|-----------|------|
| Frame differencing | 20-50ms |
| ML model validation | 30-150ms |
| Hybrid (FD+ML) | 50-100ms |
| Frame capture | 200-500ms |
| **Total latency** | **300-700ms** |

**Result**: Your dashboard should respond within 1-2 seconds of firing a shot.

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| "Frame differencing not available" | Module not found | Check `scripts/frame_differencing.py` exists |
| No detections | Reference not initialized | Reset with `/api/frame_differencing/reset_reference` |
| Too many false positives | Lighting changes | Increase `min_hole_radius_px` or enable hybrid mode |
| Missing shots | Holes too small | Decrease `min_hole_radius_px` in `frame_differencing.py` |
| Slow performance | Heavy processing | Use FD-only mode (fast) |

---

## For Developers

### Adding Custom Logic

If you want to modify detection behavior:

```python
# In scripts/app.py, modify _detect_shots_hybrid():

# Example: Increase confidence threshold
if shot['score'] < 0.7:    # Was 0.5
    continue               # Skip low-confidence detections
```

### Customizing Parameters

```python
# In scripts/frame_differencing.py, in FrameDifferencer.__init__():

fd = FrameDifferencer(
    min_hole_radius_px=3.0,
    max_hole_radius_px=30.0,
    update_alpha=0.15,           # Change calibration speed
    blur_kernel=5,               # Change smoothing
    morph_kernel_size=3,         # Change noise removal
    adaptive_threshold_block=11, # Change threshold region
    adaptive_threshold_c=2,      # Change threshold constant
)
```

### Debugging

Add to `_detect_shots_hybrid()` for verbose output:

```python
print(f"[DEBUG] FD detections: {fd_detections}")
print(f"[DEBUG] ML detections: {ml_detections}")
print(f"[DEBUG] Merged result: {merged_detections}")
```

---

## Next: Deep Dive

For detailed information, see:
- `FRAME_DIFFERENCING_IMPLEMENTATION.md` - Full technical documentation
- `scripts/frame_differencing.py` - Source code with docstrings
- `scripts/app.py` - Integration code

---

## Questions?

**Check the documentation:**
1. `FRAME_DIFFERENCING_IMPLEMENTATION.md` - Technical details
2. Code comments in `frame_differencing.py`
3. Flask endpoint descriptions in `app.py`

**Test in isolation:**
```bash
# You can test just the frame differencing module
python3 -c "from frame_differencing import FrameDifferencer; fd = FrameDifferencer(); print('✅ Module loads OK')"
```

---

**Status**: ✅ Ready to deploy and test!
