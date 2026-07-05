-- Mechanical Drawings Demo - PostgreSQL schema
-- Database: mechanical_drawings_demo
--
-- CÁCH CHẠY (pgAdmin / DBeaver / DataGrip):
--   1. Chạy demo/db/01_create_database.sql  (kết nối database "postgres")
--   2. Chọn database "mechanical_drawings_demo"
--   3. Chạy file này (schema.sql)
--
-- CÁCH CHẠY (psql CLI):
--   psql -U postgres -f demo/db/01_create_database.sql
--   psql -U postgres -d mechanical_drawings_demo -f demo/db/schema.sql

-- ---------------------------------------------------------------------------
-- Extension (tùy chọn)
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- Bảng chính: analysis_records
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_records (
    id                      SERIAL PRIMARY KEY,
    filename                VARCHAR(255),
    image_width             INTEGER      NOT NULL CHECK (image_width > 0),
    image_height            INTEGER      NOT NULL CHECK (image_height > 0),
    detection_count         INTEGER      NOT NULL CHECK (detection_count >= 0),
    image_url               VARCHAR(2048),
    image_public_id         VARCHAR(512),
    image_storage_provider  VARCHAR(64),
    payload                 JSONB        NOT NULL,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE analysis_records IS
    'Lịch sử phân tích bản vẽ: metadata ảnh + kết quả YOLO/DONUT (JSONB).';

COMMENT ON COLUMN analysis_records.id IS
    'Khóa chính, tự tăng. Frontend dùng làm analysis_id.';

COMMENT ON COLUMN analysis_records.filename IS
    'Tên file gốc user upload, ví dụ drawing-001.png.';

COMMENT ON COLUMN analysis_records.image_width IS
    'Chiều rộng ảnh gốc (pixel).';

COMMENT ON COLUMN analysis_records.image_height IS
    'Chiều cao ảnh gốc (pixel).';

COMMENT ON COLUMN analysis_records.detection_count IS
    'Số vùng YOLO detect được trên ảnh.';

COMMENT ON COLUMN analysis_records.image_url IS
    'URL ảnh đã lưu. Local: /api/uploads/<file>.jpg. Cloudinary: https://...';

COMMENT ON COLUMN analysis_records.image_public_id IS
    'ID file trên storage (tên file local hoặc public_id Cloudinary).';

COMMENT ON COLUMN analysis_records.image_storage_provider IS
    'Nguồn lưu ảnh: local hoặc cloudinary.';

COMMENT ON COLUMN analysis_records.payload IS
    'JSON đầy đủ: detections, grouped_predictions, source_image, image_size, ...';

COMMENT ON COLUMN analysis_records.created_at IS
    'Thời điểm phân tích (UTC).';

-- ---------------------------------------------------------------------------
-- Index
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_analysis_records_created_at
    ON analysis_records (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_analysis_records_filename
    ON analysis_records (filename);

CREATE INDEX IF NOT EXISTS idx_analysis_records_payload_gin
    ON analysis_records USING GIN (payload jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- Cấu trúc JSON trong payload (tham khảo)
-- ---------------------------------------------------------------------------
-- {
--   "filename": "drawing.png",
--   "image_size": { "width": 2480, "height": 3508 },
--   "detection_count": 3,
--   "detections": [
--     {
--       "index": 0,
--       "label": "title_block",
--       "class_id": 0,
--       "confidence": 0.91,
--       "bbox": { "x1": 10, "y1": 20, "x2": 400, "y2": 300 },
--       "crop_size": { "width": 390, "height": 280 },
--       "prediction": { "...": "kết quả DONUT" },
--       "crop_preview": "data:image/jpeg;base64,..."
--     }
--   ],
--   "grouped_predictions": {
--     "title_block": [ { "...": "..." } ]
--   },
--   "source_image": {
--     "url": "/api/uploads/20260705120000-drawing.jpg",
--     "provider": "local",
--     "public_id": "20260705120000-drawing.jpg",
--     "error": null
--   },
--   "analysis_id": 1
-- }
