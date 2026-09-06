"""환자 목록 — 여기서 환자를 골라 다음 화면으로 넘어간다."""

from __future__ import annotations

import streamlit as st

import ui

ui.setup("환자 목록")

st.title("환자 목록")
ui.steps("환자")
st.caption("환자를 열면 다음 화면으로 바로 넘어갑니다.")
ui.health_badge()
st.write("")

patients = ui.api("GET", "/api/patients")["patients"]
current = st.session_state.get("patient", {}).get("id")

cols = st.columns(3, gap="medium")
for i, p in enumerate(patients):
    with cols[i % 3]:
        selected = current == p["id"]
        phase = f"{p['phase']}단계" if p["phase"] else "단계 확인 필요"
        chips = [
            ui.tag(f"{p['weeks_since_surgery']}주차 · {phase}", "on" if selected else ""),
            ui.tag(f"{p['tear_size']} 파열"),
            ui.tag(f"통증 {p['pain']}", "bad" if p["pain"] >= 7 else ""),
        ]
        if p["swelling"]:
            chips.append(ui.tag("부종", "bad"))
        if not p["protocol_reviewed_by"]:
            chips.append(ui.tag("프로토콜 미확정", "warn"))

        ui.card(
            f'<b style="font-size:1.12rem">{p["name"]}</b> '
            f'<span class="rt-sub">{p["age"]}세</span>'
            f'<div style="margin-top:8px">{"".join(chips)}</div>'
            f'<div class="rt-sub" style="margin-top:2px">수술일 {p["surgery_date"]}</div>',
            "ok" if selected else "flat",
        )
        # 프로토콜이 이미 확정된 환자는 처방으로 바로 보낸다 — 한 단계 건너뛴다
        target = "pages/2_처방.py" if p["protocol_reviewed_by"] else "pages/1_프로토콜.py"
        label = "처방하기 →" if p["protocol_reviewed_by"] else "프로토콜 확인 →"
        if st.button(label, key=f"open-{p['id']}", use_container_width=True, type="primary"):
            st.session_state["patient"] = p
            for stale in ("draft", "sent", "protocol", "started_at", "inbox", "cart"):
                st.session_state.pop(stale, None)
            ui.go(target)

ui.footer()
