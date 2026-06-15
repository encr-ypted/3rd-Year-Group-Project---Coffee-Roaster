#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import torch
except ImportError as exc:
    print("PyTorch is required for prediction. Install torch before running this script.")
    raise SystemExit(1) from exc

from grayscale_utils import mean_grayscale
from model_utils import ConfigurableCNN
from paths import MODEL_DIR, TEST_OUTPUT_DIR, ensure_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict bean/no_bean/corrupted for one image.")
    parser.add_argument("image", type=Path, help="Input image path.")
    parser.add_argument("--model", type=Path, default=MODEL_DIR / "best_model.pt")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument(
        "--frame-crop",
        choices=["none", "auto"],
        default="auto",
        help="Use auto for browser screenshots/phone photos with black borders around the camera frame.",
    )
    parser.add_argument(
        "--roi-crop",
        choices=["none", "training-center"],
        default="training-center",
        help="training-center matches the centred crop used by 01_full_system_test.py.",
    )
    parser.add_argument("--crop", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"), help="Manual crop on the original image.")
    parser.add_argument("--background-threshold", type=int, default=25)
    parser.add_argument("--ignore-top-ratio", type=float, default=0.15)
    parser.add_argument("--min-row-fraction", type=float, default=0.08)
    parser.add_argument("--min-col-fraction", type=float, default=0.08)
    parser.add_argument("--save-debug", action="store_true", help="Save intermediate crops for inspection.")
    parser.add_argument("--output-dir", type=Path, default=TEST_OUTPUT_DIR)
    return parser.parse_args()


def choose_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but PyTorch cannot access a CUDA GPU.")
    return torch.device(requested)


def centred_training_crop_box(width: int, height: int) -> tuple[int, int, int, int]:
    crop_width = int(width * 0.42)
    crop_height = int(height * 0.36)
    x1 = (width - crop_width) // 2
    y1 = (height - crop_height) // 2
    return x1, y1, x1 + crop_width, y1 + crop_height


def validate_crop_box(box: tuple[int, int, int, int], width: int, height: int) -> None:
    x1, y1, x2, y2 = box
    if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x1 >= x2 or y1 >= y2:
        raise ValueError(f"Invalid crop box {box} for image size {width}x{height}")


def auto_frame_crop_box(
    image: Image.Image,
    *,
    background_threshold: int,
    ignore_top_ratio: float,
    min_row_fraction: float,
    min_col_fraction: float,
) -> tuple[int, int, int, int]:
    array = np.asarray(image.convert("RGB"))
    height, width = array.shape[:2]
    ignore_top = int(height * ignore_top_ratio)

    usable = array[ignore_top:, :, :3]
    strip_width = max(1, int(width * 0.05))
    strip_height = max(1, int((height - ignore_top) * 0.08))
    background_samples = np.concatenate(
        [
            usable[:, :strip_width, :].reshape(-1, 3),
            usable[:, -strip_width:, :].reshape(-1, 3),
            usable[-strip_height:, :, :].reshape(-1, 3),
        ],
        axis=0,
    )
    background = np.median(background_samples, axis=0)
    mask = np.abs(array[:, :, :3].astype(np.float32) - background).max(axis=2) > background_threshold
    mask[:ignore_top, :] = False

    row_counts = mask.sum(axis=1)
    col_counts = mask.sum(axis=0)
    min_row_pixels = max(10, int(width * min_row_fraction))
    min_col_pixels = max(10, int(height * min_col_fraction))
    rows = np.where(row_counts >= min_row_pixels)[0]
    cols = np.where(col_counts >= min_col_pixels)[0]

    if len(rows) == 0 or len(cols) == 0:
        rows = np.where(mask.any(axis=1))[0]
        cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        raise ValueError("Auto frame crop failed. Try --frame-crop none or pass --crop X1 Y1 X2 Y2.")

    x1, x2 = int(cols[0]), int(cols[-1]) + 1
    y1, y2 = int(rows[0]), int(rows[-1]) + 1
    return x1, y1, x2, y2


def load_checkpoint(model_path: Path, device: torch.device) -> dict:
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    return torch.load(model_path, map_location=device)


def image_to_tensor(image: Image.Image, *, image_size: tuple[int, int], mean: list[float], std: list[float]) -> torch.Tensor:
    resized = image.convert("RGB").resize(image_size, Image.Resampling.BILINEAR)
    array = np.asarray(resized, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(array).permute(2, 0, 1)
    mean_tensor = torch.tensor(mean, dtype=torch.float32).view(3, 1, 1)
    std_tensor = torch.tensor(std, dtype=torch.float32).view(3, 1, 1)
    return ((tensor - mean_tensor) / std_tensor).unsqueeze(0)


def main() -> int:
    args = parse_args()
    try:
        device = choose_device(args.device)
        checkpoint = load_checkpoint(args.model, device)
    except (RuntimeError, FileNotFoundError) as exc:
        print(exc)
        return 1

    class_names = checkpoint["class_names"]
    model = ConfigurableCNN(num_classes=len(class_names), spec=checkpoint["model_spec"])
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    with Image.open(args.image) as source:
        image = source.convert("RGB")

    original_size = image.size
    debug_dir = ensure_dir(args.output_dir) if args.save_debug else None
    debug_stem = args.image.stem

    try:
        if args.crop:
            box = tuple(args.crop)
            validate_crop_box(box, image.width, image.height)
            image = image.crop(box)
            frame_box = box
        elif args.frame_crop == "auto":
            frame_box = auto_frame_crop_box(
                image,
                background_threshold=args.background_threshold,
                ignore_top_ratio=args.ignore_top_ratio,
                min_row_fraction=args.min_row_fraction,
                min_col_fraction=args.min_col_fraction,
            )
            image = image.crop(frame_box)
        else:
            frame_box = None

        if debug_dir is not None:
            image.save(debug_dir / "predict_frame_crop.jpg", quality=95)
            image.save(debug_dir / f"{debug_stem}_frame_crop.jpg", quality=95)

        if args.roi_crop == "training-center":
            roi_box = centred_training_crop_box(image.width, image.height)
            validate_crop_box(roi_box, image.width, image.height)
            image = image.crop(roi_box)
        else:
            roi_box = None
    except ValueError as exc:
        print(exc)
        return 1

    if debug_dir is not None:
        image.save(debug_dir / "predict_roi_crop.jpg", quality=95)
        image.save(debug_dir / f"{debug_stem}_roi_crop.jpg", quality=95)

    image_size = tuple(int(value) for value in checkpoint["image_size"])
    tensor = image_to_tensor(
        image,
        image_size=image_size,
        mean=[float(value) for value in checkpoint["normalise_mean"]],
        std=[float(value) for value in checkpoint["normalise_std"]],
    ).to(device)

    with torch.no_grad():
        logits = model(tensor)
        probabilities = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()

    best_index = int(probabilities.argmax())
    prediction = class_names[best_index]
    gray_mean = mean_grayscale(image)

    print("SmartRoast image prediction")
    print(f"Input image: {args.image}")
    print(f"Original size: {original_size[0]}x{original_size[1]}")
    print(f"Model: {args.model}")
    print(f"Device: {device}")
    print(f"Frame crop: {frame_box if frame_box is not None else 'none'}")
    print(f"ROI crop: {roi_box if roi_box is not None else 'none'}")
    print(f"ROI size before model resize: {image.width}x{image.height}")
    print(f"Mean grayscale of ROI: {gray_mean:.2f}")
    print(f"Prediction: {prediction}")
    print("Probabilities:")
    for class_name, probability in sorted(zip(class_names, probabilities), key=lambda item: item[1], reverse=True):
        print(f"  {class_name}: {probability:.4f}")

    if debug_dir is not None:
        print(f"Saved debug crops to: {debug_dir}")
        print(f"Latest ROI crop: {debug_dir / 'predict_roi_crop.jpg'}")
        print(f"Named ROI crop: {debug_dir / f'{debug_stem}_roi_crop.jpg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
