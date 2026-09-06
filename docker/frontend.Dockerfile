# frontend — 치료사 화면. 표시와 입력만 하고 백엔드 API만 호출한다.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/frontend.txt requirements/frontend.txt
RUN pip install --no-cache-dir -r requirements/frontend.txt

COPY frontend/ frontend/

RUN useradd --create-home --uid 10002 app && chown -R app:app /app
USER app

EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=5s --start-period=25s --retries=5 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"

CMD ["streamlit", "run", "frontend/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
