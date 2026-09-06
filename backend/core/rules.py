"""안전의 단일 지점.

절대 규칙 1: 규칙은 코드, AI는 제안. 이 모듈은 LLM을 호출하지 않는다.
같은 입력이면 항상 같은 출력 — 순수 함수만 둔다.

판정 표 (CLAUDE.md와 1:1로 대응):
| 금지 동작 유형 포함   | 제외              | RC-P{n}-FORBID-*        |
| 각도 상한 초과       | 상한으로 하향      | RC-P{n}-ROM-*           |
| 단계 필수 항목 누락   | 추가              | RC-P1-REQ-PENDULUM      |
| 통증 ≥7 + 부종      | 전체 세트 1회 감량 | GEN-RED-FLAG            |
| 프로토콜에 정보 없음  | "확인 필요" 표시   | GEN-NO-INFO             |
"""

from __future__ import annotations

import re

from .schemas import (
    DraftResult,
    ExerciseCandidate,
    Feedback,
    Patient,
    ProtocolSlot,
    SetIssue,
    SetReview,
    TearSize,
)

# ─────────────────────────────────────────────────────────────
# 표 (데이터로 둔다 — 규칙을 코드에 숨기지 않기 위해)
# ─────────────────────────────────────────────────────────────

TYPE_WORDS = ("능동보조", "수동", "능동", "저항", "등척성")  # 긴 것부터: "능동보조" 우선

#: 동작을 특정하지 않는 껍데기 낱말. 제거하면 "유형만 지정한 문구"가 드러난다.
GENERIC_WORDS = ("관절운동", "운동", "동작", "훈련", "움직임", "가동")

#: 파열 크기별 추가 상한. 프로토콜 상한과 min()으로 합친다 (더 보수적인 쪽 채택).
TEAR_ROM_CAPS: dict[TearSize, dict[str, int]] = {
    "광범위": {"외회전": 20},
}
TEAR_RULE_ID = "RC-TEAR-MASSIVE-ER"

#: 단계별 필수 항목. slot.allowed 안에 있을 때만 추가한다.
REQUIRED_BY_PHASE: dict[int, list[tuple[str, str, dict]]] = {
    1: [
        (
            "진자 운동",
            "RC-P1-REQ-PENDULUM",
            {
                "type": "수동",
                "dose": "3회 × 2분",
                "minutes": 6,
                "grade": "표준",
                "reason": "1단계 표준 필수 항목",
                "patient_desc": "허리를 숙이고 팔에 힘을 뺀 채 천천히 원을 그립니다",
                "source": "표준본",
            },
        )
    ],
}

#: 단계별 하루 권장 운동 시간(분). 넘으면 막지 않고 주의만 준다.
MINUTES_CAP: dict[int, int] = {1: 25, 2: 30, 3: 35, 4: 45}

#: 단계별로 하루에 다뤄야 하는 방향. 빠지면 정보로 알린다(막지 않는다).
COVERAGE_BY_PHASE: dict[int, list[str]] = {
    1: ["거상", "외회전"],
    2: ["거상", "외회전", "외전"],
    3: ["거상", "외회전", "내회전"],
    4: ["거상", "외회전", "기능"],
}

#: 적신호 — 키워드·패턴 기반. LLM 아님.
RED_FLAG_PATTERNS: list[tuple[str, str]] = [
    (r"열이\s*나|발열|고열|미열", "감염 의심(발열)"),
    (r"오한|한기", "감염 의심(오한)"),
    (r"빨갛|붉게|벌겋|붉고", "감염 의심(발적)"),
    (r"고름|진물|분비물", "상처 삼출"),
    (r"수술\s*부위.*(벌어|터졌|열렸)", "상처 벌어짐"),
    (r"감각이?\s*없|마비|저림이?\s*심", "신경 증상"),
    (r"숨이?\s*차|가슴이?\s*답답|흉통", "전신 증상"),
    (r"(뚝|퍽)\s*(하는|소리)|끊어지는\s*느낌|찢어지는\s*소리", "재파열 의심"),
    (r"통증이?\s*(갑자기|심하게)\s*(심해|악화)", "급성 악화"),
]

PAIN_RED_FLAG = 7          # 이 값 이상 + 부종이면 전체 감량
STALL_WEEKS = 2            # 정체 판정 기준 (주)
ROM_SELF_LEVEL = {"허리": 1, "어깨": 2, "눈높이": 3, "머리 위": 4}


