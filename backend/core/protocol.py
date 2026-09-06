"""단계 판정과 3층 병합. 여기도 LLM 호출 없음 — 순수 함수."""

from __future__ import annotations

from datetime import date

from .schemas import Patient, Phase, Protocol, ProtocolSlot

#: 회전근개 봉합 단계 경계 (주)
PHASE_WEEKS: list[tuple[int, int, int]] = [
    (1, 0, 6),
    (2, 6, 12),
    (3, 12, 16),
    (4, 16, 999),
]


def weeks_since(surgery_date: date, today: date | None = None) -> int:
    today = today or date.today()
    return max(0, (today - surgery_date).days // 7)


def phase_for(surgery_date: date, today: date | None = None) -> Phase:
    weeks = weeks_since(surgery_date, today)
    for phase, start, end in PHASE_WEEKS:
        if start <= weeks < end:
            return phase  # type: ignore[return-value]
    return 4


def slot_for(protocol: Protocol, patient: Patient, today: date | None = None) -> ProtocolSlot | None:
    """환자의 경과 주차에 맞는 칸. 없으면 None (지어내지 않는다)."""
    phase = phase_for(patient.surgery_date, today)
    return next((s for s in protocol.slots if s.phase == phase), None)


def merge(
    standard: Protocol,
    hospital_override: Protocol | None = None,
    patient_adjust: dict[int, dict] | None = None,
) -> tuple[Protocol, list[str]]:
    """표준본 → 병원 프로토콜 → 환자 개별 조정 순으로 겹친다.

    기간·보조기·원문처럼 **사실을 기술하는 칸은 집도의(병원) 지시가 이긴다.**

    안전을 정하는 칸은 다르다. 병원 프로토콜은 사진 판독으로 들어오므로 한 항목을
    놓칠 수 있고, 그 누락이 곧 안전 구멍이 된다. 그래서:

      - **금지 목록은 합집합** — 금지가 겹치는 것은 위험하지 않다
      - **각도 상한은 더 작은 값** — 상한은 늘 보수적인 쪽을 택한다
      - 허용 목록도 합집합 — 허용은 근거 표시용이고, 안전 판정은 금지·상한이 한다

    표준본보다 느슨해지는 값은 conflicts에 남겨 치료사가 확인 화면에서 보게 한다.
    """
    conflicts: list[str] = []
    merged = standard.model_copy(deep=True)
    merged.origin = "표준본"

    if hospital_override is not None:
        merged.origin = "표준본+병원"
        merged.hospital = hospital_override.hospital
        by_phase = {s.phase: s for s in merged.slots}
        for hs in hospital_override.slots:
            base = by_phase.get(hs.phase)
            if base is None:
                merged.slots.append(hs.model_copy(deep=True))
                continue
            for field in ("brace", "weeks", "source_text"):     # 사실 — 병원 우선
                new = getattr(hs, field)
                if not new:
                    continue
                old = getattr(base, field)
                if old and old != new:
                    conflicts.append(f"{hs.phase}단계 {field}: 표준본 {old!r} → 병원 {new!r} (병원 우선)")
                setattr(base, field, new)

            for field in ("allowed", "forbidden"):               # 안전 — 합집합
                merged_list = list(dict.fromkeys([*getattr(base, field), *getattr(hs, field)]))
                only_standard = [x for x in getattr(base, field) if x not in getattr(hs, field)]
                if only_standard and getattr(hs, field):
                    conflicts.append(
                        f"{hs.phase}단계 {field}: 병원본에 없어 표준본 값을 함께 적용 {only_standard!r}"
                    )
                setattr(base, field, merged_list)

            for motion, limit in hs.rom_caps.items():            # 상한 — 더 보수적인 쪽
                current = base.rom_caps.get(motion)
                if current is not None and limit > current:
                    conflicts.append(
                        f"{hs.phase}단계 {motion}: 병원 {limit}° > 표준본 {current}° — 표준본 유지(보수적)"
                    )
                    continue
                base.rom_caps[motion] = limit

            base.confidence = min(base.confidence, hs.confidence)
        merged.slots.sort(key=lambda s: s.phase)

    if patient_adjust:
        by_phase = {s.phase: s for s in merged.slots}
        for phase, changes in patient_adjust.items():
            slot = by_phase.get(phase)
            if slot is None:
                conflicts.append(f"{phase}단계 없음 — 환자 조정 무시")
                continue
            for motion, value in (changes.get("rom_caps") or {}).items():
                current = slot.rom_caps.get(motion)
                if current is not None and value > current:
                    conflicts.append(
                        f"{phase}단계 {motion}: 환자 조정 {value}° > 프로토콜 {current}° — 무시(집도의 우선)"
                    )
                    continue
                slot.rom_caps[motion] = value
            for item in changes.get("forbidden") or []:      # 더 보수적인 방향은 항상 허용
                if item not in slot.forbidden:
                    slot.forbidden.append(item)

    merged.version = standard.version + (1 if hospital_override else 0)
    return merged, conflicts
