from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from transformers import DonutProcessor, VisionEncoderDecoderConfig

_DEMO_ROOT = Path(__file__).resolve().parent
if str(_DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(_DEMO_ROOT))

try:
    from hftuner.donut import DonutModel
except ImportError as exc:
    raise ImportError(
        "hftuner is required for DONUT inference. "
        "Run: git clone https://github.com/hftuner/clovaai-donut hftuner "
        f"(inside {_DEMO_ROOT})"
    ) from exc


class DonutInferenceService:
    def __init__(
        self,
        model_path: str,
        task_start_token: str | None = None,
        max_length: int | None = None,
    ) -> None:
        self.model_path = model_path
        self.task_start_token = task_start_token or os.getenv("DONUT_TASK_TOKEN", "<parsing>")
        self.max_length = max_length or int(os.getenv("DONUT_MAX_LENGTH", "256"))
        self._processor: DonutProcessor | None = None
        self._model: Any | None = None
        self._lock = threading.RLock()
        self._loading = False
        self._load_error: str | None = None

    @property
    def device(self) -> str:
        return "cuda" if torch.cuda.is_available() else "cpu"

    @property
    def loaded(self) -> bool:
        return self._processor is not None and self._model is not None

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def health(self) -> dict[str, Any]:
        if self.load_error:
            status = "error"
        elif self.loaded:
            status = "ok"
        elif self.loading:
            status = "loading"
        else:
            status = "waiting"
        return {
            "status": status,
            "device": self.device,
            "model_path": self.model_path,
            "model_class": "DonutModel",
            "hftuner_available": True,
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

    def load(self) -> tuple[DonutProcessor, Any]:
        if self._processor is None or self._model is None:
            with self._lock:
                if self._processor is None or self._model is None:
                    self._loading = True
                    try:
                        processor = DonutProcessor.from_pretrained(self.model_path)
                        config = VisionEncoderDecoderConfig.from_pretrained(self.model_path)
                        model = DonutModel.from_pretrained(self.model_path, config=config)
                        model.to(self.device)
                        if torch.cuda.is_available():
                            model.half()
                        model.eval()
                        self._processor = processor
                        self._model = model
                        self._load_error = None
                    except Exception as exc:
                        self._load_error = str(exc)
                        raise
                    finally:
                        self._loading = False
        return self._processor, self._model

    def infer(
        self,
        image: Image.Image,
        task_start_token: str | None = None,
        max_length: int | None = None,
    ) -> dict[str, Any]:
        processor, model = self.load()
        token = task_start_token or self.task_start_token
        length = max_length or self.max_length

        pixel_values = processor(image, return_tensors="pt").pixel_values.to(self.device)
        if torch.cuda.is_available():
            pixel_values = pixel_values.half()

        decoder_input_ids = processor.tokenizer(
            token,
            add_special_tokens=False,
            return_tensors="pt",
        ).input_ids.to(self.device)

        with torch.inference_mode():
            generated_ids = model.generate(
                pixel_values,
                decoder_input_ids=decoder_input_ids,
                max_length=length,
                bad_words_ids=[[processor.tokenizer.unk_token_id]],
            )

        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        try:
            prediction = processor.token2json(generated_text)
        except Exception:
            prediction = {"raw_text": generated_text}

        return {
            "model_path": self.model_path,
            "prediction": prediction,
        }
