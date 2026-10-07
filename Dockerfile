# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DATABASE_PATH=/data/hospital_rio_grande.db

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Usuário não-root; /data é o volume do SQLite (PVC no EKS).
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data \
    && chown -R app:app /data /app
USER 10001

EXPOSE 8000
VOLUME ["/data"]

# 1 worker + threads: o limitador de login (memória), a tarefa de segundo
# plano da Hotelaria e o SQLite dependem de um único processo.
CMD ["sh", "-c", "exec gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120 --access-logfile -"]
