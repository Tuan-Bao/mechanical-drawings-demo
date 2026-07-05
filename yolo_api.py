from __future__ import annotations

import threading
from typing import Any

import torch
from huggingface_hub import hf_hub_download
from PIL import Image
from ultralytics import YOLO


class YoloInferenceService:
    def __init__(self, model_repo: str, model_filename: str, default_confidence: float = 0.35) -> None:
        self.model_repo = model_repo
        self.model_filename = model_filename
        self.default_confidence = default_confidence
        self._model: YOLO | None = None
        self._model_path: str | None = None
        self._lock = threading.RLock()
        self._loading = False
        self._load_error: str | None = None

    @property
    def device(self) -> str:
        return "cuda" if torch.cuda.is_available() else "cpu"

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def model_path(self) -> str | None:
        return self._model_path

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.loaded or self.loading else "waiting",
            "device": self.device,
            "model_repo": self.model_repo,
            "model_filename": self.model_filename,
            "model_path": self.model_path,
            "loaded": self.loaded,
            "loading": self.loading,
            "load_error": self.load_error,
        }

    def preload(self) -> None:
        if self.loaded or self.loading:
            return
        thread = threading.Thread(target=self._load_safely, daemon=True)
        thread.start()

    def _load_safely(self) -> None:
        try:
            self.load()
        except Exception:
            pass

    def load(self) -> YOLO:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._loading = True
                    try:
                        model_path = hf_hub_download(
                            repo_id=self.model_repo,
                            filename=self.model_filename,
                        )
                        self._model_path = model_path
                        self._model = YOLO(model_path)
                        self._load_error = None
                    except Exception as exc:
                        self._load_error = str(exc)
                        raise
                    finally:
                        self._loading = False
        return self._model

    def detect(self, image: Image.Image, confidence: float | None = None) -> list[dict[str, Any]]:
        yolo = self.load()
        conf = confidence if confidence is not None else self.default_confidence

        with torch.inference_mode():
            result = yolo.predict(image, conf=conf, verbose=False)[0]

        names = getattr(yolo, "names", {})
        detections: list[dict[str, Any]] = []

        boxes = getattr(result, "boxes", None)
        obb = getattr(result, "obb", None)

        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            class_ids = boxes.cls.cpu().numpy().astype(int)
            confidences = boxes.conf.cpu().numpy().astype(float)
            for index, (coords, class_id, box_confidence) in enumerate(zip(xyxy, class_ids, confidences)):
                x1, y1, x2, y2 = [int(value) for value in coords]
                detections.append(
                    {
                        "index": index,
                        "label": names.get(class_id, str(class_id)),
                        "class_id": int(class_id),
                        "confidence": float(box_confidence),
                        "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    }
                )
        elif obb is not None and len(obb) > 0:
            polygons = getattr(obb, "xyxyxyxy", None)
            class_ids = obb.cls.cpu().numpy().astype(int)
            confidences = obb.conf.cpu().numpy().astype(float)
            if polygons is not None:
                for index, (polygon, class_id, box_confidence) in enumerate(
                    zip(polygons.cpu().numpy(), class_ids, confidences)
                ):
                    xs = polygon[:, 0]
                    ys = polygon[:, 1]
                    detections.append(
                        {
                            "index": index,
                            "label": names.get(class_id, str(class_id)),
                            "class_id": int(class_id),
                            "confidence": float(box_confidence),
                            "bbox": {
                                "x1": int(xs.min()),
                                "y1": int(ys.min()),
                                "x2": int(xs.max()),
                                "y2": int(ys.max()),
                            },
                        }
                    )

        detections.sort(key=lambda item: (item["bbox"]["y1"], item["bbox"]["x1"]))
        return detections
