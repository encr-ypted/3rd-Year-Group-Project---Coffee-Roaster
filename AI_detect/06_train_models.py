#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    import torch
    from torch import nn
    from torch.utils.data import ConcatDataset, DataLoader, Dataset
except ImportError as exc:
    print("PyTorch is required for training. Install torch before running this script.")
    raise SystemExit(1) from exc

from model_utils import ConfigurableCNN
from paths import MODEL_DIR, TEST_DIR, TRAIN_AUGMENTED_DIR, VALIDATE_DIR, ensure_dir, iter_images


class ImageFolderDataset(Dataset):
    def __init__(
        self,
        root: Path,
        *,
        image_size: tuple[int, int],
        mean: list[float],
        std: list[float],
        class_to_idx: dict[str, int] | None = None,
    ) -> None:
        self.root = root
        self.image_size = image_size
        self.mean = torch.tensor(mean, dtype=torch.float32).view(3, 1, 1)
        self.std = torch.tensor(std, dtype=torch.float32).view(3, 1, 1)

        if class_to_idx is None:
            class_names = sorted(path.name for path in root.iterdir() if path.is_dir() and any(iter_images(path)))
            self.class_to_idx = {class_name: index for index, class_name in enumerate(class_names)}
        else:
            self.class_to_idx = class_to_idx

        self.samples: list[tuple[Path, int]] = []
        for class_name, class_index in self.class_to_idx.items():
            class_dir = root / class_name
            if class_dir.exists():
                for image_path in iter_images(class_dir):
                    self.samples.append((image_path, class_index))

        self.samples.sort(key=lambda item: str(item[0]))

    @property
    def class_names(self) -> list[str]:
        return [name for name, _ in sorted(self.class_to_idx.items(), key=lambda item: item[1])]

    def sample_counts_by_class(self) -> dict[str, int]:
        index_to_class = {index: name for name, index in self.class_to_idx.items()}
        counts = {class_name: 0 for class_name in self.class_to_idx}
        for _, class_index in self.samples:
            counts[index_to_class[class_index]] += 1
        return counts

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        image_path, class_index = self.samples[index]
        with Image.open(image_path) as image:
            image = image.convert("RGB").resize(self.image_size, Image.Resampling.BILINEAR)
            array = np.asarray(image, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(array).permute(2, 0, 1)
        tensor = (tensor - self.mean) / self.std
        return tensor, torch.tensor(class_index, dtype=torch.long)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train and compare several CNN models for bean/no-bean detection.")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent / "model_config.json")
    parser.add_argument("--train-dir", type=Path, default=TRAIN_AUGMENTED_DIR)
    parser.add_argument("--validate-dir", type=Path, default=VALIDATE_DIR)
    parser.add_argument("--test-dir", type=Path, default=TEST_DIR)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], default="auto")
    return parser.parse_args()


def choose_device(requested: str) -> torch.device:
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but PyTorch cannot access a CUDA GPU.")
    if requested == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
        raise RuntimeError("MPS was requested, but PyTorch cannot access an MPS device.")
    return torch.device(requested)


def device_description(device: torch.device) -> str:
    if device.type == "cuda":
        return f"{device} ({torch.cuda.get_device_name(0)})"
    return str(device)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not config.get("models"):
        raise ValueError("Config must contain at least one model in the models list.")
    return config


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def make_loader(dataset: Dataset, *, batch_size: int, shuffle: bool, num_workers: int) -> DataLoader:
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, num_workers=num_workers)


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> tuple[float, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        batch_size = labels.size(0)
        total_loss += float(loss.item()) * batch_size
        correct += int((logits.argmax(dim=1) == labels).sum().item())
        total += batch_size
    return total_loss / max(total, 1), correct / max(total, 1)


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader, criterion: nn.Module, device: torch.device) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        logits = model(images)
        loss = criterion(logits, labels)
        batch_size = labels.size(0)
        total_loss += float(loss.item()) * batch_size
        correct += int((logits.argmax(dim=1) == labels).sum().item())
        total += batch_size
    return total_loss / max(total, 1), correct / max(total, 1)


