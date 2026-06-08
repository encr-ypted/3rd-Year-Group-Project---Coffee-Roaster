#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path

from camera_utils import CameraError, CameraSession
from paths import RAW_DIR, capture_filename, ensure_dir, next_capture_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatically capture roast images at a fixed interval.")
    parser.add_argument("--batch-id", required=True, help="Roast batch identifier, e.g. 2026-06-08-A.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between captures.")
    parser.add_argument("--count", type=int, default=0, help="Number of images. 0 means run until Ctrl+C.")
    parser.add_argument("--output-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--backend", choices=["auto", "picamera2", "opencv"], default="auto")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--warmup", type=float, default=1.5)
    parser.add_argument("--start-index", type=int, help="Override the next image number.")
    parser.add_argument("--mock", action="store_true", help="Generate synthetic frames for testing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_dir = ensure_dir(args.output_dir)
    start_index = args.start_index if args.start_index is not None else next_capture_index(raw_dir, args.batch_id)
    captured = 0

    print("SmartRoast automatic capture")
    print(f"Output directory: {raw_dir}")
    print(f"Batch id: {args.batch_id}")
    print(f"Start index: {start_index}")
    print(f"Interval: {args.interval:.2f} seconds")
    print("Press Ctrl+C to stop when count is 0.")

    try:
        with CameraSession(
            backend=args.backend,
            width=args.width,
            height=args.height,
            camera_index=args.camera_index,
            warmup_seconds=args.warmup,
            mock=args.mock,
        ) as camera:
            print(f"Camera backend: {camera.selected_backend}")
            next_time = time.monotonic()
            while args.count == 0 or captured < args.count:
                now = time.monotonic()
                if now < next_time:
                    time.sleep(next_time - now)

                image_index = start_index + captured
                filename = capture_filename(args.batch_id, image_index)
                output_path = raw_dir / filename
                metadata = camera.capture(output_path)
                captured += 1
                print(
                    f"[{captured}] saved {output_path.name} "
                    f"({metadata['width']}x{metadata['height']})"
                )
                next_time += args.interval
    except KeyboardInterrupt:
        print("Capture stopped by user.")
    except CameraError as exc:
        print(f"Capture failed: {exc}")
        return 1

    print(f"Finished. Captured {captured} image(s) into {raw_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
