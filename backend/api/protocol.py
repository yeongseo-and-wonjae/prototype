"""사진 → 6칸 추출, 치료사 확인."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..ai import extract as ai_extract
from ..core.protocol import merge
from ..core.schemas import Protocol, ProtocolSlot
from ..lib import db

router = APIRouter(prefix="/api/protocol", tags=["protocol"])


class ConfirmRequest(BaseModel):
    slots: list[ProtocolSlot]
    reviewed_by: str
    hospital: str | None = None


@router.post("/extract")
async def extract_protocol(patient_id: str = Form(...), image: UploadFile = File(...)) -> dict:
    """사진을 읽어 6칸을 채운 미확정 프로토콜을 만든다. 확정 전에는 처방에 쓰지 않는다."""
    slots = ai_extract.extract(await image.read(), image.content_type or "image/png")

    standard = db.get_protocol("standard_rc")
    hospital = Protocol(id=f"hosp_{patient_id}", origin="병원", slots=slots)
    merged, conflicts = merge(standard, hospital) if standard else (hospital, [])
    merged.id = f"hosp_{patient_id}"
    merged.version = 1                              # 병원 프로토콜 자체 버전 (확정 시 +1)
    merged.reviewed_by = None                       # 치료사 확인 전
    db.save_protocol(merged)

    return {
        "protocol": merged.model_dump(mode="json"),
        "conflicts": conflicts,
        "needs_review": [s.phase for s in merged.slots if s.needs_review],
    }


@router.put("/{protocol_id}")
def confirm_protocol(protocol_id: str, body: ConfirmRequest) -> dict:
    """치료사가 확인·수정한 값으로 확정한다. version+1."""
    current = db.get_protocol(protocol_id)
    if current is None:
        raise HTTPException(404, "프로토콜을 찾을 수 없습니다")

    current.slots = body.slots
    current.reviewed_by = body.reviewed_by
    current.hospital = body.hospital or current.hospital
    current.origin = "표준본+병원"
    current.version += 1
    db.save_protocol(current)
    return {"protocol": current.model_dump(mode="json")}


@router.get("/{protocol_id}")
def read_protocol(protocol_id: str) -> dict:
    protocol = db.get_protocol(protocol_id)
    if protocol is None:
        raise HTTPException(404, "프로토콜을 찾을 수 없습니다")
    return {"protocol": protocol.model_dump(mode="json")}
