FROM mcr.microsoft.com/playwright/python:latest

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY scripts/capture_screens.py /app/scripts/capture_screens.py
COPY console /app/console
COPY docs /app/docs

RUN useradd -m runner && chown -R runner:runner /app
USER runner

CMD ["python", "/app/scripts/capture_screens.py", "--base", "http://api:8000", "--out", "/app/docs/assets"]
