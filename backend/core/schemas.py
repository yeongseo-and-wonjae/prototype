"""프론트·백엔드·AI가 공유하는 단일 계약.

여기 있는 모델만이 계층 경계를 넘는다. AI 응답도, Streamlit 화면도,
환자 웹도 모두 이 모델로 말한다.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Phase = Literal[1, 2, 3, 4]
ExerciseType = Literal["수동", "능동보조", "능동", "저항", "등척성"]
Grade = Literal["표준", "권장", "참고"]
TearSize = Literal["소형~중형", "대형", "광범위"]
RomSelf = Literal["허리", "어깨", "눈높이", "머리 위"]


class ProtocolSlot(BaseModel):
    """프로토콜 6칸 중 한 단계."""

    phase: Phase
    weeks: tuple[int, int]                      # (0, 6) — 시작주, 끝주
    brace: str | None = None                    # "항상 착용(수면 포함)"
    allowed: list[str] = Field(default_factory=list)      # ["수동 관절운동", "진자 운동"]
    forbidden: list[str] = Field(default_factory=list)    # ["능동 거상", "저항 운동"]
    rom_caps: dict[str, int] = Field(default_factory=dict)  # {"수동 외회전": 30}
    source_text: str | None = None              # 원문 근거 (확인 화면 하이라이트용)
    confidence: float = 1.0                     # 0~1, 낮으면 "확인 필요"

    @property
    def needs_review(self) -> bool:
        return self.confidence < 0.7


class Protocol(BaseModel):
    id: str
    surgery: str = "rotator_cuff_repair"
    origin: Literal["표준본", "병원", "표준본+병원"] = "표준본"
    hospital: str | None = None
    slots: list[ProtocolSlot] = Field(default_factory=list)
    reviewed_by: str | None = None              # 확인한 치료사 — None이면 미확정
    version: int = 1


class Patient(BaseModel):
    """LLM에 넘어가도 되는 임상 정보만. 이름·전화는 patient_pii 테이블에 별도 보관."""

    id: str
    token: str                                  # 환자 웹 접근용 (이름과 분리)
    age: int
    surgery_date: date
    tear_size: TearSize = "소형~중형"
    pain: int = 0                               # 0~10
    swelling: bool = False
    brace: bool = True
    surgeon_notes: str | None = None
    protocol_id: str = "standard_rc"


class ExerciseCandidate(BaseModel):
    name: str
    type: ExerciseType
    rom: int | None = None
    dose: str = "3세트 × 10회"
    minutes: int = 5
    grade: Grade = "권장"
    reason: str = ""                            # 왜 이 환자에게 (25자 이내)
    patient_desc: str = ""                      # 환자용 쉬운 설명 (40자 이내)
    source: str = "표준본"                       # 출처 — 절대 규칙 5
    video_url: str | None = None                # 환자에게 보낼 시범 영상
    note: str | None = None                     # "확인 필요" 등 규칙이 붙인 꼬리표


class DraftResult(BaseModel):
    passed: list[ExerciseCandidate] = Field(default_factory=list)
    excluded: list[dict] = Field(default_factory=list)   # {candidate, cut_reason, rule_id}
    adjusted: list[dict] = Field(default_factory=list)   # {candidate, before, after, rule_id}
    phase: Phase = 1
    red_flag: bool = False


class SetIssue(BaseModel):
    """담긴 세트 전체를 본 판정 하나."""

    level: Literal["막음", "주의", "정보"]
    message: str
    rule_id: str


class SetReview(BaseModel):
    """장바구니에 담긴 세트를 통째로 본 결과. 발송 직전에 이걸 통과해야 한다."""

    ok: bool                                    # '막음'이 하나도 없으면 True
    total_minutes: int
    count: int
    issues: list[SetIssue] = Field(default_factory=list)
    coverage: dict[str, bool] = Field(default_factory=dict)   # 방향별 포함 여부
    videos_missing: list[str] = Field(default_factory=list)


class Feedback(BaseModel):
    patient_id: str
    date: date
    completed: list[str] = Field(default_factory=list)   # 완료한 운동 이름
    pain: int = 0
    rom_self: RomSelf | None = None
    note: str | None = None


class InboxItem(BaseModel):
    id: str
    patient_id: str
    origin: Literal["정체 감지", "환자 질문", "적신호"]
    summary: str
    related_limits: list[str] = Field(default_factory=list)
    recent: str = ""                            # "통증 3→4 (2일), 수행 5/6회"
    drafts: list[dict] = Field(default_factory=list)     # [{label, text}] — AI 생성
    reply: str | None = None
    replied_at: datetime | None = None
