# Ensures a clean pytest environment and avoids external plugins breaking collection.
import os
import sys
import types

# Disable auto-loading of external pytest plugins (e.g., ROS launch_testing)
os.environ.setdefault('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')

# Provide a minimal OpenCV stub only when:
# 1) real cv2 cannot be imported, AND
# 2) we are under pytest (gymnasium wrappers otherwise fail import-time).
#
# Do NOT stub cv2 for normal app/TTS runs: CosyVoice/torchvision require a real
# cv2 module with a non-None __spec__. A blank ModuleType breaks with:
#   cv2.__spec__ is None
_running_pytest = (
    os.environ.get('PYTEST_CURRENT_TEST') is not None
    or any(arg == 'pytest' or arg.endswith('/pytest') or arg.endswith('\\pytest')
           for arg in sys.argv)
    or any('pytest' in (arg or '') for arg in sys.argv[:2])
)

if _running_pytest and 'cv2' not in sys.modules:
    try:
        import cv2  # noqa: F401
    except ImportError:
        mod = types.ModuleType('cv2')
        mod.__version__ = '0'
        sys.modules['cv2'] = mod