# ─────────────────────────────────────────────────────────────
# 문구 매칭 (금지 목록·상한 키 모두 같은 문법을 쓴다)
# ─────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _parse_phrase(phrase: str) -> tuple[str | None, list[str]]:
    """'수동 외회전' → ('수동', ['외회전']) / '저항 운동' → ('저항', []) 로 나눈다.

    유형 낱말이 없으면 (None, 동작 목록). 껍데기 낱말은 버린다.
    구분자(`, / ·`)로 나뉜 동작들은 **또는**이다 — "손/팔꿈치 운동"은 손 운동 또는 팔꿈치 운동.
    """
    rest = _norm(phrase)
    ptype: str | None = None
    for word in TYPE_WORDS:
        if word in rest:
            ptype = word
            rest = rest.replace(word, "", 1)
            break
    for word in GENERIC_WORDS:
        rest = rest.replace(word, "")
    motions = [t for t in re.split(r"[,/·]", rest) if t]
    return ptype, motions


ITEM_SEPARATORS = r"[,;、]"


def _matches(phrase: str, cand: ExerciseCandidate) -> bool:
    """후보가 이 문구에 해당하는가.

    프로토콜 한 칸에 "능동 거상, 저항 운동"처럼 여러 항목이 한 문자열로 들어오는 경우가 있다
    (추출 결과이든 치료사가 손으로 적었든). 안전 층이 표기 방식에 흔들리면 안 되므로
    쉼표로 나눠 **하나라도** 걸리면 해당으로 본다.
    """
    parts = [p for p in re.split(ITEM_SEPARATORS, phrase) if p.strip()]
    if len(parts) > 1:
        return any(_matches_one(p, cand) for p in parts)
    return _matches_one(phrase, cand)


def _matches_one(phrase: str, cand: ExerciseCandidate) -> bool:
    """문구에 유형이 박혀 있으면 유형은 **정확히** 일치해야 한다.

    ('능동 거상' 금지가 '능동보조 거상'을 잡아가지 않도록)
    """
    ptype, motions = _parse_phrase(phrase)
    if ptype is not None:
        if cand.type != ptype:
            return False
        if not motions:
            return True                      # 유형만 지정한 금지 — 예: "저항 운동"
        return any(m in _norm(cand.name) for m in motions)
    if not motions:
        return False
    hay = _norm(cand.name) + _norm(cand.type)
    return any(m in hay for m in motions)


#: 한글 → rule_id 조각. CLAUDE.md의 예시(RC-P1-FORBID-ACTIVE-ELEV, RC-P1-ROM-ER)와 맞춘다.
_KO_SLUG = {
    "능동보조": "AAROM", "수동": "PASSIVE", "능동": "ACTIVE", "저항": "RESIST",
    "등척성": "ISOM", "거상": "ELEV", "외회전": "ER", "내회전": "IR",
    "굴곡": "FLEX", "신전": "EXT", "외전": "ABD", "진자": "PENDULUM",
    "관절운동": "ROM",
}


def _slug(phrase: str, motions_only: bool = False) -> str:
    ptype, motions = _parse_phrase(phrase)
    parts: list[str] = []
    if ptype and not motions_only:
        parts.append(_KO_SLUG.get(ptype, ptype.upper()))
    for motion in motions:
        parts.extend(en for ko, en in _KO_SLUG.items() if ko in motion)
    ascii_tail = re.sub(r"[^0-9A-Za-z]+", "-", phrase).strip("-").upper()
    if not parts and ascii_tail:
        parts.append(ascii_tail)
    return "-".join(dict.fromkeys(parts)) or "GEN"


def _rule_id(phase: int, kind: str, phrase: str) -> str:
    # ROM 상한은 동작만으로 식별한다 — RC-P1-ROM-ER
    return f"RC-P{phase}-{kind}-{_slug(phrase, motions_only=(kind == 'ROM'))}"


# ─────────────────────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────────────────────

def has_red_flag(text: str) -> bool:
    """환자 자유 텍스트에 즉시 연락이 필요한 신호가 있는가."""
    return bool(red_flag_reasons(text))


def red_flag_reasons(text: str) -> list[str]:
    if not text:
        return []
    return [label for pattern, label in RED_FLAG_PATTERNS if re.search(pattern, text)]


