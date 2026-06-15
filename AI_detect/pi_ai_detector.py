from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw

from grayscale_utils import mean_grayscale
from paths import (
    DEFAULT_CLASS_NAMES,
    DEFAULT_RPK_MODEL_PATH,
    TEST_OUTPUT_DIR,
    ensure_dir,
)


RoiBox = tuple[int, int, int, int]


@dataclass
class CapturedFrame:
    image: Image.Image
    metadata: dict[str, Any] | None = None


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
    model_format: str
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
            "model_format": self.model_format,
            "crop_path": self.crop_path,
        }
        row.update({f"prob_{name}": f"{probability:.6f}" for name, probability in self.probabilities.items()})
        return row

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def import_torch():
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is only required for .pt inference. "
            "Default Raspberry Pi AI Camera inference uses the IMX500 .rpk model."
        ) from exc
    return torch


def choose_device(requested: str):
    torch = import_torch()
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but PyTorch cannot access a CUDA GPU.")
    return torch.device(requested)


def resolve_model_format(model_path: Path, requested: str) -> str:
    if requested not in {"auto", "rpk", "pt"}:
        raise ValueError(f"Unsupported model format: {requested}")
    if requested != "auto":
        return requested
    suffix = model_path.suffix.lower()
    if suffix == ".rpk":
        return "rpk"
    if suffix == ".pt":
        return "pt"
    raise ValueError(f"Cannot infer model format from extension: {model_path}")


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


def softmax(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float32)
    values = values - np.max(values)
    exp_values = np.exp(values)
    total = float(exp_values.sum())
    if total <= 0:
        return np.zeros_like(exp_values)
    return exp_values / total


