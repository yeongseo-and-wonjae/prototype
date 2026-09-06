"""인박스 — 정체 신호·적신호·환자 질문과 조정 후보."""

from __future__ import annotations

import streamlit as st

import ui

ui.setup("인박스")

st.title("인박스")
ui.steps("인박스")
st.caption("정체 감지 · 적신호 · 환자 질문이 모입니다. 최종 결정과 발송은 치료사가 합니다.")

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

order = {"적신호": 0, "정체 감지": 1, "환자 질문": 2}
items = sorted(items, key=lambda i: (order.get(i["origin"], 3), i["patient_id"]))
pending = [i for i in items if not i["reply"]]

ui.stats([
    ("전체", len(items), "ink"),
    ("적신호", sum(i["origin"] == "적신호" for i in items), "alert"),
    ("정체 감지", sum(i["origin"] == "정체 감지" for i in items), "warn"),
    ("답변 대기", len(pending), "safe"),
])

tone = {"적신호": "cut", "정체 감지": "adj", "환자 질문": "flat"}
chip = {"적신호": "bad", "정체 감지": "warn", "환자 질문": ""}

for item in items:
    ui.card(
        ui.tag(item["origin"], chip.get(item["origin"], ""))
        + (ui.tag("2주+ 정체", "warn") if item["stalled"] else "")
        + f'<b style="font-size:1.05rem"> {item["patient_name"]}</b>'
        f'<div style="font-size:1rem;margin-top:5px">{item["summary"]}</div>'
        f'<div class="rt-sub" style="margin-top:3px">{item["recent"]}</div>'
        + (f'<div class="rt-sub" style="margin-top:5px">관련 제한 · '
           f'{" / ".join(item["related_limits"])}</div>' if item["related_limits"] else ""),
        tone.get(item["origin"], "flat"),
    )

    if item["reply"]:
        st.success(f"답변 발송됨 · {item['replied_at'][:16].replace('T', ' ')}")
        st.code(item["reply"], language=None)
        st.write("")
        continue

    labels = [d["label"] for d in item["drafts"]]
    if not labels:
        st.caption("조정 후보가 없습니다.")
        st.write("")
        continue

    pick = st.radio("조정 후보", labels, key=f"pick-{item['id']}", label_visibility="collapsed")
    body = next(d["text"] for d in item["drafts"] if d["label"] == pick)
    chosen = next(d for d in item["drafts"] if d["label"] == pick)
    if chosen.get("rule_id"):
        st.markdown(
            ui.tag(f'규칙이 만든 문구 · {chosen["rule_id"]}', "bad"), unsafe_allow_html=True)

    text = st.text_area("보낼 내용 (수정 가능)", body, key=f"text-{item['id']}", height=112)

    if st.button("이 내용으로 보내기", key=f"send-{item['id']}", type="primary"):
        res = ui.api("POST", f"/api/inbox/{item['id']}/reply", json={"text": text})
        st.success("발송했습니다.")
        st.code(res["kakao"]["preview"], language=None)
        st.session_state.pop("inbox", None)
    st.write("")

ui.footer()
