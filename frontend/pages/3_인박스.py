"""인박스 — 정체 신호·적신호·환자 질문과 AI 조정 후보."""

from __future__ import annotations

import streamlit as st

import ui

ui.setup("인박스")
st.title("인박스")
st.caption("정체 감지·적신호·환자 질문이 모입니다. 최종 결정과 발송은 치료사가 합니다.")

if st.button("새로 고침"):
    st.session_state.pop("inbox", None)

if "inbox" not in st.session_state:
    with st.spinner("신호를 모으고 조정 후보를 만드는 중"):
        st.session_state["inbox"] = ui.api("GET", "/api/inbox")["items"]

items = st.session_state["inbox"]
if not items:
    st.info("새 신호가 없습니다.")
    ui.footer()
    st.stop()

tone = {"적신호": "rt-cut", "정체 감지": "rt-adj", "환자 질문": "rt-card"}

for item in items:
    st.markdown(
        f'<div class="rt-card {tone.get(item["origin"], "")}">'
        f'<span class="rt-tag">{item["origin"]}</span>'
        f'<b>{item["patient_name"]}</b><br>'
        f'<span style="font-size:17px">{item["summary"]}</span><br>'
        f'<span style="color:#5A6B75;font-size:13px">{item["recent"]}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    if item["related_limits"]:
        st.caption("관련 제한 · " + " / ".join(item["related_limits"]))

    if item["reply"]:
        st.success(f"답변 발송됨 · {item['replied_at'][:16].replace('T', ' ')}")
        st.code(item["reply"], language=None)
        st.divider()
        continue

    labels = [d["label"] for d in item["drafts"]]
    if not labels:
        st.caption("조정 후보가 없습니다.")
        st.divider()
        continue

    pick = st.radio("조정 후보", labels, key=f"pick-{item['id']}", label_visibility="collapsed")
    body = next(d["text"] for d in item["drafts"] if d["label"] == pick)
    text = st.text_area("보낼 내용 (수정 가능)", body, key=f"text-{item['id']}", height=110)

    if st.button("이 내용으로 보내기", key=f"send-{item['id']}", type="primary"):
        res = ui.api("POST", f"/api/inbox/{item['id']}/reply", json={"text": text})
        st.success("발송했습니다.")
        st.code(res["kakao"]["preview"], language=None)
        st.session_state.pop("inbox", None)
    st.divider()

ui.footer()