def effective_caps(slot: ProtocolSlot, patient: Patient | None) -> dict[str, tuple[int, str]]:
    """프로토콜 상한 + 파열 크기 상한을 합친 실제 상한. {문구: (각도, rule_id)}"""
    caps: dict[str, tuple[int, str]] = {
        key: (value, _rule_id(slot.phase, "ROM", key)) for key, value in slot.rom_caps.items()
    }
    if patient is not None:
        for motion, limit in TEAR_ROM_CAPS.get(patient.tear_size, {}).items():
            for key, (value, rid) in list(caps.items()):
                if motion in _norm(key) and limit < value:
                    caps[key] = (limit, TEAR_RULE_ID)
    return caps


def check(
    candidates: list[ExerciseCandidate],
    protocol_slot: ProtocolSlot,
    patient: Patient | None = None,
) -> DraftResult:
    """AI 후보를 프로토콜에 대조한다. 화면에 뜨는 것은 이 함수를 통과한 것뿐이다."""
    result = DraftResult(phase=protocol_slot.phase)
    caps = effective_caps(protocol_slot, patient)

    for raw in candidates:
        cand = raw.model_copy(deep=True)

        # 1) 금지 동작 → 제외
        hit = next((f for f in protocol_slot.forbidden if _matches(f, cand)), None)
        if hit:
            result.excluded.append({
                "candidate": cand.model_dump(),
                "cut_reason": f"{protocol_slot.phase}단계 금지: {hit}",
                "rule_id": _rule_id(protocol_slot.phase, "FORBID", hit),
            })
            continue

        # 2) 각도 상한 초과 → 상한으로 하향
        if cand.rom is not None:
            for key, (limit, rid) in caps.items():
                if _matches(key, cand) and cand.rom > limit:
                    before = cand.rom
                    cand.rom = limit
                    result.adjusted.append({
                        "candidate": cand.model_dump(),
                        "before": f"{before}°",
                        "after": f"{limit}°",
                        "rule_id": rid,
                    })
                    break

        # 3) 프로토콜에 근거 없음 → 지어내지 말고 "확인 필요"
        if not _covered(cand, protocol_slot, caps):
            cand.note = "확인 필요"
            cand.grade = "참고"
            result.adjusted.append({
                "candidate": cand.model_dump(),
                "before": "프로토콜 근거 없음",
                "after": "확인 필요 표시",
                "rule_id": "GEN-NO-INFO",
            })

        result.passed.append(cand)

    # 4) 단계 필수 항목 누락 → 추가
    for name, rid, extra in REQUIRED_BY_PHASE.get(protocol_slot.phase, []):
        if not any(_matches(name, c) for c in result.passed):
            if not any(_matches(f, ExerciseCandidate(name=name, **_typed(extra))) for f in protocol_slot.forbidden):
                added = ExerciseCandidate(name=name, **_typed(extra))
                result.passed.append(added)
                result.adjusted.append({
                    "candidate": added.model_dump(),
                    "before": "없음",
                    "after": "추가됨",
                    "rule_id": rid,
                })

    # 5) 통증 ≥7 + 부종 → 적신호, 전체 세트 1회 감량
    if patient is not None and patient.pain >= PAIN_RED_FLAG and patient.swelling:
        result.red_flag = True
        for cand in result.passed:
            reduced = _reduce_sets(cand.dose)
            if reduced != cand.dose:
                result.adjusted.append({
                    "candidate": cand.model_dump(),
                    "before": cand.dose,
                    "after": reduced,
                    "rule_id": "GEN-RED-FLAG",
                })
                cand.dose = reduced

    return result


def _typed(extra: dict) -> dict:
    return dict(extra)


def _covered(cand: ExerciseCandidate, slot: ProtocolSlot, caps: dict) -> bool:
    """허용 목록이나 상한 표에 근거가 있는가."""
    if any(_matches(a, cand) for a in slot.allowed):
        return True
    return any(_matches(key, cand) for key in caps)


def _reduce_sets(dose: str) -> str:
    """'3세트 × 10회' → '2세트 × 10회'. 1세트 밑으로는 내리지 않는다."""
    def repl(m: re.Match) -> str:
        return f"{max(1, int(m.group(1)) - 1)}세트"

    return re.sub(r"(\d+)\s*세트", repl, dose, count=1)


