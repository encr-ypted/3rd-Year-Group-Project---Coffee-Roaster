#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from grayscale_utils import mean_grayscale
from paths import PLOT_DIR, RESIZED_DIR, ensure_dir, iter_images, parse_batch_and_index, safe_slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot mean grayscale trend for each roast batch.")
    parser.add_argument("--input-dir", type=Path, default=RESIZED_DIR)
    parser.add_argument("--output-dir", type=Path, default=PLOT_DIR)
    parser.add_argument("--show", action="store_true", help="Display plots interactively after saving.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = ensure_dir(args.output_dir)
    groups: dict[str, list[tuple[int, Path]]] = defaultdict(list)

    for image_path in iter_images(args.input_dir):
        parsed = parse_batch_and_index(image_path)
        if parsed is None:
            continue
        batch_id, image_index = parsed
        groups[batch_id].append((image_index, image_path))

    if not groups:
        print(f"No batch-coded images found in {args.input_dir}")
        print("Expected names like batch_2026-06-08-A_shot_0001.jpg")
        return 1

    print("SmartRoast grayscale trend plotting")
    for batch_id, items in sorted(groups.items()):
        items.sort(key=lambda item: item[0])
        indices: list[int] = []
        gray_values: list[float] = []
        for image_index, image_path in items:
            indices.append(image_index)
            gray_values.append(mean_grayscale(image_path))

        x = np.asarray(indices, dtype=np.float32)
        y = np.asarray(gray_values, dtype=np.float32)
        if len(x) >= 2 and np.std(x) > 0 and np.std(y) > 0:
            correlation = float(np.corrcoef(x, y)[0, 1])
            slope, intercept = np.polyfit(x, y, 1)
            trend_y = slope * x + intercept
        else:
            correlation = 0.0
            trend_y = y

        batch_slug = safe_slug(batch_id)
        csv_path = output_dir / f"batch_{batch_slug}_gray_values.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["batch_id", "image_index", "image_path", "mean_grayscale"])
            for image_index, image_path, gray_value in zip(indices, [item[1] for item in items], gray_values):
                writer.writerow([batch_id, image_index, str(image_path), f"{gray_value:.4f}"])

        plt.figure(figsize=(8, 4.5))
        plt.plot(indices, gray_values, marker="o", linewidth=1.5, label="mean grayscale")
        if len(indices) >= 2:
            plt.plot(indices, trend_y, linestyle="--", linewidth=1.2, label="linear trend")
        plt.title(f"Batch {batch_id} bean grayscale trend")
        plt.xlabel("Image number within batch")
        plt.ylabel("Mean grayscale value (0 dark, 255 bright)")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plot_path = output_dir / f"batch_{batch_slug}_gray_trend.png"
        plt.savefig(plot_path, dpi=160)
        if args.show:
            plt.show()
        plt.close()

        if correlation < 0:
            note = "negative trend observed"
        else:
            note = "expected negative trend not observed; check lighting, ROI, or roast ordering"
        print(f"Batch {batch_id}: {len(items)} image(s), correlation {correlation:.3f}, {note}")
        print(f"  plot: {plot_path}")
        print(f"  csv:  {csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
