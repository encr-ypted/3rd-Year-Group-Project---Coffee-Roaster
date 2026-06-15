from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

try:
    import torch
except ImportError as exc:
    print("PyTorch is required for the current .pt model inference path.")
    print("Install torch on the Raspberry Pi, or convert the model to an IMX500 .rpk firmware file first.")
    raise SystemExit(1) from exc

from grayscale_utils import mean_grayscale
from model_utils import ConfigurableCNN
from paths import MODEL_DIR, TEST_OUTPUT_DIR, ensure_dir


RoiBox = tuple[int, int, int, int]


@dataclass
class InferenceResult:
    timestamp: str
    prediction: str
    probabilities: dict[str, float]
    mean_grayscale: float
    inference_ms: float
    roi: RoiBox | str
    frame_size: tuple[int, int]
    roi_size: tuple[int, int]
    crop_path: str = ""

    def to_row(self) -> dict[str, str | int | float]:
        row: dict[str, str | int | float] = {
            "timestamp": self.timestamp,
            "prediction": self.prediction,
            "mean_grayscale": f"{self.mean_grayscale:.4f}",
            "inference_ms": f"{self.inference_ms:.3f}",
            "roi": self.roi,
            "frame_size": f"{self.frame_size[0]}x{self.frame_size[1]}",
            "roi_size": f"{self.roi_size[0]}x{self.roi_size[1]}",
            "crop_path": self.crop_path,
        }
        row.update({f"prob_{name}": f"{probability:.6f}" for name, probability in self.probabilities.items()})
        return row

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def choose_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but PyTorch cannot access a CUDA GPU.")
    return torch.device(requested)


def centered_training_crop_box(width: int, height: int) -> RoiBox:
    crop_width = int(width * 0.42)
    crop_height = int(height * 0.36)
    x1 = (width - crop_width) // 2
    y1 = (height - crop_height) // 2
    return x1, y1, x1 + crop_width, y1 + crop_height


def validate_crop_box(box: RoiBox, width: int, height: int) -> None:
    x1, y1, x2, y2 = box
    if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x1 >= x2 or y1 >= y2:
        raise ValueError(f"Invalid ROI {box} for image size {width}x{height}")


