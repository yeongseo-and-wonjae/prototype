"""추천 → 담기 → 세트 평가 → 적용(카카오톡). 세팅~발송 60초가 목표."""

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
    # 백지에서 시작하지 않게 — 규칙을 통과하고 '확인 필요'가 아닌 것은 미리 담아 둔다
    st.session_state["cart"] = [
        c["name"] for c in st.session_state["draft"]["draft"]["passed"] if not c.get("note")
    ]

if "draft" not in st.session_state:
    st.info("**AI 초안 만들기**를 누르면 이 환자의 단계에 맞는 후보를 만들고 규칙으로 검증합니다.")
    ui.footer()
    st.stop()

data = st.session_state["draft"]
draft, slot, meta = data["draft"], data["slot"], data["protocol"]
cart_names = st.session_state.setdefault("cart", [])
by_name = {c["name"]: c for c in draft["passed"]}
cart = [by_name[n] for n in cart_names if n in by_name]

review = ui.api("POST", "/api/plan/review",
                json={"patient_id": patient["id"], "exercises": cart})["review"]

badge = f'{meta["reviewed_by"]} 확인' if meta["reviewed_by"] else "⚠️ 미확정 프로토콜"
st.markdown(
    ui.tag(f'수술 후 {data["weeks_since_surgery"]}주', "on")
    + ui.tag(f'{draft["phase"]}단계', "on")
    + ui.tag(f'{meta["origin"]} v{meta["version"]}')
    + ui.tag(badge, "" if meta["reviewed_by"] else "warn")
    + (ui.tag("적신호", "bad") if draft["red_flag"] else ""),
    unsafe_allow_html=True)

if draft["red_flag"]:
    st.error("통증 7 이상 + 부종 — 규칙이 전체 세트를 1회 줄였습니다. 발송 전에 상태를 직접 확인하세요.")

left, right = st.columns([1.25, 1], gap="large")

# ── 왼쪽: 추천 후보 ────────────────────────────────────────
with left:
    ui.section("추천 운동", len(draft["passed"]))
    for i, ex in enumerate(draft["passed"]):
        picked = ex["name"] in cart_names
        rom = f" · {ex['rom']}°까지" if ex["rom"] else ""
        chips = ui.tag(ex["type"]) + ui.tag(ex["grade"]) + ui.tag(f"출처 {ex['source']}")
        chips += ui.tag("영상 있음", "on") if ex.get("video_url") else ui.tag("영상 없음")
        if ex.get("note"):
            chips += ui.tag(ex["note"], "warn")

        body, action = st.columns([4, 1])
        with body:
            ui.card(
                f'<b style="font-size:1.02rem">{ex["name"]}</b>'
                f'<span class="rt-sub">{rom} · {ex["dose"]} · {ex["minutes"]}분</span><br>'
                f'<div style="margin-top:6px">{chips}</div>'
                f'<div class="rt-sub" style="margin-top:4px">{ex["reason"]} · '
                f'환자용: {ex["patient_desc"]}</div>',
                "ok" if picked else "flat")
        with action:
            if picked:
                if st.button("빼기", key=f"rm{i}", use_container_width=True):
                    st.session_state["cart"] = [n for n in cart_names if n != ex["name"]]
                    st.rerun()
            elif st.button("담기", key=f"add{i}", type="primary", use_container_width=True):
                st.session_state["cart"] = cart_names + [ex["name"]]
                st.rerun()

    if draft["excluded"] or draft["adjusted"]:
        ui.section("규칙이 이미 걸러낸 것", len(draft["excluded"]) + len(draft["adjusted"]))
        for cut in draft["excluded"]:
            ui.card(f'<b>✕ {cut["candidate"]["name"]}</b> — {cut["cut_reason"]}<br>'
                    f'<span class="rt-rule">{cut["rule_id"]}</span>', "cut")
        for adj in draft["adjusted"]:
            ui.card(f'<b>⤳ {adj["candidate"]["name"]}</b> — {adj["before"]} → '
                    f'<b>{adj["after"]}</b><br>'
                    f'<span class="rt-rule warn">{adj["rule_id"]}</span>', "adj")

# ── 오른쪽: 담긴 세트 + 전체 평가 ───────────────────────────
with right:
    ui.section("담은 운동", review["count"])
    if not cart:
        st.caption("왼쪽에서 **담기**를 눌러 오늘 보낼 운동을 고르세요.")
    for ex in cart:
        st.markdown(
            f'<div class="rt-card rt-ok" style="padding:9px 13px">'
            f'<b>{ex["name"]}</b> <span class="rt-sub">· {ex["dose"]} · {ex["minutes"]}분</span>'
            f'{"" if ex.get("video_url") else " " + ui.tag("영상 없음")}</div>',
            unsafe_allow_html=True)

    ui.section("세트 전체 평가")
    grade = "발송 가능" if review["ok"] else "발송 불가"
    ui.stats([
        ("판정", grade, "safe" if review["ok"] else "alert"),
        ("운동", review["count"], "ink"),
        ("하루", f'{review["total_minutes"]}분', "ink"),
    ])
    if review["coverage"]:
        st.markdown(
            "".join(ui.tag(f'{k} {"✓" if v else "—"}', "on" if v else "warn")
                    for k, v in review["coverage"].items()),
            unsafe_allow_html=True)

    style = {"막음": "cut", "주의": "adj", "정보": "flat"}
    for issue in review["issues"]:
        ui.card(f'<b>{issue["level"]}</b> · {issue["message"]}<br>'
                f'<span class="rt-rule{" warn" if issue["level"] == "주의" else ""}">'
                f'{issue["rule_id"]}</span>',
                style.get(issue["level"], "flat"))
    if not review["issues"]:
        st.caption("걸린 항목이 없습니다.")

    with st.expander(f'{draft["phase"]}단계 제한'):
        st.markdown(f'**보조기** {slot["brace"] or "—"}\n\n'
                    f'**금지** {", ".join(slot["forbidden"]) or "—"}\n\n**각도 상한** '
                    + (", ".join(f"{k} {v}°" for k, v in slot["rom_caps"].items()) or "—"))
    with st.expander("AI에 넘어간 정보 (식별정보 없음)"):
        st.json(data["llm_input"])
    with st.expander(f'검색된 근거 {len(data["evidence"])}건'):
        for e in data["evidence"]:
            st.markdown(f"- `{e['kind']}` ({e['source']}) {e['text']}")

st.divider()
elapsed = time.time() - st.session_state.get("started_at", time.time())
act, timer = st.columns([1, 2])
with act:
    send = st.button(f'적용하기 — 카카오톡으로 보내기 ({review["count"]}개)',
                     type="primary", disabled=not review["ok"], use_container_width=True)
with timer:
    st.markdown(ui.tag(f"초안 후 {elapsed:.0f}초 경과 · 목표 60초",
                       "on" if elapsed <= 60 else "warn"), unsafe_allow_html=True)
    if not review["ok"]:
        st.caption("세트 평가에서 **막음**이 있어 보낼 수 없습니다. 위 항목을 빼주세요.")

if send:
    st.session_state["sent"] = ui.api(
        "POST", "/api/plan/send",
        json={"patient_id": patient["id"], "exercises": cart,
              "elapsed_seconds": round(elapsed, 1)})

if "sent" in st.session_state:
    sent = st.session_state["sent"]
    took = sent["elapsed_seconds"] or 0
    (st.success if took <= 60 else st.warning)(
        f'{sent["count"]}개 전송 · 세팅~발송 **{took:.0f}초**'
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
