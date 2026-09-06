"""프로토콜 사진 → 6칸 확인. 사진 옆에서 대조하고 고친 뒤 '맞음'."""

from __future__ import annotations

import streamlit as st

import ui

ui.setup("프로토콜")
patient = ui.require_patient()

st.title("프로토콜 확인")
ui.steps("프로토콜")
ui.patient_header(patient)

photo = st.file_uploader("병원에서 받아온 프로토콜 사진", type=["png", "jpg", "jpeg", "webp"])

# 사진을 올리면 바로 읽는다 — 버튼을 한 번 더 누르지 않게
if photo is not None and st.session_state.get("protocol_photo") != photo.name:
    with st.spinner("사진에서 단계·기간·보조기·허용·금지·각도상한을 읽는 중"):
        st.session_state["protocol"] = ui.api(
            "POST", "/api/protocol/extract",
            data={"patient_id": patient["id"]},
            files={"image": (photo.name, photo.getvalue(), photo.type)})
    st.session_state["protocol_photo"] = photo.name

if "protocol" not in st.session_state:
    st.info("병원에서 받아온 프로토콜 사진을 올리면 바로 읽습니다. "
            "샘플은 `data/sample_protocol.png` 에 있습니다.")
    if st.button("사진 없이 표준본으로 처방하기 →", use_container_width=False):
        ui.go("pages/2_처방.py")
    ui.footer()
    st.stop()

result = st.session_state["protocol"]
protocol = result["protocol"]
low = [s for s in protocol["slots"] if s["confidence"] < 0.7]

ui.stats([
    ("읽은 단계", len(protocol["slots"]), "safe"),
    ("확인 필요", len(low), "warn" if low else "ink"),
    ("표준본과 차이", len(result["conflicts"]), "ink"),
    ("버전", f'v{protocol["version"]}', "ink"),
])

left, right = st.columns([1, 1.35], gap="large")

with left:
    ui.section("원본 사진")
    if photo:
        st.image(photo, use_container_width=True)
    else:
        st.caption("사진을 다시 올리면 여기 표시됩니다.")

    if result["conflicts"]:
        ui.section("표준본과 다른 점", len(result["conflicts"]))
        st.caption("기간·보조기는 병원 값을 따르고, 금지·상한은 안전한 쪽으로 합칩니다.")
        for c in result["conflicts"][:12]:
            ui.card(c, "adj")
        if len(result["conflicts"]) > 12:
            st.caption(f"… 외 {len(result['conflicts']) - 12}건")

with right:
    ui.section("추출된 6칸 — 사진과 대조해 고치세요", len(protocol["slots"]))
    edited = []
    for slot in protocol["slots"]:
        needs = slot["confidence"] < 0.7
        head = f"{slot['phase']}단계 ({ui.weeks_label(slot['weeks'])})"
        with st.expander(("⚠️ 확인 필요 · " if needs else "") + head, expanded=needs):
            st.markdown(
                ui.tag(f"신뢰도 {slot['confidence']:.2f}", "warn" if needs else "on"),
                unsafe_allow_html=True)
            if slot["source_text"]:
                st.caption(f"원문 근거 · {slot['source_text']}")
            brace = st.text_input("보조기", slot["brace"] or "", key=f"b{slot['phase']}",
                                  placeholder="사진에서 읽지 못함 — 직접 입력")
            c1, c2 = st.columns(2)
            with c1:
                allowed = st.text_area("허용 (한 줄에 하나)", "\n".join(slot["allowed"]),
                                       key=f"a{slot['phase']}", height=112)
            with c2:
                forbidden = st.text_area("금지 (한 줄에 하나)", "\n".join(slot["forbidden"]),
                                         key=f"f{slot['phase']}", height=112)
            caps = st.text_area("각도 상한 (한 줄에 `동작=각도`)",
                                "\n".join(f"{k}={v}" for k, v in slot["rom_caps"].items()),
                                key=f"c{slot['phase']}", height=78)
            edited.append({
                **slot,
                "brace": brace or None,
                "allowed": [x.strip() for x in allowed.splitlines() if x.strip()],
                "forbidden": [x.strip() for x in forbidden.splitlines() if x.strip()],
                "rom_caps": {k.strip(): int(v) for k, v in
                             (line.split("=", 1) for line in caps.splitlines() if "=" in line)},
                "confidence": 1.0 if (brace or not needs) else slot["confidence"],
            })

    st.write("")
    who, where = st.columns(2)
    reviewer = who.text_input("확인한 치료사", "박지현 PT")
    hospital = where.text_input("병원", protocol.get("hospital") or "OO정형외과")

    if st.button("맞음 — 확정하고 처방하기 →", type="primary", use_container_width=True):
        confirmed = ui.api("PUT", f"/api/protocol/{protocol['id']}",
                           json={"slots": edited, "reviewed_by": reviewer, "hospital": hospital})
        st.session_state["protocol"]["protocol"] = confirmed["protocol"]
        st.session_state.pop("draft", None)
        st.session_state.pop("cart", None)
        ui.go("pages/2_처방.py")

ui.footer()
