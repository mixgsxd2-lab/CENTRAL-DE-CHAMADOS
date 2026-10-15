# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Usuário não-root. O banco agora é o MySQL (ver MYSQL_* em config.py),
# acessado pela rede — não há mais volume de dados neste container.
RUN useradd --system --uid 10001 --no-create-home app \
    && chown -R app:app /app
USER 10001

EXPOSE 8000

# 1 worker + threads: o limitador de login (memória) e a tarefa de segundo
# plano da Hotelaria dependem de um único processo; o MySQL já aceita
# conexões concorrentes de vários workers, mas isso continua valendo.
CMD ["sh", "-c", "exec gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120 --access-logfile -"]
