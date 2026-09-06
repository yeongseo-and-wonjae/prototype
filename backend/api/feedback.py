"""환자 기록. 토큰으로만 접근한다."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import rules
from ..core.schemas import Feedback, InboxItem, RomSelf
from ..lib import db

router = APIRouter(prefix="/api", tags=["feedback"])


class FeedbackRequest(BaseModel):
    token: str
    completed: list[str] = []
    pain: int = 0
    rom_self: RomSelf | None = None
    note: str | None = None


@router.post("/feedback")
def record(body: FeedbackRequest) -> dict:
    patient = db.get_patient_by_token(body.token)
    if patient is None:
        raise HTTPException(404, "잘못된 링크입니다")

    fb = Feedback(patient_id=patient.id, date=date.today(), completed=body.completed,
                  pain=body.pain, rom_self=body.rom_self, note=body.note)
    db.save_feedback(fb)

    reasons = rules.red_flag_reasons(body.note or "")
    if reasons:                                  # 적신호는 치료사 인박스로 올린다
        db.save_inbox(InboxItem(
            id=f"rf-{patient.id}-{date.today().isoformat()}",
            patient_id=patient.id, origin="적신호",
            summary=f"환자 메모: {body.note}",
            related_limits=reasons,
            recent=f"통증 {body.pain}, 완료 {len(body.completed)}개",
        ))

    return {"saved": True, "red_flag": bool(reasons), "reasons": reasons}
