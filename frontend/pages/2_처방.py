"""AI 초안 → 규칙 검증 리포트 → 카카오톡 발송. 세팅~발송 60초가 목표."""

from __future__ import annotations

import time

import streamlit as st

import ui

ui.setup("처방")
patient = ui.require_patient()

st.title("오늘의 처방")
ui.patient_header(patient)

if st.button("AI 초안 만들기", type="primary"):
    st.session_state["started_at"] = time.time()
    st.session_state.pop("sent", None)
    with st.spinner("sanitize → 검색 → AI → 규칙 검사"):
        st.session_state["draft"] = ui.api("POST", "/api/plan/draft",
                                           json={"patient_id": patient["id"]})

if "draft" not in st.session_state:
    st.info("**AI 초안 만들기**를 누르면 이 환자의 단계에 맞는 후보를 만들고 규칙으로 검증합니다.")
    ui.footer()
    st.stop()

data = st.session_state["draft"]
draft, slot, meta = data["draft"], data["slot"], data["protocol"]

review = f'{meta["reviewed_by"]} 확인' if meta["reviewed_by"] else "⚠️ 미확정 프로토콜"
st.markdown(
    ui.tag(f'수술 후 {data["weeks_since_surgery"]}주', "on")
    + ui.tag(f'{draft["phase"]}단계', "on")
    + ui.tag(f'{meta["origin"]} v{meta["version"]}')
    + ui.tag(review, "" if meta["reviewed_by"] else "warn")
    + (ui.tag("적신호", "bad") if draft["red_flag"] else ""),
    unsafe_allow_html=True,
)

if draft["red_flag"]:
    st.error("통증 7 이상 + 부종 — 규칙이 전체 세트를 1회 줄였습니다. 발송 전에 상태를 직접 확인하세요.")

ui.stats([
    ("통과", len(draft["passed"]), "safe"),
    ("제외", len(draft["excluded"]), "alert" if draft["excluded"] else "ink"),
    ("조정", len(draft["adjusted"]), "warn" if draft["adjusted"] else "ink"),
    ("검색 근거", len(data["evidence"]), "ink"),
])

left, right = st.columns([1.35, 1], gap="large")

with left:
    ui.section("보낼 운동 고르기", len(draft["passed"]))
    chosen = []
    for i, ex in enumerate(draft["passed"]):
        rom = f" · {ex['rom']}°까지" if ex["rom"] else ""
        keep = st.checkbox(f"**{ex['name']}**{rom} — {ex['dose']}",
                           value=not ex.get("note"), key=f"ex{i}")
        chips = ui.tag(ex["type"]) + ui.tag(ex["grade"]) + ui.tag(f"출처 {ex['source']}")
        if ex.get("note"):
            chips += ui.tag(ex["note"], "warn")
        ui.card(
            f'{chips}<div class="rt-sub" style="margin-top:4px">'
            f'{ex["reason"]} · 환자용: {ex["patient_desc"]}</div>',
            "ok" if keep else "flat",
        )
        if keep:
            chosen.append(ex)

with right:
    ui.section("규칙이 한 일", len(draft["excluded"]) + len(draft["adjusted"]))
    for cut in draft["excluded"]:
        ui.card(
            f'<b>✕ {cut["candidate"]["name"]}</b><br>{cut["cut_reason"]}<br>'
            f'<span class="rt-rule">{cut["rule_id"]}</span>', "cut")
    for adj in draft["adjusted"]:
        ui.card(
            f'<b>⤳ {adj["candidate"]["name"]}</b><br>'
            f'{adj["before"]} <span class="rt-sub">→</span> <b>{adj["after"]}</b><br>'
            f'<span class="rt-rule warn">{adj["rule_id"]}</span>', "adj")
    if not draft["excluded"] and not draft["adjusted"]:
        st.caption("규칙에 걸린 항목이 없습니다.")

    with st.expander(f"{draft['phase']}단계 제한"):
        st.markdown(
            f'**보조기** {slot["brace"] or "—"}\n\n'
            f'**금지** {", ".join(slot["forbidden"]) or "—"}\n\n'
            f'**각도 상한** ' +
            (", ".join(f"{k} {v}°" for k, v in slot["rom_caps"].items()) or "—"))
    with st.expander("AI에 넘어간 정보 (식별정보 없음)"):
        st.json(data["llm_input"])
    with st.expander(f"검색된 근거 {len(data['evidence'])}건"):
        for e in data["evidence"]:
            st.markdown(f"- `{e['kind']}` ({e['source']}) {e['text']}")

st.divider()
elapsed = time.time() - st.session_state.get("started_at", time.time())
act, timer = st.columns([1, 2])
with act:
    send = st.button(f"카카오톡으로 보내기 ({len(chosen)}개)", type="primary",
                     disabled=not chosen, use_container_width=True)
with timer:
    st.markdown(
        ui.tag(f"초안 후 {elapsed:.0f}초 경과 · 목표 60초", "on" if elapsed <= 60 else "warn"),
        unsafe_allow_html=True)

if send:
    st.session_state["sent"] = ui.api(
        "POST", "/api/plan/send",
        json={"patient_id": patient["id"], "exercises": chosen,
              "elapsed_seconds": round(elapsed, 1)})

if "sent" in st.session_state:
    sent = st.session_state["sent"]
    took = sent["elapsed_seconds"] or 0
    (st.success if took <= 60 else st.warning)(
        f"{sent['count']}개 전송 · 세팅~발송 **{took:.0f}초**"
        + ("" if took <= 60 else " (목표 60초 초과)"))
    preview, link = st.columns([1.6, 1])
    with preview:
        st.markdown("**알림톡 미리보기**")
        st.code(sent["kakao"]["preview"], language=None)
    with link:
        st.markdown("**환자 링크**")
        st.code(sent["kakao"]["link"], language=None)
        st.caption("데모라 실제로 발송하지 않습니다. 링크를 열면 환자 화면이 그대로 보입니다.")

ui.footer()
