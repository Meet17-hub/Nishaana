# module_loader.py - Dynamic Module Loader for Rifle/Pistol Mode Switching
# 
# This module handles dynamic loading of mode-specific modules (model_prediction, frame_differencing, etc.)
# allowing seamless switching between rifle and pistol modes without restarting Flask.

import sys
import importlib
from pathlib import Path
from typing import Optional, Any

# Determine script directories
SCRIPT_DIR = Path(__file__).parent
SCRIPTS_RIFLE_DIR = SCRIPT_DIR  # scripts/
SCRIPTS_PISTOL_DIR = SCRIPT_DIR.parent / "scripts_pistol"  # scripts_pistol/

# Module cache: {module_name: {mode: module_object}}
_module_cache = {}
_current_mode = 'rifle'

print(f"[ModuleLoader] Initialized", flush=True)
print(f"[ModuleLoader] RIFLE dir: {SCRIPTS_RIFLE_DIR}", flush=True)
print(f"[ModuleLoader] PISTOL dir: {SCRIPTS_PISTOL_DIR}", flush=True)


def set_mode(mode: str) -> None:
    """Set the current shooting mode ('rifle' or 'pistol')."""
    global _current_mode
    mode_lower = mode.lower()
    assert mode_lower in ('rifle', 'pistol'), f"Invalid mode: {mode}"
    _current_mode = mode_lower
    print(f"[ModuleLoader] Mode set to: {_current_mode}", flush=True)


def get_current_mode() -> str:
    """Get the current shooting mode."""
    return _current_mode


def reload_modules_for_mode(mode: str) -> None:
    """
    Force reload all cached modules for the given mode.
    
    This removes modules from sys.modules to trigger fresh imports,
    ensuring the correct rifle vs pistol code is loaded.
    
    Args:
        mode: 'rifle' or 'pistol'
    """
    global _current_mode, _module_cache
    
    mode_lower = mode.lower()
    assert mode_lower in ('rifle', 'pistol'), f"Invalid mode: {mode}"
    
    _current_mode = mode_lower
    
    # Remove old module references from sys.modules to force reimport
    # This ensures we get fresh module instances from the correct directory
    modules_to_remove = [
        m for m in list(sys.modules.keys()) 
        if m in ('model_prediction', 'frame_differencing', 'frame_preprocess')
    ]
    
    for m in modules_to_remove:
        try:
            del sys.modules[m]
            print(f"[ModuleLoader] Removed {m} from sys.modules", flush=True)
        except KeyError:
            pass
    
    # Clear cache for this mode
    _module_cache.clear()
    
    print(f"[ModuleLoader] Modules reloaded for mode: {_current_mode}", flush=True)


def get_module(module_name: str) -> Any:
    """
    Dynamically import and cache a module based on current mode.
    
    This function:
    1. Checks if the module is already cached for current mode
    2. If not, determines the correct directory (rifle or pistol)
    3. Adds that directory to sys.path
    4. Imports the module dynamically
    5. Caches it for future use
    
    Args:
        module_name: 'model_prediction', 'frame_differencing', 'frame_preprocess'
    
    Returns:
        The imported module from the appropriate folder
    
    Raises:
        ImportError: If the module cannot be imported
    """
    global _module_cache
    
    # Initialize cache for this module name if needed
    if module_name not in _module_cache:
        _module_cache[module_name] = {}
    
    # Return cached module if available
    if _current_mode in _module_cache[module_name]:
        return _module_cache[module_name][_current_mode]
    
    # Determine source folder
    if _current_mode == 'rifle':
        module_dir = SCRIPTS_RIFLE_DIR
        source = "rifle"
    else:
        module_dir = SCRIPTS_PISTOL_DIR
        source = "pistol"
    
    # Ensure module directory exists
    if not module_dir.exists():
        raise FileNotFoundError(f"Module directory not found: {module_dir}")
    
    # Add to sys.path temporarily if not already there
    module_dir_str = str(module_dir)
    if module_dir_str not in sys.path:
        sys.path.insert(0, module_dir_str)
        print(f"[ModuleLoader] Added to sys.path: {module_dir_str}", flush=True)
    
    try:
        # Dynamic import with proper error handling
        print(f"[ModuleLoader] Importing {module_name} from {source}...", flush=True)
        module = importlib.import_module(module_name)
        _module_cache[module_name][_current_mode] = module
        print(f"[ModuleLoader] ✅ Loaded {module_name} from {source} ({module_dir})", flush=True)
        return module
    except ImportError as e:
        print(f"[ModuleLoader] ❌ ERROR: Failed to load {module_name} from {source}: {e}", flush=True)
        raise


def get_model_prediction() -> Any:
    """Convenience wrapper to get mode-specific model_prediction module."""
    return get_module('model_prediction')


def get_frame_differencing() -> Any:
    """Convenience wrapper to get mode-specific frame_differencing module."""
    return get_module('frame_differencing')


def get_frame_preprocess() -> Any:
    """Convenience wrapper to get mode-specific frame_preprocess module."""
    return get_module('frame_preprocess')
