"""환자 모바일 웹. 토큰으로만 접근하고 Streamlit을 쓰지 않는다."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..core import protocol as core_protocol
from ..lib import db

router = APIRouter(tags=["patient"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/p/{token}", response_class=HTMLResponse)
def patient_page(request: Request, token: str):
    patient = db.get_patient_by_token(token)
    if patient is None:
        raise HTTPException(404, "잘못된 링크입니다")

    exercises = db.get_plan(patient.id)
    protocol = db.get_protocol(f"hosp_{patient.id}") or db.get_protocol(patient.protocol_id)
    slot = core_protocol.slot_for(protocol, patient) if protocol else None

    return templates.TemplateResponse(request, "patient.html", {
        "name": db.patient_name(patient.id),
        "today": date.today(),
        "token": token,
        "exercises": exercises,
        "minutes": sum(e.get("minutes", 5) for e in exercises),
        "weeks": core_protocol.weeks_since(patient.surgery_date),
        "phase": slot.phase if slot else "-",
        "brace": slot.brace if slot else None,
        "forbidden": slot.forbidden if slot else [],
    })
