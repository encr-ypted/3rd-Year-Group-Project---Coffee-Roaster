#!/usr/bin/env python3
from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from PIL import Image

from camera_utils import CameraError, capture_image, module_available
from grayscale_utils import mean_grayscale
from paths import TEST_OUTPUT_DIR, ensure_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a one-command camera and image-processing test.")
    parser.add_argument("--backend", choices=["auto", "picamera2", "opencv"], default="auto")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index when using OpenCV.")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--warmup", type=float, default=1.5, help="Camera warmup seconds.")
    parser.add_argument("--output-dir", type=Path, default=TEST_OUTPUT_DIR)
    parser.add_argument("--mock", action="store_true", help="Generate a synthetic frame instead of using hardware.")
    parser.add_argument("--crop", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"))
    return parser.parse_args()


def centered_crop_box(width: int, height: int) -> tuple[int, int, int, int]:
    crop_width = int(width * 0.42)
    crop_height = int(height * 0.36)
    x1 = (width - crop_width) // 2
    y1 = (height - crop_height) // 2
    return x1, y1, x1 + crop_width, y1 + crop_height


def check_dependencies() -> None:
    print("[1/5] Environment and dependency check")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.platform()}")
    for module_name in ["PIL", "numpy", "matplotlib", "torch", "cv2", "picamera2"]:
        status = "available" if module_available(module_name) else "missing"
        print(f"  - {module_name}: {status}")


def main() -> int:
    args = parse_args()
    output_dir = ensure_dir(args.output_dir)
    capture_path = output_dir / "camera_test_frame.jpg"
    crop_path = output_dir / "camera_test_crop.jpg"
    gray_path = output_dir / "camera_test_gray.jpg"

    print("SmartRoast AI camera and image-processing test")
    check_dependencies()

    print("[2/5] Capturing test frame")
    try:
        metadata = capture_image(
            capture_path,
            backend=args.backend,
            width=args.width,
            height=args.height,
            camera_index=args.camera_index,
            warmup_seconds=args.warmup,
            mock=args.mock,
        )
    except CameraError as exc:
        print(f"Camera test failed: {exc}")
        print("Try --mock on a laptop, or check Raspberry Pi camera cable, libcamera, and Picamera2 install.")
        return 1
    print(f"Saved frame: {capture_path}")
    print(f"Capture backend: {metadata['backend']}")

    print("[3/5] Inspecting image resolution and format")
    with Image.open(capture_path) as image:
        width, height = image.size
        print(f"Image size: {width} x {height}")
        print(f"Image mode: {image.mode}")
        print(f"File size: {capture_path.stat().st_size / 1024:.1f} KiB")

        crop_box = tuple(args.crop) if args.crop else centered_crop_box(width, height)
        x1, y1, x2, y2 = crop_box
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x1 >= x2 or y1 >= y2:
            print(f"Invalid crop box {crop_box} for image size {width}x{height}")
            return 1

        print("[4/5] Running crop and grayscale processing")
        cropped = image.crop(crop_box)
        cropped.save(crop_path, quality=95)

    gray_mean = mean_grayscale(crop_path, save_gray_to=gray_path)
    print(f"Crop box: ({x1}, {y1}) to ({x2}, {y2})")
    print(f"Saved crop: {crop_path}")
    print(f"Saved grayscale crop: {gray_path}")
    print(f"Mean grayscale value: {gray_mean:.2f} / 255")

    print("[5/5] Final analysis")
    if gray_mean < 70:
        brightness_note = "The selected crop is quite dark; check lighting before collecting training data."
    elif gray_mean > 190:
        brightness_note = "The selected crop is very bright; watch for glare or overexposure."
    else:
        brightness_note = "The selected crop brightness is in a usable starting range."
    print(brightness_note)
    print("Camera capture, crop, grayscale conversion, and basic file output completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