def train_with_validation(
    spec: dict[str, Any],
    *,
    train_loader: DataLoader,
    validate_loader: DataLoader,
    config: dict[str, Any],
    device: torch.device,
    num_classes: int,
) -> tuple[nn.Module, dict[str, Any]]:
    model = ConfigurableCNN(num_classes=num_classes, spec=spec).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(config["learning_rate"]),
        weight_decay=float(config.get("weight_decay", 0.0)),
    )

    best_state = copy.deepcopy(model.state_dict())
    best_metrics = {"validate_loss": float("inf"), "validate_accuracy": 0.0, "epoch": 0}
    for epoch in range(1, int(config["epochs_stage1"]) + 1):
        train_loss, train_accuracy = train_one_epoch(model, train_loader, criterion, optimizer, device)
        validate_loss, validate_accuracy = evaluate(model, validate_loader, criterion, device)
        print(
            f"  epoch {epoch:02d}: train loss {train_loss:.4f}, train acc {train_accuracy:.3f}, "
            f"val loss {validate_loss:.4f}, val acc {validate_accuracy:.3f}"
        )
        if validate_accuracy > best_metrics["validate_accuracy"] or (
            validate_accuracy == best_metrics["validate_accuracy"]
            and validate_loss < best_metrics["validate_loss"]
        ):
            best_state = copy.deepcopy(model.state_dict())
            best_metrics = {
                "validate_loss": float(validate_loss),
                "validate_accuracy": float(validate_accuracy),
                "train_loss": float(train_loss),
                "train_accuracy": float(train_accuracy),
                "epoch": epoch,
            }

    model.load_state_dict(best_state)
    return model, best_metrics


def train_final_model(
    spec: dict[str, Any],
    *,
    train_loader: DataLoader,
    config: dict[str, Any],
    device: torch.device,
    num_classes: int,
) -> tuple[nn.Module, dict[str, Any]]:
    model = ConfigurableCNN(num_classes=num_classes, spec=spec).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(config["learning_rate"]),
        weight_decay=float(config.get("weight_decay", 0.0)),
    )
    last_metrics = {"train_loss": 0.0, "train_accuracy": 0.0}
    for epoch in range(1, int(config["epochs_final"]) + 1):
        train_loss, train_accuracy = train_one_epoch(model, train_loader, criterion, optimizer, device)
        last_metrics = {"train_loss": float(train_loss), "train_accuracy": float(train_accuracy), "epoch": epoch}
        print(f"  final epoch {epoch:02d}: train loss {train_loss:.4f}, train acc {train_accuracy:.3f}")
    return model, last_metrics


def require_non_empty_dataset(name: str, dataset: Dataset) -> None:
    if len(dataset) == 0:
        raise ValueError(f"{name} is empty. Check that it contains class folders with images.")


