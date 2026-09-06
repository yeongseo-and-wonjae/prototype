# frontend — 치료사 화면. 표시와 입력만 하고 백엔드 API만 호출한다.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/frontend.txt requirements/frontend.txt
RUN pip install --no-cache-dir -r requirements/frontend.txt

COPY .streamlit/ .streamlit/
COPY frontend/ frontend/

RUN useradd --create-home --uid 10002 app && chown -R app:app /app
USER app

# PORT를 주면 그 포트로 뜬다 (Render 등 PaaS). 없으면 8501 — compose·로컬은 그대로다.
EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=5s --start-period=25s --retries=5 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/_stcore/health' % os.getenv('PORT','8501'), timeout=4)"

CMD ["sh", "-c", "streamlit run frontend/환자_목록.py \
     --server.port=${PORT:-8501} --server.address=0.0.0.0 \
     --server.headless=true --browser.gatherUsageStats=false"]
