# 리햅톡 (RehabTalk) — 수술 후 재활 운동처방 설계·전달 데모

## 한 문장

환자가 수술 병원에서 받아온 재활 프로토콜을 물리치료사가 **사진 한 장**으로 넣으면, AI가 **그 병원의 허용·금지 안에서** 운동 초안을 만들고, 치료사가 확인·수정해 **클릭 한 번으로 환자의 카카오톡**에 보내 **수행과 통증까지 돌려받는** 서비스.

---

## 시연 시나리오 (이 6장면 밖은 만들지 않는다)

1. 치료사가 환자(김OO, 62세, 회전근개 봉합 후 3주)를 열고 **프로토콜 사진**을 올린다
2. AI가 **6칸**(단계·기간·보조기·허용·금지·각도상한)을 추출 → 치료사가 사진 옆에서 확인·수정 후 "맞음"
3. **AI 초안**이 뜬다. 통과 항목과 **제외된 항목이 이유와 함께** 함께 보인다
4. 치료사가 필요한 운동을 **담고**, 담긴 세트에 대한 **전체 평가**(시간·커버리지·막음/주의)를 본 뒤 **"적용하기"** → 세팅 소요 시간 표시(목표 60초 이내). 환자에게는 운동 **영상 링크**와 상태 한 줄이 함께 간다
5. 환자 화면: 알림톡 미리보기 → 링크 → 오늘 운동 3개, **완료 체크·통증 0~10·가동범위 그림 선택**
6. 치료사 **인박스**: "2주째 가동범위 정체" 카드 + **AI 조정 후보 2개** → 하나 선택해 발송

---

## 사용자와 원칙

| 대상 | 상황 | 화면 원칙 |
|---|---|---|
| 물리치료사 (주 사용자) | 하루 20명, 진료 중 사용 | 세팅~발송 **60초**. 클릭 최소. 백지에서 시작하지 않게 |
| 환자 (50~70대) | 앱 설치가 최대 이탈 지점 | **앱 없음**. 카톡 링크 → 모바일 웹. 큰 글씨, 오늘 할 것만 |
| 원장 | 결제자, 매일 안 봄 | 이 데모에서는 **화면 없음** |

---

## 절대 규칙 (모든 코드가 지켜야 함)

1. **규칙은 코드, AI는 제안.** 금지 동작·각도 상한·만료일은 구조화 데이터로 저장하고 **순수 함수로 검사**한다. LLM 판단에 안전을 걸지 않는다.
2. **AI 출력은 반드시 규칙 검사를 통과해야 화면에 뜬다.** 순서: `sanitize → AI → rules.check → 화면`
3. **환자 식별정보는 LLM에 보내지 않는다.** 이름·전화·생년월일·병원등록번호는 `sanitize()`에서 제거. LLM에는 "62세, 봉합 후 21일, 대형 파열, 통증 4"까지만.
4. **최종 결정은 치료사.** AI가 환자에게 직접 처방을 바꾸거나 전송하지 않는다.
5. **모든 추천에 출처를 표시한다.** (병원 프로토콜 / 공개 표준본 / 문헌)
6. **정보가 없으면 지어내지 않는다.** 추출 실패한 칸은 비워두고 "확인 필요"로 표시.

---

## 기술 스택

- **프론트(치료사)**: Streamlit
- **프론트(환자)**: FastAPI가 Jinja2 템플릿으로 직접 서빙 (Streamlit 사용 금지 — 토큰 링크·모바일·속도 문제)
- **백엔드**: FastAPI + Pydantic (RESTful)
- **AI**: provider를 **직접 호출** (LangChain·LangGraph 사용하지 않음 — 호출이 3개뿐이라 과잉)
  - 기본 **Upstage**: Solar(채팅·JSON 스키마 강제) + Document Parse(사진→표) + 임베딩
  - **Anthropic**도 지원 (`AI_PROVIDER=anthropic`). 키가 없으면 **목업**으로 돈다
  - 세 모드 전환은 `ai/client.py` 안에서만 일어난다. 나머지 코드는 provider를 모른다
- **RAG**: ChromaDB (로컬) + provider 임베딩. **메타데이터 필터 필수**
- **DB**: SQLite (데모 단계)
- **테스트**: pytest
- **배포**: docker compose — 역할별 컨테이너 셋

