# Skill Catalog

> Auto-generated from the `@skill` registry. Do not edit manually.
> Run `python scripts/generate_skill_catalog.py` to regenerate.

| Skill Name | Safety Class | Description |
|---|---|---|
| `community.system_info.get_overview` | `read_only` | Retrieve comprehensive hardware, host operating system, and runtime telemetry. |
| `computer_use.browser.click` | `act_with_approval` | Click a DOM element identified by CSS or XPath selector. |
| `computer_use.browser.close` | `act_autonomous` | Close the active browser tab and session. |
| `computer_use.browser.get_text` | `read_only` | Extract visible text content from a DOM element or entire page. |
| `computer_use.browser.open_url` | `act_with_approval` | Navigate the browser to a given URL. |
| `computer_use.browser.screenshot` | `read_only` | Capture a screenshot of the current browser tab. |
| `computer_use.browser.type_text` | `act_with_approval` | Fill or type text into an input field identified by selector. |
| `computer_use.desktop.click_mouse` | `act_with_approval` | Click a mouse button at the current cursor position. |
| `computer_use.desktop.focus_window` | `act_with_approval` | Activate and focus an application window by handle or title query. |
| `computer_use.desktop.get_active_window` | `read_only` | Retrieve the active foreground desktop window. |
| `computer_use.desktop.get_cursor_position` | `read_only` | Get current absolute screen coordinates of mouse cursor. |
| `computer_use.desktop.get_screen_size` | `read_only` | Query primary screen width and height in pixels. |
| `computer_use.desktop.list_windows` | `read_only` | Enumerate visible desktop application windows with titles, dimensions, and process IDs. |
| `computer_use.desktop.mouse_drag` | `act_with_approval` | Drag mouse from start coordinates to end coordinates. |
| `computer_use.desktop.mouse_scroll` | `act_with_approval` | Scroll the mouse wheel up or down. |
| `computer_use.desktop.move_mouse` | `act_with_approval` | Move cursor to screen coordinates (x, y) with safety bounds validation. |
| `computer_use.desktop.send_hotkey` | `act_with_approval` | Send hotkey combination with destructive combination prevention. |
| `computer_use.desktop.set_safety_bounds` | `act_with_approval` | Configure cursor safety bounding box and enforcement policy ('raise' or 'clamp'). |
| `computer_use.desktop.type_text` | `act_with_approval` | Type text string via low-level native keyboard unicode dispatch. |
| `computer_use.file.delete` | `act_with_approval` | Delete a file or directory tree |
| `computer_use.file.list_dir` | `read_only` | List directory contents |
| `computer_use.file.read` | `read_only` | Read a file |
| `computer_use.file.write` | `act_with_approval` | Write to a file |
| `computer_use.shell.run` | `act_with_approval` | Run a shell command |
| `iot.lights.get_status` | `read_only` | Read current light state |
| `iot.lights.set_brightness` | `act_with_approval` | Set brightness level (0-100) |
| `iot.lights.toggle` | `act_with_approval` | Toggle light on/off via MQTT |
| `iot.sensors.list` | `read_only` | List available sensors |
| `iot.sensors.read` | `read_only` | Read a named sensor's current value |
| `iot.thermostat.get_temperature` | `read_only` | Read current temperature |
| `iot.thermostat.set_mode` | `act_with_approval` | Set mode (heat/cool/auto/off) |
| `iot.thermostat.set_temperature` | `act_with_approval` | Set target temperature |
| `robotics.arm.home` | `act_autonomous` | Return arm to default home configuration. |
| `robotics.arm.move_to` | `act_with_approval` | Calculate kinematics and move robot arm end-effector to target Cartesian position (x, y, z). |
| `robotics.arm.pick_place` | `act_with_approval` | Execute complete autonomous pick-and-place sequence with approach, grasp, transfer, and release. |
| `robotics.arm.set_gripper` | `act_with_approval` | Actuate arm gripper mechanism to grab or release objects. |
| `robotics.navigate.compute_velocity` | `read_only` | Compute safe (linear, angular) velocity commands to reach a goal while avoiding obstacles via DWA. |
| `robotics.navigate.get_position` | `read_only` | Query current odometry pose, velocity, and distance telemetry. |
| `robotics.navigate.go_to` | `act_with_approval` | Navigate mobile robot to a named map waypoint or Cartesian coordinates. |
| `robotics.navigate.go_to_coords` | `act_with_approval` | Navigate robot base to exact (x, y, yaw_degrees) planar coordinates. |
| `robotics.navigate.localize_landmark` | `read_only` | Fuse relative range and bearing measurement to a known landmark into EKF state. |
| `robotics.navigate.localize_position_fix` | `read_only` | Fuse an absolute coordinate position fix (GPS/UWB/vision) into EKF state. |
| `robotics.navigate.localize_predict` | `read_only` | Advance robot state and covariance prediction using EKF motion model. |
| `robotics.navigate.plan_path` | `read_only` | Compute collision-free 2D path waypoints to target coordinates using A* planning. |
| `robotics.navigate.stop` | `act_autonomous` | Engage emergency brake and immediately halt all mobile base movement. |
| `robotics.navigate.track_path` | `read_only` | Calculate steering and velocity commands to track waypoints using Pure Pursuit. |
