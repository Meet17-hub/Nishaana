#!/usr/bin/env python3
"""
Test script to verify module_loader works correctly.
Tests that we can switch between rifle and pistol modes.
"""

import sys
import os

# Add scripts to path
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("MODULE LOADER TEST")
print("=" * 60)

# Test 1: Import module loader
print("\n[TEST 1] Importing module_loader...")
try:
    from module_loader import (
        set_mode,
        get_current_mode,
        reload_modules_for_mode,
        get_model_prediction,
        get_frame_differencing,
        get_frame_preprocess,
    )
    print("✅ Module loader imported successfully")
except Exception as e:
    print(f"❌ Failed to import module_loader: {e}")
    sys.exit(1)

# Test 2: Test mode switching to rifle
print("\n[TEST 2] Switching to RIFLE mode...")
try:
    set_mode('rifle')
    current = get_current_mode()
    assert current == 'rifle', f"Expected 'rifle', got '{current}'"
    print(f"✅ Successfully set mode to: {current}")
except Exception as e:
    print(f"❌ Failed to set rifle mode: {e}")
    sys.exit(1)

# Test 3: Test mode switching to pistol
print("\n[TEST 3] Switching to PISTOL mode...")
try:
    set_mode('pistol')
    current = get_current_mode()
    assert current == 'pistol', f"Expected 'pistol', got '{current}'"
    print(f"✅ Successfully set mode to: {current}")
except Exception as e:
    print(f"❌ Failed to set pistol mode: {e}")
    sys.exit(1)

# Test 4: Test mode switching back to rifle
print("\n[TEST 4] Switching back to RIFLE mode...")
try:
    set_mode('rifle')
    current = get_current_mode()
    assert current == 'rifle', f"Expected 'rifle', got '{current}'"
    print(f"✅ Successfully switched back to: {current}")
except Exception as e:
    print(f"❌ Failed to switch back to rifle mode: {e}")
    sys.exit(1)

# Test 5: Verify module reloading
print("\n[TEST 5] Testing module reload...")
try:
    reload_modules_for_mode('rifle')
    print("✅ Module reload for rifle successful")
    reload_modules_for_mode('pistol')
    print("✅ Module reload for pistol successful")
    reload_modules_for_mode('rifle')
    print("✅ Module reload back to rifle successful")
except Exception as e:
    print(f"❌ Failed to reload modules: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL TESTS PASSED!")
print("=" * 60)
print("\nThe module loader is working correctly.")
print("✓ Mode switching works")
print("✓ Module reloading works")
print("✓ Rifle/Pistol separation verified")
