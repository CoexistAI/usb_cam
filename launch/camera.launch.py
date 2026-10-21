#!/usr/bin/env python3
"""Launch the USB camera and its image transports in the /fisheye namespace."""

import glob
import os
import re
import subprocess

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _device_product_name(dev_path: str) -> str:
    """Return the product name for a /dev/video* node, or an empty string."""
    try:
        result = subprocess.run(
            ['v4l2-ctl', '-d', dev_path, '--info'],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            match = re.search(r'Card type\s*:\s*(.+)', result.stdout)
            if match:
                return match.group(1).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    sysfs_name = f'/sys/class/video4linux/{os.path.basename(dev_path)}/name'
    try:
        with open(sysfs_name, encoding='utf-8') as name_file:
            return name_file.read().strip()
    except OSError:
        return ''


def _is_capture_device(dev_path: str) -> bool:
    """Check that a video node supports capture rather than only metadata."""
    try:
        result = subprocess.run(
            ['v4l2-ctl', '-d', dev_path, '--all'],
            capture_output=True, text=True, timeout=2,
        )
        return (
            result.returncode == 0
            and 'Video Capture' in result.stdout
            and 'Format Video Capture' in result.stdout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True


def _resolve_video_device(name_filter: str) -> str:
    """Pick the first capture device matching an optional product substring."""
    candidates = sorted(
        glob.glob('/dev/video[0-9]*'),
        key=lambda path: int(re.search(r'\d+', os.path.basename(path)).group()),
    )
    if not candidates:
        raise RuntimeError('No /dev/video* devices found on this system.')

    for device in candidates:
        if not _is_capture_device(device):
            continue
        product = _device_product_name(device)
        if not name_filter or name_filter.lower() in product.lower():
            print(f'[usb_cam_launch] Selected camera: {device} ("{product}")')
            return device

    raise RuntimeError(
        f'No capture device matched camera_name_filter "{name_filter}". '
        f'Available devices: {candidates}'
    )


def _launch_setup(context, *args, **kwargs):
    """Resolve the camera device and create the USB camera node."""
    camera_config = LaunchConfiguration('camera_config').perform(context)
    name_filter = LaunchConfiguration('camera_name_filter').perform(context)
    video_device = LaunchConfiguration('video_device').perform(context)

    if video_device:
        print(f'[usb_cam_launch] Using user-specified camera: {video_device}')
    else:
        video_device = _resolve_video_device(name_filter)

    return [Node(
        package='usb_cam',
        executable='usb_cam_node_exe',
        name='usb_cam',
        namespace='fisheye',
        output='screen',
        parameters=[
            camera_config,
            {'video_device': video_device},
        ],
    )]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'camera_config',
            default_value=PathJoinSubstitution([
                FindPackageShare('usb_cam'), 'config', 'params_1.yaml',
            ]),
            description='Path to the USB camera ROS parameter YAML file.',
        ),
        DeclareLaunchArgument(
            'video_device',
            default_value='',
            description=(
                'Explicit video device (e.g. /dev/video0). '
                'If empty, auto-detect a capture device.'
            ),
        ),
        DeclareLaunchArgument(
            'camera_name_filter',
            default_value='See3CAM_CU31',
            description=(
                'Optional camera product-name substring for auto-detection. '
                'If empty, use the first capture device.'
            ),
        ),
        OpaqueFunction(function=_launch_setup),
    ])
