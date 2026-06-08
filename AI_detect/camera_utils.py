from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


class CameraError(RuntimeError):
    """Raised when no configured camera backend can capture an image."""


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def create_mock_image(output_path: Path, width: int, height: int) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (40, 42, 45))
    draw = ImageDraw.Draw(image)
    chamber = (width * 0.18, height * 0.16, width * 0.82, height * 0.84)
    draw.rounded_rectangle(chamber, radius=max(12, width // 80), outline=(150, 150, 150), width=4)
    bean_area = (width * 0.34, height * 0.48, width * 0.66, height * 0.74)
    for i in range(18):
        x = bean_area[0] + (i % 6) * (bean_area[2] - bean_area[0]) / 6
        y = bean_area[1] + (i // 6) * (bean_area[3] - bean_area[1]) / 3
        draw.ellipse(
            (x, y, x + width * 0.055, y + height * 0.055),
            fill=(105 + i * 3, 66 + i, 34),
            outline=(35, 22, 13),
        )
    draw.text((20, 20), "mock camera frame", fill=(230, 230, 230))
    image.save(output_path, quality=95)
    return {"backend": "mock", "width": width, "height": height, "path": str(output_path)}


class CameraSession:
    def __init__(
        self,
        *,
        backend: str = "auto",
        width: int = 1920,
        height: int = 1080,
        camera_index: int = 0,
        warmup_seconds: float = 1.5,
        mock: bool = False,
    ) -> None:
        self.backend = backend
        self.width = width
        self.height = height
        self.camera_index = camera_index
        self.warmup_seconds = warmup_seconds
        self.mock = mock
        self._selected_backend: str | None = None
        self._picam2: Any | None = None
        self._cv2: Any | None = None
        self._cap: Any | None = None

    @property
    def selected_backend(self) -> str | None:
        return self._selected_backend

    def __enter__(self) -> "CameraSession":
        if self.mock:
            self._selected_backend = "mock"
            return self

        errors: list[str] = []
        if self.backend in {"auto", "picamera2"}:
            try:
                from picamera2 import Picamera2

                self._picam2 = Picamera2()
                config = self._picam2.create_still_configuration(main={"size": (self.width, self.height)})
                self._picam2.configure(config)
                self._picam2.start()
                time.sleep(self.warmup_seconds)
                self._selected_backend = "picamera2"
                return self
            except Exception as exc:
                errors.append(f"picamera2: {exc}")
                if self.backend == "picamera2":
                    raise CameraError("; ".join(errors)) from exc

        if self.backend in {"auto", "opencv"}:
            try:
                import cv2

                cap = cv2.VideoCapture(self.camera_index)
                if not cap.isOpened():
                    raise CameraError(f"OpenCV camera index {self.camera_index} did not open")
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                time.sleep(self.warmup_seconds)
                for _ in range(3):
                    cap.read()
                self._cv2 = cv2
                self._cap = cap
                self._selected_backend = "opencv"
                return self
            except Exception as exc:
                errors.append(f"opencv: {exc}")
                if self.backend == "opencv":
                    raise CameraError("; ".join(errors)) from exc

        raise CameraError("; ".join(errors) or "No camera backend was attempted")

    def capture(self, output_path: Path) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self._selected_backend == "mock":
            return create_mock_image(output_path, self.width, self.height)

        if self._selected_backend == "picamera2" and self._picam2 is not None:
            self._picam2.capture_file(str(output_path))
            with Image.open(output_path) as image:
                width, height = image.size
            return {"backend": "picamera2", "width": width, "height": height, "path": str(output_path)}

        if self._selected_backend == "opencv" and self._cap is not None and self._cv2 is not None:
            ok, frame = self._cap.read()
            if not ok:
                raise CameraError("OpenCV failed to read a frame")
            self._cv2.imwrite(str(output_path), frame)
            height, width = frame.shape[:2]
            return {"backend": "opencv", "width": width, "height": height, "path": str(output_path)}

        raise CameraError("Camera session is not open")

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._picam2 is not None:
            try:
                self._picam2.stop()
            finally:
                self._picam2.close()
        if self._cap is not None:
            self._cap.release()


def capture_image(
    output_path: Path,
    *,
    backend: str = "auto",
    width: int = 1920,
    height: int = 1080,
    camera_index: int = 0,
    warmup_seconds: float = 1.5,
    mock: bool = False,
) -> dict[str, Any]:
    with CameraSession(
        backend=backend,
        width=width,
        height=height,
        camera_index=camera_index,
        warmup_seconds=warmup_seconds,
        mock=mock,
    ) as camera:
        return camera.capture(output_path)
