# Setup demo — Frontend đến Backend (PostgreSQL)

Hướng dẫn chạy full stack `demo` trên Windows. Backend gom YOLO + DONUT trong một process; database dùng **PostgreSQL**.

## Tổng quan

```text
Browser :5173 (Vite + React)
    │  proxy /api → :8000
    ▼
Backend :8000 (FastAPI)
    ├── YOLO   ← Hugging Face: Tuan-Bao/yolo-obb
    ├── DONUT  ← Hugging Face: Tuan-Bao/donut-finetuned-v2.2
    └── PostgreSQL
```

| Thành phần | Port | File chính |
|---|---|---|
| Frontend | 5173 | `demo/frontend/` |
| Backend | 8000 | `demo/backend.py` |
| PostgreSQL | 5432 | `demo/db/schema.sql` |

---

## 1) Yêu cầu

- Python 3.11+
- Node.js 20+
- PostgreSQL 15+ (cài local hoặc Docker)
- Git + kết nối internet (tải model Hugging Face)

---

## 2) Clone / mở project

Làm việc ở thư mục gốc chứa folder `demo` (ví dụ `D:\DATN`):

```powershell
cd D:\DATN
```

---

## 3) PostgreSQL

### Cách A — Docker (nhanh)

```powershell
docker run -d `
  --name demo-postgres `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=mechanical_drawings_demo `
  -p 5432:5432 `
  postgres:17-alpine
```

### Cách B — PostgreSQL cài sẵn trên máy

Tạo database bằng SQL (pgAdmin hoặc psql):

```powershell
# Bước 1 — tạo database (kết nối postgres)
psql -U postgres -f demo\db\01_create_database.sql

# Bước 2 — tạo bảng (kết nối mechanical_drawings_demo)
psql -U postgres -d mechanical_drawings_demo -f demo\db\schema.sql
```

Trong **pgAdmin**: chạy `01_create_database.sql` trên DB `postgres`, rồi chọn `mechanical_drawings_demo` và chạy `schema.sql`.

---

Làm việc trong thư mục `demo`:

```powershell
cd D:\DATN\demo
```

---

## 4) Python backend

```powershell
cd D:\DATN\demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install torch torchvision
pip install -r requirements.txt
```

## 4b) Cài hftuner (cho DONUT)

