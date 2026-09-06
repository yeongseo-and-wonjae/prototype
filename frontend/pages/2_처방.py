"""추천 → 담기 → 세트 평가 → 적용(카카오톡). 세팅~발송 60초가 목표.

담기/빼기는 fragment 안에서 처리한다 — 한 번 누를 때마다 화면 전체가
다시 그려지지 않게. 초안은 화면에 들어오면 알아서 만든다.
"""

from __future__ import annotations

import time

import streamlit as st

import ui

ui.setup("처방")
patient = ui.require_patient()

st.title("오늘의 처방")
ui.steps("처방")
ui.patient_header(patient)

# 화면에 들어오면 초안을 알아서 만든다 (환자가 바뀌면 다시)
if st.session_state.get("draft_for") != patient["id"]:
    st.session_state.pop("sent", None)
    st.session_state["started_at"] = time.time()
    with st.spinner("sanitize → 검색 → AI → 규칙 검사"):
        st.session_state["draft"] = ui.api("POST", "/api/plan/draft",
                                           json={"patient_id": patient["id"]})
    st.session_state["draft_for"] = patient["id"]
    # 백지에서 시작하지 않게 — 규칙을 통과하고 '확인 필요'가 아닌 것은 미리 담아 둔다
    st.session_state["cart"] = [
        c["name"] for c in st.session_state["draft"]["draft"]["passed"] if not c.get("note")
    ]

data = st.session_state["draft"]
draft, slot, meta = data["draft"], data["slot"], data["protocol"]

badge = f'{meta["reviewed_by"]} 확인' if meta["reviewed_by"] else "⚠️ 미확정 프로토콜"
head, redo = st.columns([4, 1])
with head:
    st.markdown(
        ui.tag(f'수술 후 {data["weeks_since_surgery"]}주', "on")
        + ui.tag(f'{draft["phase"]}단계', "on")
        + ui.tag(f'{meta["origin"]} v{meta["version"]}')
        + ui.tag(badge, "" if meta["reviewed_by"] else "warn")
        + (ui.tag("적신호", "bad") if draft["red_flag"] else ""),
        unsafe_allow_html=True)
with redo:
    if st.button("초안 다시 만들기", use_container_width=True):
        st.session_state.pop("draft_for", None)
        st.rerun()

if draft["red_flag"]:
    st.error("통증 7 이상 + 부종 — 규칙이 전체 세트를 1회 줄였습니다. 발송 전에 상태를 직접 확인하세요.")


@st.fragment
def cart_and_review() -> None:
    """담기/빼기와 세트 평가. 이 안에서만 다시 그려진다."""
    cart_names = st.session_state.setdefault("cart", [])
    by_name = {c["name"]: c for c in draft["passed"]}
    cart = [by_name[n] for n in cart_names if n in by_name]

    review = ui.api("POST", "/api/plan/review",
                    json={"patient_id": patient["id"], "exercises": cart})["review"]

    left, right = st.columns([1.25, 1], gap="large")

    with left:
        head, bulk = st.columns([3, 2])
        with head:
            ui.section("추천 운동", len(draft["passed"]))
        with bulk:
            a, b = st.columns(2)
            if a.button("모두 담기", use_container_width=True):
                st.session_state["cart"] = [c["name"] for c in draft["passed"]]
                st.rerun(scope="fragment")
            if b.button("비우기", use_container_width=True):
                st.session_state["cart"] = []
                st.rerun(scope="fragment")

        for i, ex in enumerate(draft["passed"]):
            picked = ex["name"] in cart_names
            rom = f' · {ex["rom"]}°까지' if ex["rom"] else ""
            chips = ui.tag(ex["type"]) + ui.tag(f'출처 {ex["source"]}')
            chips += ui.tag("영상", "on") if ex.get("video_url") else ui.tag("영상 없음")
            if ex.get("note"):
                chips += ui.tag(ex["note"], "warn")

            body, action = st.columns([4, 1])
            with body:
                ui.card(
                    f'<b style="font-size:1.02rem">{ex["name"]}</b>'
                    f'<span class="rt-sub">{rom} · {ex["dose"]} · {ex["minutes"]}분</span>'
                    f'<div style="margin-top:5px">{chips}</div>'
                    f'<div class="rt-sub" style="margin-top:3px">{ex["patient_desc"]}</div>',
                    "ok" if picked else "flat")
            with action:
                if picked:
                    if st.button("빼기", key=f"rm{i}", use_container_width=True):
                        st.session_state["cart"] = [n for n in cart_names if n != ex["name"]]
                        st.rerun(scope="fragment")
                elif st.button("담기", key=f"add{i}", type="primary", use_container_width=True):
                    st.session_state["cart"] = cart_names + [ex["name"]]
                    st.rerun(scope="fragment")

    with right:
        ui.section("담은 운동", review["count"])
        if not cart:
            st.caption("왼쪽에서 **담기**를 눌러 오늘 보낼 운동을 고르세요.")
        for ex in cart:
            st.markdown(
                f'<div class="rt-card rt-ok" style="padding:8px 12px;margin-bottom:6px">'
                f'<b>{ex["name"]}</b> <span class="rt-sub">· {ex["dose"]} · {ex["minutes"]}분</span>'
                f'{"" if ex.get("video_url") else " " + ui.tag("영상 없음")}</div>',
                unsafe_allow_html=True)

        ui.section("세트 전체 평가")
        ui.stats([
            ("판정", "발송 가능" if review["ok"] else "발송 불가", "safe" if review["ok"] else "alert"),
            ("운동", review["count"], "ink"),
            ("하루", f'{review["total_minutes"]}분', "ink"),
        ])
        if review["coverage"]:
            st.markdown("".join(ui.tag(f'{k} {"✓" if v else "—"}', "on" if v else "warn")
                                for k, v in review["coverage"].items()), unsafe_allow_html=True)

        style = {"막음": "cut", "주의": "adj", "정보": "flat"}
        for issue in review["issues"]:
            ui.card(f'<b>{issue["level"]}</b> · {issue["message"]}<br>'
                    f'<span class="rt-rule{" warn" if issue["level"] == "주의" else ""}">'
                    f'{issue["rule_id"]}</span>', style.get(issue["level"], "flat"))
        if not review["issues"]:
            st.caption("걸린 항목이 없습니다.")

        st.write("")
        elapsed = time.time() - st.session_state.get("started_at", time.time())
        if st.button(f'적용하기 — 카카오톡으로 보내기 ({review["count"]}개)',
                     type="primary", disabled=not review["ok"], use_container_width=True):
            st.session_state["sent"] = ui.api(
                "POST", "/api/plan/send",
                json={"patient_id": patient["id"], "exercises": cart,
                      "elapsed_seconds": round(elapsed, 1)})
            st.rerun(scope="app")
        st.markdown(ui.tag(f"초안 후 {elapsed:.0f}초 경과 · 목표 60초",
                           "on" if elapsed <= 60 else "warn"), unsafe_allow_html=True)
        if not review["ok"]:
            st.caption("세트 평가에 **막음**이 있어 보낼 수 없습니다. 위 항목을 빼주세요.")


