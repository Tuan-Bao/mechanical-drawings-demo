from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image, ImageOps
from sqlalchemy import DateTime, Integer, JSON, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

try:
    from demo.donut_api import DonutInferenceService
    from demo.yolo_api import YoloInferenceService
except ModuleNotFoundError:
    from donut_api import DonutInferenceService
    from yolo_api import YoloInferenceService

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
DEFAULT_UPLOAD_DIR = ROOT_DIR / "uploads"
DEFAULT_DATABASE_URL = f"sqlite:///{(ROOT_DIR / 'demo.sqlite3').as_posix()}"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env.example")
except Exception:
    pass

YOLO_MODEL_REPO = os.getenv("YOLO_MODEL_REPO", "Tuan-Bao/yolo-obb")
YOLO_MODEL_FILENAME = os.getenv("YOLO_MODEL_FILENAME", "yolo26n_OPP.pt")
DONUT_MODEL_PATH = os.getenv("DONUT_MODEL_PATH", "Tuan-Bao/donut-finetuned-v2.2")
YOLO_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.35"))
MAX_LENGTH = int(os.getenv("DONUT_MAX_LENGTH", "256"))
TASK_START_TOKEN = os.getenv("DONUT_TASK_TOKEN", "<parsing>")
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(24 * 1024 * 1024)))
IMAGE_STORAGE_PROVIDER = os.getenv("IMAGE_STORAGE_PROVIDER", "local").strip().lower()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR))).resolve()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


PRELOAD_YOLO = _env_flag("PRELOAD_YOLO", "true")
PRELOAD_DONUT = _env_flag("PRELOAD_DONUT", "true")


engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    detection_count: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    image_public_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_storage_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class AnalyzeRequest(BaseModel):
    filename: str | None = None
    image_base64: str = Field(..., min_length=1)


class DrawingAnalysisConfig(BaseModel):
    yolo_model_repo: str = YOLO_MODEL_REPO
    yolo_model_filename: str = YOLO_MODEL_FILENAME
    donut_model_path: str = DONUT_MODEL_PATH
    yolo_confidence: float = YOLO_CONFIDENCE
    max_length: int = MAX_LENGTH
    task_start_token: str = TASK_START_TOKEN
    max_image_bytes: int = MAX_IMAGE_BYTES
    image_storage_provider: str = IMAGE_STORAGE_PROVIDER
    upload_dir: str = str(UPLOAD_DIR)
    public_base_url: str = PUBLIC_BASE_URL


class AnalysisSummary(BaseModel):
    id: int
    filename: str | None
    image_width: int
    image_height: int
    detection_count: int
    created_at: datetime
    image_url: str | None = None
    image_storage_provider: str | None = None


class AnalysisDetail(AnalysisSummary):
    image_public_id: str | None = None
    payload: dict[str, Any]


@dataclass(frozen=True)
class StoredImage:
    url: str | None
    provider: str
    public_id: str | None = None
    error: str | None = None


def _decode_image_payload(image_base64: str) -> Image.Image:
    payload = image_base64.strip()
    if payload.startswith("data:"):
        payload = payload.split(",", 1)[1]

    try:
        raw_bytes = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise ValueError("Invalid base64 image payload") from exc

    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image is too large. Maximum size is {MAX_IMAGE_BYTES // (1024 * 1024)} MB")

    try:
        with Image.open(BytesIO(raw_bytes)) as image:
            return ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise ValueError("Unsupported image format") from exc


def _resize_preview(image: Image.Image, max_side: int = 256) -> Image.Image:
    preview = image.copy()
    preview.thumbnail((max_side, max_side))
    return preview


def _image_to_data_url(image: Image.Image, image_format: str = "PNG", quality: int = 90) -> str:
    buffer = BytesIO()
    save_kwargs: dict[str, Any] = {"format": image_format, "optimize": True}
    if image_format.upper() in {"JPEG", "WEBP"}:
        save_kwargs["quality"] = quality
    image.save(buffer, **save_kwargs)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    mime = "jpeg" if image_format.upper() == "JPEG" else image_format.lower()
    return f"data:image/{mime};base64,{encoded}"


def _safe_filename_stem(filename: str | None) -> str:
    stem = Path(filename or "drawing").stem.strip().lower()
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem)
    return stem.strip("-._") or "drawing"


