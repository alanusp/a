FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UMASK=027 \
    SOURCE_DATE_EPOCH=1704067200

RUN addgroup --system --gid 1001 app \
    && adduser --system --uid 1001 --ingroup app app \
    && mkdir -p /workspace

WORKDIR /workspace

COPY pyproject.toml README.md /workspace/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

COPY . /workspace

RUN chown -R app:app /workspace

USER app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import os; os.kill(1, 0)"

CMD ["python", "-m", "streaming.pipeline"]
