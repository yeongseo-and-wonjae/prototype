"""시연 6장면이 API 수준에서 그대로 돌아가는지 확인한다."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.lib import db
from backend.main import app

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_protocol.png"


@pytest.fixture(scope="module")
def client():
    db.init(force=True)
    with TestClient(app) as c:
        yield c


def test_scene1_2_extract_and_confirm(client):
    r = client.post("/api/protocol/extract", data={"patient_id": "p1"},
                    files={"image": ("p.png", io.BytesIO(SAMPLE.read_bytes()), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["needs_review"], "확인 필요 칸이 하나도 없으면 확인 화면이 의미를 잃는다"
    assert all(s["source_text"] for s in body["protocol"]["slots"]), "원문 근거가 없다"

    slots = body["protocol"]["slots"]
    slots[1]["brace"] = "외출 시에만 착용"
    slots[1]["confidence"] = 1.0
    r2 = client.put("/api/protocol/hosp_p1",
                    json={"slots": slots, "reviewed_by": "박지현 PT", "hospital": "OO정형외과"})
    assert r2.json()["protocol"]["reviewed_by"] == "박지현 PT"
    assert r2.json()["protocol"]["version"] == 2


def test_scene3_draft_shows_cuts_with_reasons(client):
    d = client.post("/api/plan/draft", json={"patient_id": "p1"}).json()
    draft = d["draft"]

    assert draft["passed"], "통과한 운동이 없다"
    assert draft["excluded"], "제외 카드가 비면 규칙 층이 보이지 않는다"
    for cut in draft["excluded"]:
        assert cut["cut_reason"] and cut["rule_id"], "제외에는 이유와 rule_id가 붙어야 한다"
    for ex in draft["passed"]:
        assert ex["source"], "모든 추천에 출처가 있어야 한다 (절대 규칙 5)"

    leaked = {"id", "token", "name", "phone", "surgery_date"} & set(d["llm_input"])
    assert not leaked, f"식별정보가 AI 입력에 남았다: {leaked}"


def test_scene4_send_returns_kakao_preview(client):
    draft = client.post("/api/plan/draft", json={"patient_id": "p1"}).json()["draft"]
    r = client.post("/api/plan/send", json={"patient_id": "p1", "exercises": draft["passed"],
                                            "elapsed_seconds": 42.0}).json()
    assert r["count"] == len(draft["passed"])
    assert r["kakao"]["sent"] is False, "데모는 실제로 보내지 않는다"
    assert "리햅톡" in r["kakao"]["preview"] and "/p/" in r["kakao"]["link"]


def test_send_refuses_a_cart_with_forbidden_items(client):
    """치료사가 담은 목록에 금지가 있으면 조용히 빼지 않고 되돌린다."""
    draft = client.post("/api/plan/draft", json={"patient_id": "p1"}).json()["draft"]
    bad = draft["passed"] + [{
        "name": "능동 거상", "type": "능동", "rom": 90, "dose": "3세트 × 10회",
        "minutes": 5, "grade": "참고", "reason": "", "patient_desc": "", "source": "참고",
    }]

    review = client.post("/api/plan/review",
                         json={"patient_id": "p1", "exercises": bad}).json()["review"]
    assert review["ok"] is False

    res = client.post("/api/plan/send", json={"patient_id": "p1", "exercises": bad})
    assert res.status_code == 422, res.text
    assert "능동 거상" in res.json()["detail"]


def test_review_reports_time_and_videos(client):
    draft = client.post("/api/plan/draft", json={"patient_id": "p1"}).json()["draft"]
    review = client.post("/api/plan/review",
                         json={"patient_id": "p1", "exercises": draft["passed"]}).json()["review"]

    assert review["count"] == len(draft["passed"])
    assert review["total_minutes"] > 0
    assert set(review["coverage"]) == {"거상", "외회전"}, review["coverage"]


def test_scene5_patient_page_and_feedback(client):
    page = client.get("/p/tok_kim62")
    assert page.status_code == 200
    assert "지금 하지 말아야 할 것" in page.text
    assert "실제 임상 처방에 사용할 수 없습니다" in page.text, "면책 문구 누락"
    assert client.get("/p/wrong-token").status_code == 404

    ok = client.post("/api/feedback", json={"token": "tok_kim62", "completed": ["진자 운동"],
                                            "pain": 4, "rom_self": "어깨"}).json()
    assert ok["red_flag"] is False

    flag = client.post("/api/feedback", json={"token": "tok_kim62", "pain": 6,
                                              "note": "어깨가 빨갛게 붓고 열이 나요"}).json()
    assert flag["red_flag"] is True and flag["reasons"]


def test_scene6_inbox_and_reply(client):
    items = client.get("/api/inbox").json()["items"]
    by_origin = {i["origin"]: i for i in items}
    assert "정체 감지" in by_origin and "적신호" in by_origin

    stall = by_origin["정체 감지"]
    assert len(stall["drafts"]) >= 2, "조정 후보 2개가 있어야 한다"

    red = by_origin["적신호"]
    assert all(d.get("rule_id") == "GEN-RED-FLAG" for d in red["drafts"]), \
        "적신호에는 AI 용량 조정이 아니라 규칙 안내만 나가야 한다"

    r = client.post(f"/api/inbox/{stall['id']}/reply", json={"text": stall["drafts"][0]["text"]})
    assert r.status_code == 200 and r.json()["replied"]


def test_plan_blocked_without_protocol(client):
    r = client.post("/api/plan/draft", json={"patient_id": "nope"})
    assert r.status_code == 404
