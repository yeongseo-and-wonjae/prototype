"""치료사 화면이 백엔드와 붙어 실제로 렌더링되는지 확인한다.

백엔드(uvicorn)가 REHABTALK_API 주소에 떠 있어야 한다. 없으면 건너뛴다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import requests
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("REHABTALK_API", "http://localhost:8000")
sys.path.insert(0, str(ROOT / "frontend"))


def _backend_up() -> bool:
    try:
        return requests.get(f"{API}/api/health", timeout=2).ok
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not _backend_up(), reason=f"백엔드가 {API}에 없습니다")


def run(path: str) -> AppTest:
    at = AppTest.from_file(str(ROOT / path), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_patient_list_renders():
    at = run("frontend/환자_목록.py")
    assert "환자 목록" in at.title[0].value
    assert len(at.button) >= 3                      # 환자마다 다음 화면으로 가는 버튼


def test_protocol_page_needs_patient():
    at = run("frontend/pages/1_프로토콜.py")
    assert any("환자 목록" in i.value for i in at.info)


def test_plan_page_draft_and_send():
    """화면에 들어오면 초안이 알아서 만들어진다 — 버튼을 누르지 않는다."""
    at = AppTest.from_file(str(ROOT / "frontend/pages/2_처방.py"), default_timeout=180)
    at.session_state["patient"] = requests.get(f"{API}/api/patients").json()["patients"][0]
    at.run()
    assert not at.exception, at.exception

    draft = at.session_state["draft"]["draft"]
    assert draft["passed"], "통과한 운동이 없습니다"
    # 무엇이 걸러지는지는 AI 응답에 따라 달라진다. 규칙 판정 자체는
    # tests/test_rules.py 와 test_api.py 가 목업으로 결정론적으로 검증한다.
    # 여기서는 화면이 검증 결과를 받아 그릴 수 있는 모양인지만 본다.
    for cut in draft["excluded"]:
        assert cut["cut_reason"] and cut["rule_id"]
    for adj in draft["adjusted"]:
        assert adj["before"] and adj["after"] and adj["rule_id"]

    assert at.session_state["cart"], "안전한 항목이 미리 담기지 않았습니다"

    send = next(b for b in at.button if "적용하기" in b.label)
    send.click().run()
    assert not at.exception, at.exception
    assert at.session_state["sent"]["count"] > 0
    assert "리햅톡" in at.session_state["sent"]["kakao"]["preview"]


def test_inbox_page_lists_signals():
    at = run("frontend/pages/3_인박스.py")
    assert at.session_state["inbox"], "인박스가 비었습니다"
    origins = {i["origin"] for i in at.session_state["inbox"]}
    assert "정체 감지" in origins