DONUT fine-tune bằng [hftuner/clovaai-donut](https://github.com/hftuner/clovaai-donut). Demo load `DonutModel` từ package này; không có thì fallback `VisionEncoderDecoderModel` (vẫn chạy nhưng nên cài cho khớp model).

```powershell
cd D:\DATN\demo
git clone https://github.com/hftuner/clovaai-donut hftuner
```

Kiểm tra:

```powershell
python -c "from hftuner.donut import DonutModel; print(DonutModel)"
```

Thư mục `hftuner/` nằm trong `.gitignore` — mỗi máy clone một lần.

Đăng nhập Hugging Face (lần đầu, nếu repo model private):

```powershell
hf auth login
```

---

## 5) File `.env`

```powershell
copy .env.example .env
```

Sửa `.env`, tối thiểu:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/mechanical_drawings_demo
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
UPLOAD_DIR=./uploads
PUBLIC_BASE_URL=http://localhost:8000

YOLO_MODEL_REPO=Tuan-Bao/yolo-obb
YOLO_MODEL_FILENAME=yolo26n_OPP.pt
YOLO_CONFIDENCE=0.35
PRELOAD_YOLO=true

DONUT_MODEL_PATH=Tuan-Bao/donut-finetuned-v2.2
DONUT_MAX_LENGTH=256
DONUT_TASK_TOKEN=<parsing>
PRELOAD_DONUT=true

IMAGE_STORAGE_PROVIDER=local
```

> Nếu PostgreSQL chạy port khác (vd. Docker map `5434:5432`), đổi port trong `DATABASE_URL`.

---

## 6) Frontend

```powershell
cd frontend
npm install
```

Vite đã cấu hình proxy `/api` → `http://127.0.0.1:8000` (`vite.config.js`), nên frontend gọi backend không cần CORS phức tạp khi dev.

---

## 7) Chạy ứng dụng

**Terminal 1 — Backend** (từ `D:\DATN\demo`):

```powershell
cd D:\DATN\demo
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend:app --reload --host 0.0.0.0 --port 8000
```

> Nếu chạy từ thư mục cha `D:\DATN` thì dùng:  
> `python -m uvicorn demo.backend:app --reload --host 0.0.0.0 --port 8000`

**Terminal 2 — Frontend**:

```powershell
cd D:\DATN\demo\frontend
npm run dev
```

Mở trình duyệt:

| URL | Mục đích |
|---|---|
| http://localhost:5173 | Giao diện upload & xem kết quả |
| http://localhost:8000/api/health | Kiểm tra YOLO + DONUT đã load chưa |
| http://localhost:8000/api/config | Xem cấu hình đang dùng |

---

## 8) Kiểm tra pipeline

1. Mở http://localhost:5173
2. Đợi status chip chuyển **Ready** (YOLO + DONUT loaded)
3. Upload ảnh bản vẽ → **Analyze**
4. Xem detections + JSON prediction trên UI
5. Kiểm tra DB:

```powershell
psql -U postgres -d mechanical_drawings_demo -c "SELECT id, filename, detection_count, created_at FROM analysis_records ORDER BY id DESC LIMIT 5;"
```

Hoặc dùng các query trong `demo/db/queries_check.sql`.

---

## 9) Database — bảng lưu gì?

App chỉ dùng **1 bảng**: `analysis_records`

| Cột | Kiểu | Mô tả |
|---|---|---|
| `id` | SERIAL PK | ID phân tích, tự tăng |
| `filename` | VARCHAR(255) | Tên file user upload |
| `image_width` | INTEGER | Rộng ảnh gốc (px) |
| `image_height` | INTEGER | Cao ảnh gốc (px) |
| `detection_count` | INTEGER | Số vùng YOLO detect |
| `image_url` | VARCHAR(2048) | URL ảnh đã lưu (`/api/uploads/...`) |
| `image_public_id` | VARCHAR(512) | ID file trên storage |
| `image_storage_provider` | VARCHAR(64) | `local` hoặc `cloudinary` |
| `payload` | JSONB | Toàn bộ kết quả pipeline (detections, predictions, ...) |
| `created_at` | TIMESTAMPTZ | Thời điểm phân tích (UTC) |

Chi tiết cấu trúc JSON trong `payload` xem comment trong `demo/db/schema.sql`.

Backend cũng tự `CREATE TABLE` lúc startup (SQLAlchemy) nếu bảng chưa có — nhưng nên chạy `schema.sql` trước để có index và comment đầy đủ.

---

## 10) Xử lý lỗi thường gặp

| Triệu chứng | Cách xử lý |
|---|---|
| `Could not connect to the backend` | Backend chưa chạy hoặc sai port |
| YOLO/DONUT **Waiting** lâu | Lần đầu tải model từ HF — đợi hoặc xem `/api/health` → `load_error` |
| `No module named 'psycopg2'` | `DATABASE_URL` phải dùng `postgresql+psycopg://` (Neon copy thường là `postgresql://` — code tự đổi sau khi redeploy) |
| Lỗi kết nối PostgreSQL | Kiểm tra `DATABASE_URL`, Postgres đã start, database đã tạo |
| `No module named 'psycopg'` | `pip install "psycopg[binary]>=3.2"` |
| `DonutProcessor` / `Could not import module` | Cài **torchvision**: `pip install torch torchvision` |
| `Tokenizer class TokenizersBackend does not exist` | Nâng `transformers` lên 5.x: `pip install "transformers>=5.3,<6.0"` |

---

## 11) API chính (tham khảo)

| Method | Path | Mô tả |
|---|---|---|
| GET | `/api/health` | Trạng thái model |
| POST | `/api/analyze` | Upload ảnh base64, chạy pipeline, lưu DB |
| GET | `/api/analyses` | Danh sách 50 phân tích gần nhất |
| GET | `/api/analyses/{id}` | Chi tiết 1 phân tích |
| GET | `/api/uploads/{file}` | Ảnh đã lưu local |
