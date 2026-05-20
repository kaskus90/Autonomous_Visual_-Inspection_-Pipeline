FROM python:3.11-slim

# OpenCV runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the model weights at build time so the container starts instantly
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

COPY main.py .

CMD ["python", "main.py"]