def check_set(
    exercises: list[ExerciseCandidate],
    protocol_slot: ProtocolSlot,
    patient: Patient | None = None,
) -> SetReview:
    """담긴 세트를 통째로 본다. 개별 검사(check)가 통과시킨 것도 여기서 다시 본다.

    운동 하나하나가 안전해도 묶음이 과하거나 한쪽으로 쏠릴 수 있다.
    '막음'이 하나라도 있으면 발송을 막는다 — 판단은 전부 코드가 한다.
    """
    issues: list[SetIssue] = []
    caps = effective_caps(protocol_slot, patient)

    if not exercises:
        issues.append(SetIssue(level="막음", message="담긴 운동이 없습니다",
                               rule_id="SET-EMPTY"))

    for cand in exercises:
        hit = next((f for f in protocol_slot.forbidden if _matches(f, cand)), None)
        if hit:
            issues.append(SetIssue(
                level="막음", message=f"{cand.name} — {protocol_slot.phase}단계 금지: {hit}",
                rule_id=_rule_id(protocol_slot.phase, "FORBID", hit)))
        if cand.rom is not None:
            for key, (limit, rid) in caps.items():
                if _matches(key, cand) and cand.rom > limit:
                    issues.append(SetIssue(
                        level="막음",
                        message=f"{cand.name} — 상한 {limit}°를 넘습니다 ({cand.rom}°)",
                        rule_id=rid))
                    break

    for name, rid, _ in REQUIRED_BY_PHASE.get(protocol_slot.phase, []):
        if not any(_matches(name, c) for c in exercises):
            issues.append(SetIssue(
                level="주의", message=f"{protocol_slot.phase}단계 필수 항목 '{name}'이 빠졌습니다",
                rule_id=rid))

    total = sum(c.minutes for c in exercises)
    cap = MINUTES_CAP.get(protocol_slot.phase, 45)
    if total > cap:
        issues.append(SetIssue(
            level="주의", message=f"하루 {total}분 — {protocol_slot.phase}단계 권장 {cap}분을 넘습니다",
            rule_id="SET-MINUTES"))

    if patient is not None and patient.pain >= PAIN_RED_FLAG and patient.swelling:
        issues.append(SetIssue(
            level="주의", message=f"통증 {patient.pain} + 부종 — 세트를 줄여 보냅니다",
            rule_id="GEN-RED-FLAG"))

    coverage = {}
    for direction in COVERAGE_BY_PHASE.get(protocol_slot.phase, []):
        covered = any(direction in _norm(c.name) or direction in _norm(" ".join(
            [c.reason, c.patient_desc])) for c in exercises)
        coverage[direction] = covered
        if not covered:
            issues.append(SetIssue(
                level="정보", message=f"'{direction}' 방향 운동이 없습니다",
                rule_id="SET-COVERAGE"))

    missing = [c.name for c in exercises if not c.video_url]
    if missing:
        issues.append(SetIssue(
            level="정보", message=f"영상이 없는 운동 {len(missing)}개 — 글 설명만 전달됩니다",
            rule_id="SET-NO-VIDEO"))

    return SetReview(
        ok=not any(i.level == "막음" for i in issues),
        total_minutes=total,
        count=len(exercises),
        issues=issues,
        coverage=coverage,
        videos_missing=missing,
    )


def within_plan(reply: str, plan: list[ExerciseCandidate], faq: list[str] | None = None) -> bool:
    """치료사에게 보여줄 AI 문장이 처방 범위 안에 있는가.

    (2단계 환자 챗봇을 위한 자리. 지금은 인박스 초안 검사에 쓴다.)
    """
    if not reply:
        return False
    if has_red_flag(reply):
        return False
    norm = _norm(reply)
    banned = ("무거운", "웨이트", "덤벨", "밴드", "혼자판단", "약을드세요", "처방을바꾸")
    if any(b in norm for b in banned):
        return False
    numbers = [int(n) for n in re.findall(r"(\d+)\s*도", reply)]
    caps = [c.rom for c in plan if c.rom is not None]
    if numbers and caps and max(numbers) > max(caps):
        return False
    return True


def is_stalled(feedback_history: list[Feedback], weeks: int = STALL_WEEKS) -> bool:
    """가동범위 자가보고가 N주 이상 올라가지 않았는가."""
    scored = [
        (f.date, ROM_SELF_LEVEL[f.rom_self])
        for f in feedback_history
        if f.rom_self in ROM_SELF_LEVEL
    ]
    if len(scored) < 2:
        return False
    scored.sort(key=lambda x: x[0])
    first_date, _ = scored[0]
    last_date, _ = scored[-1]
    if (last_date - first_date).days < weeks * 7:
        return False
    cutoff_index = next(
        (i for i, (d, _) in enumerate(scored) if (last_date - d).days <= weeks * 7),
        0,
    )
    window = scored[max(0, cutoff_index - 1):]
    return max(level for _, level in window) <= window[0][1]
