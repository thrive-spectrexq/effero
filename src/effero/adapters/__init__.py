"""Device Abstraction Layer (DAL): where skills actually touch hardware.

Submodules:

- ros2          -- robotics middleware bridge (requires the `ros2` extra)
- mqtt_matter   -- IoT bridge for MQTT / Matter / Zigbee / Thread (requires the `iot` extra)
- serial_gpio   -- microcontroller bridge (Arduino, ESP32, raw GPIO)
- cloud_api     -- generic REST / cloud API adapter
"""