def create_mock_frame(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (35, 35, 35))
    draw = ImageDraw.Draw(image)
    chamber = (width * 0.24, height * 0.18, width * 0.76, height * 0.86)
    draw.ellipse(chamber, fill=(42, 38, 35), outline=(150, 150, 145), width=max(3, width // 180))
    bean_area = (width * 0.36, height * 0.42, width * 0.64, height * 0.72)
    for index in range(30):
        x = bean_area[0] + (index % 6) * (bean_area[2] - bean_area[0]) / 6
        y = bean_area[1] + (index // 6) * (bean_area[3] - bean_area[1]) / 5
        draw.ellipse(
            (x, y, x + width * 0.045, y + height * 0.055),
            fill=(105 + (index % 4) * 9, 65 + (index % 3) * 5, 35),
            outline=(38, 24, 14),
        )
    draw.line((width * 0.5, height * 0.64, width * 0.54, height * 0.96), fill=(220, 220, 200), width=max(2, width // 160))
    return image


class PiFrameSource:
    def __init__(
        self,
        *,
        backend: str = "picamera2",
        camera_index: int = 0,
        width: int = 1920,
        height: int = 1080,
        warmup: float = 1.5,
    ) -> None:
        self.backend = backend
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.warmup = warmup
        self._picam2 = None
        self._cv2 = None
        self._cap = None

    def open(self) -> None:
        if self.backend == "mock":
            return

        if self.backend == "picamera2":
            from picamera2 import Picamera2

            self._picam2 = Picamera2()
            try:
                config = self._picam2.create_still_configuration(main={"size": (self.width, self.height)})
                self._picam2.configure(config)
                self._picam2.start()
                time.sleep(self.warmup)
            except Exception:
                self.close()
                raise
            return

        if self.backend == "opencv":
            import cv2

            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                raise RuntimeError(f"OpenCV camera index {self.camera_index} did not open")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            time.sleep(self.warmup)
            self._cv2 = cv2
            self._cap = cap
            return

        raise ValueError(f"Unsupported backend: {self.backend}")

    def capture(self) -> Image.Image:
        if self.backend == "mock":
            return create_mock_frame(self.width, self.height)

        if self._picam2 is not None:
            array = self._picam2.capture_array()
            return Image.fromarray(array).convert("RGB")

        if self._cap is not None and self._cv2 is not None:
            ok, frame = self._cap.read()
            if not ok:
                raise RuntimeError("OpenCV failed to read a frame")
            frame = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
            return Image.fromarray(frame).convert("RGB")

        raise RuntimeError("Frame source is not open")

    def close(self) -> None:
        if self._picam2 is not None:
            try:
                self._picam2.stop()
            except Exception:
                pass
            try:
                self._picam2.close()
            finally:
                self._picam2 = None

        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._cv2 = None

    def __enter__(self) -> "PiFrameSource":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class SmartRoastAIDetector:
    def __init__(
        self,
        *,
        model_path: str | Path = MODEL_DIR / "best_model.pt",
        backend: str = "picamera2",
        device: str = "auto",
        camera_index: int = 0,
        width: int = 1920,
        height: int = 1080,
        warmup: float = 1.5,
        roi: RoiBox | None = None,
        roi_mode: str = "training-center",
        output_dir: str | Path = TEST_OUTPUT_DIR / "pi_inference",
    ) -> None:
        self.model_path = Path(model_path)
        self.backend = backend
        self.device = choose_device(device)
        self.roi = roi
        self.roi_mode = roi_mode
        self.output_dir = Path(output_dir)
        self.source = PiFrameSource(
            backend=backend,
            camera_index=camera_index,
            width=width,
            height=height,
            warmup=warmup,
        )
        self.model, self.checkpoint = self._load_model()
        self.class_names = self.checkpoint["class_names"]
        self.processed = 0
        self._is_open = False

    def _load_model(self) -> tuple[ConfigurableCNN, dict]:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        checkpoint = torch.load(self.model_path, map_location=self.device)
        class_names = checkpoint["class_names"]
        model = ConfigurableCNN(num_classes=len(class_names), spec=checkpoint["model_spec"])
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(self.device)
        model.eval()
        return model, checkpoint

    def open(self) -> None:
        if not self._is_open:
            self.source.open()
            self._is_open = True

    def close(self) -> None:
        self.source.close()
        self._is_open = False

    def __enter__(self) -> "SmartRoastAIDetector":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def select_roi(self, image: Image.Image) -> tuple[Image.Image, RoiBox | str]:
        if self.roi is not None:
            validate_crop_box(self.roi, image.width, image.height)
            return image.crop(self.roi), self.roi

        if self.roi_mode == "training-center":
            box = centered_training_crop_box(image.width, image.height)
            validate_crop_box(box, image.width, image.height)
            return image.crop(box), box

        if self.roi_mode == "full-frame":
            return image, "full-frame"

        raise ValueError(f"Unsupported roi_mode: {self.roi_mode}")

    def image_to_tensor(self, image: Image.Image) -> torch.Tensor:
        image_size = tuple(int(value) for value in self.checkpoint["image_size"])
        resized = image.convert("RGB").resize(image_size, Image.Resampling.BILINEAR)
        array = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(array).permute(2, 0, 1)
        mean = torch.tensor(self.checkpoint["normalise_mean"], dtype=torch.float32).view(3, 1, 1)
        std = torch.tensor(self.checkpoint["normalise_std"], dtype=torch.float32).view(3, 1, 1)
        return ((tensor - mean) / std).unsqueeze(0)

    def infer_once(self, *, save_crop: bool = False) -> InferenceResult:
        if not self._is_open:
            self.open()

        timestamp = datetime.now().isoformat(timespec="seconds")
        frame = self.source.capture()
        roi_image, roi_box = self.select_roi(frame)
        tensor = self.image_to_tensor(roi_image).to(self.device)

        start = time.perf_counter()
        with torch.no_grad():
            logits = self.model(tensor)
            probabilities_array = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
        inference_ms = (time.perf_counter() - start) * 1000

        best_index = int(probabilities_array.argmax())
        prediction = self.class_names[best_index]
        probabilities = {
            name: float(probabilities_array[index])
            for index, name in enumerate(self.class_names)
        }
        gray_mean = mean_grayscale(roi_image)
        self.processed += 1

        crop_path = ""
        if save_crop:
            output_dir = ensure_dir(self.output_dir)
            crop_path = str(output_dir / f"pi_roi_{self.processed:04d}_{prediction}.jpg")
            roi_image.save(crop_path, quality=95)

        return InferenceResult(
            timestamp=timestamp,
            prediction=prediction,
            probabilities=probabilities,
            mean_grayscale=gray_mean,
            inference_ms=inference_ms,
            roi=roi_box,
            frame_size=(frame.width, frame.height),
            roi_size=(roi_image.width, roi_image.height),
            crop_path=crop_path,
        )

    @staticmethod
    def format_result(index: int, result: InferenceResult) -> str:
        probability_text = ", ".join(
            f"{name}={probability:.3f}" for name, probability in result.probabilities.items()
        )
        return (
            f"[{index}] {result.timestamp} prediction={result.prediction} "
            f"gray={result.mean_grayscale:.2f} inference={result.inference_ms:.1f}ms {probability_text}"
        )
