-- Query kiểm tra sau khi chạy pipeline (chạy riêng file này khi cần)
-- Kết nối database: mechanical_drawings_demo

-- Đếm số bản ghi
SELECT COUNT(*) AS total_analyses FROM analysis_records;

-- 10 lần phân tích gần nhất
SELECT
    id,
    filename,
    image_width,
    image_height,
    detection_count,
    image_storage_provider,
    created_at
FROM analysis_records
ORDER BY id DESC
LIMIT 10;

-- Xem label YOLO và confidence từng detection
SELECT
    ar.id,
    ar.filename,
    detection->>'label' AS label,
    (detection->>'confidence')::numeric AS confidence,
    detection->'bbox' AS bbox
FROM analysis_records ar
CROSS JOIN LATERAL jsonb_array_elements(ar.payload->'detections') AS detection
ORDER BY ar.id DESC, (detection->>'index')::int;

-- Xem prediction DONUT của một analysis cụ thể (đổi id = 1 nếu cần)
SELECT
    id,
    filename,
    jsonb_pretty(payload->'grouped_predictions') AS grouped_predictions
FROM analysis_records
WHERE id = 1;
