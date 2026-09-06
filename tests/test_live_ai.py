"""실제 provider(Upstage/Anthropic)를 부르는 테스트.

키가 없으면 통째로 건너뛴다. 호출 비용이 있으므로 최소한만 확인한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.ai import client, draft, extract, retrieve
from backend.core import protocol as core_protocol
from backend.core import rules
from backend.lib import db
from backend.lib.sanitize import sanitize

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_protocol.png"

pytestmark = pytest.mark.skipif(
    not (os.getenv("UPSTAGE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),
    reason="AI 키가 없습니다",
)


@pytest.fixture(autouse=True)
def live(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)   # conftest의 목업 강제를 푼다
    retrieve.reset()
    assert client.is_live(), "키는 있는데 live 판정이 나지 않았습니다"
    yield
    retrieve.reset()


def test_reads_the_real_protocol_photo():
    slots = extract.extract(SAMPLE.read_bytes(), filename="sample_protocol.png")

    phases = {s.phase: s for s in slots}
    assert set(phases) == {1, 2, 3, 4}, f"4단계를 다 읽지 못했습니다: {sorted(phases)}"

    first = phases[1]
    assert first.weeks == (0, 6)
    assert first.rom_caps.get("수동 외회전") == 30, first.rom_caps
    assert any("능동" in f for f in first.forbidden), first.forbidden
    assert first.source_text, "원문 근거가 비었습니다"

    last = phases[4]
    assert last.weeks[1] > last.weeks[0], f"열린 구간 정리 실패: {last.weeks}"
    assert all(0 < v <= extract.MAX_DEGREES for v in last.rom_caps.values()), last.rom_caps


def test_draft_is_checked_by_rules():
    db.init()
    patient = db.get_patient("p1")
    slot = core_protocol.slot_for(db.get_protocol("standard_rc"), patient)

    candidates, evidence = draft.draft(sanitize(patient), slot)
    assert 4 <= len(candidates) <= 12, len(candidates)
    assert all(c.source for c in candidates), "출처 없는 추천이 있습니다 (절대 규칙 5)"
    assert evidence, "검색 근거가 비었습니다"

    result = rules.check(candidates, slot, patient)
    assert result.passed
    for cut in result.excluded:
        assert cut["rule_id"].startswith("RC-P1-")


def test_search_uses_provider_embeddings():
    if client.provider() != "upstage":
        pytest.skip("임베딩은 Upstage에서만 사용합니다")
    assert retrieve.backend_name() == "upstage"
    hits = retrieve.search("1단계에서 외회전을 몇 도까지 허용하나", phase=1, n_results=3)
    assert hits and any("외회전" in h["text"] or "외회전" in h["source"] for h in hits)
