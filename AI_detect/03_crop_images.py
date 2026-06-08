#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from paths import RAW_DIR, RESIZED_DIR, clear_directory, ensure_dir, iter_images


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crop a fixed bean region from all captured images.")
    parser.add_argument("--x1", type=int, required=True, help="Top-left x coordinate.")
    parser.add_argument("--y1", type=int, required=True, help="Top-left y coordinate.")
    parser.add_argument("--x2", type=int, required=True, help="Bottom-right x coordinate.")
    parser.add_argument("--y2", type=int, required=True, help="Bottom-right y coordinate.")
    parser.add_argument("--input-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=RESIZED_DIR)
    parser.add_argument("--resize", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--label", help="Optional class folder name, e.g. bean or no_bean.")
    parser.add_argument("--clear-output", action="store_true", help="Delete old cropped images first.")
    return parser.parse_args()


def output_path_for(image_path: Path, input_dir: Path, output_dir: Path, label: str | None) -> Path:
    if label:
        relative_parent = Path(label)
    else:
        relative_parent = image_path.parent.relative_to(input_dir)
        if str(relative_parent) == ".":
            relative_parent = Path()
    return output_dir / relative_parent / image_path.name


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for counter in range(1, 10000):
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique output path for {path}")


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir
    output_dir = ensure_dir(args.output_dir)
    if args.clear_output:
        clear_directory(output_dir)

    crop_box = (args.x1, args.y1, args.x2, args.y2)
    if args.x1 < 0 or args.y1 < 0 or args.x1 >= args.x2 or args.y1 >= args.y2:
        print(f"Invalid crop box: {crop_box}")
        return 1

    images = list(iter_images(input_dir))
    if not images:
        print(f"No images found in {input_dir}")
        return 1

    print("SmartRoast fixed-region crop")
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Crop box: {crop_box}")
    if args.resize:
        print(f"Resize cropped output to: {args.resize[0]}x{args.resize[1]}")

    saved = 0
    skipped = 0
    for image_path in images:
        try:
            with Image.open(image_path) as image:
                width, height = image.size
                if args.x2 > width or args.y2 > height:
                    print(f"skip {image_path.name}: crop box outside {width}x{height}")
                    skipped += 1
                    continue
                cropped = image.crop(crop_box)
                if args.resize:
                    cropped = cropped.resize(tuple(args.resize), Image.Resampling.LANCZOS)
                target = unique_path(output_path_for(image_path, input_dir, output_dir, args.label))
                target.parent.mkdir(parents=True, exist_ok=True)
                cropped.save(target, quality=95)
                saved += 1
        except Exception as exc:
            print(f"skip {image_path}: {exc}")
            skipped += 1

    print(f"Finished. Saved {saved} cropped image(s), skipped {skipped}.")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