| 서비스 | 책임 | 노출 |
|---|---|---|
| `chroma` | 검색 인덱스 저장·조회 | 내부만 |
| `backend` | 규칙 판정 · AI 호출 · API · 환자 웹 | 8000 |
| `frontend` | 치료사 화면 (백엔드 API만 호출) | 8501 |

의존성도 역할별로 나눈다(`requirements/backend.txt`, `requirements/frontend.txt`) — 치료사 화면 이미지에 AI·DB 라이브러리를 넣지 않는다.
상태는 볼륨 두 개(`rehabtalk-data`, `chroma-data`)에만 둔다. 컨테이너는 언제 지워도 된다.

---

## 디렉터리 구조

```
rehabtalk/
├─ CLAUDE.md
├─ .env                        UPSTAGE_API_KEY / ANTHROPIC_API_KEY (절대 커밋 금지)
├─ frontend/                   Streamlit — 치료사용
│   ├─ 환자_목록.py            진입 화면 (환자 목록)
│   └─ pages/
│       ├─ 1_프로토콜.py
│       ├─ 2_처방.py
│       └─ 3_인박스.py
├─ backend/
│   ├─ main.py                 FastAPI 앱, 라우터 등록
│   ├─ api/
│   │   ├─ protocol.py         POST /extract, PUT /{id}
│   │   ├─ plan.py             POST /draft, POST /send
│   │   ├─ feedback.py         POST /feedback
│   │   ├─ inbox.py            GET /inbox, POST /inbox/{id}/reply
│   │   └─ patient_web.py      GET /p/{token}  ← HTML 반환
│   ├─ core/                   ★ 규칙 — LLM 호출 금지, 순수 함수만
│   │   ├─ schemas.py          Pydantic 모델 (프론트·AI 공통 계약)
│   │   ├─ protocol.py         단계 판정, 3층 병합
│   │   └─ rules.py            금지·상한·만료 검사, 적신호 감지
│   ├─ ai/                     ★ LLM 호출은 여기서만
│   │   ├─ client.py           provider 층 (upstage / anthropic / mock)
│   │   ├─ extract.py          사진 → 6칸 JSON
│   │   ├─ draft.py            환자 상태 → 운동 후보
│   │   ├─ adjust.py           피드백 → 조정 후보
│   │   ├─ retrieve.py         Chroma 검색
│   │   └─ prompts/            *.txt — 프롬프트는 코드와 분리 (자문이 읽고 고침)
│   ├─ lib/
│   │   ├─ sanitize.py         ★ PII 제거 — ai 호출 전 반드시 통과
│   │   ├─ db.py               SQLite
│   │   └─ notify.py           sendKakao() — 지금은 미리보기 반환
│   └─ templates/patient.html
├─ data/
│   ├─ standard_protocol.json  공개 프로토콜 기반 표준본 (회전근개)
│   ├─ exercises.json          운동 라이브러리 + 태그 (초기 30개)
│   └─ seed.json               데모 환자 3명
├─ docker/
│   ├─ backend.Dockerfile
│   └─ frontend.Dockerfile
├─ docker-compose.yml
├─ requirements/               서비스별 의존성 (backend / frontend / dev)
└─ tests/test_rules.py
```

---

## 데이터 모델 (core/schemas.py — 여기가 프론트·백·AI 공통 계약)

