FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/backend
WORKDIR /app
# Local Korean and English OCR; no external OCR service or uploaded image persistence.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-kor tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
# Install CPU PyTorch first to avoid large CUDA dependencies on demo laptops.
RUN python -m pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install -r /app/backend/requirements.txt
COPY backend /app/backend
COPY ai /app/ai
COPY data /app/data
COPY scripts /app/scripts
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
