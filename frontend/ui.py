"""화면 공통 — API 호출과 톤. 규칙 검사도 AI 호출도 여기서 하지 않는다.

색은 CLAUDE.md에 정해진 것만 쓴다.
  ink #152530 · safe #0B6355 · warn #9A5B0C · alert #A32A20 · line #D8E0E5
"""

from __future__ import annotations

import os

import requests
import streamlit as st

API = os.getenv("REHABTALK_API", "http://localhost:8000")

INK, SAFE, WARN, ALERT, LINE = "#152530", "#0B6355", "#9A5B0C", "#A32A20", "#D8E0E5"
MUTED, BG = "#5A6B75", "#FBFCFC"

CSS = f"""
<style>
  @import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");

  html, body, [class*="css"], .stMarkdown, .stButton button {{
    font-family: Pretendard, -apple-system, BlinkMacSystemFont,
                 "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  }}
  .block-container {{ padding-top: 2.2rem; max-width: 1280px; }}
  h1 {{ font-size: 1.9rem !important; letter-spacing: -.02em; margin-bottom: .1rem !important; }}
  h2 {{ font-size: 1.15rem !important; letter-spacing: -.01em; }}
  h3 {{ font-size: 1.02rem !important; letter-spacing: -.01em; color: {INK}; }}

  /* ── 환자 머리글 ───────────────────────────────────── */
  .rt-head {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;
              border-bottom:2px solid {LINE}; padding-bottom:12px; margin-bottom:18px; }}
  .rt-head .name {{ font-size:1.55rem; font-weight:700; letter-spacing:-.02em; }}
  .rt-head .meta {{ color:{MUTED}; font-size:.92rem; }}

  /* ── 진행 표시 ────────────────────────────────────── */
  .rt-steps {{ display:flex; align-items:center; gap:6px; margin:-4px 0 18px;
               font-size:.83rem; color:{MUTED}; flex-wrap:wrap; }}
  .rt-steps .s {{ display:inline-flex; align-items:center; gap:6px;
                  padding:4px 12px; border:1px solid {LINE}; border-radius:99px; background:#fff; }}
  .rt-steps .s.now  {{ border-color:{SAFE}; background:#F0F7F5; color:{SAFE}; font-weight:700; }}
  .rt-steps .s.done {{ border-color:#BFDBD4; color:{SAFE}; }}
  .rt-steps .arrow {{ color:{LINE}; }}

  /* ── 카드 ─────────────────────────────────────────── */
  .rt-card {{ border:1px solid {LINE}; border-left:3px solid {LINE}; border-radius:10px;
              padding:12px 15px; margin-bottom:9px; background:#fff; }}
  .rt-card b {{ letter-spacing:-.01em; }}
  .rt-ok   {{ border-left-color:{SAFE};  background:#F5FAF9; }}
  .rt-cut  {{ border-left-color:{ALERT}; background:#FDF6F5; }}
  .rt-adj  {{ border-left-color:{WARN};  background:#FDF9F1; }}
  .rt-flat {{ background:#fff; }}
  .rt-sub  {{ color:{MUTED}; font-size:.86rem; line-height:1.5; }}

  /* ── 칩 ───────────────────────────────────────────── */
  .rt-tag {{ display:inline-block; font-size:.74rem; padding:2px 9px; border-radius:99px;
             border:1px solid {LINE}; color:{MUTED}; margin:0 5px 4px 0; white-space:nowrap;
             background:#fff; }}
  .rt-tag.on   {{ border-color:{SAFE};  color:{SAFE};  background:#F0F7F5; font-weight:600; }}
  .rt-tag.warn {{ border-color:#E4CDA4; color:{WARN};  background:#FDF8EF; font-weight:600; }}
  .rt-tag.bad  {{ border-color:#EBC9C4; color:{ALERT}; background:#FDF3F1; font-weight:600; }}

  .rt-rule {{ font-family: ui-monospace, SFMono-Regular, monospace;
              font-size:.72rem; color:{ALERT}; letter-spacing:-.01em; }}
  .rt-rule.warn {{ color:{WARN}; }}

  /* ── 구간 제목 ────────────────────────────────────── */
  .rt-sec {{ display:flex; align-items:center; gap:9px; margin:6px 0 10px; }}
  .rt-sec .t {{ font-weight:700; font-size:1rem; letter-spacing:-.01em; }}
  .rt-sec .n {{ font-size:.76rem; color:{MUTED}; border:1px solid {LINE};
                border-radius:99px; padding:1px 8px; }}
  .rt-sec .bar {{ flex:1; height:1px; background:{LINE}; }}

  /* ── 요약 바 (화면 맨 위에 붙여 스크롤 없이 결정) ─── */
  .rt-bar {{ display:flex; align-items:center; gap:18px; flex-wrap:wrap;
             border:1px solid {LINE}; border-left:4px solid {SAFE}; border-radius:12px;
             padding:12px 18px; background:#fff; margin-bottom:14px; }}
  .rt-bar.blocked {{ border-left-color:{ALERT}; background:#FDF6F5; }}
  .rt-bar .verdict {{ font-size:1.25rem; font-weight:700; letter-spacing:-.02em; color:{SAFE}; }}
  .rt-bar.blocked .verdict {{ color:{ALERT}; }}
  .rt-bar .num {{ font-size:1.1rem; font-weight:700; }}
  .rt-bar .lbl {{ font-size:.78rem; color:{MUTED}; margin-left:3px; }}
  .rt-bar .sep {{ width:1px; height:26px; background:{LINE}; }}

  /* ── 통계 ─────────────────────────────────────────── */
  .rt-stats {{ display:flex; gap:10px; margin-bottom:14px; flex-wrap:wrap; }}
  .rt-stat {{ flex:1; min-width:96px; border:1px solid {LINE}; border-radius:10px;
              padding:10px 13px; background:#fff; }}
  .rt-stat .v {{ font-size:1.5rem; font-weight:700; line-height:1.15; letter-spacing:-.02em; }}
  .rt-stat .k {{ font-size:.76rem; color:{MUTED}; margin-top:1px; }}

  /* ── 버튼 ─────────────────────────────────────────── */
  .stButton button {{ border-radius:9px; font-weight:600; letter-spacing:-.01em; }}
  .stButton button[kind="primary"] {{ background:{SAFE}; border-color:{SAFE}; }}
  .stButton button[kind="primary"]:hover {{ background:#0A5449; border-color:#0A5449; }}

  div[data-testid="stCheckbox"] {{ margin-bottom:-10px; }}
  div[data-testid="stCheckbox"] label p {{ font-size:1rem; }}
  div[data-testid="stExpander"] details {{ border-color:{LINE}; border-radius:10px; }}

  .rt-foot {{ color:{MUTED}; font-size:.75rem; border-top:1px solid {LINE};
              padding-top:11px; margin-top:34px; line-height:1.55; }}
</style>
"""

