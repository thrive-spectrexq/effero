# Example: Mobile Manipulator (VLA + ROS 2 + Navigation)

A unified mobile manipulator agent that coordinates planar base navigation, visual perception, and robotic arm trajectory planning with OMG CDR wire streaming to ROS 2.

```
┌─────────────────────────────────────────────────────────────┐
│                 Effero Agent Runtime                        │
│   - Mobile Navigation (_nav_controller / A* / DWA / EKF)    │
│   - Vision Perception (Detector / Frame Stream)             │
│   - Arm Manipulation (_arm_controller / Kinematics)        │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
                ▼                             ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ geometry_msgs/Twist (CDR)    │ │ trajectory_msgs/JointTraj    │
│ -> /cmd_vel (socket / 9090)  │ │ -> /joint_trajectory (CDR)   │
└──────────────────────────────┘ └──────────────────────────────┘
```

## Features

- **Mobile Base Navigation**: Uses A* global path planning and DWA obstacle avoidance to transit between named map coordinates (`charging_station`, `lab`, `workstation`).
- **Vision Perception**: Inspects surface workpieces, extracts bounding boxes, and computes 3D grasping coordinates.
- **Arm Kinematics & Collision Checks**: Analytical inverse kinematics with quintic minimum jerk trajectories and Cartesian workspace bounding box checks.
- **Real-Time ROS 2 Streaming**: Emits length-prefixed OMG CDR little-endian wire frames over TCP to ROS 2 nodes or rosbridge.

## Running the Example

### 1. Run the Autonomous Scenario

Execute the end-to-end mission (navigate to workstation, detect workpiece, execute pick-and-place, and return to charging station):

```bash
python examples/mobile-manipulator/main.py --scenario
```

### 2. Interactive Console REPL

Start an interactive natural language chat session with the mobile manipulator agent:

```bash
python examples/mobile-manipulator/main.py
```

Example commands:
- `Navigate to the lab workstation`
- `Pick up the workpiece at x=0.25, y=0.10, z=0.05 and place it at x=0.25, y=-0.15, z=0.08`
- `Return to charging station and report current odometry`