```python
Phase = Literal[1, 2, 3, 4]
ExerciseType = Literal["수동", "능동보조", "능동", "저항", "등척성"]
Grade = Literal["표준", "권장", "참고"]

class ProtocolSlot(BaseModel):          # 6칸 중 한 단계
    phase: Phase
    weeks: tuple[int, int]              # (0, 6)
    brace: str | None                   # "항상 착용(수면 포함)"
    allowed: list[str]                  # ["수동 관절운동", "진자 운동"]
    forbidden: list[str]                # ["능동 거상", "저항 운동"]
    rom_caps: dict[str, int]            # {"수동 외회전": 30, "수동 거상": 90}
    source_text: str | None             # 원문 어디서 읽었는지 (확인 화면 하이라이트용)
    confidence: float                   # 0~1, 낮으면 "확인 필요"

class Protocol(BaseModel):
    id: str
    surgery: str                        # "rotator_cuff_repair"
    origin: Literal["표준본", "병원", "표준본+병원"]
    hospital: str | None
    slots: list[ProtocolSlot]
    reviewed_by: str | None             # 확인한 치료사
    version: int

class Patient(BaseModel):
    id: str
    token: str                          # 환자 웹 접근용 (이름과 분리)
    age: int
    surgery_date: date
    tear_size: Literal["소형~중형", "대형", "광범위"]
    pain: int                           # 0~10
    swelling: bool
    brace: bool
    surgeon_notes: str | None
    protocol_id: str
# 이름·전화번호는 별도 테이블(patient_pii)에 암호화 저장. 절대 AI에 전달하지 않음.

class ExerciseCandidate(BaseModel):
    name: str
    type: ExerciseType
    rom: int | None
    dose: str                           # "3세트 × 10회"
    minutes: int
    grade: Grade
    reason: str                         # 왜 이 환자에게 (25자 이내)
    patient_desc: str                   # 환자용 쉬운 설명 (40자 이내)
    source: str                         # 출처
    video_url: str | None               # 시범 영상 — 모델이 만들지 않는다. 라이브러리에 등록된 것만

class DraftResult(BaseModel):
    passed: list[ExerciseCandidate]
    excluded: list[dict]                # {candidate, cut_reason, rule_id}
    adjusted: list[dict]                # {candidate, before, after, rule_id}
    phase: Phase
    red_flag: bool

class Feedback(BaseModel):
    patient_id: str
    date: date
    completed: list[str]                # 완료한 운동 이름
    pain: int
    rom_self: Literal["허리", "어깨", "눈높이", "머리 위"] | None
    note: str | None

class InboxItem(BaseModel):
    id: str
    patient_id: str
    origin: Literal["정체 감지", "환자 질문", "적신호"]
    summary: str
    related_limits: list[str]
    recent: str                         # "통증 3→4 (2일), 수행 5/6회"
    drafts: list[dict]                  # [{label, text}] — AI 생성
    reply: str | None
    replied_at: datetime | None
```

---

## 컴포넌트별 역할과 책임

### core/rules.py — 안전의 단일 지점
**책임**: AI 출력과 환자 메시지를 규칙에 대조. LLM을 호출하지 않는다. 같은 입력이면 항상 같은 출력.

```python
def check(candidates: list[ExerciseCandidate], protocol_slot: ProtocolSlot) -> DraftResult
def check_set(exercises: list[ExerciseCandidate], protocol_slot: ProtocolSlot) -> SetReview
def has_red_flag(text: str) -> bool          # 키워드·패턴 기반, LLM 아님
def within_plan(reply: str, plan, faq) -> bool  # 챗 출력 검사
def is_stalled(feedback_history) -> bool     # 정체 감지 (N주 이상)
```

**판정 표** (반드시 이대로):

| 위반 | 결과 | rule_id 예시 |
|---|---|---|
| 금지 동작 유형 포함 | **제외** | RC-P1-FORBID-ACTIVE-ELEV |
| 각도 상한 초과 | **상한으로 하향** | RC-P1-ROM-ER |
| 단계 필수 항목 누락 | **추가** | RC-P1-REQ-PENDULUM |
| 통증 ≥7 + 부종 | **전체 세트 1회 감량** | GEN-RED-FLAG |
| 프로토콜에 정보 없음 | **"확인 필요" 표시** | GEN-NO-INFO |

**세트 단위 판정** — `check_set()`. 운동 하나하나가 안전해도 묶음이 과하거나 한쪽으로 쏠릴 수 있다.

| 판정 | 결과 | rule_id |
|---|---|---|
| 담긴 것이 없음 | **막음** | SET-EMPTY |
| 금지·상한 위반이 담김 | **막음** (조용히 빼지 않는다 — 치료사가 정한다) | RC-P{n}-* |
| 하루 권장 시간 초과 | 주의 | SET-MINUTES |
| 단계 필수 항목 누락 | 주의 | RC-P{n}-REQ-* |
| 방향 커버리지 부족 | 정보 | SET-COVERAGE |
| 영상 미등록 | 정보 | SET-NO-VIDEO |

`ok=False`면 `POST /api/plan/send`가 **422로 되돌린다.** 담은 것을 말없이 빼고 보내지 않는다.

문구 매칭은 표기 방식에 흔들리지 않아야 한다. `"손/팔꿈치 운동"`의 슬래시는 **또는**으로 읽고,
`"능동 거상, 저항 운동"`처럼 한 칸에 쉼표로 묶여 들어온 항목은 각각으로 나눠 본다.

