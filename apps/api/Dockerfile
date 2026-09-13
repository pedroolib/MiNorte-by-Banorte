FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv
# opencv-python-headless (lectura de QR de tickets) igual necesita estas
# libs de sistema en tiempo de ejecución, aunque sea "headless".
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN uv pip install --system -e ".[dev]"
# Browser Agent (spec #19): Chromium real + libs del sistema que necesita
# para correr headless dentro del contenedor.
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY tests ./tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
