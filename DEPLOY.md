# Deploy demo — Vercel (FE) + Render (BE) + PostgreSQL

Hướng dẫn đưa `demo` lên production. Đọc trước khi deploy.

## Tổng quan kiến trúc

```text
Vercel (React)          Render (FastAPI + YOLO + DONUT)
https://xxx.vercel.app  https://xxx.onrender.com
        │                        │
        └────── /api/* ──────────┘
                                 │
                    PostgreSQL (Render / Neon / Supabase)
                    Cloudinary (ảnh upload — bắt buộc trên Render)
                    Hugging Face Hub (tải model YOLO + DONUT)
                    GitHub clone hftuner lúc build (DonutModel)
```

> **Lưu ý:** Backend load **PyTorch + YOLO + DONUT** — RAM lớn (~2–4GB+). Render **free** thường không đủ; dùng plan **Starter** trở lên hoặc máy có GPU. Lần đầu cold start có thể mất vài phút tải model.

---

## Bước 1 — Đăng nhập GitHub (cá nhân)

### Cách A — GitHub CLI (khuyên dùng)

```powershell
winget install GitHub.cli
gh auth login
```

Chọn: **GitHub.com** → **HTTPS** → **Login with a web browser** → copy code → đăng nhập trên trình duyệt.

Kiểm tra:

```powershell
gh auth status
```

### Cách B — Git thuần

Khi `git push` lần đầu, Windows/Git Credential Manager sẽ mở trình duyệt đăng nhập GitHub.

Cấu hình tên commit (một lần):

```powershell
git config --global user.name "Tên bạn"
git config --global user.email "email@github.com"
```

---

## Bước 2 — Đưa source lên GitHub

Khuyên dùng **repo riêng chỉ chứa `demo`** (deploy đơn giản hơn monorepo `DATN`).

```powershell
cd D:\DATN\demo
git init
git add .
git commit -m "Initial demo: mechanical drawing analyzer"
```

Tạo repo trên GitHub (private hoặc public):

```powershell
gh repo create mechanical-drawings-demo --private --source=. --remote=origin --push
```

Hoặc tạo repo thủ công trên https://github.com/new rồi:

```powershell
git remote add origin https://github.com/<username>/mechanical-drawings-demo.git
git branch -M main
git push -u origin main
```

### File KHÔNG lên git (đã có trong `.gitignore`)

- `.venv/`, `hftuner/` (clone lúc build Render)
- `.env` (secrets)
- `uploads/`, `*.sqlite3`

---

## Bước 3 — hftuner trên Render (backend)

`hftuner` **không có trên PyPI**. Import trong code:

```python
from hftuner.donut import DonutModel
```

**Giải pháp:** script build Render tự clone:

```bash
git clone --depth 1 https://github.com/hftuner/clovaai-donut.git hftuner
```

Đã có sẵn trong `scripts/render-build.sh` và `render.yaml`.

Local dev vẫn clone thủ công:

```powershell
cd D:\DATN\demo
git clone https://github.com/hftuner/clovaai-donut hftuner
```

---

## Bước 4 — Database (chọn 1)

| Nền tảng | Ưu | Nhược |
|---|---|---|
| **Neon** | Free tier tốt, tách BE/DB, đang dùng | Cấu hình `DATABASE_URL` thủ công trên Render |
| **Render PostgreSQL** | Cùng dashboard Render | Không dùng trong `render.yaml` hiện tại |
| **Supabase** | UI đẹp, free tier | Cấu hình riêng |

### Neon (khuyên dùng — không tạo DB trên Render)

`render.yaml` **không** tạo PostgreSQL trên Render. Bạn tự set `DATABASE_URL` từ Neon trong Render Dashboard.

1. Tạo project tại https://neon.tech
2. SQL Editor → chạy `db/schema.sql`
3. Copy connection string, đổi thành:

```env
DATABASE_URL=postgresql+psycopg://USER:PASS@ep-xxx.neon.tech/neondb?sslmode=require
```

4. Paste vào Render → Environment → `DATABASE_URL`

### Render Postgres (tùy chọn — không dùng trong bản này)

Deploy Blueprint sẽ tạo DB + API. `DATABASE_URL` tự inject.

Sau deploy, chạy schema (từ máy local):

```powershell
psql "<DATABASE_URL từ Render>" -f db/schema.sql
```

Hoặc dùng pgAdmin / Neon SQL editor chạy `db/01_create_database.sql` + `db/schema.sql`.

**Lưu ý:** Render có thể trả URL dạng `postgres://` — SQLAlchemy cần:

```env
DATABASE_URL=postgresql+psycopg://user:pass@host/dbname
```

(thay `postgres://` → `postgresql+psycopg://` nếu cần)

