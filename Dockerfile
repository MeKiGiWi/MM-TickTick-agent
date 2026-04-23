FROM python:3.11-slim

ENV PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY config.local.example.json ./
COPY ticktick_open_api_codex_guide.md ./

RUN pip install --no-cache-dir .

CMD ["python", "-m", "app"]
