FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-dejavu-core \
    libcairo2 \
    libffi-dev \
    libgdk-pixbuf-2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ai.txt ./

RUN pip install --upgrade pip \
    && pip install -r requirements-ai.txt

COPY . .

RUN sed -i 's/\r$//' deploy/*.sh \
    && chmod +x deploy/*.sh \
    && mkdir -p /app/media /app/staticfiles

EXPOSE 10000

CMD ["bash", "deploy/render-start.sh"]
