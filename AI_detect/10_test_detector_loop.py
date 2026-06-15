#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path

from pi_ai_detector import SmartRoastAIDetector
from paths import DEFAULT_CLASS_NAMES, DEFAULT_PT_MODEL_PATH, DEFAULT_RPK_MODEL_PATH, TEST_OUTPUT_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the reusable SmartRoastAIDetector class.")
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_RPK_MODEL_PATH,
        help=f"Path to the IMX500 .rpk model. Default: {DEFAULT_RPK_MODEL_PATH}",
    )
    parser.add_argument("--model-format", choices=["auto", "rpk", "pt"], default="auto")
    parser.add_argument(
        "--class-names",
        nargs="+",
        default=list(DEFAULT_CLASS_NAMES),
        help="Class order used by the .rpk model output.",
    )
    parser.add_argument("--backend", choices=["picamera2", "opencv", "mock"], default="picamera2")
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help=f"Only used with --model-format pt, for example --model {DEFAULT_PT_MODEL_PATH}.",
    )
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--warmup", type=float, default=1.5)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--roi", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"))
    parser.add_argument("--roi-mode", choices=["training-center", "full-frame"], default="training-center")
    parser.add_argument("--save-crops", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=TEST_OUTPUT_DIR / "detector_loop")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roi = tuple(args.roi) if args.roi else None

    try:
        detector = SmartRoastAIDetector(
            model_path=args.model,
            model_format=args.model_format,
            backend=args.backend,
            device=args.device,
            camera_index=args.camera_index,
            width=args.width,
            height=args.height,
            warmup=args.warmup,
            roi=roi,
            roi_mode=args.roi_mode,
            output_dir=args.output_dir,
            class_names=args.class_names,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(exc)
        return 1

    print("SmartRoast detector loop test")
    print(f"Backend: {args.backend}")
    print(f"Inference: {detector.device_label}")
    print(f"Model format: {detector.model_format}")
    print(f"Model is loaded once from: {args.model}")
    print(f"Interval: {args.interval:.1f}s")
    print(f"Count: {'until Ctrl+C' if args.count == 0 else args.count}")

    processed = 0
    try:
        with detector:
            while args.count == 0 or processed < args.count:
                result = detector.infer_once(save_crop=args.save_crops)
                processed += 1
                print(SmartRoastAIDetector.format_result(processed, result))

                if args.count == 0 or processed < args.count:
                    time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as exc:
        print(f"Detector loop failed: {exc}")
        return 1

    print(f"Finished. Processed {processed} frame(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
