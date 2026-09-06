"""정체·질문·적신호 인박스와 치료사 답변."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..ai import adjust as ai_adjust
from ..core import protocol as core_protocol
from ..core import rules
from ..lib import db, notify
from ..lib.sanitize import sanitize

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class ReplyRequest(BaseModel):
    text: str


@router.get("")
def list_inbox() -> dict:
    items = []
    for item in db.list_inbox():
        patient = db.get_patient(item.patient_id)
        if patient is None:
            continue
        protocol = db.get_protocol(f"hosp_{patient.id}") or db.get_protocol(patient.protocol_id)
        slot = core_protocol.slot_for(protocol, patient) if protocol else None

        if not item.drafts and item.reply is None and slot is not None:
            item.drafts = ai_adjust.adjust(
                item.summary, sanitize(patient), slot, db.get_feedback(patient.id)
            )
            db.save_inbox(item)

        items.append({
            **item.model_dump(mode="json"),
            "patient_name": db.patient_name(item.patient_id),
            "stalled": rules.is_stalled(db.get_feedback(patient.id)),
        })
    return {"items": items}


@router.post("/{item_id}/reply")
def reply(item_id: str, body: ReplyRequest) -> dict:
    item = db.get_inbox(item_id)
    if item is None:
        raise HTTPException(404, "인박스 항목을 찾을 수 없습니다")

    patient = db.get_patient(item.patient_id)
    from ..core.schemas import ExerciseCandidate

    plan = db.get_plan(item.patient_id)                 # 발송용 dict
    if not rules.within_plan(body.text, [ExerciseCandidate(**e) for e in plan]):
        raise HTTPException(422, "처방 범위를 벗어난 문장입니다. 내용을 확인해 주세요")

    item.reply = body.text
    item.replied_at = datetime.now()
    db.save_inbox(item)

    message = notify.send_kakao(db.patient_name(patient.id), patient.token, plan)
    message["preview"] = f"[리햅톡] 치료사 답변\n\n{body.text}\n\n{message['link']}"
    return {"replied": True, "kakao": message}
