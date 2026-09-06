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
    at = run("frontend/app.py")
    assert "환자 목록" in at.title[0].value
    assert len(at.button) >= 3                      # 환자마다 '열기' 버튼


def test_protocol_page_needs_patient():
    at = run("frontend/pages/1_프로토콜.py")
    assert any("환자 목록" in i.value for i in at.info)


def test_plan_page_draft_and_send():
    at = AppTest.from_file(str(ROOT / "frontend/pages/2_처방.py"), default_timeout=120)
    at.session_state["patient"] = requests.get(f"{API}/api/patients").json()["patients"][0]
    at.run()
    assert not at.exception, at.exception

    at.button[0].click().run()                      # AI 초안 만들기
    assert not at.exception, at.exception
    assert at.session_state["draft"]["draft"]["passed"], "통과한 운동이 없습니다"
    assert at.session_state["draft"]["draft"]["excluded"], "규칙이 걸러낸 항목이 없습니다"

    send = next(b for b in at.button if "카카오톡" in b.label)
    send.click().run()
    assert not at.exception, at.exception
    assert at.session_state["sent"]["count"] > 0
    assert "리햅톡" in at.session_state["sent"]["kakao"]["preview"]


def test_inbox_page_lists_signals():
    at = run("frontend/pages/3_인박스.py")
    assert at.session_state["inbox"], "인박스가 비었습니다"
    origins = {i["origin"] for i in at.session_state["inbox"]}
    assert "정체 감지" in origins