class PiFrameSource:
    def __init__(
        self,
        *,
        backend: str = "picamera2",
        camera_index: int = 0,
        width: int = 1920,
        height: int = 1080,
        warmup: float = 1.5,
        enable_imx500: bool = False,
        rpk_model_path: str | Path | None = None,
    ) -> None:
        self.backend = backend
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.warmup = warmup
        self.enable_imx500 = enable_imx500
        self.rpk_model_path = Path(rpk_model_path) if rpk_model_path else None
        self._picam2 = None
        self._imx500 = None
        self._cv2 = None
        self._cap = None

    @staticmethod
    def _load_imx500_class():
        try:
            from picamera2.devices.imx500 import IMX500
        except ImportError:
            from picamera2.devices import IMX500
        return IMX500

    def open(self) -> None:
        if self.backend == "mock":
            if self.enable_imx500:
                raise RuntimeError("IMX500 .rpk inference requires the picamera2 backend, not mock.")
            return

        if self.backend == "picamera2":
            from picamera2 import Picamera2

            camera_num = 0
            controls: dict[str, Any] = {}
            if self.enable_imx500:
                if self.rpk_model_path is None:
                    raise RuntimeError("An IMX500 .rpk model path is required.")
                if not self.rpk_model_path.exists():
                    raise FileNotFoundError(f"RPK model file not found: {self.rpk_model_path}")

                IMX500 = self._load_imx500_class()
                self._imx500 = IMX500(str(self.rpk_model_path))
                camera_num = int(getattr(self._imx500, "camera_num", 0))

                if hasattr(self._imx500, "show_network_fw_progress_bar"):
                    self._imx500.show_network_fw_progress_bar()
                if hasattr(self._imx500, "set_auto_aspect_ratio"):
                    self._imx500.set_auto_aspect_ratio()

                intrinsics = getattr(self._imx500, "network_intrinsics", None)
                inference_rate = getattr(intrinsics, "inference_rate", None)
                if inference_rate:
                    controls["FrameRate"] = inference_rate

            self._picam2 = Picamera2(camera_num)
            try:
                if self.enable_imx500:
                    config_kwargs: dict[str, Any] = {
                        "main": {"size": (self.width, self.height)},
                        "buffer_count": 12,
                    }
                    if controls:
                        config_kwargs["controls"] = controls
                    config = self._picam2.create_preview_configuration(**config_kwargs)
                else:
                    config = self._picam2.create_still_configuration(main={"size": (self.width, self.height)})
                self._picam2.configure(config)
                self._picam2.start()
                time.sleep(self.warmup)
            except Exception:
                self.close()
                raise
            return

        if self.backend == "opencv":
            if self.enable_imx500:
                raise RuntimeError("IMX500 .rpk inference requires the picamera2 backend, not opencv.")
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

    def capture_frame(self) -> CapturedFrame:
        if self.backend == "mock":
            return CapturedFrame(create_mock_frame(self.width, self.height))

        if self._picam2 is not None:
            if hasattr(self._picam2, "capture_request"):
                request = self._picam2.capture_request()
                try:
                    array = request.make_array("main")
                    metadata = request.get_metadata()
                finally:
                    request.release()
                return CapturedFrame(Image.fromarray(array).convert("RGB"), metadata)

            array = self._picam2.capture_array()
            metadata = self._picam2.capture_metadata() if hasattr(self._picam2, "capture_metadata") else None
            return CapturedFrame(Image.fromarray(array).convert("RGB"), metadata)

        if self._cap is not None and self._cv2 is not None:
            ok, frame = self._cap.read()
            if not ok:
                raise RuntimeError("OpenCV failed to read a frame")
            frame = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
            return CapturedFrame(Image.fromarray(frame).convert("RGB"))

        raise RuntimeError("Frame source is not open")

    def capture(self) -> Image.Image:
        return self.capture_frame().image

    def get_imx500_outputs(self, metadata: dict[str, Any] | None):
        if self._imx500 is None:
            raise RuntimeError("IMX500 is not open.")
        if metadata is None:
            return None
        return self._imx500.get_outputs(metadata, add_batch=True)

    def get_imx500_labels(self) -> list[str] | None:
        if self._imx500 is None:
            return None
        intrinsics = getattr(self._imx500, "network_intrinsics", None)
        labels = getattr(intrinsics, "labels", None)
        if labels:
            return [str(label) for label in labels]
        return None

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
        self._imx500 = None

    def __enter__(self) -> "PiFrameSource":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class SmartRoastAIDetector:
    def __init__(
        self,
        *,
        model_path: str | Path = DEFAULT_RPK_MODEL_PATH,
        model_format: str = "auto",
        backend: str = "picamera2",
        device: str = "auto",
        camera_index: int = 0,
        width: int = 1920,
        height: int = 1080,
        warmup: float = 1.5,
        roi: RoiBox | None = None,
        roi_mode: str = "training-center",
        output_dir: str | Path = TEST_OUTPUT_DIR / "pi_inference",
        class_names: Sequence[str] = DEFAULT_CLASS_NAMES,
        rpk_output_activation: str = "softmax",
        rpk_output_timeout: float = 2.0,
    ) -> None:
        self.model_path = Path(model_path)
        self.model_format = resolve_model_format(self.model_path, model_format)
        self.backend = backend
        self.device = None
        self.roi = roi
        self.roi_mode = roi_mode
        self.output_dir = Path(output_dir)
        self.class_names = list(class_names)
        self.rpk_output_activation = rpk_output_activation
        self.rpk_output_timeout = rpk_output_timeout
        self._torch = None
        self.model = None
        self.checkpoint: dict[str, Any] = {}

        if self.model_format == "pt":
            self.device = choose_device(device)
            self.model, self.checkpoint = self._load_pytorch_model()
            self.class_names = list(self.checkpoint["class_names"])
        elif self.model_format == "rpk":
            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"RPK model file not found: {self.model_path}. "
                    f"Copy the converted .rpk file to {DEFAULT_RPK_MODEL_PATH} "
                    "or pass --model /path/to/model.rpk."
                )
        else:
            raise ValueError(f"Unsupported model format: {self.model_format}")

        self.source = PiFrameSource(
            backend=backend,
            camera_index=camera_index,
            width=width,
            height=height,
            warmup=warmup,
            enable_imx500=self.model_format == "rpk",
            rpk_model_path=self.model_path if self.model_format == "rpk" else None,
        )
        self.processed = 0
        self._is_open = False

    @property
    def device_label(self) -> str:
        return "imx500" if self.model_format == "rpk" else str(self.device)

    def _load_pytorch_model(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        torch = import_torch()
        from model_utils import ConfigurableCNN

        self._torch = torch
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
            labels = self.source.get_imx500_labels()
            if labels and len(labels) == len(self.class_names):
                self.class_names = labels
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

    def image_to_tensor(self, image: Image.Image):
        if self._torch is None:
            raise RuntimeError("image_to_tensor is only available for .pt inference.")

        image_size = tuple(int(value) for value in self.checkpoint["image_size"])
        resized = image.convert("RGB").resize(image_size, Image.Resampling.BILINEAR)
        array = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = self._torch.from_numpy(array).permute(2, 0, 1)
        mean = self._torch.tensor(self.checkpoint["normalise_mean"], dtype=self._torch.float32).view(3, 1, 1)
        std = self._torch.tensor(self.checkpoint["normalise_std"], dtype=self._torch.float32).view(3, 1, 1)
        return ((tensor - mean) / std).unsqueeze(0)

    def _infer_pytorch(self, roi_image: Image.Image) -> tuple[str, dict[str, float], float]:
        if self._torch is None or self.model is None:
            raise RuntimeError("PyTorch model is not loaded.")

        tensor = self.image_to_tensor(roi_image).to(self.device)
        start = time.perf_counter()
        with self._torch.no_grad():
            logits = self.model(tensor)
            probabilities_array = self._torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
        inference_ms = (time.perf_counter() - start) * 1000
        return self._probabilities_to_prediction(probabilities_array, inference_ms)

    def _normalise_rpk_output(self, values: np.ndarray) -> np.ndarray:
        if self.rpk_output_activation == "softmax":
            return softmax(values)
        if self.rpk_output_activation == "none":
            total = float(values.sum())
            if total > 0:
                return values / total
            return values
        raise ValueError(f"Unsupported rpk_output_activation: {self.rpk_output_activation}")

    def _extract_rpk_scores(self, outputs: Any) -> np.ndarray:
        if isinstance(outputs, dict):
            outputs = next(iter(outputs.values()))
        if isinstance(outputs, (list, tuple)):
            candidates = [np.asarray(output).squeeze() for output in outputs]
            candidates = [candidate.reshape(-1) for candidate in candidates if candidate.size]
            if not candidates:
                raise RuntimeError("IMX500 returned empty outputs.")
            scores = max(candidates, key=lambda candidate: candidate.size)
        else:
            scores = np.asarray(outputs).squeeze().reshape(-1)

        expected = len(self.class_names)
        if scores.size < expected:
            raise RuntimeError(f"IMX500 output has {scores.size} value(s), expected at least {expected}.")
        return scores.astype(np.float32)[:expected]

    def _infer_imx500(self, outputs: Any, start: float) -> tuple[str, dict[str, float], float]:
        scores = self._extract_rpk_scores(outputs)
        probabilities_array = self._normalise_rpk_output(scores)
        inference_ms = (time.perf_counter() - start) * 1000
        return self._probabilities_to_prediction(probabilities_array, inference_ms)

    def _probabilities_to_prediction(
        self,
        probabilities_array: np.ndarray,
        inference_ms: float,
    ) -> tuple[str, dict[str, float], float]:
        best_index = int(probabilities_array.argmax())
        prediction = self.class_names[best_index]
        probabilities = {
            name: float(probabilities_array[index])
            for index, name in enumerate(self.class_names)
        }
        return prediction, probabilities, inference_ms

    def _capture_rpk_frame_and_outputs(self) -> tuple[CapturedFrame, Image.Image, RoiBox | str, Any, float]:
        start = time.perf_counter()
        deadline = start + self.rpk_output_timeout

        while True:
            captured = self.source.capture_frame()
            roi_image, roi_box = self.select_roi(captured.image)
            outputs = self.source.get_imx500_outputs(captured.metadata)
            if outputs is not None:
                return captured, roi_image, roi_box, outputs, start
            if time.perf_counter() >= deadline:
                raise RuntimeError("Timed out waiting for IMX500 inference outputs.")
            time.sleep(0.05)

    def infer_once(self, *, save_crop: bool = False) -> InferenceResult:
        if not self._is_open:
            self.open()

        timestamp = datetime.now().isoformat(timespec="seconds")

        if self.model_format == "rpk":
            captured, roi_image, roi_box, outputs, start = self._capture_rpk_frame_and_outputs()
            prediction, probabilities, inference_ms = self._infer_imx500(outputs, start)
        else:
            captured = self.source.capture_frame()
            roi_image, roi_box = self.select_roi(captured.image)
            prediction, probabilities, inference_ms = self._infer_pytorch(roi_image)

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
            frame_size=(captured.image.width, captured.image.height),
            roi_size=(roi_image.width, roi_image.height),
            model_format=self.model_format,
            crop_path=crop_path,
        )

    @staticmethod
    def format_result(index: int, result: InferenceResult) -> str:
        probability_text = ", ".join(
            f"{name}={probability:.3f}" for name, probability in result.probabilities.items()
        )
        return (
            f"[{index}] {result.timestamp} format={result.model_format} "
            f"prediction={result.prediction} gray={result.mean_grayscale:.2f} "
            f"inference={result.inference_ms:.1f}ms {probability_text}"
        )
