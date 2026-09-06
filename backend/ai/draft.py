"""환자 상태 + 프로토콜 + 검색 결과 → 운동 후보. LLM 호출은 여기서만.

이 층은 '넓게 제안'하고, 안전 판정은 core/rules.py가 한다.
목업도 일부러 금지 항목을 섞어 넣는다 — 규칙 층이 실제로 걸러내는 것을 보여주기 위함.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core.schemas import ExerciseCandidate, ProtocolSlot
from . import client, retrieve

DATA = Path(__file__).resolve().parents[2] / "data"
LIBRARY = json.loads((DATA / "exercises.json").read_text(encoding="utf-8"))["exercises"]

SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["수동", "능동보조", "능동", "저항", "등척성"]},
                    "rom": {"type": ["integer", "null"]},
                    "dose": {"type": "string"},
                    "minutes": {"type": "integer"},
                    "grade": {"type": "string", "enum": ["표준", "권장", "참고"]},
                    "reason": {"type": "string"},
                    "patient_desc": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["name", "type", "rom", "dose", "minutes", "grade",
                             "reason", "patient_desc", "source"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


def draft(clean_patient: dict, slot: ProtocolSlot) -> tuple[list[ExerciseCandidate], list[dict]]:
    """(후보, 검색근거)를 돌려준다. clean_patient는 sanitize를 거친 dict여야 한다."""
    from ..lib.sanitize import assert_clean

    assert_clean(clean_patient)
    evidence = retrieve.search(
        f"{slot.phase}단계 허용 운동, 각도 상한, {clean_patient['tear_size']} 파열", slot.phase
    )

    if not client.is_live():
        return _mock(clean_patient, slot), evidence

    system = client.prompt(
        "draft",
        patient=json.dumps(clean_patient, ensure_ascii=False, default=str),
        slot=slot.model_dump_json(),
        evidence="\n".join(f"- ({e['source']}) {e['text']}" for e in evidence) or "검색 결과 없음",
        library=json.dumps(
            [{k: e[k] for k in ("name", "type", "rom", "dose", "minutes", "patient_desc", "source")}
             for e in LIBRARY if e["phase"] <= slot.phase + 1],
            ensure_ascii=False,
        ),
    )
    raw = client.ask_json(system, "오늘 시행할 운동 후보를 제안하세요.", SCHEMA)
    return [ExerciseCandidate(**c) for c in raw["candidates"]], evidence


def _mock(clean_patient: dict, slot: ProtocolSlot) -> list[ExerciseCandidate]:
    """단계를 무시하고 한 단계 위까지 제안한다 — 규칙 층이 걸러낼 거리를 남긴다."""
    current = [e for e in LIBRARY if e["phase"] <= slot.phase][:5]
    ahead = [e for e in LIBRARY if e["phase"] == slot.phase + 1][:3]
    reasons = {
        1: "1단계 보호 범위 안",
        2: "가동범위 회복 단계",
        3: "근력 회복 시작",
        4: "기능 복귀 준비",
    }
    out = []
    for e in current + ahead:
        out.append(ExerciseCandidate(
            name=e["name"], type=e["type"], rom=e["rom"], dose=e["dose"], minutes=e["minutes"],
            grade="표준" if e["phase"] <= slot.phase else "참고",
            reason=f"{reasons.get(e['phase'], '')} ({clean_patient['weeks_since_surgery']}주차)"[:25],
            patient_desc=e["patient_desc"], source=e["source"],
        ))
    return out
