FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY config.local.example.json ./
COPY ticktick_open_api_codex_guide.md ./

RUN pip install --no-cache-dir .

CMD ["python", "-m", "app"]
