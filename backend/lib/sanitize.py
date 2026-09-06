"""모든 AI 호출의 관문.

절대 규칙 3: 환자 식별정보는 LLM에 보내지 않는다.
ai/ 안의 모든 함수는 이 모듈을 거친 입력만 받는다.
"""

from __future__ import annotations

import re
from datetime import date

from ..core.protocol import phase_for, weeks_since
from ..core.schemas import Patient

MASK = "[제거됨]"

#: 자유 텍스트 마스킹 규칙. 넓게 잡는다 — 놓치는 것보다 지나친 편이 낫다.
PII_PATTERNS: list[tuple[str, str]] = [
    (r"01[016-9][-\s.]?\d{3,4}[-\s.]?\d{4}", "[전화]"),
    (r"\d{6}\s?[-–]\s?[1-4]\d{6}", "[주민번호]"),
    (r"(?<!\d)(19|20)\d{2}[.\-/년]\s?\d{1,2}[.\-/월]\s?\d{1,2}\s?일?(?!\d)", "[생년월일]"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[이메일]"),
    (r"\b(?:등록번호|차트번호|환자번호)\s*[:：]?\s*\w+", "[등록번호]"),
    (r"[가-힣]{1,3}(시|도)\s?[가-힣]{1,10}(구|군|시)\s?[가-힣0-9\-]+(로|길|동)\s?\d*", "[주소]"),
    (r"[가-힣]{2,4}\s?(님|씨|환자분|환자)(?=[\s,.은는이가을를의]|$)", "[환자]"),
]


def mask_text(text: str | None) -> str | None:
    """자유 텍스트에서 식별정보를 지운다."""
    if not text:
        return text
    out = text
    for pattern, label in PII_PATTERNS:
        out = re.sub(pattern, label, out)
    return out


def sanitize(patient: Patient, today: date | None = None) -> dict:
    """Patient → LLM에 넘겨도 되는 임상 정보만 남긴 dict.

    이름·전화·생년월일·등록번호·주소는 애초에 담기지 않는다(별도 테이블).
    id·token도 넘기지 않는다 — 재식별 고리를 만들지 않기 위해.
    """
    return {
        "age": patient.age,
        "weeks_since_surgery": weeks_since(patient.surgery_date, today),
        "days_since_surgery": ((today or date.today()) - patient.surgery_date).days,
        "phase": phase_for(patient.surgery_date, today),
        "tear_size": patient.tear_size,
        "pain": patient.pain,
        "swelling": patient.swelling,
        "brace": patient.brace,
        "surgeon_notes": mask_text(patient.surgeon_notes),
    }


FORBIDDEN_KEYS = {"name", "phone", "birth", "rrn", "chart_no", "address", "id", "token", "surgery_date"}


def assert_clean(payload: dict) -> dict:
    """AI 호출 직전 마지막 방어선. 식별 키가 남아 있으면 즉시 실패시킨다."""
    leaked = FORBIDDEN_KEYS & set(payload)
    if leaked:
        raise ValueError(f"PII가 AI 입력에 남아 있습니다: {sorted(leaked)}")
    return payload
