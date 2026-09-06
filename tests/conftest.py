"""테스트는 기본적으로 목업 AI로 돈다 — 결정론적이고, 무료이고, 오프라인에서도 통과한다.

실제 provider를 부르는 테스트는 tests/test_live_ai.py 하나뿐이며 스스로 이 설정을 푼다.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _force_mock_ai():
    previous = os.environ.get("AI_PROVIDER")
    os.environ["AI_PROVIDER"] = "mock"
    yield
    if previous is None:
        os.environ.pop("AI_PROVIDER", None)
    else:
        os.environ["AI_PROVIDER"] = previous
