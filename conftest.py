import sys

def pytest_configure(config):
    # Actively remove ROS launch testing plugins if loaded to prevent unexpected hooks
    for name in list(sys.modules.keys()):
        if name.startswith('launch_testing') or name.startswith('launch_testing_ros'):
            sys.modules.pop(name, None)