DISCLAIMER = (
    '<div class="rt-foot">데모용. 프로토콜 수치와 환자 정보는 구조를 보여주기 위한 예시이며 '
    '<b>실제 임상 처방에 사용할 수 없습니다.</b> 운영 시에는 집도의 프로토콜 원문과 '
    '물리치료사 검증을 거친 값만 사용합니다.</div>'
)


# ─────────────────────────────────────────────────────────────
# 화면 뼈대
# ─────────────────────────────────────────────────────────────

def setup(title: str) -> None:
    st.set_page_config(page_title=f"리햅톡 · {title}", page_icon="🦾", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def footer() -> None:
    st.markdown(DISCLAIMER, unsafe_allow_html=True)


def patient_header(patient: dict, *, extra: list[str] | None = None) -> None:
    """어느 화면에서든 '지금 누구를 보고 있는지'가 같은 자리에 있게 한다."""
    chips = [
        f"{patient['tear_size']} 파열",
        f"통증 {patient['pain']}",
        "부종 있음" if patient["swelling"] else "부종 없음",
        *(extra or []),
    ]
    tags = "".join(
        f'<span class="rt-tag{" bad" if ("부종 있음" in c or "적신호" in c) else ""}">{c}</span>'
        for c in chips
    )
    st.markdown(
        f'<div class="rt-head"><span class="name">{patient["name"]}</span>'
        f'<span class="meta">{patient["age"]}세 · 수술일 {patient["surgery_date"]}</span>'
        f'<span style="flex:1"></span>{tags}</div>',
        unsafe_allow_html=True,
    )


def section(title: str, count: int | None = None) -> None:
    badge = f'<span class="n">{count}</span>' if count is not None else ""
    st.markdown(
        f'<div class="rt-sec"><span class="t">{title}</span>{badge}'
        f'<span class="bar"></span></div>',
        unsafe_allow_html=True,
    )


def stats(items: list[tuple[str, object, str]]) -> None:
    """(라벨, 값, 색) 묶음. 색은 ink/safe/warn/alert 중 하나."""
    palette = {"ink": INK, "safe": SAFE, "warn": WARN, "alert": ALERT}
    cells = "".join(
        f'<div class="rt-stat"><div class="v" style="color:{palette[tone]}">{value}</div>'
        f'<div class="k">{label}</div></div>'
        for label, value, tone in items
    )
    st.markdown(f'<div class="rt-stats">{cells}</div>', unsafe_allow_html=True)


def summary_bar(verdict: str, blocked: bool, items: list[tuple[str, str]],
                chips: str = "") -> None:
    """판정과 숫자를 한 줄로. 결정에 필요한 것만 위에 붙인다."""
    cells = "".join(
        f'<span><span class="num">{value}</span><span class="lbl">{label}</span></span>'
        f'<span class="sep"></span>' for label, value in items)
    st.markdown(
        f'<div class="rt-bar {"blocked" if blocked else ""}">'
        f'<span class="verdict">{verdict}</span><span class="sep"></span>'
        f'{cells}<span>{chips}</span></div>',
        unsafe_allow_html=True)


def card(body: str, tone: str = "flat") -> None:
    st.markdown(f'<div class="rt-card rt-{tone}">{body}</div>', unsafe_allow_html=True)


def tag(text: str, tone: str = "") -> str:
    return f'<span class="rt-tag {tone}">{text}</span>'


STEPS = [("환자", None),
         ("프로토콜", "pages/1_프로토콜.py"),
         ("처방", "pages/2_처방.py"),
         ("인박스", "pages/3_인박스.py")]


def steps(current: str) -> None:
    """지금 어디쯤인지 늘 보이게 한다. 사이드바를 뒤지지 않아도 되도록."""
    index = [name for name, _ in STEPS].index(current)
    cells = []
    for i, (name, _) in enumerate(STEPS):
        cls = "now" if i == index else ("done" if i < index else "")
        cells.append(f'<span class="s {cls}">{i + 1} {name}</span>')
    st.markdown('<div class="rt-steps">'
                + '<span class="arrow">→</span>'.join(cells)
                + '</div>', unsafe_allow_html=True)


def go(page: str) -> None:
    """다음 화면으로 넘긴다."""
    st.switch_page(page)


def weeks_label(weeks) -> str:
    """999는 '끝이 정해지지 않음'을 뜻하는 내부 값이다 — 화면에는 열린 구간으로 쓴다."""
    start, end = weeks[0], weeks[1]
    return f"{start}주~" if end >= 999 else f"{start}~{end}주"


# ─────────────────────────────────────────────────────────────
# 백엔드
# ─────────────────────────────────────────────────────────────

def api(method: str, path: str, **kwargs) -> dict:
    try:
        res = requests.request(method, f"{API}{path}", timeout=180, **kwargs)
    except requests.RequestException as exc:
        st.error(f"백엔드에 연결하지 못했습니다 ({API}).\n\n{exc}")
        st.stop()
    if res.status_code >= 400:
        try:
            detail = res.json().get("detail", res.text)
        except ValueError:
            detail = res.text
        st.error(f"{res.status_code} · {detail}")
        st.stop()
    return res.json()


def health_badge() -> None:
    h = api("GET", "/api/health")
    mode = "실제 AI 호출" if h["ai_mode"] == "live" else "목업 (키 없음)"
    st.markdown(
        tag(f"AI {mode}", "on" if h["ai_mode"] == "live" else "warn")
        + tag(h["model"]) + tag(f"검색 {h['search_embedding']}"),
        unsafe_allow_html=True,
    )


def require_patient() -> dict:
    if "patient" not in st.session_state:
        st.info("먼저 **환자 목록**에서 환자를 선택하세요.")
        st.stop()
    return st.session_state["patient"]
