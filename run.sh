#!/usr/bin/env bash
# 백엔드(FastAPI)와 치료사 화면(Streamlit)을 함께 띄운다.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }

.venv/bin/python -m uvicorn backend.main:app --port 8000 --reload &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null' EXIT

sleep 2
echo "─────────────────────────────────────────────"
echo "  치료사 화면 : http://localhost:8501"
echo "  환자 화면   : http://localhost:8000/p/tok_kim62"
echo "  API 문서    : http://localhost:8000/docs"
echo "─────────────────────────────────────────────"
.venv/bin/python -m streamlit run frontend/app.py --server.port 8501
