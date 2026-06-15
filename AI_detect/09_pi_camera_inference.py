#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from pi_ai_detector import InferenceResult, SmartRoastAIDetector
from paths import DEFAULT_CLASS_NAMES, DEFAULT_PT_MODEL_PATH, DEFAULT_RPK_MODEL_PATH, TEST_OUTPUT_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SmartRoast bean/corrupted inference on Raspberry Pi camera frames.")
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
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index when using --backend opencv.")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--warmup", type=float, default=1.5)
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between frames in continuous mode.")
    parser.add_argument("--count", type=int, default=1, help="Number of frames to process. 0 means run until Ctrl+C.")
    parser.add_argument("--roi", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"), help="Manual ROI crop.")
    parser.add_argument(
        "--roi-mode",
        choices=["training-center", "full-frame"],
        default="training-center",
        help="training-center matches 01_full_system_test.py.",
    )
    parser.add_argument(
        "--imx500-roi-mode",
        choices=["match-output-roi", "manual", "auto-aspect"],
        default="match-output-roi",
        help="How the IMX500 inference input ROI is selected for .rpk inference.",
    )
    parser.add_argument(
        "--imx500-roi-abs",
        nargs=4,
        type=int,
        metavar=("X", "Y", "W", "H"),
        help="Manual IMX500 inference ROI in full sensor coordinates.",
    )
    parser.add_argument("--save-crops", action="store_true", help="Save ROI crops used for inference.")
    parser.add_argument("--output-dir", type=Path, default=TEST_OUTPUT_DIR / "pi_inference")
    parser.add_argument("--csv-log", type=Path, help="Optional CSV log path.")
    return parser.parse_args()


def append_csv(path: Path, result: InferenceResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = result.to_row()
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    args = parse_args()
    roi = tuple(args.roi) if args.roi else None
    imx500_roi_abs = tuple(args.imx500_roi_abs) if args.imx500_roi_abs else None

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
            imx500_roi_abs=imx500_roi_abs,
            imx500_roi_mode=args.imx500_roi_mode,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(exc)
        return 1

    print("SmartRoast Raspberry Pi inference")
    print(f"Backend: {args.backend}")
    print(f"Inference: {detector.device_label}")
    print(f"Model format: {detector.model_format}")
    print(f"Model: {args.model}")
    print(f"Classes: {detector.class_names}")
    print(f"Output ROI: {detector.output_roi_for_inference}")
    print(f"IMX500 ROI mode: {args.imx500_roi_mode}")
    print(f"Count: {'until Ctrl+C' if args.count == 0 else args.count}")

    processed = 0
    try:
        with detector:
            while args.count == 0 or processed < args.count:
                result = detector.infer_once(save_crop=args.save_crops)
                processed += 1
                print(SmartRoastAIDetector.format_result(processed, result))

                if args.csv_log:
                    append_csv(args.csv_log, result)

                if args.count == 0 or processed < args.count:
                    time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as exc:
        print(f"Inference failed: {exc}")
        return 1

    print(f"Finished. Processed {processed} frame(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
