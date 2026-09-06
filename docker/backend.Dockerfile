# backend — 규칙 판정 · AI 호출 · API · 환자 모바일 웹
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/backend.txt requirements/backend.txt
RUN pip install --no-cache-dir -r requirements/backend.txt

COPY backend/ backend/
COPY data/ data/

# 쓰기가 필요한 곳은 볼륨으로 뺀다 (SQLite · 로컬 색인)
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /var/lib/rehabtalk \
 && chown -R app:app /var/lib/rehabtalk /app
USER app

ENV REHABTALK_DB=/var/lib/rehabtalk/rehabtalk.db \
    CHROMA_DIR=/var/lib/rehabtalk/chroma

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
