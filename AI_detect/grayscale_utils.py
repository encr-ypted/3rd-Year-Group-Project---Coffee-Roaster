from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageStat


ImageInput = str | Path | Image.Image | BinaryIO


def to_grayscale_image(image_input: ImageInput) -> Image.Image:
    if isinstance(image_input, Image.Image):
        image = image_input
    else:
        image = Image.open(image_input)
    return image.convert("L")


def mean_grayscale(image_input: ImageInput, save_gray_to: str | Path | None = None) -> float:
    gray = to_grayscale_image(image_input)
    if save_gray_to is not None:
        output_path = Path(save_gray_to)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gray.save(output_path)
    return float(ImageStat.Stat(gray).mean[0])
