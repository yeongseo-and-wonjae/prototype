"""AI 초안 → 규칙 검증 리포트 → 카카오톡 발송. 세팅~발송 60초가 목표."""

from __future__ import annotations

import time

import streamlit as st

import ui

ui.setup("처방")
patient = ui.require_patient()
st.title("오늘의 처방")
st.caption(f"{patient['name']} · {patient['age']}세 · {patient['tear_size']} 파열 · 통증 {patient['pain']}")

if st.button("AI 초안 만들기", type="primary"):
    st.session_state["started_at"] = time.time()
    st.session_state.pop("sent", None)
    with st.spinner("sanitize → 검색 → AI → 규칙 검사"):
        st.session_state["draft"] = ui.api("POST", "/api/plan/draft", json={"patient_id": patient["id"]})

if "draft" not in st.session_state:
    st.info("**AI 초안 만들기**를 누르면 이 환자의 단계에 맞는 후보를 만들고 규칙으로 검증합니다.")
    ui.footer()
    st.stop()

data = st.session_state["draft"]
draft, slot = data["draft"], data["slot"]

meta = data["protocol"]
badge = f'{meta["origin"]} v{meta["version"]}' + (
    f' · {meta["reviewed_by"]} 확인' if meta["reviewed_by"] else " · ⚠️ 미확정"
)
st.markdown(
    f'<span class="rt-tag">수술 후 {data["weeks_since_surgery"]}주</span>'
    f'<span class="rt-tag">{draft["phase"]}단계</span>'
    f'<span class="rt-tag">{badge}</span>'
    + ('<span class="rt-tag" style="border-color:#EBC9C4;color:#A32A20">적신호</span>' if draft["red_flag"] else ""),
    unsafe_allow_html=True,
)
if draft["red_flag"]:
    st.error("통증 7 이상 + 부종 — 전체 세트를 1회 줄였습니다. 발송 전에 상태를 직접 확인하세요.")

left, right = st.columns([1.3, 1])

with left:
    st.subheader(f"통과한 운동 {len(draft['passed'])}개")
    chosen = []
    for i, ex in enumerate(draft["passed"]):
        rom = f" · {ex['rom']}°까지" if ex["rom"] else ""
        note = ' <span class="rt-warn">확인 필요</span>' if ex.get("note") else ""
        keep = st.checkbox(
            f"**{ex['name']}**{rom} · {ex['dose']}", value=not ex.get("note"), key=f"ex{i}"
        )
        st.markdown(
            f'<div class="rt-card rt-ok" style="margin-top:-6px">'
            f'<span class="rt-tag">{ex["type"]}</span><span class="rt-tag">{ex["grade"]}</span>'
            f'<span class="rt-tag">출처: {ex["source"]}</span>{note}<br>'
            f'<span style="color:#5A6B75;font-size:13px">{ex["reason"]} — 환자용: {ex["patient_desc"]}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if keep:
            chosen.append(ex)

with right:
    st.subheader("검증 리포트")
    for cut in draft["excluded"]:
        st.markdown(
            f'<div class="rt-card rt-cut"><b>✕ {cut["candidate"]["name"]}</b><br>'
            f'{cut["cut_reason"]}<br><span class="rt-rule">{cut["rule_id"]}</span></div>',
            unsafe_allow_html=True,
        )
    for adj in draft["adjusted"]:
        st.markdown(
            f'<div class="rt-card rt-adj"><b>⤳ {adj["candidate"]["name"]}</b><br>'
            f'{adj["before"]} → {adj["after"]}<br><span class="rt-rule">{adj["rule_id"]}</span></div>',
            unsafe_allow_html=True,
        )
    if not draft["excluded"] and not draft["adjusted"]:
        st.caption("규칙에 걸린 항목이 없습니다.")

    with st.expander("AI에 넘어간 정보 (식별정보 없음)"):
        st.json(data["llm_input"])
    with st.expander(f"검색된 근거 {len(data['evidence'])}건"):
        for e in data["evidence"]:
            st.markdown(f"- `{e['kind']}` ({e['source']}) {e['text']}")

st.divider()
elapsed = time.time() - st.session_state.get("started_at", time.time())
c1, c2 = st.columns([1, 2])
with c1:
    send = st.button(f"카카오톡으로 보내기 ({len(chosen)}개)", type="primary",
                     disabled=not chosen, use_container_width=True)
with c2:
    st.caption(f"초안 생성 후 {elapsed:.0f}초 경과 · 목표 60초 이내")

if send:
    st.session_state["sent"] = ui.api(
        "POST", "/api/plan/send",
        json={"patient_id": patient["id"], "exercises": chosen, "elapsed_seconds": round(elapsed, 1)},
    )

if "sent" in st.session_state:
    sent = st.session_state["sent"]
    took = sent["elapsed_seconds"] or 0
    (st.success if took <= 60 else st.warning)(
        f"{sent['count']}개 전송 · 세팅~발송 {took:.0f}초"
        + ("" if took <= 60 else " (목표 60초 초과)")
    )
    st.markdown("**알림톡 미리보기**")
    st.code(sent["kakao"]["preview"], language=None)
    st.caption(f"환자 링크: {sent['kakao']['link']}  ·  실제 발송은 하지 않습니다(데모)")

ui.footer()
