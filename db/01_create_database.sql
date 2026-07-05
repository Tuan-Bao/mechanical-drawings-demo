-- Bước 1: Chạy file này khi đang kết nối database "postgres"
-- (pgAdmin: chuột phải postgres -> Query Tool -> paste & Execute)

CREATE DATABASE mechanical_drawings_demo
    ENCODING 'UTF8'
    TEMPLATE template0;

-- Nếu database đã tồn tại sẽ báo lỗi — bỏ qua và chuyển sang schema.sql
