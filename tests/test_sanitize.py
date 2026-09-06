"""절대 규칙 3 — 환자 식별정보는 LLM에 보내지 않는다."""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.schemas import Patient
from backend.lib.sanitize import assert_clean, mask_text, sanitize

TODAY = date(2026, 9, 6)


def test_sanitize_keeps_only_clinical_fields():
    patient = Patient(
        id="p1",
        token="tok_kim62",
        age=62,
        surgery_date=date(2026, 8, 16),
        tear_size="대형",
        pain=4,
    )
    out = sanitize(patient, TODAY)

    assert out["age"] == 62 and out["weeks_since_surgery"] == 3 and out["phase"] == 1
    assert not {"id", "token", "surgery_date"} & set(out)
    assert_clean(out)


def test_mask_text_removes_identifiers():
    raw = "김철수 님 010-1234-5678, 등록번호: A12345, 1964-03-02생, 서울시 강남구 테헤란로 12"
    out = mask_text(raw)

    for leak in ("김철수", "010-1234", "A12345", "1964-03-02", "테헤란로"):
        assert leak not in out, leak


def test_assert_clean_blocks_leak():
    with pytest.raises(ValueError, match="PII"):
        assert_clean({"age": 62, "name": "김철수"})