### Neon (nếu không dùng Render DB)

1. Tạo project tại https://neon.tech
2. Copy connection string → `DATABASE_URL` trên Render
3. Chạy `db/schema.sql` trên Neon

---

## Bước 5 — Deploy Backend (Render)

### Cách A — Blueprint (`render.yaml`)

1. Render Dashboard → **New** → **Blueprint**
2. Connect repo GitHub `mechanical-drawings-demo`
3. Chọn branch `main` → Apply

### Cách B — Web Service thủ công

| Mục | Giá trị |
|---|---|
| Root Directory | `demo` (nếu repo là monorepo) hoặc `.` (nếu repo chỉ demo) |
| Runtime | Python 3.11 |
| Build Command | `bash scripts/render-build.sh` |
| Start Command | `uvicorn backend:app --host 0.0.0.0 --port $PORT` |
| Health Check | `/api/health` |

### Biến môi trường Render (Environment)

```env
DATABASE_URL=postgresql+psycopg://...
FRONTEND_ORIGINS=https://your-app.vercel.app
PUBLIC_BASE_URL=https://your-api.onrender.com
UPLOAD_DIR=./uploads

YOLO_MODEL_REPO=Tuan-Bao/yolo-obb
YOLO_MODEL_FILENAME=yolo26n_OPP.pt
YOLO_CONFIDENCE=0.35
PRELOAD_YOLO=false
PRELOAD_DONUT=false

DONUT_MODEL_PATH=Tuan-Bao/donut-finetuned-v2.2
DONUT_MAX_LENGTH=256
DONUT_TASK_TOKEN=<parsing>

IMAGE_STORAGE_PROVIDER=cloudinary
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
CLOUDINARY_FOLDER=mechanical-drawings

HF_TOKEN=hf_...   # nếu model private
```

**Quan trọng:**

- `PRELOAD_*=false` trên Render — tránh timeout lúc startup; model load lần đầu khi analyze.
- **Cloudinary bắt buộc** — Render filesystem ephemeral, `uploads/` mất sau restart.
- `FRONTEND_ORIGINS` = URL Vercel chính xác (không slash cuối).

---

## Bước 6 — Deploy Frontend (Vercel)

1. https://vercel.com → **Add New Project** → import repo GitHub
2. **Root Directory:** `frontend` (nếu repo root là `demo`) hoặc `demo/frontend` (monorepo)
3. Framework: **Vite**
4. Build: `npm run build` · Output: `dist`
5. Environment Variable:

```env
VITE_API_BASE_URL=https://your-api.onrender.com
```

6. Deploy → copy URL `https://xxx.vercel.app`
7. Quay lại Render → sửa `FRONTEND_ORIGINS` = URL Vercel → redeploy API

Local test production build:

```powershell
cd frontend
$env:VITE_API_BASE_URL="https://your-api.onrender.com"
npm run build
npm run preview
```

---

## Bước 7 — Kiểm tra sau deploy

1. `https://your-api.onrender.com/api/health` → `yolo` + `donut` loaded (hoặc waiting lần đầu)
2. `POST /api/warmup` hoặc upload ảnh trên Vercel
3. `GET /api/analyses` → có record trong DB
4. Ảnh hiển thị qua Cloudinary URL

---

## Checklist nhanh

- [ ] `gh auth login` / đăng nhập GitHub
- [ ] Repo push lên GitHub (không commit `.env`)
- [ ] PostgreSQL + chạy `db/schema.sql`
- [ ] Render: build script clone `hftuner`
- [ ] Render: `transformers>=5.3`, env đầy đủ
- [ ] Cloudinary cho `IMAGE_STORAGE_PROVIDER`
- [ ] Vercel: `VITE_API_BASE_URL`
- [ ] Render: `FRONTEND_ORIGINS` = URL Vercel

---

## Xử lý lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| `No module named 'hftuner'` | Build thiếu `render-build.sh` / chưa clone hftuner |
| `DonutProcessor` / `Could not import module` | Thiếu **torchvision** — `pip install torch torchvision` (CPU wheel trên Render); redeploy |
| `DonutProcessor` / Python 3.14 | Render → **PYTHON_VERSION=3.11.9**, commit `runtime.txt`, redeploy |
| `TokenizersBackend does not exist` | `pip install "transformers>=5.3"` trên Render |
| CORS | Sửa `FRONTEND_ORIGINS` khớp domain Vercel |
| Ảnh history mất | Bật Cloudinary, không dùng `local` trên Render |
| OOM / crash | Tăng RAM Render hoặc tắt preload, dùng plan lớn hơn |
| Cold start chậm | Bình thường với free tier; cân nhắc warmup cron |
