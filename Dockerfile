FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/logs /app/temp /app/repos /app/data

EXPOSE 9292

ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
