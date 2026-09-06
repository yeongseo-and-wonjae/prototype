"""프로토콜 사진 → 6칸 확인. 사진 옆에서 대조하고 고친 뒤 '맞음'."""

from __future__ import annotations

import streamlit as st

import ui

ui.setup("프로토콜")
patient = ui.require_patient()
st.title("프로토콜 확인")
st.caption(f"{patient['name']} · {patient['age']}세 · {patient['tear_size']} 파열")

photo = st.file_uploader("병원에서 받아온 프로토콜 사진", type=["png", "jpg", "jpeg", "webp"])

if st.button("AI로 6칸 추출", type="primary", disabled=photo is None):
    with st.spinner("사진에서 단계·기간·보조기·허용·금지·각도상한을 읽는 중"):
        st.session_state["protocol"] = ui.api(
            "POST", "/api/protocol/extract",
            data={"patient_id": patient["id"]},
            files={"image": (photo.name, photo.getvalue(), photo.type)},
        )

if "protocol" not in st.session_state:
    st.info("사진을 올리고 **AI로 6칸 추출**을 누르세요. (키가 없으면 목업 프로토콜이 나옵니다)")
    ui.footer()
    st.stop()

result = st.session_state["protocol"]
protocol = result["protocol"]

left, right = st.columns([1, 1.4])
with left:
    st.subheader("원본 사진")
    if photo:
        st.image(photo, use_container_width=True)
    else:
        st.caption("사진을 다시 올리면 여기 표시됩니다.")
    if result["conflicts"]:
        st.markdown("**표준본과 달라 병원 값을 따른 항목**")
        for c in result["conflicts"]:
            st.markdown(f'<div class="rt-card rt-adj">{c}</div>', unsafe_allow_html=True)

with right:
    st.subheader("추출된 6칸 — 사진과 대조해 고치세요")
    edited = []
    for slot in protocol["slots"]:
        low = slot["confidence"] < 0.7
        label = f"{slot['phase']}단계 ({slot['weeks'][0]}~{slot['weeks'][1]}주)"
        with st.expander(f"{'⚠️ 확인 필요 · ' if low else ''}{label}", expanded=low):
            if slot["source_text"]:
                st.caption(f"원문 근거: {slot['source_text']}")
            brace = st.text_input("보조기", slot["brace"] or "", key=f"b{slot['phase']}",
                                  placeholder="사진에서 읽지 못함 — 직접 입력")
            allowed = st.text_area("허용", "\n".join(slot["allowed"]), key=f"a{slot['phase']}", height=90)
            forbidden = st.text_area("금지", "\n".join(slot["forbidden"]), key=f"f{slot['phase']}", height=90)
            caps = st.text_area("각도 상한 (한 줄에 `동작=각도`)",
                                "\n".join(f"{k}={v}" for k, v in slot["rom_caps"].items()),
                                key=f"c{slot['phase']}", height=80)
            edited.append({
                **slot,
                "brace": brace or None,
                "allowed": [x.strip() for x in allowed.splitlines() if x.strip()],
                "forbidden": [x.strip() for x in forbidden.splitlines() if x.strip()],
                "rom_caps": {k.strip(): int(v) for k, v in
                             (line.split("=", 1) for line in caps.splitlines() if "=" in line)},
                "confidence": 1.0 if (brace or not low) else slot["confidence"],
            })

    reviewer = st.text_input("확인한 치료사", "박지현 PT")
    hospital = st.text_input("병원", protocol.get("hospital") or "OO정형외과")

    if st.button("맞음 — 이 값으로 확정", type="primary", use_container_width=True):
        confirmed = ui.api("PUT", f"/api/protocol/{protocol['id']}",
                           json={"slots": edited, "reviewed_by": reviewer, "hospital": hospital})
        st.session_state["protocol"]["protocol"] = confirmed["protocol"]
        st.success(f"확정되었습니다 (version {confirmed['protocol']['version']}). "
                   "왼쪽 **처방** 화면으로 넘어가세요.")

ui.footer()
