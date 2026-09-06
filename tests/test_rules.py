"""CLAUDE.md의 테스트 케이스 7개. 이것부터 통과해야 다음 단계로 넘어간다."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.core import protocol as proto
from backend.core import rules
from backend.core.schemas import (
    ExerciseCandidate,
    Feedback,
    Patient,
    Protocol,
    ProtocolSlot,
)


@pytest.fixture
def phase1() -> ProtocolSlot:
    return ProtocolSlot(
        phase=1,
        weeks=(0, 6),
        brace="항상 착용(수면 포함)",
        allowed=["수동 관절운동", "진자 운동"],
        forbidden=["능동 거상", "저항 운동", "능동 관절운동"],
        rom_caps={"수동 외회전": 30, "수동 거상": 90},
        source_text="Phase I (0-6주): 보조기 상시 착용, PROM only",
    )


@pytest.fixture
def phase2() -> ProtocolSlot:
    return ProtocolSlot(
        phase=2,
        weeks=(6, 12),
        brace="외출 시 착용",
        allowed=["능동보조 관절운동", "능동 관절운동", "등척성 운동"],
        forbidden=["저항 운동"],
        rom_caps={"능동보조 외회전": 45, "능동보조 거상": 140},
    )


def patient(**kw) -> Patient:
    base = dict(
        id="p1",
        token="tok_demo",
        age=62,
        surgery_date=date.today() - timedelta(days=21),
        tear_size="대형",
        pain=4,
        swelling=False,
        brace=True,
        protocol_id="standard_rc",
    )
    base.update(kw)
    return Patient(**base)


def pendulum() -> ExerciseCandidate:
    return ExerciseCandidate(name="진자 운동", type="수동", dose="3회 × 2분", reason="1단계 표준")


# 1. 1단계 + "능동 거상" → 제외
def test_forbidden_active_elevation_is_excluded(phase1):
    cand = ExerciseCandidate(name="능동 거상", type="능동", rom=90, reason="가동범위 회복")
    result = rules.check([cand], phase1)

    assert not any(c.name == "능동 거상" for c in result.passed)
    assert len(result.excluded) == 1
    cut = result.excluded[0]
    assert cut["rule_id"] == "RC-P1-FORBID-ACTIVE-ELEV"
    assert "금지" in cut["cut_reason"]


# 2. 1단계 + 수동 외회전 60° → 30°로 하향
def test_rom_cap_downgrades_to_limit(phase1):
    cand = ExerciseCandidate(name="수동 외회전", type="수동", rom=60, reason="외회전 확보")
    result = rules.check([cand], phase1, patient())

    passed = result.passed[0]
    assert passed.rom == 30
    adj = next(a for a in result.adjusted if a["rule_id"] == "RC-P1-ROM-ER")
    assert adj["before"] == "60°" and adj["after"] == "30°"


# 3. 광범위 파열 + 1단계 + 수동 외회전 40° → 20°로 하향
def test_massive_tear_tightens_cap(phase1):
    cand = ExerciseCandidate(name="수동 외회전", type="수동", rom=40, reason="외회전 확보")
    result = rules.check([cand], phase1, patient(tear_size="광범위"))

    assert result.passed[0].rom == 20
    assert any(a["rule_id"] == rules.TEAR_RULE_ID for a in result.adjusted)


# 4. 통증 8 + 부종 → red_flag, 전체 세트 1회 감량
def test_pain_and_swelling_reduce_every_set(phase1):
    cands = [
        ExerciseCandidate(name="수동 거상", type="수동", rom=90, dose="3세트 × 10회"),
        ExerciseCandidate(name="수동 외회전", type="수동", rom=30, dose="2세트 × 10회"),
    ]
    result = rules.check(cands, phase1, patient(pain=8, swelling=True))

    assert result.red_flag is True
    doses = {c.name: c.dose for c in result.passed}
    assert doses["수동 거상"] == "2세트 × 10회"
    assert doses["수동 외회전"] == "1세트 × 10회"
    assert all(
        a["rule_id"] == "GEN-RED-FLAG"
        for a in result.adjusted
        if a["candidate"]["name"] in doses and a["before"].endswith("회")
    )


# 5. 자유 텍스트 적신호
def test_red_flag_keywords():
    assert rules.has_red_flag("어깨가 빨갛게 붓고 열이 나요") is True
    assert rules.has_red_flag("오늘 운동은 다 했어요. 통증은 3이에요") is False


# 6. 2단계 + 저항밴드 → 제외 (2단계도 저항 금지)
def test_resistance_band_excluded_in_phase2(phase2):
    cand = ExerciseCandidate(name="저항밴드 외회전", type="저항", rom=45, reason="근력 회복")
    result = rules.check([cand], phase2)

    assert result.passed == []
    assert result.excluded[0]["rule_id"] == "RC-P2-FORBID-RESIST"


# 7. 1단계 필수 항목(진자 운동) 누락 → 자동 추가
def test_required_pendulum_is_added(phase1):
    cand = ExerciseCandidate(name="수동 거상", type="수동", rom=90, dose="3세트 × 10회")
    result = rules.check([cand], phase1)

    assert any(c.name == "진자 운동" for c in result.passed)
    assert any(a["rule_id"] == "RC-P1-REQ-PENDULUM" for a in result.adjusted)


def test_required_pendulum_not_duplicated(phase1):
    result = rules.check([pendulum()], phase1)
    assert [c.name for c in result.passed].count("진자 운동") == 1


# 프로토콜에 근거 없음 → 지어내지 않고 "확인 필요"
def test_unknown_exercise_marked_needs_review(phase1):
    cand = ExerciseCandidate(name="등척성 외전", type="등척성", dose="3세트 × 5회")
    result = rules.check([cand], phase1)

    marked = next(c for c in result.passed if c.name == "등척성 외전")
    assert marked.note == "확인 필요" and marked.grade == "참고"
    assert any(a["rule_id"] == "GEN-NO-INFO" for a in result.adjusted)


# 프로토콜 원문의 "손/팔꿈치 운동" 같은 묶음 표기는 '또는'으로 읽어야 한다
def test_slash_grouped_phrase_is_or_not_and():
    slot = ProtocolSlot(
        phase=1, weeks=(0, 6),
        allowed=["수동 관절운동", "손/팔꿈치 운동"],
        forbidden=["능동 거상"],
        rom_caps={"수동 외회전": 30},
    )
    hand = ExerciseCandidate(name="손 쥐었다 펴기", type="능동", dose="3세트 × 20회")
    elbow = ExerciseCandidate(name="팔꿈치 굽혔다 펴기", type="능동", dose="3세트 × 15회")

    result = rules.check([hand, elbow], slot)
    marked = {c.name: c.note for c in result.passed if c.name in ("손 쥐었다 펴기", "팔꿈치 굽혔다 펴기")}
    assert marked == {"손 쥐었다 펴기": None, "팔꿈치 굽혔다 펴기": None}, \
        f"허용된 항목이 '확인 필요'로 잘못 표시됐다: {marked}"
    assert not any(a["rule_id"] == "GEN-NO-INFO" for a in result.adjusted)


# 프로토콜 한 칸이 "A, B, C" 한 덩어리로 들어와도 안전 판정은 흔들리지 않아야 한다
def test_comma_joined_forbidden_still_cuts():
    slot = ProtocolSlot(
        phase=1, weeks=(0, 6),
        allowed=["수동 관절운동, 진자 운동"],
        forbidden=["능동 거상, 능동보조 운동, 저항 운동"],
        rom_caps={"수동 외회전": 30},
    )
    aarom = ExerciseCandidate(name="능동보조 전방거상 (막대)", type="능동보조", rom=140)
    band = ExerciseCandidate(name="저항밴드 외회전", type="저항", rom=45)
    passive = ExerciseCandidate(name="수동 외회전 (막대 이용)", type="수동", rom=30)

    result = rules.check([aarom, band, passive], slot)
    cut = {x["candidate"]["name"] for x in result.excluded}
    assert cut == {"능동보조 전방거상 (막대)", "저항밴드 외회전"}, cut
    kept = next(c for c in result.passed if c.name == "수동 외회전 (막대 이용)")
    assert kept.note is None, "허용된 항목이 '확인 필요'로 잘못 표시됐다"


def test_check_is_pure(phase1):
    cands = [ExerciseCandidate(name="수동 외회전", type="수동", rom=60, dose="3세트 × 10회")]
    a = rules.check(cands, phase1, patient())
    b = rules.check(cands, phase1, patient())
    assert a.model_dump() == b.model_dump()
    assert cands[0].rom == 60, "입력 후보를 변형하면 안 된다"


# ── 단계 판정 · 3층 병합 ────────────────────────────────────

def test_phase_boundaries():
    today = date(2026, 9, 6)
    assert proto.phase_for(today - timedelta(weeks=3), today) == 1
    assert proto.phase_for(today - timedelta(weeks=6), today) == 2
    assert proto.phase_for(today - timedelta(weeks=13), today) == 3
    assert proto.phase_for(today - timedelta(weeks=20), today) == 4


def test_hospital_facts_win_and_conflicts_are_recorded(phase1):
    standard = Protocol(id="std", slots=[phase1])
    hospital = Protocol(
        id="h1",
        hospital="OO정형외과",
        slots=[ProtocolSlot(phase=1, weeks=(0, 6), brace="상시 착용(2주 후 재평가)",
                            rom_caps={"수동 외회전": 20})],
    )
    merged, conflicts = proto.merge(standard, hospital)
    slot = merged.slots[0]

    assert slot.brace == "상시 착용(2주 후 재평가)", "사실 칸은 병원 값이어야 한다"
    assert slot.rom_caps["수동 외회전"] == 20, "더 보수적인 병원 상한을 따라야 한다"
    assert slot.rom_caps["수동 거상"] == 90, "병원본에 없는 상한은 표준본 값이 남아야 한다"
    assert merged.origin == "표준본+병원"
    assert any("병원 우선" in c for c in conflicts)


# 사진 판독이 금지 항목을 빠뜨려도 표준본의 금지가 살아 있어야 한다
def test_merge_keeps_standard_safety_when_hospital_read_is_incomplete():
    standard = Protocol(id="std", slots=[ProtocolSlot(
        phase=1, weeks=(0, 6), brace="항상 착용",
        allowed=["수동 관절운동", "진자 운동"],
        forbidden=["능동 거상", "능동보조 관절운동", "저항 운동"],
        rom_caps={"수동 외회전": 30, "수동 거상": 90},
    )])
    partial = Protocol(id="h1", hospital="OO정형외과", slots=[ProtocolSlot(
        phase=1, weeks=(0, 6), brace="상시 착용",
        forbidden=["능동 거상"],                       # '능동보조 관절운동'을 놓쳤다
        rom_caps={"수동 외회전": 45},                   # 표준본(30°)보다 느슨하다
    )])
    merged, conflicts = proto.merge(standard, partial)
    slot = merged.slots[0]

    assert "능동보조 관절운동" in slot.forbidden, "표준본 금지가 사라졌다"
    assert slot.rom_caps["수동 외회전"] == 30, "느슨한 상한이 그대로 반영됐다"
    assert any("보수적" in c for c in conflicts)
    assert slot.brace == "상시 착용", "사실 칸은 병원 값이어야 한다"

    aarom = ExerciseCandidate(name="능동보조 전방거상 (막대)", type="능동보조", rom=140)
    assert rules.check([aarom], slot).excluded, "병합 후에도 걸러내지 못했다"


def test_patient_adjust_cannot_loosen(phase1):
    standard = Protocol(id="std", slots=[phase1])
    merged, conflicts = proto.merge(standard, None, {1: {"rom_caps": {"수동 외회전": 60}}})

    assert merged.slots[0].rom_caps["수동 외회전"] == 30
    assert any("무시" in c for c in conflicts)


def test_is_stalled():
    start = date(2026, 8, 1)
    flat = [
        Feedback(patient_id="p1", date=start + timedelta(days=i * 7), pain=4, rom_self="어깨")
        for i in range(4)
    ]
    assert rules.is_stalled(flat) is True

    improving = list(flat)
    improving[-1] = Feedback(
        patient_id="p1", date=start + timedelta(days=21), pain=3, rom_self="눈높이"
    )
    assert rules.is_stalled(improving) is False