def _storage_file_id(filename: str | None) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{timestamp}-{_safe_filename_stem(filename)}"


def _image_to_jpeg_bytes(image: Image.Image, max_side: int = 1800, quality: int = 88) -> bytes:
    display_image = image.copy()
    display_image.thumbnail((max_side, max_side))

    background = Image.new("RGB", display_image.size, (255, 255, 255))
    background.paste(display_image)

    buffer = BytesIO()
    background.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buffer.getvalue()


def _with_public_base_url(path: str) -> str:
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}{path}"
    return path


def _local_upload_path(path: str) -> Path:
    upload_root = UPLOAD_DIR.resolve()
    target = (upload_root / path).resolve()
    if target != upload_root and upload_root not in target.parents:
        raise HTTPException(status_code=404, detail="Upload not found")
    return target


@dataclass
class DrawingAnalysisService:
    config: DrawingAnalysisConfig
    yolo: YoloInferenceService
    donut: DonutInferenceService

    def store_image(self, image: Image.Image, filename: str | None = None) -> StoredImage:
        image_bytes = _image_to_jpeg_bytes(image)
        file_id = _storage_file_id(filename)
        return self._store_image_local(image_bytes, file_id)

    def _store_image_local(self, image_bytes: bytes, file_id: str) -> StoredImage:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{file_id}.jpg"
        target_path = _local_upload_path(filename)
        target_path.write_bytes(image_bytes)
        return StoredImage(
            url=_with_public_base_url(f"/api/uploads/{filename}"),
            provider="local",
            public_id=filename,
        )

    def _extract_detections(self, image: Image.Image) -> list[dict[str, Any]]:
        return self.yolo.detect(image, confidence=self.config.yolo_confidence)

    def _crop_image(self, image: Image.Image, bbox: dict[str, int]) -> Image.Image:
        width, height = image.size
        x1 = max(0, min(width, bbox["x1"]))
        y1 = max(0, min(height, bbox["y1"]))
        x2 = max(0, min(width, bbox["x2"]))
        y2 = max(0, min(height, bbox["y2"]))
        if x2 <= x1 or y2 <= y1:
            raise ValueError("Invalid crop region")
        return image.crop((x1, y1, x2, y2))

    def _run_donut(self, crop: Image.Image) -> Any:
        result = self.donut.infer(
            crop,
            task_start_token=self.config.task_start_token,
            max_length=self.config.max_length,
        )
        return result.get("prediction", result)

    def analyze(self, image: Image.Image, filename: str | None = None) -> dict[str, Any]:
        detections = self._extract_detections(image)
        response_detections: list[dict[str, Any]] = []
        grouped_predictions: dict[str, list[Any]] = {}

        for detection in detections:
            crop: Image.Image | None = None
            try:
                crop = self._crop_image(image, detection["bbox"])
                prediction = self._run_donut(crop)
                preview = _image_to_data_url(_resize_preview(crop), image_format="JPEG", quality=82)
            except Exception as exc:
                prediction = {"error": str(exc)}
                preview = None

            grouped_predictions.setdefault(detection["label"], []).append(prediction)
            response_detections.append(
                {
                    **detection,
                    "crop_size": {"width": crop.width if crop else 0, "height": crop.height if crop else 0},
                    "prediction": prediction,
                    "crop_preview": preview,
                }
            )

        return {
            "filename": filename,
            "image_size": {"width": image.width, "height": image.height},
            "detection_count": len(response_detections),
            "detections": response_detections,
            "grouped_predictions": grouped_predictions,
        }


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def analysis_summary_from_record(record: AnalysisRecord) -> AnalysisSummary:
    return AnalysisSummary(
        id=record.id,
        filename=record.filename,
        image_width=record.image_width,
        image_height=record.image_height,
        detection_count=record.detection_count,
        created_at=record.created_at,
        image_url=record.image_url,
        image_storage_provider=record.image_storage_provider,
    )


