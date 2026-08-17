FROM python:3.10-slim

# -------------------------
# System dependencies
# -------------------------
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# -------------------------
# Set working directory
# -------------------------
WORKDIR /app

# -------------------------
# Copy files
# -------------------------
COPY . /app

# -------------------------
# Install Python dependencies
# -------------------------
RUN pip install --no-cache-dir -r requirements.txt

# -------------------------
# Environment variables
# -------------------------
ENV PORT=7860

# -------------------------
# Run FastAPI
# -------------------------
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]