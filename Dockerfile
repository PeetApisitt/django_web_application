FROM python:3.12-slim

# ป้องกันไม่ให้ Python สร้างไฟล์ .pyc และให้แสดงผล Log แบบ Real-time
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ตั้งค่า Working Directory
WORKDIR /app

# คัดลอกไฟล์ requirements.txt และติดตั้งแพ็กเกจ
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมดในโปรเจกต์เข้าสู่ Container
COPY . /app/

# เปิดพอร์ต 8000 สำหรับ Django
EXPOSE 8000

# คำสั่งเริ่มต้นสำหรับรันเซิร์ฟเวอร์
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

