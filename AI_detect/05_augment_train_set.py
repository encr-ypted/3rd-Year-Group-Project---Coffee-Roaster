#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from paths import TRAIN_AUGMENTED_DIR, TRAIN_DIR, clear_directory, iter_images


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Augment training images and write a clean train_set_augmented folder.")
    parser.add_argument("--input-dir", type=Path, default=TRAIN_DIR)
    parser.add_argument("--output-dir", type=Path, default=TRAIN_AUGMENTED_DIR)
    parser.add_argument("--copies-per-image", type=int, default=5)
    parser.add_argument("--rotation-deg", type=float, default=8.0)
    parser.add_argument("--brightness", type=float, default=0.12)
    parser.add_argument("--blur-probability", type=float, default=0.45)
    parser.add_argument("--noise-std", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def add_noise(image: Image.Image, rng: np.random.Generator, noise_std: float) -> Image.Image:
    array = np.asarray(image).astype(np.float32)
    noise = rng.normal(0.0, noise_std, array.shape)
    noisy = np.clip(array + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(noisy, mode="RGB")


def augment_once(
    image: Image.Image,
    python_rng: random.Random,
    numpy_rng: np.random.Generator,
    args: argparse.Namespace,
) -> Image.Image:
    augmented = image.copy()
    if python_rng.random() < 0.5:
        augmented = ImageOps.mirror(augmented)

    angle = python_rng.uniform(-args.rotation_deg, args.rotation_deg)
    fill = tuple(int(v) for v in ImageStatMean(augmented))
    augmented = augmented.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=fill)

    brightness_factor = 1.0 + python_rng.uniform(-args.brightness, args.brightness)
    augmented = ImageEnhance.Brightness(augmented).enhance(brightness_factor)

    if python_rng.random() < args.blur_probability:
        augmented = augmented.filter(ImageFilter.GaussianBlur(radius=python_rng.uniform(0.3, 1.0)))

    if args.noise_std > 0:
        augmented = add_noise(augmented, numpy_rng, python_rng.uniform(0.3, 1.0) * args.noise_std)

    return augmented


def ImageStatMean(image: Image.Image) -> tuple[float, float, float]:
    array = np.asarray(image.convert("RGB"), dtype=np.float32)
    return tuple(array.reshape(-1, 3).mean(axis=0))


def main() -> int:
    args = parse_args()
    images = list(iter_images(args.input_dir))
    if not images:
        print(f"No images found in {args.input_dir}")
        return 1
    if args.copies_per_image < 0:
        print("--copies-per-image must be >= 0")
        return 1

    clear_directory(args.output_dir)
    python_rng = random.Random(args.seed)
    numpy_rng = np.random.default_rng(args.seed)

    print("SmartRoast training data augmentation")
    print(f"Input: {args.input_dir}")
    print(f"Output: {args.output_dir}")
    print(f"Copies per image: {args.copies_per_image}")

    original_count = 0
    augmented_count = 0
    for source in images:
        relative = source.relative_to(args.input_dir)
        original_target = args.output_dir / relative
        original_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, original_target)
        original_count += 1

        with Image.open(source) as raw_image:
            image = raw_image.convert("RGB")
            for copy_index in range(1, args.copies_per_image + 1):
                augmented = augment_once(image, python_rng, numpy_rng, args)
                target = original_target.with_name(f"{original_target.stem}_aug{copy_index:02d}{original_target.suffix}")
                augmented.save(target, quality=95)
                augmented_count += 1

    print(f"Finished. Copied {original_count} original image(s), created {augmented_count} augmented image(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