### core/protocol.py
**책임**: 수술일로 단계 판정, 3층 병합. `merge(standard, hospital_override, patient_adjust)`.
칸의 성격에 따라 병합 방식이 다르다 — 병원 프로토콜은 **사진 판독으로 들어오므로 한 항목을 놓칠 수 있고, 그 누락이 곧 안전 구멍이 되기 때문**이다.

| 칸 | 병합 | 이유 |
|---|---|---|
| 기간·보조기·원문 | **집도의 지시 우선** | 사실을 기술하는 칸 |
| 금지·허용 목록 | **합집합** | 금지가 겹치는 것은 위험하지 않다 |
| 각도 상한 | **더 작은 값** | 상한은 늘 보수적인 쪽 |

표준본보다 느슨해지는 값과 병원본에 없어 표준본을 함께 적용한 항목은 `conflicts`에 남겨 확인 화면에 띄운다.
환자 개별 조정은 프로토콜보다 느슨해질 수 없다.
회전근개 단계: 1(0~6주) / 2(6~12) / 3(12~16) / 4(16~)

### ai/extract.py
**책임**: 프로토콜 사진 → `list[ProtocolSlot]`.
Upstage에서는 **Document Parse로 표 구조를 먼저 뽑고** 그 텍스트를 Solar에 넘겨 구조화한다(한국어 표에 강함). Anthropic에서는 vision으로 직접 읽는다.
JSON 스키마를 서버가 강제하되 **출력을 그대로 믿지 않는다.**
`_to_slot()`에서 열린 구간(`-1`→`999`)과 각도 아닌 항목(`"제한 없음" -1°`)을 정리하고, 쉼표로 뭉쳐 온 목록을 항목별로 쪼갠다.
`_flag_broken_timeline()`은 단계 기간이 이어지는지 본다 — 모델이 보조기 문구("8주 후 해제")의 숫자를 기간으로 잘못 읽는 일이 있고, **자신 있게 틀리기도 한다.** 값을 고치지 않고 confidence를 내려 치료사에게 넘긴다. 1단계가 0주에서 시작하지 않으면 번호가 밀린 것으로 보고 전 단계를 확인 대상으로 올린다.
검증 실패 시 1회 재시도.
**읽지 못한 칸은 비워두고 confidence를 낮춘다.** 원문 근거를 `source_text`에 남겨 확인 화면에서 대조 가능하게.

### ai/draft.py
**책임**: 환자 상태 + 프로토콜 + 검색 결과 → `list[ExerciseCandidate]` 6~8개.
프롬프트에 **"금지된 유형도 포함해도 된다. 검증은 별도 시스템이 한다"**고 명시하고, **지금 단계 5~6개 + 다음 단계 2개**를 요구한다 → 규칙 층이 실제로 걸러내는 것을 데모에서 보여주기 위함. (모델이 알아서 걸러내면 치료사는 무엇이 왜 배제됐는지 볼 수 없다.)

### ai/adjust.py
**책임**: 피드백 이력 + 프로토콜 → 조정 후보 2개. (a) 범위 안에서 용량·빈도 조정, (b) 다음 진료 때 측정 후 판단. 정체 N주 이상이면 (c) 집도의 확인 권고를 **규칙이** 추가.

### ai/retrieve.py
**책임**: Chroma 검색. **메타데이터 필터를 먼저 적용한 뒤 의미 검색.**
문서는 passage, 질의는 query 임베딩을 쓴다. 임베딩 API가 없으면 로컬 해시로 떨어져 오프라인에서도 돈다(품질은 낮음). 임베딩 차원이 다르므로 컬렉션 이름을 backend별로 나눈다.
```python
collection.query(query_texts=[...],
    where={"$and": [{"surgery": "rotator_cuff"}, {"phase": 1}]}, n_results=5)
```
색인 대상: 공개 프로토콜 조각, 문헌 근거 카드. **운동 라이브러리와 금지 목록은 벡터에 넣지 않는다** (태그 필터·규칙 검사 대상).

### lib/sanitize.py — 모든 AI 호출의 관문
**책임**: 이름·전화번호·생년월일·등록번호·주소 제거. Patient → 나이·경과주차·파열크기·통증만 남긴 dict 반환. 자유 텍스트는 정규식 마스킹. **ai/ 안의 모든 함수는 sanitize를 거친 입력만 받는다.**

### lib/notify.py
**책임**: `send_kakao(patient, plan) -> dict`. 데모에서는 알림톡 미리보기 문자열을 반환. 실제 API 연동 시 이 함수만 교체.

