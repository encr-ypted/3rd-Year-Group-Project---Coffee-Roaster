#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

from paths import RESIZED_DIR, TEST_DIR, TRAIN_DIR, VALIDATE_DIR, clear_directory, ensure_dir, iter_images


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split cropped images into train, validate, and test sets.")
    parser.add_argument("--input-dir", type=Path, default=RESIZED_DIR)
    parser.add_argument("--train-dir", type=Path, default=TRAIN_DIR)
    parser.add_argument("--validate-dir", type=Path, default=VALIDATE_DIR)
    parser.add_argument("--test-dir", type=Path, default=TEST_DIR)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validate-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def split_counts(n_items: int, train_ratio: float, validate_ratio: float) -> tuple[int, int, int]:
    if n_items < 3:
        raise ValueError("At least 3 images are required so train, validate, and test can all receive data.")
    validate_count = max(1, round(n_items * validate_ratio))
    test_count = max(1, n_items - round(n_items * train_ratio) - validate_count)
    train_count = n_items - validate_count - test_count
    if train_count < 1:
        train_count = 1
        test_count = max(0, n_items - train_count - validate_count)
    return train_count, validate_count, test_count


def has_class_folders(input_dir: Path) -> bool:
    direct_images = [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}]
    image_dirs = [path for path in input_dir.iterdir() if path.is_dir() and any(iter_images(path))]
    return bool(image_dirs) and not direct_images


def copy_group(
    files: list[Path],
    input_root: Path,
    output_root: Path,
    rng: random.Random,
    train_count: int,
    validate_count: int,
) -> tuple[int, int, int]:
    shuffled = files[:]
    rng.shuffle(shuffled)
    train_files = shuffled[:train_count]
    validate_files = shuffled[train_count : train_count + validate_count]
    test_files = shuffled[train_count + validate_count :]

    for dataset_files, dataset_dir in [
        (train_files, output_root / "train"),
        (validate_files, output_root / "validate"),
        (test_files, output_root / "test"),
    ]:
        for source in dataset_files:
            relative = source.relative_to(input_root)
            target = dataset_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    return len(train_files), len(validate_files), len(test_files)


def main() -> int:
    args = parse_args()
    total_ratio = args.train_ratio + args.validate_ratio + args.test_ratio
    if abs(total_ratio - 1.0) > 0.001:
        print(f"Ratios must add to 1.0, got {total_ratio:.3f}")
        return 1

    input_dir = args.input_dir
    if not input_dir.exists():
        print(f"Input directory does not exist: {input_dir}")
        return 1

    for directory in [args.train_dir, args.validate_dir, args.test_dir]:
        clear_directory(directory)

    temp_output_root = ensure_dir(input_dir.parent / "_split_tmp")
    clear_directory(temp_output_root)
    rng = random.Random(args.seed)
    class_mode = has_class_folders(input_dir)
    groups: list[tuple[str, Path, list[Path]]] = []

    if class_mode:
        for class_dir in sorted(path for path in input_dir.iterdir() if path.is_dir()):
            files = list(iter_images(class_dir))
            if files:
                groups.append((class_dir.name, input_dir, files))
    else:
        files = list(iter_images(input_dir))
        if files:
            groups.append(("all", input_dir, files))

    if not groups:
        print(f"No images found in {input_dir}")
        return 1

    too_small = [(group_name, len(files)) for group_name, _, files in groups if len(files) < 3]
    if too_small:
        print("Dataset split failed: every class/group needs at least 3 images.")
        for group_name, count in too_small:
            print(f"  - {group_name}: {count} image(s)")
        print("Add more images so train, validate, and test can each receive at least one sample.")
        return 1

    print("SmartRoast dataset split")
    print(f"Input: {input_dir}")
    print(f"Mode: {'class folders' if class_mode else 'flat images'}")
    print(f"Ratios: {args.train_ratio:.1f}:{args.validate_ratio:.1f}:{args.test_ratio:.1f}")

    totals = {"train": 0, "validate": 0, "test": 0}
    for group_name, input_root, files in groups:
        train_count, validate_count, test_count = split_counts(len(files), args.train_ratio, args.validate_ratio)
        train_saved, validate_saved, test_saved = copy_group(
            files,
            input_root,
            temp_output_root,
            rng,
            train_count,
            validate_count,
        )
        totals["train"] += train_saved
        totals["validate"] += validate_saved
        totals["test"] += test_saved
        print(
            f"  - {group_name}: {len(files)} image(s) -> "
            f"train {train_saved}, validate {validate_saved}, test {test_saved}"
        )

    for split_name, final_dir in [
        ("train", args.train_dir),
        ("validate", args.validate_dir),
        ("test", args.test_dir),
    ]:
        split_dir = temp_output_root / split_name
        if split_dir.exists():
            for source in split_dir.rglob("*"):
                if source.is_file():
                    relative = source.relative_to(split_dir)
                    target = final_dir / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))

    clear_directory(temp_output_root)
    temp_output_root.rmdir()

    if not class_mode:
        print("Note: training needs class folders such as resized/bean and resized/no_bean.")
    print(f"Finished. train={totals['train']}, validate={totals['validate']}, test={totals['test']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
