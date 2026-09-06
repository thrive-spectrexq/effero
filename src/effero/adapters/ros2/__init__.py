"""ROS 2 bridge.

Requires the optional `ros2` extra (`pip install effero[ros2]`), which
pulls in rclpy. This module intentionally does not import rclpy at the
top level so that `import effero` works fine on machines without ROS 2
installed.
"""