def payload_from_record(record: AnalysisRecord) -> dict[str, Any]:
    payload = dict(record.payload)
    payload.setdefault("analysis_id", record.id)
    payload.setdefault(
        "source_image",
        {
            "url": record.image_url,
            "provider": record.image_storage_provider,
            "public_id": record.image_public_id,
            "error": None,
        },
    )
    return payload


config = DrawingAnalysisConfig()
yolo_service = YoloInferenceService(
    model_repo=config.yolo_model_repo,
    model_filename=config.yolo_model_filename,
    default_confidence=config.yolo_confidence,
)
donut_service = DonutInferenceService(
    model_path=config.donut_model_path,
    task_start_token=config.task_start_token,
    max_length=config.max_length,
)
service = DrawingAnalysisService(config=config, yolo=yolo_service, donut=donut_service)

app = FastAPI(title="Mechanical Drawing Analyzer", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    if PRELOAD_YOLO:
        yolo_service.preload()
    if PRELOAD_DONUT:
        donut_service.preload()


@app.post("/api/warmup")
def warmup() -> dict[str, Any]:
    yolo_service.load()
    donut_service.load()
    return {
        "status": "ok",
        "yolo": yolo_service.health(),
        "donut": donut_service.health(),
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    yolo_health = yolo_service.health()
    donut_health = donut_service.health()
    device = yolo_health.get("device") or donut_health.get("device") or "unknown"
    return {
        "status": "ok",
        "device": device,
        "yolo_model_repo": config.yolo_model_repo,
        "yolo_model_filename": config.yolo_model_filename,
        "donut_model_path": config.donut_model_path,
        "yolo": yolo_health,
        "donut": donut_health,
        "image_storage": {"provider": config.image_storage_provider},
    }


@app.get("/api/config")
def read_config() -> dict[str, Any]:
    return config.model_dump()


@app.get("/api/analyses", response_model=list[AnalysisSummary])
def list_analyses(db: Session = Depends(get_db)) -> list[AnalysisSummary]:
    records = db.execute(
        select(AnalysisRecord).order_by(AnalysisRecord.id.desc()).limit(50)
    ).scalars().all()
    return [analysis_summary_from_record(record) for record in records]


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisDetail)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)) -> AnalysisDetail:
    record = db.get(AnalysisRecord, analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisDetail(
        id=record.id,
        filename=record.filename,
        image_width=record.image_width,
        image_height=record.image_height,
        detection_count=record.detection_count,
        created_at=record.created_at,
        image_url=record.image_url,
        image_storage_provider=record.image_storage_provider,
        image_public_id=record.image_public_id,
        payload=payload_from_record(record),
    )


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        image = _decode_image_payload(request.image_base64)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = service.analyze(image, filename=request.filename)
        stored_image = service.store_image(image, filename=request.filename)
        result["source_image"] = {
            "url": stored_image.url,
            "provider": stored_image.provider,
            "public_id": stored_image.public_id,
            "error": stored_image.error,
        }
        record = AnalysisRecord(
            filename=request.filename,
            image_width=result["image_size"]["width"],
            image_height=result["image_size"]["height"],
            detection_count=result["detection_count"],
            image_url=stored_image.url,
            image_public_id=stored_image.public_id,
            image_storage_provider=stored_image.provider,
            payload=result,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        result["analysis_id"] = record.id
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.get("/api/uploads/{path:path}")
def uploaded_image(path: str) -> FileResponse:
    target_path = _local_upload_path(path)
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Upload not found")
    return FileResponse(target_path, media_type="image/jpeg")


@app.get("/")
def index() -> FileResponse:
    if (FRONTEND_DIST_DIR / "index.html").exists():
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/assets/{path:path}")
def frontend_assets(path: str) -> FileResponse:
    asset_from_dist = FRONTEND_DIST_DIR / path
    if asset_from_dist.exists():
        return FileResponse(asset_from_dist)
    asset_from_src = FRONTEND_DIR / path
    if asset_from_src.exists():
        return FileResponse(asset_from_src)
    raise HTTPException(status_code=404, detail="Asset not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
