FROM python:3.12.10-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        curl \
        fonts-dejavu-core \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.deploy.txt ./
RUN python -m pip install --requirement requirements.deploy.txt

RUN groupadd --gid 1000 andyhub \
    && useradd --uid 1000 --gid andyhub --create-home andyhub
COPY --chown=andyhub:andyhub . .
USER andyhub

EXPOSE 8000 8001
CMD ["uvicorn", "andyhub_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
