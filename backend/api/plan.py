"""처방 초안과 발송. 순서는 sanitize → retrieve → AI → rules.check → 화면."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..ai import draft as ai_draft
from ..core import protocol as core_protocol
from ..core import rules
from ..core.schemas import ExerciseCandidate
from ..lib import db, notify
from ..lib.sanitize import sanitize

router = APIRouter(prefix="/api/plan", tags=["plan"])


class DraftRequest(BaseModel):
    patient_id: str


class SendRequest(BaseModel):
    patient_id: str
    exercises: list[ExerciseCandidate]
    elapsed_seconds: float | None = None


def _context(patient_id: str):
    patient = db.get_patient(patient_id)
    if patient is None:
        raise HTTPException(404, "환자를 찾을 수 없습니다")

    protocol = db.get_protocol(f"hosp_{patient_id}") or db.get_protocol(patient.protocol_id)
    if protocol is None:
        raise HTTPException(409, "프로토콜이 없습니다. 먼저 프로토콜을 등록하세요")

    slot = core_protocol.slot_for(protocol, patient)
    if slot is None:
        raise HTTPException(409, "해당 주차의 프로토콜 단계가 없습니다 — 확인 필요")
    return patient, protocol, slot


@router.post("/draft")
def draft_plan(body: DraftRequest) -> dict:
    patient, protocol, slot = _context(body.patient_id)

    clean = sanitize(patient)                       # ① PII 제거
    candidates, evidence = ai_draft.draft(clean, slot)   # ② 검색 + AI 제안
    result = rules.check(candidates, slot, patient)      # ③ 규칙 검사

    return {
        "draft": result.model_dump(mode="json"),
        "slot": slot.model_dump(mode="json"),
        "protocol": {"id": protocol.id, "origin": protocol.origin,
                     "reviewed_by": protocol.reviewed_by, "version": protocol.version},
        "evidence": evidence,
        "llm_input": clean,                         # 화면에서 "AI에 넘어간 것"을 그대로 보여준다
        "weeks_since_surgery": clean["weeks_since_surgery"],
    }


@router.post("/send")
def send_plan(body: SendRequest) -> dict:
    patient, _, slot = _context(body.patient_id)

    # 화면에서 온 목록이라도 한 번 더 규칙을 통과시킨다 (절대 규칙 2)
    checked = rules.check(body.exercises, slot, patient)
    exercises = [c.model_dump(mode="json") for c in checked.passed]

    db.save_plan(patient.id, date.today(), exercises, sent=True)
    message = notify.send_kakao(db.patient_name(patient.id), patient.token, exercises)

    return {
        "kakao": message,
        "count": len(exercises),
        "elapsed_seconds": body.elapsed_seconds,
        "adjusted_on_send": checked.adjusted,
        "excluded_on_send": checked.excluded,
    }
