# Ensures a clean pytest environment and avoids external plugins breaking collection.
import os, sys, types

# Disable auto-loading of external pytest plugins (e.g., ROS launch_testing)
os.environ.setdefault('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')

# Provide a minimal stub for OpenCV to avoid import-time failures in gymnasium wrappers
if 'cv2' not in sys.modules:
    mod = types.ModuleType('cv2')
    mod.__version__ = '0'
    sys.modules['cv2'] = mod
