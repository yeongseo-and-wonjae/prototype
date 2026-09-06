"""FastAPI 앱. 치료사 화면(Streamlit)은 이 API만 호출한다."""

from __future__ import annotations

from fastapi import FastAPI

from .ai import client as ai_client
from .ai import retrieve
from .api import feedback, inbox, patient_web, plan, protocol
from .core import protocol as core_protocol
from .lib import db

app = FastAPI(title="리햅톡 API", version="0.1.0",
              description="데모용. 실제 임상 처방에 사용할 수 없습니다.")

app.include_router(protocol.router)
app.include_router(plan.router)
app.include_router(feedback.router)
app.include_router(inbox.router)
app.include_router(patient_web.router)


@app.on_event("startup")
def _startup() -> None:
    db.init()


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "ai_mode": "live" if ai_client.is_live() else "mock",
        "provider": ai_client.provider(),
        "model": ai_client.model(),
        "reads_documents": ai_client.can_read_documents(),
        "search_embedding": retrieve.backend_name(),
        "disclaimer": "데모용. 실제 임상 처방에 사용할 수 없습니다.",
    }


@app.get("/api/patients")
def patients() -> dict:
    """목록에 필요한 경과 주차·단계는 여기서 계산한다 — 프론트는 규칙을 모른다."""
    out = []
    for row in db.list_patients():
        patient = db.get_patient(row["id"])
        protocol = db.get_protocol(f"hosp_{patient.id}") or db.get_protocol(patient.protocol_id)
        slot = core_protocol.slot_for(protocol, patient) if protocol else None
        out.append({
            **row,
            "weeks_since_surgery": core_protocol.weeks_since(patient.surgery_date),
            "phase": slot.phase if slot else None,
            "protocol_reviewed_by": protocol.reviewed_by if protocol else None,
        })
    return {"patients": out}
