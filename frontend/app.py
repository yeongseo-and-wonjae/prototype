"""환자 목록 — 여기서 환자를 골라 다음 화면으로 넘어간다."""

from __future__ import annotations

import streamlit as st

import ui

ui.setup("환자 목록")
st.title("환자 목록")
ui.health_badge()

patients = ui.api("GET", "/api/patients")["patients"]

cols = st.columns(3)
for i, p in enumerate(patients):
    with cols[i % 3]:
        selected = st.session_state.get("patient", {}).get("id") == p["id"]
        st.markdown(
            f'<div class="rt-card {"rt-ok" if selected else ""}">'
            f'<b style="font-size:18px">{p["name"]}</b> · {p["age"]}세<br>'
            f'<span class="rt-tag">{p["tear_size"]} 파열</span>'
            f'<span class="rt-tag">통증 {p["pain"]}</span>'
            f'<span class="rt-tag">{"부종 있음" if p["swelling"] else "부종 없음"}</span><br>'
            f'<span style="color:#5A6B75;font-size:13px">수술일 {p["surgery_date"]}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("이 환자 열기", key=f"open-{p['id']}", use_container_width=True):
            st.session_state["patient"] = p
            for stale in ("draft", "sent", "protocol"):
                st.session_state.pop(stale, None)
            st.rerun()

if "patient" in st.session_state:
    st.success(f"선택됨: **{st.session_state['patient']['name']}** — 왼쪽에서 프로토콜 → 처방 순서로 진행하세요.")

ui.footer()