def require_complete_class_coverage(name: str, dataset: ImageFolderDataset) -> None:
    counts = dataset.sample_counts_by_class()
    missing = [class_name for class_name, count in counts.items() if count == 0]
    if missing:
        raise ValueError(
            f"{name} is missing sample(s) for class(es): {', '.join(missing)}. "
            "Each split must contain at least one image from every class."
        )


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    set_seed(int(config.get("seed", 42)))
    try:
        device = choose_device(args.device)
    except RuntimeError as exc:
        print(exc)
        return 1
    model_dir = ensure_dir(args.model_dir)

    image_size = tuple(int(value) for value in config["image_size"])
    mean = [float(value) for value in config.get("normalise_mean", [0.5, 0.5, 0.5])]
    std = [float(value) for value in config.get("normalise_std", [0.5, 0.5, 0.5])]

    train_dataset = ImageFolderDataset(args.train_dir, image_size=image_size, mean=mean, std=std)
    if not train_dataset.class_to_idx:
        print("No class folders found. Expected folders like train_set_augmented/bean and train_set_augmented/no_bean.")
        return 1
    if len(train_dataset.class_names) < 2:
        print(
            "Training needs at least two class folders, for example "
            "train_set_augmented/bean and train_set_augmented/no_bean."
        )
        return 1

    validate_dataset = ImageFolderDataset(
        args.validate_dir,
        image_size=image_size,
        mean=mean,
        std=std,
        class_to_idx=train_dataset.class_to_idx,
    )
    test_dataset = ImageFolderDataset(
        args.test_dir,
        image_size=image_size,
        mean=mean,
        std=std,
        class_to_idx=train_dataset.class_to_idx,
    )

    try:
        require_non_empty_dataset("train_set_augmented", train_dataset)
        require_non_empty_dataset("validate_set", validate_dataset)
        require_non_empty_dataset("test_set", test_dataset)
        require_complete_class_coverage("train_set_augmented", train_dataset)
        require_complete_class_coverage("validate_set", validate_dataset)
        require_complete_class_coverage("test_set", test_dataset)
    except ValueError as exc:
        print(exc)
        return 1

    batch_size = int(config.get("batch_size", 16))
    num_workers = int(config.get("num_workers", 0))
    train_loader = make_loader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    validate_loader = make_loader(validate_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    test_loader = make_loader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    combined_loader = make_loader(
        ConcatDataset([train_dataset, validate_dataset]),
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
    )

    print("SmartRoast CNN model comparison")
    print(f"Device: {device_description(device)}")
    print(f"Classes: {train_dataset.class_names}")
    print(f"Dataset sizes: train_aug={len(train_dataset)}, validate={len(validate_dataset)}, test={len(test_dataset)}")

    stage1_results: list[dict[str, Any]] = []
    for spec in config["models"]:
        print(f"Stage 1 training: {spec['name']}")
        _, metrics = train_with_validation(
            spec,
            train_loader=train_loader,
            validate_loader=validate_loader,
            config=config,
            device=device,
            num_classes=len(train_dataset.class_names),
        )
        stage1_results.append({"name": spec["name"], "spec": spec, "metrics": metrics})
        print(
            f"Best validation for {spec['name']}: "
            f"acc {metrics['validate_accuracy']:.3f}, loss {metrics['validate_loss']:.4f}, epoch {metrics['epoch']}"
        )

    ranked = sorted(
        stage1_results,
        key=lambda item: (-item["metrics"]["validate_accuracy"], item["metrics"]["validate_loss"]),
    )
    top_three = ranked[: min(3, len(ranked))]
    print("Top validation models:")
    for rank, item in enumerate(top_three, start=1):
        metrics = item["metrics"]
        print(f"  {rank}. {item['name']} val acc {metrics['validate_accuracy']:.3f}, val loss {metrics['validate_loss']:.4f}")

    final_results: list[dict[str, Any]] = []
    criterion = nn.CrossEntropyLoss()
    for item in top_three:
        spec = item["spec"]
        print(f"Final training with train_set_augmented + validate_set: {spec['name']}")
        model, train_metrics = train_final_model(
            spec,
            train_loader=combined_loader,
            config=config,
            device=device,
            num_classes=len(train_dataset.class_names),
        )
        test_loss, test_accuracy = evaluate(model, test_loader, criterion, device)
        result = {
            "name": spec["name"],
            "spec": spec,
            "train_metrics": train_metrics,
            "test_loss": float(test_loss),
            "test_accuracy": float(test_accuracy),
            "state_dict": copy.deepcopy(model.cpu().state_dict()),
        }
        final_results.append(result)
        print(f"Test result for {spec['name']}: acc {test_accuracy:.3f}, loss {test_loss:.4f}")

    best = sorted(final_results, key=lambda item: (-item["test_accuracy"], item["test_loss"]))[0]
    best_model_path = model_dir / "best_model.pt"
    torch.save(
        {
            "model_name": best["name"],
            "model_spec": best["spec"],
            "model_state_dict": best["state_dict"],
            "class_names": train_dataset.class_names,
            "class_to_idx": train_dataset.class_to_idx,
            "image_size": image_size,
            "normalise_mean": mean,
            "normalise_std": std,
            "test_accuracy": best["test_accuracy"],
            "test_loss": best["test_loss"],
        },
        best_model_path,
    )

    summary_path = model_dir / "training_summary.json"
    summary = {
        "class_names": train_dataset.class_names,
        "dataset_sizes": {
            "train_augmented": len(train_dataset),
            "validate": len(validate_dataset),
            "test": len(test_dataset),
        },
        "stage1_results": [
            {"name": item["name"], "metrics": item["metrics"], "spec": item["spec"]} for item in ranked
        ],
        "final_results": [
            {
                "name": item["name"],
                "train_metrics": item["train_metrics"],
                "test_loss": item["test_loss"],
                "test_accuracy": item["test_accuracy"],
                "spec": item["spec"],
            }
            for item in sorted(final_results, key=lambda entry: (-entry["test_accuracy"], entry["test_loss"]))
        ],
        "best_model": best["name"],
        "best_model_path": str(best_model_path),
    }
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print(f"Best model: {best['name']} with test acc {best['test_accuracy']:.3f}")
    print(f"Saved best model to: {best_model_path}")
    print(f"Saved training summary to: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
