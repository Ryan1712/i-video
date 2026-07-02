FROM python:3.11-slim

WORKDIR /app

# System deps for Pillow, imageio-ffmpeg, psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the API. Override CMD for the worker.
CMD ["uvicorn", "saas.main:app", "--host", "0.0.0.0", "--port", "8000"]