if "sent" not in st.session_state:
    cart_and_review()

    with st.expander("규칙이 이미 걸러낸 것 "
                     f'({len(draft["excluded"]) + len(draft["adjusted"])})'):
        for cut in draft["excluded"]:
            ui.card(f'<b>✕ {cut["candidate"]["name"]}</b> — {cut["cut_reason"]}<br>'
                    f'<span class="rt-rule">{cut["rule_id"]}</span>', "cut")
        for adj in draft["adjusted"]:
            ui.card(f'<b>⤳ {adj["candidate"]["name"]}</b> — {adj["before"]} → '
                    f'<b>{adj["after"]}</b><br>'
                    f'<span class="rt-rule warn">{adj["rule_id"]}</span>', "adj")
        if not draft["excluded"] and not draft["adjusted"]:
            st.caption("걸린 항목이 없습니다.")

    with st.expander(f'{draft["phase"]}단계 제한 · AI 입력 · 검색 근거'):
        st.markdown(f'**보조기** {slot["brace"] or "—"}\n\n'
                    f'**금지** {", ".join(slot["forbidden"]) or "—"}\n\n**각도 상한** '
                    + (", ".join(f"{k} {v}°" for k, v in slot["rom_caps"].items()) or "—"))
        st.markdown("**AI에 넘어간 정보** (식별정보 없음)")
        st.json(data["llm_input"], expanded=False)
        st.markdown(f'**검색된 근거 {len(data["evidence"])}건**')
        for e in data["evidence"]:
            st.markdown(f"- `{e['kind']}` ({e['source']}) {e['text']}")

else:
    sent = st.session_state["sent"]
    took = sent["elapsed_seconds"] or 0
    (st.success if took <= 60 else st.warning)(
        f'{sent["count"]}개 전송 · 세팅~발송 **{took:.0f}초**'
        + ("" if took <= 60 else " (목표 60초 초과)"))

    preview, side = st.columns([1.6, 1])
    with preview:
        st.markdown("**알림톡 미리보기**")
        st.code(sent["kakao"]["preview"], language=None)
    with side:
        st.markdown("**환자 화면**")
        st.link_button("환자가 보는 화면 열기 ↗", sent["kakao"]["link"], use_container_width=True)
        st.caption("데모라 실제로 발송하지 않습니다.")
        st.write("")
        if st.button("인박스로 →", type="primary", use_container_width=True):
            st.session_state.pop("inbox", None)
            ui.go("pages/3_인박스.py")
        if st.button("다음 환자 보기", use_container_width=True):
            for stale in ("draft", "draft_for", "sent", "cart", "protocol", "protocol_photo"):
                st.session_state.pop(stale, None)
            ui.go("환자_목록.py")

ui.footer()
