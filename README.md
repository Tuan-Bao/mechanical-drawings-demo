# Mechanical Drawings Demo

Bản này là bản chạy local, không dùng Docker.

## Thành phần

- `backend.py`: FastAPI app duy nhất — API, YOLO, DONUT, lưu lịch sử
- `yolo_api.py`: class `YoloInferenceService` (model từ Hugging Face)
- `donut_api.py`: class `DonutInferenceService` (model từ Hugging Face + **hftuner**)
- `hftuner/`: clone từ [hftuner/clovaai-donut](https://github.com/hftuner/clovaai-donut) (không commit, xem SETUP)
- `frontend/`: React + Vite UI
- `db/schema.sql`: thiết kế PostgreSQL (bảng `analysis_records`)
- `requirements.txt`: Python dependencies
- `.env.example`: cấu hình local mẫu

`yolo_api.py` và `donut_api.py` chỉ là module logic model, **không** chạy server riêng.

## Kiến trúc

```text
Frontend :5173
    -> Backend :8000
        -> YoloInferenceService  (HF: Tuan-Bao/yolo-obb)
        -> DonutInferenceService (HF: Tuan-Bao/donut-finetuned-v2.2)
```

## Chạy nhanh

1. Cài dependencies Python từ `requirements.txt`.
2. `hf auth login` nếu cần tải model từ Hugging Face.
3. Chạy backend ở port `8000`.
4. Chạy frontend Vite ở port `5173`.

Chi tiết deploy Vercel + Render + PostgreSQL: [DEPLOY.md](DEPLOY.md).
