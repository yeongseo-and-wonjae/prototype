"""화면 공통 — API 호출과 톤. 규칙 검사도 AI 호출도 여기서 하지 않는다."""

from __future__ import annotations

import os

import requests
import streamlit as st

API = os.getenv("REHABTALK_API", "http://localhost:8000")

INK, SAFE, WARN, ALERT, LINE = "#152530", "#0B6355", "#9A5B0C", "#A32A20", "#D8E0E5"

CSS = f"""
<style>
  html, body, [class*="css"] {{
    font-family: Pretendard, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif;
    color: {INK};
  }}
  .rt-card {{ border:1px solid {LINE}; border-radius:12px; padding:14px 16px; margin-bottom:10px;
             background:#fff; }}
  .rt-cut  {{ border-color:#EBC9C4; background:#FDF6F5; }}
  .rt-adj  {{ border-color:#EBD8B7; background:#FDF8EF; }}
  .rt-ok   {{ border-color:#BFDBD4; background:#F4F9F8; }}
  .rt-tag  {{ font-size:12px; padding:2px 8px; border-radius:99px; border:1px solid {LINE};
             color:#5A6B75; margin-right:6px; }}
  .rt-rule {{ font-family: ui-monospace, monospace; font-size:12px; color:{ALERT}; }}
  .rt-warn {{ color:{WARN}; font-weight:600; }}
  .rt-safe {{ color:{SAFE}; font-weight:600; }}
  .rt-foot {{ color:#5A6B75; font-size:12px; border-top:1px solid {LINE};
             padding-top:10px; margin-top:28px; line-height:1.5; }}
</style>
"""

DISCLAIMER = (
    '<div class="rt-foot">데모용. 프로토콜 수치와 환자 정보는 구조를 보여주기 위한 예시이며 '
    '<b>실제 임상 처방에 사용할 수 없습니다.</b> 운영 시에는 집도의 프로토콜 원문과 '
    '물리치료사 검증을 거친 값만 사용합니다.</div>'
)


def setup(title: str) -> None:
    st.set_page_config(page_title=f"리햅톡 · {title}", page_icon="🦾", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def footer() -> None:
    st.markdown(DISCLAIMER, unsafe_allow_html=True)


def api(method: str, path: str, **kwargs) -> dict:
    try:
        res = requests.request(method, f"{API}{path}", timeout=120, **kwargs)
    except requests.RequestException as exc:
        st.error(f"백엔드에 연결하지 못했습니다 ({API}). `uvicorn backend.main:app` 이 떠 있는지 확인하세요.\n\n{exc}")
        st.stop()
    if res.status_code >= 400:
        st.error(f"{res.status_code} · {res.json().get('detail', res.text)}")
        st.stop()
    return res.json()


def health_badge() -> None:
    h = api("GET", "/api/health")
    mode = "실제 AI 호출" if h["ai_mode"] == "live" else "목업 (API 키 없음)"
    st.caption(f"AI: {mode} · 모델 {h['model']}")


def require_patient() -> dict:
    if "patient" not in st.session_state:
        st.info("먼저 **환자 목록**에서 환자를 선택하세요.")
        st.stop()
    return st.session_state["patient"]
