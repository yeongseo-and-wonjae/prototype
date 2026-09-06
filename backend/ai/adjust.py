"""피드백 이력 + 프로토콜 → 조정 후보 2개. 정체가 길면 규칙이 (c)를 덧붙인다."""

from __future__ import annotations

import json

from ..core import rules
from ..core.schemas import Feedback, ProtocolSlot
from . import client

SCHEMA = {
    "type": "object",
    "properties": {
        "drafts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "text": {"type": "string"}},
                "required": ["label", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["drafts"],
    "additionalProperties": False,
}

STALL_ESCALATION_WEEKS = 3


def adjust(
    signal: str,
    clean_patient: dict,
    slot: ProtocolSlot,
    history: list[Feedback],
) -> list[dict]:
    from ..lib.sanitize import assert_clean

    assert_clean(clean_patient)

    # 적신호에는 용량 조정을 제안하지 않는다. AI를 부르지 않고 규칙이 정한 안내만 낸다.
    flags = rules.red_flag_reasons(signal)
    if flags:
        return [
            {
                "label": "즉시 연락 안내 (규칙)",
                "text": "적어주신 증상은 확인이 필요합니다. 오늘 운동은 멈추시고 "
                        "가능한 한 빨리 수술받으신 병원에 연락해 주세요.",
                "rule_id": "GEN-RED-FLAG",
            },
            {
                "label": f"치료사 메모 — 감지된 신호: {', '.join(flags)}",
                "text": "감염·재파열 의심 신호가 있어 운동 조정 전에 집도의 확인이 필요합니다. "
                        "조정 후보는 생성하지 않았습니다.",
                "rule_id": "GEN-RED-FLAG",
            },
        ]

    if client.is_live():
        system = client.prompt(
            "adjust",
            signal=signal,
            patient=json.dumps(clean_patient, ensure_ascii=False, default=str),
            limits=json.dumps(
                {"금지": slot.forbidden, "각도상한": slot.rom_caps, "보조기": slot.brace},
                ensure_ascii=False,
            ),
            history="\n".join(
                f"- {f.date}: 통증 {f.pain}, 가동범위 {f.rom_self}, 완료 {len(f.completed)}개"
                for f in history[-10:]
            ) or "기록 없음",
        )
        drafts = client.ask_json(system, "조정 후보 2개를 만드세요.", SCHEMA, effort="medium")["drafts"]
    else:
        drafts = _mock(signal, slot)

    # 규칙이 덧붙이는 항목 — AI 판단이 아니라 코드가 결정한다
    if rules.is_stalled(history, weeks=STALL_ESCALATION_WEEKS):
        drafts.append({
            "label": "집도의 확인 권고 (규칙)",
            "text": f"{STALL_ESCALATION_WEEKS}주 이상 가동범위가 늘지 않았습니다. "
                    "운동을 올리기 전에 집도의 확인을 먼저 받는 것을 권합니다.",
            "rule_id": "GEN-STALL-ESCALATE",
        })
    return drafts


def _mock(signal: str, slot: ProtocolSlot) -> list[dict]:
    cap = ", ".join(f"{k} {v}°" for k, v in slot.rom_caps.items()) or "상한 없음"
    return [
        {
            "label": "(a) 범위 안에서 용량 조정",
            "text": "지금 하시는 운동을 하루 한 번 더 나눠서 해보시겠어요? "
                    f"각도는 지금 그대로({cap}) 두고 횟수만 조금 늘립니다. 통증이 5를 넘으면 바로 멈추세요.",
        },
        {
            "label": "(b) 다음 진료 때 측정 후 판단",
            "text": "지금은 무리해서 늘리지 마시고 하던 대로 해주세요. "
                    "다음 진료 때 각도를 직접 재보고 다음 단계를 정하겠습니다.",
        },
    ]