### frontend/ (Streamlit)
**책임**: 표시와 입력만. **규칙 검사 금지, AI 직접 호출 금지.** 백엔드 API만 호출.
**주의**: Streamlit은 위젯 변경 시 스크립트 전체가 재실행됨. AI 호출 결과는 반드시 `st.session_state`에 저장하고 **버튼 클릭 시에만** 호출할 것.

### backend/templates/patient.html
**책임**: 환자 모바일 웹. 토큰으로만 접근. 큰 글씨, 오늘 할 운동만, 완료 체크, 통증 슬라이더, 가동범위 4단계 그림 선택, "지금 하지 말아야 할 것".

---

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/protocol/extract` | 사진 업로드 → 6칸 추출 (미확정 상태 저장) |
| PUT | `/api/protocol/{id}` | 치료사 확인·수정 → 확정, version+1 |
| POST | `/api/plan/draft` | 환자 상태 → `sanitize → retrieve → AI → rules.check` → DraftResult |
| POST | `/api/plan/review` | 담긴 세트 → `rules.check_set` → SetReview (담을 때마다 호출) |
| POST | `/api/plan/send` | 선택 운동 저장 + `send_kakao()` |
| POST | `/api/feedback` | 환자 완료·통증·가동범위 기록 (토큰 인증) |
| GET | `/api/inbox` | 정체 신호·질문 목록 + AI 조정 후보 |
| POST | `/api/inbox/{id}/reply` | 치료사 답변 발송 |
| GET | `/p/{token}` | 환자 모바일 웹 (HTML) |

---

## 작업 순서 (안에서 밖으로)

1. `core/schemas.py` + `core/rules.py` + `tests/test_rules.py` (테스트 5개 통과)
2. `data/standard_protocol.json`, `data/exercises.json` (운동 30개)
3. `ai/extract.py` — **실제 프로토콜 사진으로 테스트** (CLI로 먼저 확인)
4. `ai/draft.py` + `ai/retrieve.py` — CLI로 결과 확인
5. FastAPI 엔드포인트
6. Streamlit 화면 3개
7. `patient.html`
8. `ai/adjust.py` + 인박스

> 화면부터 만들지 말 것. 규칙과 AI가 CLI에서 돌아가는 걸 확인한 뒤에 붙인다.

---

## 테스트 케이스 (tests/test_rules.py — 이것부터 통과시킬 것)

1. 1단계 + "능동 거상" 후보 → **제외**, rule_id 포함
2. 1단계 + 수동 외회전 60° → **30°로 하향**
3. **광범위 파열** + 1단계 + 수동 외회전 40° → **20°로 하향**
4. 통증 8 + 부종 있음 → **red_flag=True**, 전체 세트 1회 감량
5. "어깨가 빨갛게 붓고 열이 나요" → `has_red_flag()` **True**
6. 2단계 + "저항밴드 외회전" → **제외** (2단계도 저항 금지)
7. 1단계에 진자 운동 없음 → **자동 추가**

---

## 하지 않을 것 (범위 밖)

- 카메라 동작인식, 환자 전용 앱, 로그인 시스템, 결제, EMR 연동
- 실제 카카오 알림톡 발송 (미리보기로 대체)
- LangChain / LangGraph
- 환자 챗봇 (2단계 — 단 인박스에 `origin` 필드를 미리 두어 나중에 이어붙일 자리를 남긴다)
- 회전근개 외 질환

---

## 참고 자료

`reference/` 폴더의 HTML 데모가 **화면 톤·색·규칙 구조의 기준**이다.
- `rehabtalk-demo-v2.html` — 파이프라인·검증 리포트·인박스 흐름
- `리햅톡_AI데모.html` — 실제 AI 호출 구조, 챗 4갈래 분기
- `리햅톡_페르소나.html` — 사용자 맥락 (박지현·정민수·김순자)

색: ink #152530, safe #0B6355, warn #9A5B0C, alert #A32A20, line #D8E0E5
폰트: Pretendard. 한국어 UI.

---

## 면책

데모용. 프로토콜 수치와 환자 정보는 구조를 보여주기 위한 예시이며 **실제 임상 처방에 사용할 수 없다.** 운영 시에는 집도의 프로토콜 원문과 물리치료사 검증을 거친 값만 사용한다. 모든 화면 하단에 이 문구를 표시할 것.
