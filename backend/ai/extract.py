"""프로토콜 사진 → 6칸 JSON.

Upstage: 사진 → Document Parse(한국어 표 구조 추출) → Solar(JSON 스키마 강제)
Claude : 사진 → vision 직접 판독
키 없음: 목업

모델 출력은 그대로 믿지 않는다. _to_slot()에서 형태를 정리한 뒤 Pydantic으로 검증한다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from ..core.schemas import ProtocolSlot
from . import client

DATA = Path(__file__).resolve().parents[2] / "data"
MAX_DEGREES = 200          # 이보다 크면 잘못 읽은 값으로 본다
ITEM_SEPARATORS = r"[,;、]"  # "능동 거상, 저항 운동" 처럼 한 덩어리로 오는 경우를 쪼갠다

SCHEMA = {
    "type": "object",
    "properties": {
        "slots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phase": {"type": "integer"},
                    "weeks": {"type": "array", "items": {"type": "integer"}},
                    "brace": {"type": ["string", "null"]},
                    "allowed": {"type": "array", "items": {"type": "string"}},
                    "forbidden": {"type": "array", "items": {"type": "string"}},
                    "rom_caps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"motion": {"type": "string"},
                                           "degrees": {"type": "integer"}},
                            "required": ["motion", "degrees"],
                            "additionalProperties": False,
                        },
                    },
                    "source_text": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["phase", "weeks", "brace", "allowed", "forbidden",
                             "rom_caps", "source_text", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["slots"],
    "additionalProperties": False,
}


def extract(image: bytes, media_type: str = "image/png",
            filename: str = "protocol.png") -> list[ProtocolSlot]:
    """사진에서 단계별 6칸을 읽는다. 읽지 못한 칸은 비우고 confidence를 낮춘다."""
    if not client.is_live():
        return _mock()

    document = client.read_document(image, filename)
    if document:
        user = ("다음은 프로토콜 사진에서 읽어낸 내용입니다. 단계별 6칸을 추출하세요.\n\n"
                f"{document}")
        images = None
    else:
        user = "이 프로토콜 사진에서 단계별 6칸을 추출하세요."
        images = [image]

    system = client.prompt("extract")
    for attempt in range(2):
        raw = client.ask_json(system, user, SCHEMA, images=images)
        slots, errors = _to_slots(raw.get("slots", []))
        if slots:
            return slots
        if attempt == 1:
            raise ValueError(f"프로토콜을 읽지 못했습니다: {errors}")
        user += f"\n\n앞선 응답이 검증을 통과하지 못했습니다: {errors}. 다시 추출하세요."
    return []


# ─────────────────────────────────────────────────────────────

def _to_slots(raw: list[dict]) -> tuple[list[ProtocolSlot], list[str]]:
    slots, errors, seen = [], [], set()
    for item in raw:
        try:
            slot = _to_slot(item)
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            errors.append(f"{item.get('phase', '?')}단계: {exc}")
            continue
        if slot.phase in seen:                      # 같은 단계가 두 번 나오면 첫 것만
            continue
        seen.add(slot.phase)
        slots.append(slot)
    slots.sort(key=lambda s: s.phase)
    return _flag_broken_timeline(slots), errors


def _flag_broken_timeline(slots: list[ProtocolSlot]) -> list[ProtocolSlot]:
    """단계 기간이 이어지지 않으면 확인 필요로 내린다.

    모델이 보조기 문구("8주 후 해제")의 숫자를 기간으로 잘못 읽는 일이 있다.
    자신 있게 틀리는 경우도 있어서, 값 자체를 고치지 않고 치료사에게 넘긴다.
    """
    suspect: set[int] = set()
    for i, slot in enumerate(slots):
        if slot.weeks[1] <= slot.weeks[0]:
            suspect.add(i)
        if i == 0 and slot.weeks[0] != 0:
            # 첫 단계가 0주에서 시작하지 않으면 단계 번호가 통째로 밀렸을 수 있다.
            # 뒤 단계의 번호도 같이 틀리므로 전부 확인 대상으로 올린다.
            suspect.update(range(len(slots)))
        if i > 0 and slot.weeks[0] != slots[i - 1].weeks[1]:
            suspect.update({i - 1, i})         # 끊긴 자리는 양쪽 다 의심스럽다

    for i in suspect:
        slots[i].confidence = min(slots[i].confidence, 0.5)
    return slots


def _to_slot(item: dict) -> ProtocolSlot:
    """모델 출력을 스키마에 맞게 정리한다. 이상한 값은 버리고 신뢰도를 낮춘다."""
    weeks = [int(w) for w in (item.get("weeks") or [0, 0])][:2]
    while len(weeks) < 2:
        weeks.append(weeks[0])
    start = max(0, weeks[0])
    end = weeks[1] if weeks[1] > start else 999     # -1·0 같은 '무기한' 표기 정리

    caps, dropped = {}, 0
    for cap in item.get("rom_caps") or []:
        motion, degrees = str(cap.get("motion", "")).strip(), cap.get("degrees")
        if not motion or not isinstance(degrees, int) or not 0 < degrees <= MAX_DEGREES:
            dropped += 1                            # "제한 없음 -1°" 같은 항목
            continue
        caps[motion] = degrees

    confidence = float(item.get("confidence", 0.5))
    if dropped:
        confidence = min(confidence, 0.65)          # 버린 값이 있으면 확인 필요로 내린다

    return ProtocolSlot(
        phase=int(item["phase"]),
        weeks=(start, end),
        brace=(item.get("brace") or None),
        allowed=_items(item.get("allowed")),
        forbidden=_items(item.get("forbidden")),
        rom_caps=caps,
        source_text=(item.get("source_text") or None),
        confidence=max(0.0, min(1.0, confidence)),
    )


def _items(raw: object) -> list[str]:
    """모델이 "A, B, C"를 한 원소로 반환하는 경우가 있어 항목 단위로 쪼갠다.

    슬래시는 쪼개지 않는다 — "손/팔꿈치 운동"은 한 항목이고 규칙 층이 '또는'으로 읽는다.
    """
    out = []
    for entry in raw or []:
        for part in re.split(ITEM_SEPARATORS, str(entry)):
            part = part.strip(" ·-—")
            if part:
                out.append(part)
    return out


def _mock() -> list[ProtocolSlot]:
    """키가 없을 때. 표준본을 바탕으로 하되 '흐려서 못 읽은 칸'을 일부러 남긴다."""
    raw = json.loads((DATA / "standard_protocol.json").read_text(encoding="utf-8"))
    slots = []
    for s in raw["slots"]:
        s = dict(s)
        s["weeks"] = tuple(s["weeks"])
        s["source_text"] = f"[사진에서 읽음] {s['source_text']}"
        if s["phase"] == 2:
            s["brace"] = None
            s["rom_caps"] = {"능동보조 거상": 140}
            s["confidence"] = 0.55
            s["source_text"] = "[사진에서 읽음] Phase II (6-12주) ... (표가 잘려 일부 확인 불가)"
        elif s["phase"] == 4:
            s["confidence"] = 0.62
        else:
            s["confidence"] = 0.93
        slots.append(ProtocolSlot(**s))
    return slots
