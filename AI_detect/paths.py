from __future__ import annotations

import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
RESIZED_DIR = ROOT / "resized"
TRAIN_DIR = ROOT / "train_set"
VALIDATE_DIR = ROOT / "validate_set"
TEST_DIR = ROOT / "test_set"
TRAIN_AUGMENTED_DIR = ROOT / "train_set_augmented"
PLOT_DIR = ROOT / "plot"
MODEL_DIR = ROOT / "models"
TEST_OUTPUT_DIR = ROOT / "test_outputs"

DEFAULT_RPK_MODEL_PATH = MODEL_DIR / "coffee_qmodel.rpk"
DEFAULT_PT_MODEL_PATH = MODEL_DIR / "best_model.pt"
DEFAULT_CLASS_NAMES = ("bean", "corrupted", "no_bean")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_directory(path: Path) -> None:
    ensure_dir(path)
    for child in path.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def iter_images(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    slug = slug.strip("._-")
    return slug or "batch"


def capture_filename(batch_id: str, index: int, suffix: str = ".jpg") -> str:
    return f"batch_{safe_slug(batch_id)}_shot_{index:04d}{suffix.lower()}"


def parse_batch_and_index(path: Path) -> tuple[str, int] | None:
    match = re.search(
        r"batch[_-](?P<batch>.+?)[_-]shot[_-](?P<index>\d+)",
        path.stem,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group("batch"), int(match.group("index"))


def next_capture_index(raw_dir: Path, batch_id: str) -> int:
    safe_batch = safe_slug(batch_id)
    max_index = 0
    for image_path in iter_images(raw_dir):
        parsed = parse_batch_and_index(image_path)
        if parsed is None:
            continue
        parsed_batch, parsed_index = parsed
        if parsed_batch == safe_batch:
            max_index = max(max_index, parsed_index)
    return max_index + 1
