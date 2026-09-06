"""추천 → 고르기 → 세트 평가 → 적용(카카오톡).

한 화면에 같은 운동이 두 번 나오지 않게 표 하나로 고른다.
판정과 적용 버튼은 맨 위에 붙여 스크롤 없이 결정한다.
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

if st.session_state.get("draft_for") != patient["id"]:
    st.session_state.pop("sent", None)
    st.session_state["started_at"] = time.time()
    with st.spinner("sanitize → 검색 → AI → 규칙 검사"):
        st.session_state["draft"] = ui.api("POST", "/api/plan/draft",
                                           json={"patient_id": patient["id"]})
    st.session_state["draft_for"] = patient["id"]
    st.session_state["cart"] = [
        c["name"] for c in st.session_state["draft"]["draft"]["passed"] if not c.get("note")
    ]

data = st.session_state["draft"]
draft, slot, meta = data["draft"], data["slot"], data["protocol"]

badge = f'{meta["reviewed_by"]} 확인' if meta["reviewed_by"] else "⚠️ 미확정 프로토콜"
info, redo = st.columns([4, 1])
with info:
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
def picker() -> None:
    """고르기 + 판정. 표를 건드릴 때 이 안에서만 다시 그린다."""
    cart_names = st.session_state.setdefault("cart", [])
    by_name = {c["name"]: c for c in draft["passed"]}

    # 판정과 적용 버튼이 표 길이에 밀리지 않게 자리를 먼저 잡아둔다
    verdict_slot = st.container()

    has_note = any(c.get("note") for c in draft["passed"])
    rows = [{
        "보냄": ex["name"] in cart_names,
        "운동": ex["name"],
        "유형": ex["type"],
        "용량": ex["dose"],
        "각도": f'{ex["rom"]}°' if ex["rom"] else "—",
        "분": ex["minutes"],
        "영상": bool(ex.get("video_url")),
        "환자에게 보이는 설명": ex["patient_desc"],
        **({"확인": ex.get("note") or ""} if has_note else {}),
    } for ex in draft["passed"]]

    edited = st.data_editor(
        rows, key="picker_table", hide_index=True, use_container_width=True,
        row_height=44,                                  # 진료 중 빠르게 누르는 화면 — 넓게
        height=min(46 + 44 * len(rows), 480),           # 길어지면 표 안에서 스크롤
        disabled=[c for c in rows[0] if c != "보냄"] if rows else True,
        column_config={
            "보냄": st.column_config.CheckboxColumn("보냄", width="small",
                                                   help="체크한 운동만 환자에게 갑니다"),
            "운동": st.column_config.TextColumn(width="medium"),
            "유형": st.column_config.TextColumn(width="small"),
            "용량": st.column_config.TextColumn(width="medium"),
            "각도": st.column_config.TextColumn(width="small"),
            "분": st.column_config.NumberColumn(width="small", format="%d분"),
            "영상": st.column_config.CheckboxColumn("영상", width="small",
                                                   help="시범 영상이 등록된 운동"),
            "환자에게 보이는 설명": st.column_config.TextColumn(width="large"),
            "확인": st.column_config.TextColumn("확인 필요", width="small"),
        },
    )

    picked = [r["운동"] for r in edited if r["보냄"]]
    if picked != cart_names:
        st.session_state["cart"] = picked
        st.rerun(scope="fragment")

    cart = [by_name[n] for n in picked if n in by_name]
    review = ui.api("POST", "/api/plan/review",
                    json={"patient_id": patient["id"], "exercises": cart})["review"]
    st.session_state["review"] = review

    coverage = "".join(ui.tag(f'{k} {"✓" if v else "—"}', "on" if v else "warn")
                       for k, v in review["coverage"].items())
    elapsed = time.time() - st.session_state.get("started_at", time.time())

    with verdict_slot:                                  # 표 위에 그린다
        ui.summary_bar(
            "발송 가능" if review["ok"] else "발송 불가",
            blocked=not review["ok"],
            items=[("개", review["count"]), ("분", review["total_minutes"]),
                   ("영상 없음", len(review["videos_missing"]))],
            chips=coverage)
        act, note = st.columns([1, 2])
        with act:
            if st.button(f'적용하기 — 카카오톡으로 보내기 ({review["count"]}개)',
                         type="primary", disabled=not review["ok"], use_container_width=True):
                st.session_state["sent"] = ui.api(
                    "POST", "/api/plan/send",
                    json={"patient_id": patient["id"], "exercises": cart,
                          "elapsed_seconds": round(elapsed, 1)})
                st.rerun(scope="app")
        with note:
            st.markdown(ui.tag(f"초안 후 {elapsed:.0f}초 경과 · 목표 60초",
                               "on" if elapsed <= 60 else "warn"), unsafe_allow_html=True)
            if not review["ok"]:
                st.caption("**막음**이 있어 보낼 수 없습니다. 아래에서 해당 운동의 체크를 해제하세요.")

    blocking = [i for i in review["issues"] if i["level"] == "막음"]
    others = [i for i in review["issues"] if i["level"] != "막음"]
    for issue in blocking:
        ui.card(f'<b>막음</b> · {issue["message"]}<br>'
                f'<span class="rt-rule">{issue["rule_id"]}</span>', "cut")
    if others:
        with st.expander(f"주의·정보 {len(others)}건"):
            for issue in others:
                ui.card(f'<b>{issue["level"]}</b> · {issue["message"]}<br>'
                        f'<span class="rt-rule warn">{issue["rule_id"]}</span>',
                        "adj" if issue["level"] == "주의" else "flat")


if "sent" not in st.session_state:
    picker()

    cut_count = len(draft["excluded"]) + len(draft["adjusted"])
    detail, limits = st.columns(2)
    with detail:
        with st.expander(f"규칙이 이미 걸러낸 것 ({cut_count})"):
            for cut in draft["excluded"]:
                ui.card(f'<b>✕ {cut["candidate"]["name"]}</b> — {cut["cut_reason"]}<br>'
                        f'<span class="rt-rule">{cut["rule_id"]}</span>', "cut")
            for adj in draft["adjusted"]:
                ui.card(f'<b>⤳ {adj["candidate"]["name"]}</b> — {adj["before"]} → '
                        f'<b>{adj["after"]}</b><br>'
                        f'<span class="rt-rule warn">{adj["rule_id"]}</span>', "adj")
            if not cut_count:
                st.caption("걸린 항목이 없습니다.")
    with limits:
        with st.expander(f'{draft["phase"]}단계 제한 · AI 입력 · 검색 근거 {len(data["evidence"])}건'):
            st.markdown(f'**보조기** {slot["brace"] or "—"}\n\n'
                        f'**금지** {", ".join(slot["forbidden"]) or "—"}\n\n**각도 상한** '
                        + (", ".join(f"{k} {v}°" for k, v in slot["rom_caps"].items()) or "—"))
            st.markdown("**AI에 넘어간 정보** (식별정보 없음)")
            st.json(data["llm_input"], expanded=False)
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
